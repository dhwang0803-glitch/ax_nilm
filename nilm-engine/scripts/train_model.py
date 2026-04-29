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

    def __init__(self, base: NILMDataset, cache_dir: Path | None = None):
        self.base = base
        n = len(base)

        _tda_cache: Path | None = None
        if cache_dir is not None and hasattr(base, "cache_key"):
            from features.tda import TDA_DIM
            _tda_cache = cache_dir / f"tda_{base.cache_key}_d{TDA_DIM}.pt"

        if _tda_cache is not None and _tda_cache.exists():
            self._tda = torch.load(str(_tda_cache), weights_only=True)
            print(f"  TDA 캐시 로드: {_tda_cache.name}  ({n:,} windows)", flush=True)
        else:
            print(f"  TDA 사전 계산 중... ({n:,}개)", flush=True)
            from joblib import Parallel, delayed
            signals = [base[i][0].numpy() for i in range(n)]
            results = Parallel(n_jobs=-1, backend="loky")(
                delayed(_compute_tda_one)(s) for s in signals
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
def evaluate(model: nn.Module, loader: DataLoader, model_name: str, device: torch.device) -> dict:
    """MAE / RMSE / SAE / R² (전체 평균 + 22종 개별) 계산 후 dict 반환."""
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

    # cls 헤드 사용 가능 시 logit 기반 F1도 계산
    has_cls = len(all_fusion_logit) > 0
    if has_cls:
        logit_arr = np.concatenate(all_fusion_logit, axis=0)

    valid_mask = valid_arr > 0
    p    = pred_arr[valid_mask]
    t    = true_arr[valid_mask]
    p_on = pred_on[valid_mask]
    t_on = on_off_arr[valid_mask].astype(bool)

    mae  = float(np.abs(p - t).mean())
    rmse = float(np.sqrt(((p - t) ** 2).mean()))
    sae  = float(np.abs(pred_arr.sum(axis=0) - true_arr.sum(axis=0)).sum()
                 / (true_arr.sum() + 1e-8))

    tp   = float((p_on & t_on).sum())
    fp   = float((p_on & ~t_on).sum())
    fn   = float((~p_on & t_on).sum())
    f1   = 2 * tp / (2 * tp + fp + fn + 1e-8)

    f1_cls = None
    best_cls_threshold = 0.0
    if has_cls:
        # val 기준 전역 임계값 최적화 (고정 0.5 대신)
        lo_v = logit_arr[valid_mask]   # 1-D: valid (sample, class) 쌍
        best_thr, best_f = 0.0, -1.0
        for _thr in np.arange(-1.5, 1.6, 0.1):
            _p  = lo_v >= _thr
            _tp = float((_p & t_on).sum())
            _fp = float((_p & ~t_on).sum())
            _fn = float((~_p & t_on).sum())
            _f  = 2 * _tp / (2 * _tp + _fp + _fn + 1e-8)
            if _f > best_f:
                best_f, best_thr = _f, float(_thr)
        best_cls_threshold = best_thr
        pred_on_cls = logit_arr >= best_cls_threshold  # (N, 22) — per-class F1에서 재사용
        pc_on = pred_on_cls[valid_mask]
        tp_c  = float((pc_on & t_on).sum())
        fp_c  = float((pc_on & ~t_on).sum())
        fn_c  = float((~pc_on & t_on).sum())
        f1_cls = 2 * tp_c / (2 * tp_c + fp_c + fn_c + 1e-8)

    # ── 22종 개별 지표 ────────────────────────────────────────────────────────
    per_appliance = {}
    for i, name in enumerate(APPLIANCE_LABELS):
        col_valid = valid_arr[:, i] > 0
        if not col_valid.any():
            per_appliance[name] = {"mae": None, "rmse": None, "f1": None, "f1_cls": None}
            continue
        pi    = pred_arr[col_valid, i]
        ti    = true_arr[col_valid, i]
        pi_on = pred_on[col_valid, i]
        ti_on = on_off_arr[col_valid, i].astype(bool)
        tp_i  = float((pi_on & ti_on).sum())
        fp_i  = float((pi_on & ~ti_on).sum())
        fn_i  = float((~pi_on & ti_on).sum())
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
            "f1":    2 * tp_i / (2 * tp_i + fp_i + fn_i + 1e-8),
            "f1_cls": f1_cls_i,
        }

    return {"mae": mae, "rmse": rmse, "sae": sae,
            "f1": f1, "f1_cls": f1_cls,
            "best_cls_threshold": best_cls_threshold,
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
        train_ds = _NILMDatasetWithTDA(base_train, cache_dir=cache_dir)
        val_ds   = _NILMDatasetWithTDA(base_val,   cache_dir=cache_dir)
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
            model.load_state_dict(torch.load(prev_ckpt, map_location=device, weights_only=True))
            print(f"  └─ 모델 로드: {prev_ckpt.name}")
        else:
            print(f"  └─ 경고: {prev_ckpt.name} 없음 — 처음부터 학습")

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

    best_val_mae = float("inf")
    best_state   = None
    no_improve   = 0
    epoch_times: list[float] = []
    t_train_start = time.perf_counter()

    for epoch in range(1, epochs + 1):
        t_epoch = time.perf_counter()
        train_loss = train_one_epoch(model, train_loader, optimizer, args.model, device,
                                      amp_scaler, pos_weight=pos_weight,
                                      appliance_scale=appliance_scale)
        epoch_times.append(time.perf_counter() - t_epoch)

        val_metrics = evaluate(model, val_loader, args.model, device)
        val_mae = val_metrics["mae"]

        scheduler.step(val_mae)
        lr_now = optimizer.param_groups[0]["lr"]

        f1_cls_str = (f"  val_f1_cls={val_metrics['f1_cls']:.3f}"
                      f"(thr={val_metrics['best_cls_threshold']:+.1f})"
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
                mlflow_metrics["best_cls_threshold"] = val_metrics["best_cls_threshold"]
            mlflow.log_metrics(mlflow_metrics, step=epoch)

        if val_mae < best_val_mae - 1e-4:
            best_val_mae = val_mae
            best_state   = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            no_improve   = 0
        else:
            no_improve += 1
            if no_improve >= patience:
                print(f"  조기 종료: {patience} epoch 동안 val_mae 개선 없음")
                break

    training_time_s = time.perf_counter() - t_train_start
    avg_epoch_s     = sum(epoch_times) / len(epoch_times) if epoch_times else 0.0
    print(f"  학습 완료: 총 {training_time_s:.1f}s  에폭 평균 {avg_epoch_s:.1f}s")

    # ── 체크포인트 & 지표 저장 ──────────────────────────────────────────────
    if best_state is not None:
        model.load_state_dict({k: v.to(device) for k, v in best_state.items()})

    ckpt_path = ckpt_dir / f"{args.exp}_{args.model}.pt"
    torch.save(model.state_dict(), ckpt_path)
    print(f"  체크포인트 저장: {ckpt_path.relative_to(_NILM_ROOT)}")

    if base_train.scaler is not None:
        scaler_path = ckpt_dir / f"{args.exp}_{args.model}_scaler.json"
        base_train.scaler.save(scaler_path)

    final_metrics = evaluate(model, val_loader, args.model, device)
    final_metrics["exp"]             = args.exp
    final_metrics["model"]           = args.model
    final_metrics["date_range"]      = list(train_date_range) if train_date_range else f"week={train_week}"
    final_metrics["training_time_s"] = round(training_time_s, 1)
    final_metrics["avg_epoch_s"]     = round(avg_epoch_s, 1)
    final_metrics["n_epochs"]        = len(epoch_times)

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
        mlflow.log_metrics(
            {"best_val_mae": final_metrics["mae"], "best_val_f1": final_metrics["f1"]}
        )
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

    print(f"\n[완료] {args.exp}/{args.model}  MAE={final_metrics['mae']:.4f}  RMSE={final_metrics['rmse']:.4f}  SAE={final_metrics['sae']:.4f}  F1={final_metrics['f1']:.3f}")
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
    replacement = (
        f"| {model} "
        f"| {metrics['mae']:.2f} "
        f"| {metrics['rmse']:.2f} "
        f"| {metrics['sae']:.4f} "
        f"| {metrics['f1']:.3f} "
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
