"""
단일 모델 학습 스크립트.

Usage:
    python scripts/train_model.py --model seq2point --exp EXP1 --data-root /path/to/data
    python scripts/train_model.py --model bert4nilm  --exp EXP2 --data-root /path/to/data
    python scripts/train_model.py --model cnn_tda    --exp EXP1 --data-root /path/to/data

출력:
    checkpoints/{exp}_{model}.pt          학습된 모델 가중치
    docs/results/{exp}_{model}_metrics.json  val 성능 지표
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
import yaml

# ── 경로 설정 ────────────────────────────────────────────────────────────────
_NILM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_NILM_ROOT / "src"))

from acquisition.dataset import NILMDataset
from classifier.label_map import N_APPLIANCES, APPLIANCE_LABELS, get_on_thresholds
from features.tda import compute_tda_features
from models.seq2point import Seq2Point
from models.bert4nilm import BERT4NILM
from models.cnn_tda import CNNTDAHybrid

# ── TDA 래퍼 Dataset ──────────────────────────────────────────────────────────

def _compute_tda_one(agg_np: np.ndarray) -> np.ndarray:
    return compute_tda_features(agg_np)


class _NILMDatasetWithTDA(Dataset):
    """NILMDataset에 TDA 특징을 추가한 래퍼 (cnn_tda 전용)."""

    def __init__(
        self,
        base: NILMDataset,
        cache_dir: Path | None = None,
        event_context: int | None = None,
        steady_stride: int | None = None,
    ):
        self.base = base
        n = len(base)

        _tda_cache: Path | None = None
        if cache_dir is not None and hasattr(base, "cache_key"):
            from features.tda import TDA_DIM
            _ec = event_context or 0
            _ss = steady_stride or 0
            _tda_cache = cache_dir / f"tda_{base.cache_key}_ec{_ec}_ss{_ss}_d{TDA_DIM}.pt"

        _need_compute = True
        if _tda_cache is not None and _tda_cache.exists():
            _loaded = torch.load(str(_tda_cache), weights_only=True)
            if len(_loaded) == n:
                self._tda = _loaded
                _need_compute = False
                print(f"  TDA 캐시 로드: {_tda_cache.name}  ({n:,} windows)", flush=True)
            else:
                print(
                    f"  TDA 캐시 크기 불일치 ({len(_loaded):,} != {n:,}) → 재계산",
                    flush=True,
                )
                _tda_cache.unlink()

        if _need_compute:
            print(f"  TDA 사전 계산 중... ({n:,}개)", flush=True)
            from joblib import Parallel, delayed
            # contiguous shared array → threading 백엔드로 직렬화 오버헤드 제거
            # (loky는 2GB+ 리스트를 cloudpickle로 복사 → window=1024에서 수십 분 낭비)
            signals_arr = np.stack([base[i][0].numpy() for i in range(n)])
            results = Parallel(n_jobs=-1, backend="threading")(
                delayed(_compute_tda_one)(signals_arr[i]) for i in range(n)
            )
            self._tda = torch.from_numpy(np.stack(results))
            print("  TDA 사전 계산 완료", flush=True)
            if _tda_cache is not None:
                _tda_cache.parent.mkdir(parents=True, exist_ok=True)
                torch.save(self._tda, str(_tda_cache))
                print(f"  TDA 캐시 저장: {_tda_cache.name}", flush=True)

    def __len__(self) -> int:
        return len(self.base)

    def __getitem__(self, idx: int):
        agg, target, on_off, validity = self.base[idx]
        return agg, self._tda[idx], target, on_off, validity


# ── 모델 팩토리 ───────────────────────────────────────────────────────────────

def build_model(model_name: str, window_size: int) -> nn.Module:
    if model_name == "seq2point":
        return Seq2Point(window_size=window_size)
    elif model_name == "bert4nilm":
        return BERT4NILM(window_size=window_size)
    elif model_name == "cnn_tda":
        return CNNTDAHybrid(window_size=window_size)
    else:
        raise ValueError(f"Unknown model: {model_name}")


# ── 손실 함수 ─────────────────────────────────────────────────────────────────

def masked_weighted_mse(
    pred: torch.Tensor,
    target: torch.Tensor,
    on_off: torch.Tensor,
    validity: torch.Tensor,
    on_weight: float = 5.0,
    appliance_scale: torch.Tensor | None = None,
) -> torch.Tensor:
    """validity=False 채널 제외. ON 구간은 on_weight 배, 가전별 scale 추가 적용."""
    weight = validity.float() * (1.0 + (on_weight - 1.0) * on_off.float())
    if appliance_scale is not None:
        weight = weight * appliance_scale.unsqueeze(0)
    diff = (pred - target) ** 2 * weight
    denom = weight.sum().clamp(min=1.0)
    return diff.sum() / denom


def compute_pos_weight(loader: DataLoader, device: torch.device, max_weight: float = 20.0) -> torch.Tensor:
    """학습 데이터 ON/OFF 분포에서 per-channel pos_weight 계산.

    sqrt scaling + clamp(max=max_weight)으로 발산 방지.
    분모 floor=10 — ON 샘플 < 10인 채널은 임계 낮춤.
    max_weight: train.yaml training.pos_weight_max 로 제어 (기본 20 → 희귀 가전은 50 권장).
    """
    on_counts  = torch.zeros(N_APPLIANCES)
    off_counts = torch.zeros(N_APPLIANCES)

    for batch in loader:
        on_off   = batch[-2]   # (batch, 22, window_size)
        validity = batch[-1]   # (batch, 22)
        center   = on_off.shape[-1] // 2
        mask     = on_off[:, :, center].float()           # (batch, 22)
        valid    = validity.float()
        on_counts  += (mask * valid).sum(0).cpu()
        off_counts += ((1.0 - mask) * valid).sum(0).cpu()

    total_counts = on_counts + off_counts
    pw = torch.sqrt(off_counts / on_counts.clamp(min=10)).clamp(max=max_weight)
    # validity=0 for all windows → off_counts=0 → sqrt(0)=0 → ON 샘플에 weight 0 적용 방지
    pw = torch.where(total_counts == 0, torch.ones_like(pw), pw)
    # on_counts < 5 → max_weight(50) 적용 시 BCE gradient 폭증 방지 (false positive 양산 차단)
    pw = torch.where(on_counts < 5, torch.ones_like(pw), pw)
    return pw.to(device)


def bce_validity(
    logit: torch.Tensor,
    target: torch.Tensor,
    validity: torch.Tensor,
    pos_weight: torch.Tensor,
) -> torch.Tensor:
    """validity 마스크 + per-channel pos_weight BCE. (batch, 22) 입력."""
    weight = target.float() * pos_weight.unsqueeze(0) + (1.0 - target.float())
    loss   = F.binary_cross_entropy_with_logits(logit, target.float(),
                                                weight=weight, reduction="none")
    valid  = validity.float()
    return (loss * valid).sum() / valid.sum().clamp(min=1.0)


# ── 평가 함수 ─────────────────────────────────────────────────────────────────

@torch.no_grad()
def evaluate(
    model: nn.Module,
    loader: DataLoader,
    model_name: str,
    device: torch.device,
    cls_thresholds: np.ndarray | None = None,
    postprocess_stride_sec: float | None = None,
) -> dict:
    """MAE / RMSE / SAE / R² (전체 평균 + 22종 개별) 계산 후 dict 반환.

    cls_thresholds: None이면 가전별 독립 탐색 (val loop용).
                    ndarray(22,)이면 그 값을 freeze해서 사용 (test/final eval용).
    """
    model.eval()

    all_pred, all_true, all_on_off, all_valid = [], [], [], []
    all_fusion_logit = []

    for batch in loader:
        if model_name == "cnn_tda":
            agg, tda, target, on_off, validity = batch
            agg = agg.unsqueeze(1).to(device)
            tda = tda.to(device)
            result = model(agg, tda)
            pred = result[0]
            fusion_logit = result[3] if len(result) == 4 else None
        elif model_name == "seq2point":
            agg, target, on_off, validity = batch
            pred = model(agg.unsqueeze(1).to(device))
            fusion_logit = None
        else:  # bert4nilm
            agg, target, on_off, validity = batch
            pred = model(agg.to(device))
            fusion_logit = None

        center   = target.shape[-1] // 2
        target_c = target[:, :, center].to(device)
        valid    = validity.to(device).float()

        all_pred.append(pred.cpu().numpy())
        all_true.append(target_c.cpu().numpy())
        all_on_off.append(on_off[:, :, center].numpy())
        all_valid.append(valid.cpu().numpy())
        if fusion_logit is not None:
            all_fusion_logit.append(fusion_logit.cpu().numpy())

    pred_arr   = np.concatenate(all_pred,   axis=0)   # (N, 22)
    true_arr   = np.concatenate(all_true,   axis=0)
    on_off_arr = np.concatenate(all_on_off, axis=0)   # (N, 22) bool
    valid_arr  = np.concatenate(all_valid,  axis=0)

    # ── ON/OFF 예측 ───────────────────────────────────────────────────────────
    raw_thr = np.array(get_on_thresholds(), dtype=np.float32)
    # target이 raw W → 임계도 raw W로 직접 비교
    pred_on = pred_arr >= raw_thr[np.newaxis, :]

    # always_on 가전 — 이 house에 실제로 존재하는 경우(on_off_arr에 ON 구간 있음)만 고정
    from postprocessor import ALWAYS_ON_IDX
    has_appliance = on_off_arr.any(axis=0)          # (N_APP,) bool
    present_always_on = [i for i in ALWAYS_ON_IDX if has_appliance[i]]
    pred_on[:, present_always_on] = True

    # 예측 후처리: min_active spike 제거 + gap 메우기 (최종 eval 전용)
    if postprocess_stride_sec is not None:
        from postprocessor import apply_postprocess
        pred_on = apply_postprocess(pred_on, stride_sec=postprocess_stride_sec)

    # cls 헤드 사용 가능 시 logit 기반 F1도 계산
    has_cls = len(all_fusion_logit) > 0
    if has_cls:
        logit_arr = np.concatenate(all_fusion_logit, axis=0)

    valid_mask = valid_arr > 0
    p = pred_arr[valid_mask]
    t = true_arr[valid_mask]

    mae  = float(np.abs(p - t).mean())
    rmse = float(np.sqrt(((p - t) ** 2).mean()))
    sae  = float(np.abs(pred_arr.sum(axis=0) - true_arr.sum(axis=0)).sum()
                 / (true_arr.sum() + 1e-8))

    f1_cls = None
    best_cls_thresholds = np.zeros(N_APPLIANCES)
    if has_cls:
        if cls_thresholds is None:
            # 가전별 독립 임계값 탐색 (val loop 전용) — 범위 [-3, +3]
            _search = np.arange(-3.0, 3.1, 0.1)
            for i in range(N_APPLIANCES):
                col_valid = valid_arr[:, i] > 0
                if not col_valid.any():
                    continue
                lo_i = logit_arr[col_valid, i]
                ti_i = on_off_arr[col_valid, i].astype(bool)
                best_thr_i, best_f_i = 0.0, -1.0
                for _thr in _search:
                    _p  = lo_i >= _thr
                    _tp = float((_p & ti_i).sum())
                    _fp = float((_p & ~ti_i).sum())
                    _fn = float((~_p & ti_i).sum())
                    _f  = 2 * _tp / (2 * _tp + _fp + _fn + 1e-8)
                    if _f > best_f_i:
                        best_f_i, best_thr_i = _f, float(_thr)
                best_cls_thresholds[i] = best_thr_i
        else:
            # val에서 구한 임계값을 freeze해서 사용 (test/final eval 누설 방지)
            best_cls_thresholds = np.asarray(cls_thresholds)
        pred_on_cls = logit_arr >= best_cls_thresholds[np.newaxis, :]  # (N, 22)

    # ── 22종 개별 지표 — val positive 없는 클래스 제외(weighted macro F1 집계 대상에서) ──
    per_appliance = {}
    _f1_items: list[tuple[float, int]] = []      # (f1, n_positive) for weighted macro
    _f1_cls_items: list[tuple[float, int]] = []
    for i, name in enumerate(APPLIANCE_LABELS):
        col_valid = valid_arr[:, i] > 0
        if not col_valid.any():
            per_appliance[name] = {"mae": None, "rmse": None, "f1": None, "f1_cls": None}
            continue
        pi    = pred_arr[col_valid, i]
        ti    = true_arr[col_valid, i]
        pi_on = pred_on[col_valid, i]
        ti_on = on_off_arr[col_valid, i].astype(bool)
        n_pos = int(ti_on.sum())
        if n_pos == 0:
            per_appliance[name] = {"mae": float(np.abs(pi - ti).mean()),
                                   "rmse": float(np.sqrt(((pi - ti) ** 2).mean())),
                                   "f1": None, "f1_cls": None}
            continue
        tp_i  = float((pi_on & ti_on).sum())
        fp_i  = float((pi_on & ~ti_on).sum())
        fn_i  = float((~pi_on & ti_on).sum())
        f1_i  = 2 * tp_i / (2 * tp_i + fp_i + fn_i + 1e-8)
        f1_cls_i = None
        if has_cls:
            pc_on_i = pred_on_cls[col_valid, i]
            tc  = float((pc_on_i & ti_on).sum())
            fc  = float((pc_on_i & ~ti_on).sum())
            fnc = float((~pc_on_i & ti_on).sum())
            f1_cls_i = 2 * tc / (2 * tc + fc + fnc + 1e-8)
        per_appliance[name] = {
            "mae":   float(np.abs(pi - ti).mean()),
            "rmse":  float(np.sqrt(((pi - ti) ** 2).mean())),
            "f1":    f1_i,
            "f1_cls": f1_cls_i,
            "n_pos": n_pos,
        }
        _f1_items.append((f1_i, n_pos))
        if f1_cls_i is not None:
            _f1_cls_items.append((f1_cls_i, n_pos))

    # weighted macro F1 — val positive 수에 비례한 가중 평균
    if _f1_items:
        _vals, _w = zip(*_f1_items)
        f1 = float(np.average(_vals, weights=_w))
    else:
        f1 = 0.0
    if has_cls:
        if _f1_cls_items:
            _vals, _w = zip(*_f1_cls_items)
            f1_cls = float(np.average(_vals, weights=_w))
        else:
            f1_cls = None

    return {"mae": mae, "rmse": rmse, "sae": sae,
            "f1": f1, "f1_cls": f1_cls,
            "best_cls_thresholds": best_cls_thresholds.tolist(),
            "per_appliance": per_appliance}



# ── 학습 루프 ─────────────────────────────────────────────────────────────────

def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    model_name: str,
    device: torch.device,
    amp_scaler: torch.cuda.amp.GradScaler | None = None,
    pos_weight: torch.Tensor | None = None,
    lambda_mse: float = 0.1,
    appliance_scale: torch.Tensor | None = None,
) -> float:
    model.train()
    total_loss = 0.0
    use_amp = amp_scaler is not None and device.type == "cuda"

    for batch in loader:
        optimizer.zero_grad()

        with torch.autocast(device_type=device.type, enabled=use_amp):
            if model_name == "cnn_tda":
                agg, tda, target, on_off, validity = batch
                agg = agg.unsqueeze(1).to(device)
                tda = tda.to(device)
                result = model(agg, tda)
                pred, _conf, cnn_logit, fusion_logit = result
            elif model_name == "seq2point":
                agg, target, on_off, validity = batch
                pred = model(agg.unsqueeze(1).to(device))
                cnn_logit = fusion_logit = None
            else:  # bert4nilm
                agg, target, on_off, validity = batch
                pred = model(agg.to(device))
                cnn_logit = fusion_logit = None

            center   = target.shape[-1] // 2
            target_c = target[:, :, center].to(device)
            on_off_c = on_off[:, :, center].to(device)
            validity = validity.to(device)

            mse_loss = masked_weighted_mse(pred, target_c, on_off_c, validity,
                                           appliance_scale=appliance_scale)

            if cnn_logit is not None and pos_weight is not None:
                # dual head BCE — gate collapse 방지 (리뷰 2번)
                bce_cnn    = bce_validity(cnn_logit,    on_off_c, validity, pos_weight)
                bce_fusion = bce_validity(fusion_logit, on_off_c, validity, pos_weight)
                loss = bce_cnn + bce_fusion + lambda_mse * mse_loss
            else:
                loss = mse_loss

        if use_amp:
            amp_scaler.scale(loss).backward()
            amp_scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            amp_scaler.step(optimizer)
            amp_scaler.update()
        else:
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

        total_loss += loss.item()

    return total_loss / max(len(loader), 1)


# ── cnn_tda 그룹 단위 학습 헬퍼 ───────────────────────────────────────────────

def _train_cnn_tda_group(
    group_name: str,
    group_cfg: dict,
    exp: str,
    resume_exp: str | None,
    train_cfg: dict,
    data_root: Path,
    ckpt_dir: Path,
    cache_dir: Path | None,
    device: torch.device,
    train_houses: list[str],
    val_houses: list[str],
    train_week: int | None,
    train_date_range,
    eval_date_range,
    batch_size: int,
    epochs: int,
    patience: int,
    lr_init: float,
    wd: float,
    lambda_mse: float,
    pos_weight_max: float,
    appliance_scale: torch.Tensor,
) -> dict:
    """cnn_tda 단일 speed group 학습 후 val_metrics 반환. 스케일러는 그룹별 독립 관리."""
    from acquisition.preprocessor import PowerScaler

    g_window    = group_cfg["window_size"]
    g_stride    = group_cfg["stride"]
    g_resample  = group_cfg["resample_hz"]
    g_event_ctx = group_cfg.get("event_context")
    g_steady    = group_cfg.get("steady_stride")

    # ── scaler: resume 시 per-group 파일 우선, 없으면 fit ─────────────────────
    group_scaler: PowerScaler | None = None
    if resume_exp:
        _prev_sc_path = ckpt_dir / f"{resume_exp}_cnn_tda_{group_name}_scaler.json"
        if _prev_sc_path.exists():
            group_scaler = PowerScaler.load(_prev_sc_path)
            print(f"  [{group_name}] scaler 로드: mean={group_scaler.mean:.2f}W  std={group_scaler.std:.2f}W")

    # ── Dataset ──────────────────────────────────────────────────────────────
    if group_scaler is not None:
        g_train_base = NILMDataset(
            train_houses, data_root, g_window, g_stride,
            date_range=train_date_range, week=train_week,
            scaler=group_scaler, cache_dir=cache_dir,
            event_context=g_event_ctx, steady_stride=g_steady,
            resample_hz=g_resample, appliance_group=group_name,
        )
    else:
        g_train_base = NILMDataset(
            train_houses, data_root, g_window, g_stride,
            date_range=train_date_range, week=train_week,
            fit_scaler=True, cache_dir=cache_dir,
            event_context=g_event_ctx, steady_stride=g_steady,
            resample_hz=g_resample, appliance_group=group_name,
        )
        group_scaler = g_train_base.scaler

    g_val_base = NILMDataset(
        val_houses, data_root, g_window, g_stride,
        date_range=eval_date_range,
        scaler=group_scaler, cache_dir=cache_dir,
        event_context=g_event_ctx, steady_stride=g_steady,
        resample_hz=g_resample, appliance_group=group_name,
    )

    g_train_ds = _NILMDatasetWithTDA(g_train_base, cache_dir=cache_dir,
                                      event_context=g_event_ctx, steady_stride=g_steady)
    g_val_ds   = _NILMDatasetWithTDA(g_val_base,   cache_dir=cache_dir,
                                      event_context=g_event_ctx, steady_stride=g_steady)
    g_train_loader = DataLoader(g_train_ds, batch_size=batch_size, shuffle=True,
                                num_workers=4, pin_memory=True)
    g_val_loader   = DataLoader(g_val_ds,   batch_size=batch_size, shuffle=False,
                                num_workers=4, pin_memory=True)
    print(f"  [{group_name}] train={len(g_train_ds):,}  val={len(g_val_ds):,} windows")

    # ── Model ─────────────────────────────────────────────────────────────────
    model = CNNTDAHybrid(window_size=g_window).to(device)
    lr = lr_init

    if resume_exp:
        prev_ckpt = ckpt_dir / f"{resume_exp}_cnn_tda_{group_name}.pt"
        if prev_ckpt.exists():
            _ckpt  = torch.load(prev_ckpt, map_location=device, weights_only=True)
            _state = _ckpt["model_state"] if isinstance(_ckpt, dict) and "model_state" in _ckpt else _ckpt
            model.load_state_dict(_state)
            print(f"  [{group_name}] └─ 모델 로드: {prev_ckpt.name}")
        else:
            print(f"  [{group_name}] └─ 경고: {prev_ckpt.name} 없음 — 처음부터 학습")

        _prev_m_path = ckpt_dir.parent / "docs" / "results" / f"{resume_exp}_cnn_tda_{group_name}_metrics.json"
        if _prev_m_path.exists():
            _prev_m = json.load(open(_prev_m_path))
            lr = _prev_m.get("final_lr", lr)
            print(f"  [{group_name}] └─ LR 이어받기: {lr:.2e}")

    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=wd)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min",
        factor=train_cfg["scheduler"]["factor"],
        patience=train_cfg["scheduler"]["patience"],
    )

    print(f"  [{group_name}] pos_weight 계산 중...")
    pos_weight = compute_pos_weight(g_train_loader, device, max_weight=pos_weight_max)
    # always_on 그룹은 분류 BCE 없이 회귀만 학습 (ON/OFF 분류 자체가 무의미)
    _pw_train = None if group_name == "always_on" else pos_weight

    # ── Training loop ─────────────────────────────────────────────────────────
    amp_scaler          = torch.amp.GradScaler("cuda") if device.type == "cuda" else None
    best_score          = (-float("inf"), float("inf"))
    best_cls_thresholds = np.zeros(N_APPLIANCES)
    best_state          = None
    no_improve          = 0
    epoch_times: list[float] = []
    t_start = time.perf_counter()

    for epoch in range(1, epochs + 1):
        t_ep = time.perf_counter()
        train_loss = train_one_epoch(
            model, g_train_loader, optimizer, "cnn_tda", device,
            amp_scaler, pos_weight=_pw_train,
            lambda_mse=lambda_mse, appliance_scale=appliance_scale,
        )
        epoch_times.append(time.perf_counter() - t_ep)

        val_metrics = evaluate(model, g_val_loader, "cnn_tda", device)
        val_mae     = val_metrics["mae"]
        scheduler.step(val_mae)
        lr_now = optimizer.param_groups[0]["lr"]

        f1_cls_str = (f"  f1_cls={val_metrics['f1_cls']:.3f}"
                      if val_metrics.get("f1_cls") is not None else "")
        print(
            f"  [{group_name}] epoch {epoch:3d}/{epochs}  "
            f"loss={train_loss:.4f}  mae={val_mae:.2f}  "
            f"f1={val_metrics['f1']:.3f}{f1_cls_str}  "
            f"lr={lr_now:.2e}  time={epoch_times[-1]:.1f}s"
        )

        _f1_cls = val_metrics.get("f1_cls") or 0.0
        _score  = (_f1_cls, -val_mae)
        if _score > best_score or best_state is None:
            best_score          = _score
            best_cls_thresholds = np.array(val_metrics["best_cls_thresholds"])
            best_state          = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            no_improve          = 0
        else:
            no_improve += 1
            if no_improve >= patience:
                print(f"  [{group_name}] 조기 종료: {patience} epoch 개선 없음")
                break

    total_time = time.perf_counter() - t_start
    avg_ep     = sum(epoch_times) / len(epoch_times) if epoch_times else 0.0
    print(f"  [{group_name}] 완료: 총 {total_time:.1f}s  에폭 평균 {avg_ep:.1f}s")

    # ── Checkpoint ────────────────────────────────────────────────────────────
    if best_state is not None:
        model.load_state_dict({k: v.to(device) for k, v in best_state.items()})

    ckpt_path = ckpt_dir / f"{exp}_cnn_tda_{group_name}.pt"
    torch.save({"model_state": model.state_dict(),
                "best_cls_thresholds": best_cls_thresholds.tolist()}, ckpt_path)
    print(f"  [{group_name}] 체크포인트: {ckpt_path.name}")

    if group_scaler is not None:
        group_scaler.save(ckpt_dir / f"{exp}_cnn_tda_{group_name}_scaler.json")

    # ── Final evaluate ────────────────────────────────────────────────────────
    _stride_sec = g_stride / g_resample
    final_m = evaluate(model, g_val_loader, "cnn_tda", device,
                       cls_thresholds=best_cls_thresholds,
                       postprocess_stride_sec=_stride_sec)
    final_m["group"]           = group_name
    final_m["final_lr"]        = optimizer.param_groups[0]["lr"]
    final_m["training_time_s"] = round(total_time, 1)
    final_m["n_epochs"]        = len(epoch_times)

    g_metrics_path = ckpt_dir.parent / "docs" / "results" / f"{exp}_cnn_tda_{group_name}_metrics.json"
    g_metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(g_metrics_path, "w", encoding="utf-8") as f:
        json.dump(final_m, f, ensure_ascii=False, indent=2)
    print(f"  [{group_name}] 그룹 지표 저장: {g_metrics_path.name}")

    return final_m


def _merge_group_metrics(group_metrics: dict[str, dict]) -> dict:
    """fast/slow/always_on 그룹 지표를 합쳐 n_pos 가중 macro F1 재계산."""
    merged_pa: dict[str, dict] = {}
    for gm in group_metrics.values():
        for name, app_m in gm.get("per_appliance", {}).items():
            if app_m.get("f1") is not None:
                merged_pa[name] = app_m

    f1_items:     list[tuple[float, int]] = []
    f1_cls_items: list[tuple[float, int]] = []
    mae_items:    list[tuple[float, int]] = []
    rmse_items:   list[tuple[float, int]] = []

    for app_m in merged_pa.values():
        n = max(app_m.get("n_pos", 1), 1)
        if app_m.get("f1")     is not None: f1_items.append((app_m["f1"], n))
        if app_m.get("f1_cls") is not None: f1_cls_items.append((app_m["f1_cls"], n))
        if app_m.get("mae")    is not None: mae_items.append((app_m["mae"], n))
        if app_m.get("rmse")   is not None: rmse_items.append((app_m["rmse"], n))

    def _wavg(items: list[tuple[float, int]]) -> float:
        if not items:
            return 0.0
        vals, ws = zip(*items)
        return float(np.average(vals, weights=ws))

    saes = [gm.get("sae", 0.0) for gm in group_metrics.values() if "sae" in gm]

    # per_appliance 전체 22종 키 보장 (None 값으로 패딩)
    full_pa = {name: merged_pa.get(name, {"mae": None, "rmse": None, "f1": None, "f1_cls": None})
               for name in APPLIANCE_LABELS}

    return {
        "mae":  _wavg(mae_items),
        "rmse": _wavg(rmse_items),
        "sae":  float(np.mean(saes)) if saes else 0.0,
        "f1":   _wavg(f1_items),
        "f1_cls": _wavg(f1_cls_items) if f1_cls_items else None,
        "per_appliance": full_pa,
        "group_metrics": {
            k: {kk: vv for kk, vv in v.items() if kk != "per_appliance"}
            for k, v in group_metrics.items()
        },
    }


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model",     required=True, choices=["seq2point", "bert4nilm", "cnn_tda"])
    parser.add_argument("--exp",       required=True, help="예: EXP1, EXP2, ...")
    parser.add_argument("--data-root", required=True, help="AIHub 데이터셋 루트 경로")
    parser.add_argument("--config-dir", default=str(_NILM_ROOT / "config"))
    parser.add_argument("--no-mlflow", action="store_true")
    parser.add_argument("--cache-dir", default=None, help="전처리 캐시 디렉토리 (지정 시 재실행 속도 개선)")
    args = parser.parse_args()

    cfg_dir = Path(args.config_dir)
    with open(cfg_dir / "train.yaml")   as f: train_cfg   = yaml.safe_load(f)
    with open(cfg_dir / "dataset.yaml") as f: dataset_cfg = yaml.safe_load(f)

    exp_cfg = train_cfg["experiments"].get(args.exp)
    if exp_cfg is None:
        raise ValueError(f"{args.exp} 가 train.yaml experiments 에 없습니다.")

    data_root   = Path(args.data_root)
    window_size   = dataset_cfg["window"]["size"]
    stride        = dataset_cfg["window"]["stride"]
    event_context = dataset_cfg["window"].get("event_context")   # None → full sliding
    steady_stride = dataset_cfg["window"].get("steady_stride")   # None → stride × 20
    batch_size  = (train_cfg["training"].get("batch_size_bert", 64)
                   if args.model == "bert4nilm"
                   else train_cfg["training"]["batch_size"])
    epochs      = train_cfg["training"]["epochs"]
    patience    = train_cfg["training"]["early_stopping_patience"]
    lr          = train_cfg["training"]["learning_rate"]
    wd          = train_cfg["optimizer"]["weight_decay"]
    lambda_mse  = train_cfg["training"]["loss_weights"]["mse"]

    # week 우선, 없으면 date_range 사용
    train_week       = exp_cfg.get("week")
    train_date_range = tuple(exp_cfg["date_range"]) if "date_range" in exp_cfg else None
    eval_date_range  = train_cfg["eval"]["date_range"]  # None 또는 ["YYYY-MM-DD","YYYY-MM-DD"]
    if eval_date_range is not None:
        eval_date_range = tuple(eval_date_range)

    # ── 데이터셋 ────────────────────────────────────────────────────────────
    train_houses = dataset_cfg["split"]["train"]
    val_houses   = dataset_cfg["split"]["val"]

    from acquisition.preprocessor import PowerScaler

    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    ckpt_dir = _NILM_ROOT / "checkpoints"
    ckpt_dir.mkdir(exist_ok=True)
    resume_exp = exp_cfg.get("resume_from")

    # EXP2+ 재개 시 이전 scaler 재사용 — 정규화 기준 일관성 유지
    prev_scaler: PowerScaler | None = None
    if resume_exp:
        scaler_path = ckpt_dir / f"{resume_exp}_{args.model}_scaler.json"
        if scaler_path.exists():
            prev_scaler = PowerScaler.load(scaler_path)
            print(f"  └─ scaler 로드: mean={prev_scaler.mean:.2f}W  std={prev_scaler.std:.2f}W")

    # ── cnn_tda multi-speed (dataset.yaml groups 설정 존재 시 우선 진입) ────────
    if args.model == "cnn_tda" and "groups" in dataset_cfg:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        _app_index = {name: i for i, name in enumerate(APPLIANCE_LABELS)}
        _scale_cfg = train_cfg.get("appliance_loss_scale", {})
        appliance_scale = torch.ones(N_APPLIANCES, device=device)
        for _name, _s in _scale_cfg.items():
            if _name in _app_index:
                appliance_scale[_app_index[_name]] = float(_s)
                print(f"  appliance_loss_scale [{_name}]: ×{_s}")

        all_group_metrics: dict[str, dict] = {}

        for group_name, group_cfg in dataset_cfg["groups"].items():
            print(f"\n{'='*60}")
            print(f"  cnn_tda / {group_name}  "
                  f"(window={group_cfg['window_size']}  hz={group_cfg['resample_hz']})")
            print(f"{'='*60}")
            g_metrics = _train_cnn_tda_group(
                group_name=group_name,     group_cfg=group_cfg,
                exp=args.exp,              resume_exp=resume_exp,
                train_cfg=train_cfg,       data_root=data_root,
                ckpt_dir=ckpt_dir,         cache_dir=cache_dir,
                device=device,
                train_houses=train_houses, val_houses=val_houses,
                train_week=train_week,     train_date_range=train_date_range,
                eval_date_range=eval_date_range,
                batch_size=batch_size,     epochs=epochs,
                patience=patience,         lr_init=lr,
                wd=wd,                     lambda_mse=lambda_mse,
                pos_weight_max=float(train_cfg["training"].get("pos_weight_max", 20.0)),
                appliance_scale=appliance_scale,
            )
            all_group_metrics[group_name] = g_metrics

        final_metrics = _merge_group_metrics(all_group_metrics)
        final_metrics.update({
            "exp":        args.exp,
            "model":      args.model,
            "date_range": list(train_date_range) if train_date_range else f"week={train_week}",
        })

        results_dir = _NILM_ROOT / "docs" / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = results_dir / f"{args.exp}_{args.model}_metrics.json"
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(final_metrics, f, ensure_ascii=False, indent=2)
        print(f"  지표 저장: {metrics_path.relative_to(_NILM_ROOT)}")
        _fill_md_row(args.exp, args.model, final_metrics, results_dir)

        _cls = (f"  F1_cls={final_metrics['f1_cls']:.3f}"
                if final_metrics.get("f1_cls") is not None else "")
        print(f"\n[완료] {args.exp}/cnn_tda(multi-speed)  "
              f"MAE={final_metrics['mae']:.4f}  RMSE={final_metrics['rmse']:.4f}  "
              f"F1={final_metrics['f1']:.3f}{_cls}")
        return final_metrics

    # ── 기존 단일 모델 학습 (seq2point / bert4nilm / cnn_tda without groups) ───
    if prev_scaler is not None:
        base_train = NILMDataset(train_houses, data_root, window_size, stride,
                                 date_range=train_date_range, week=train_week,
                                 scaler=prev_scaler, cache_dir=cache_dir,
                                 event_context=event_context, steady_stride=steady_stride)
        base_val   = NILMDataset(val_houses,   data_root, window_size, stride,
                                 date_range=eval_date_range,
                                 scaler=prev_scaler, cache_dir=cache_dir,
                                 event_context=event_context, steady_stride=steady_stride)
    else:
        base_train = NILMDataset(train_houses, data_root, window_size, stride,
                                 date_range=train_date_range, week=train_week,
                                 fit_scaler=True, cache_dir=cache_dir,
                                 event_context=event_context, steady_stride=steady_stride)
        base_val   = NILMDataset(val_houses,   data_root, window_size, stride,
                                 date_range=eval_date_range,
                                 scaler=base_train.scaler, cache_dir=cache_dir,
                                 event_context=event_context, steady_stride=steady_stride)

    if args.model == "cnn_tda":
        train_ds = _NILMDatasetWithTDA(base_train, cache_dir=cache_dir,
                                       event_context=event_context, steady_stride=steady_stride)
        val_ds   = _NILMDatasetWithTDA(base_val,   cache_dir=cache_dir,
                                       event_context=event_context, steady_stride=steady_stride)
    else:
        train_ds, val_ds = base_train, base_val

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,  num_workers=4, pin_memory=True)
    val_loader   = DataLoader(val_ds,   batch_size=batch_size, shuffle=False, num_workers=4, pin_memory=True)

    print(f"[{args.exp}/{args.model}] train={len(train_ds):,}  val={len(val_ds):,} windows")

    # ── 모델 & 옵티마이저 ───────────────────────────────────────────────────
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model  = build_model(args.model, window_size).to(device)

    # 이전 EXP 체크포인트 로드 (추가학습)
    if resume_exp:
        prev_ckpt = ckpt_dir / f"{resume_exp}_{args.model}.pt"
        if prev_ckpt.exists():
            _ckpt = torch.load(prev_ckpt, map_location=device, weights_only=True)
            _state = _ckpt["model_state"] if isinstance(_ckpt, dict) and "model_state" in _ckpt else _ckpt
            model.load_state_dict(_state)
            print(f"  └─ 모델 로드: {prev_ckpt.name}")
        else:
            print(f"  └─ 경고: {prev_ckpt.name} 없음 — 처음부터 학습")

    if resume_exp:
        _prev_metrics_path = _NILM_ROOT / "docs" / "results" / f"{resume_exp}_{args.model}_metrics.json"
        if _prev_metrics_path.exists():
            _prev_m = json.load(open(_prev_metrics_path))
            lr = _prev_m.get("final_lr", lr)
            print(f"  └─ LR 이어받기: {lr:.2e}")

    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=wd)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=train_cfg["scheduler"]["factor"],
        patience=train_cfg["scheduler"]["patience"]
    )

    # ── MLflow ──────────────────────────────────────────────────────────────
    mlflow_run = None
    if not args.no_mlflow:
        try:
            import mlflow
            mlflow.set_experiment("nilm_exp")
            mlflow_run = mlflow.start_run(run_name=f"{args.exp}_{args.model}")
            mlflow.log_params({
                "model": args.model, "exp": args.exp,
                "date_range": str(train_date_range),
                "window_size": window_size, "batch_size": batch_size,
                "resume_from": resume_exp or "scratch",
            })
        except Exception as e:
            print(f"  MLflow 스킵: {e}")

    # ── per-appliance loss scale (구조 C) ────────────────────────────────────
    _app_index = {name: i for i, name in enumerate(APPLIANCE_LABELS)}
    _scale_cfg = train_cfg.get("appliance_loss_scale", {})
    appliance_scale = torch.ones(N_APPLIANCES, device=device)
    for _name, _s in _scale_cfg.items():
        if _name in _app_index:
            appliance_scale[_app_index[_name]] = float(_s)
            print(f"  appliance_loss_scale [{_name}]: ×{_s}")

    # ── pos_weight 계산 (cnn_tda 전용) ──────────────────────────────────────
    pos_weight_max = float(train_cfg["training"].get("pos_weight_max", 20.0))
    pos_weight = None
    if args.model == "cnn_tda":
        print("  pos_weight 계산 중...")
        pos_weight = compute_pos_weight(train_loader, device, max_weight=pos_weight_max)
        for name, pw in zip(APPLIANCE_LABELS, pos_weight.cpu().tolist()):
            print(f"    {name}: {pw:.2f}")

    # ── 학습 루프 ────────────────────────────────────────────────────────────
    amp_scaler = torch.amp.GradScaler("cuda") if device.type == "cuda" else None

    # (f1_cls, -mae) 튜플 우선순위 — 단위 차이 없이 Pareto 우선순위로 비교
    best_score          = (-float("inf"), float("inf"))
    best_val_mae        = float("inf")
    best_cls_thresholds = np.zeros(N_APPLIANCES)
    best_state          = None
    no_improve         = 0
    epoch_times: list[float] = []
    t_train_start = time.perf_counter()

    for epoch in range(1, epochs + 1):
        t_epoch = time.perf_counter()
        train_loss = train_one_epoch(model, train_loader, optimizer, args.model, device,
                                      amp_scaler, pos_weight=pos_weight,
                                      lambda_mse=lambda_mse, appliance_scale=appliance_scale)
        epoch_times.append(time.perf_counter() - t_epoch)

        val_metrics = evaluate(model, val_loader, args.model, device)
        val_mae = val_metrics["mae"]

        scheduler.step(val_mae)
        lr_now = optimizer.param_groups[0]["lr"]

        f1_cls_str = (f"  val_f1_cls={val_metrics['f1_cls']:.3f}"
                      if val_metrics.get("f1_cls") is not None else "")
        print(
            f"  epoch {epoch:3d}/{epochs}  "
            f"train_loss={train_loss:.4f}  "
            f"val_mae={val_mae:.2f}  val_f1={val_metrics['f1']:.3f}"
            f"{f1_cls_str}  lr={lr_now:.2e}  epoch_time={epoch_times[-1]:.1f}s"
        )

        if mlflow_run:
            import mlflow
            mlflow_metrics = {
                "train_loss": train_loss, "val_mae": val_mae,
                "val_f1": val_metrics["f1"], "val_rmse": val_metrics["rmse"],
                "epoch_time_s": epoch_times[-1],
            }
            if val_metrics.get("f1_cls") is not None:
                mlflow_metrics["val_f1_cls"] = val_metrics["f1_cls"]
            mlflow.log_metrics(mlflow_metrics, step=epoch)

        _f1_cls = val_metrics.get("f1_cls") or 0.0
        _score  = (_f1_cls, -val_mae)
        if _score > best_score or best_state is None:
            best_score         = _score
            best_val_mae       = val_mae
            best_cls_thresholds = np.array(val_metrics["best_cls_thresholds"])
            best_state         = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            no_improve         = 0
        else:
            no_improve += 1
            if no_improve >= patience:
                print(f"  조기 종료: {patience} epoch 동안 (f1_cls, -mae) 개선 없음")
                break

    training_time_s = time.perf_counter() - t_train_start
    avg_epoch_s     = sum(epoch_times) / len(epoch_times) if epoch_times else 0.0
    print(f"  학습 완료: 총 {training_time_s:.1f}s  에폭 평균 {avg_epoch_s:.1f}s")

    # ── 체크포인트 & 지표 저장 ──────────────────────────────────────────────
    if best_state is not None:
        model.load_state_dict({k: v.to(device) for k, v in best_state.items()})

    ckpt_path = ckpt_dir / f"{args.exp}_{args.model}.pt"
    torch.save({"model_state": model.state_dict(), "best_cls_thresholds": best_cls_thresholds.tolist()}, ckpt_path)
    print(f"  체크포인트 저장: {ckpt_path.relative_to(_NILM_ROOT)}  (per-class thr 저장)")

    if base_train.scaler is not None:
        scaler_path = ckpt_dir / f"{args.exp}_{args.model}_scaler.json"
        base_train.scaler.save(scaler_path)

    _sr = dataset_cfg["window"].get("sampling_rate", 30)
    _stride_sec = stride / _sr
    final_metrics = evaluate(model, val_loader, args.model, device,
                             cls_thresholds=best_cls_thresholds,
                             postprocess_stride_sec=_stride_sec)
    final_metrics["exp"]             = args.exp
    final_metrics["model"]           = args.model
    final_metrics["date_range"]      = list(train_date_range) if train_date_range else f"week={train_week}"
    final_metrics["training_time_s"] = round(training_time_s, 1)
    final_metrics["avg_epoch_s"]     = round(avg_epoch_s, 1)
    final_metrics["n_epochs"]        = len(epoch_times)
    final_metrics["final_lr"]        = optimizer.param_groups[0]["lr"]   # EXP resume 시 이어받기용

    results_dir = _NILM_ROOT / "docs" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = results_dir / f"{args.exp}_{args.model}_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(final_metrics, f, ensure_ascii=False, indent=2)
    print(f"  지표 저장: {metrics_path.relative_to(_NILM_ROOT)}")

    # MD 보고서 해당 행 업데이트
    _fill_md_row(args.exp, args.model, final_metrics, results_dir)

    # ── per-appliance RMSE 요약 출력 (문제 5) ──────────────────────────────
    _pa = final_metrics.get("per_appliance", {})
    if _pa:
        print("\n  [per-appliance RMSE 요약]")
        _rows = [
            (name, m["rmse"], m["mae"])
            for name, m in _pa.items()
            if m.get("rmse") is not None and m.get("mae") is not None
        ]
        _rows.sort(key=lambda x: -(x[1] / max(x[2], 1e-8)))
        for name, rmse, mae in _rows:
            ratio = rmse / max(mae, 1e-8)
            flag = "  ⚠️" if ratio > 2.0 else ""
            print(f"    {name}: RMSE={rmse:.1f}W  MAE={mae:.1f}W  ({ratio:.1f}x){flag}")

    if mlflow_run:
        import mlflow
        _mlflow_final = {"best_val_mae": final_metrics["mae"], "best_val_f1": final_metrics["f1"]}
        if final_metrics.get("f1_cls") is not None:
            _mlflow_final["best_val_f1_cls"] = final_metrics["f1_cls"]
        mlflow.log_metrics(_mlflow_final)
        if _pa:
            pa_mlflow = {}
            for name, m in _pa.items():
                if m.get("rmse") is not None:
                    pa_mlflow[f"final_rmse_{name}"] = m["rmse"]
                if m.get("mae") is not None:
                    pa_mlflow[f"final_mae_{name}"] = m["mae"]
            if pa_mlflow:
                mlflow.log_metrics(pa_mlflow)
        mlflow.end_run()

    _cls_summary = (
        f"  F1_cls={final_metrics['f1_cls']:.3f}"
        if final_metrics.get("f1_cls") is not None else ""
    )
    print(f"\n[완료] {args.exp}/{args.model}  MAE={final_metrics['mae']:.4f}  RMSE={final_metrics['rmse']:.4f}  SAE={final_metrics['sae']:.4f}  F1={final_metrics['f1']:.3f}{_cls_summary}")
    return final_metrics


def _fill_md_row(exp: str, model: str, metrics: dict, results_dir: Path) -> None:
    """MD 보고서에서 해당 모델 행의 — 값을 실제 지표로 교체."""
    md_path = results_dir / f"{exp}_results.md"
    if not md_path.exists():
        print(f"  ⚠️ MD 파일 없음 ({md_path.name}) — init_results.py 를 먼저 실행하세요.")
        return

    content = md_path.read_text(encoding="utf-8")

    # "| model_name |" 로 시작하는 행을 찾아 교체
    # 기존: | seq2point | — | — | — | — | ⬜ |
    # 교체: | seq2point | 45.23 | 67.89 | 0.1234 | 0.821 | ✅ |
    import re
    pattern = rf"(\| {re.escape(model)} \|).*"
    _f1_cls_str = f"{metrics['f1_cls']:.3f}" if metrics.get("f1_cls") is not None else "—"
    replacement = (
        f"| {model} "
        f"| {metrics['mae']:.2f} "
        f"| {metrics['rmse']:.2f} "
        f"| {metrics['sae']:.4f} "
        f"| {metrics['f1']:.3f} "
        f"| {_f1_cls_str} "
        f"| ✅ |"
    )
    new_content, n = re.subn(pattern, replacement, content)
    if n == 0:
        print(f"  ⚠️ MD에서 '{model}' 행을 찾지 못했습니다.")
        return

    md_path.write_text(new_content, encoding="utf-8")
    print(f"  MD 업데이트: {md_path.name} ← {model} 행 채움")


if __name__ == "__main__":
    main()
