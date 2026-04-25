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
from classifier.label_map import N_APPLIANCES, get_on_thresholds
from features.tda import compute_tda_features
from models.seq2point import Seq2Point
from models.bert4nilm import BERT4NILM
from models.cnn_tda import CNNTDAHybrid

# ── TDA 래퍼 Dataset ──────────────────────────────────────────────────────────

def _compute_tda_one(agg_np: np.ndarray) -> np.ndarray:
    return compute_tda_features(agg_np)


class _NILMDatasetWithTDA(Dataset):
    """NILMDataset에 TDA 특징을 추가한 래퍼 (cnn_tda 전용)."""

    def __init__(self, base: NILMDataset):
        self.base = base
        n = len(base)
        print(f"  TDA 사전 계산 중... ({n:,}개)", flush=True)
        from joblib import Parallel, delayed
        signals = [base[i][0].numpy() for i in range(n)]
        results = Parallel(n_jobs=-1, backend="loky")(
            delayed(_compute_tda_one)(s) for s in signals
        )
        self._tda = torch.from_numpy(np.stack(results))
        print("  TDA 사전 계산 완료", flush=True)

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
) -> torch.Tensor:
    """validity=False 채널 제외. ON 구간은 on_weight 배 가중해 trivial zero 예측 방지."""
    # pred, target, on_off: (batch, N_APPLIANCES)
    weight = validity.float() * (1.0 + (on_weight - 1.0) * on_off.float())
    diff = (pred - target) ** 2 * weight
    denom = weight.sum().clamp(min=1.0)
    return diff.sum() / denom


# ── 평가 함수 ─────────────────────────────────────────────────────────────────

@torch.no_grad()
def evaluate(model: nn.Module, loader: DataLoader, model_name: str, device: torch.device) -> dict:
    """MAE / RMSE / SAE / R² (전체 평균 + 22종 개별) 계산 후 dict 반환."""
    model.eval()

    all_pred, all_true, all_on_off, all_valid = [], [], [], []

    for batch in loader:
        if model_name == "cnn_tda":
            agg, tda, target, on_off, validity = batch
            agg = agg.unsqueeze(1).to(device)
            tda = tda.to(device)
            pred, _ = model(agg, tda)
        elif model_name == "seq2point":
            agg, target, on_off, validity = batch
            pred = model(agg.unsqueeze(1).to(device))
        else:  # bert4nilm
            agg, target, on_off, validity = batch
            pred = model(agg.to(device))

        center = target.shape[-1] // 2
        target_c = target[:, :, center].to(device)
        valid = validity.to(device).float()

        all_pred.append(pred.cpu().numpy())
        all_true.append(target_c.cpu().numpy())
        all_on_off.append(on_off[:, :, center].numpy())
        all_valid.append(valid.cpu().numpy())

    pred_arr   = np.concatenate(all_pred,   axis=0)   # (N, 22)
    true_arr   = np.concatenate(all_true,   axis=0)
    on_off_arr = np.concatenate(all_on_off, axis=0)   # (N, 22) bool
    valid_arr  = np.concatenate(all_valid,  axis=0)   # 1 = 이 house에 해당 가전 존재

    # ── 전체 평균 지표 ────────────────────────────────────────────────────────
    from classifier.label_map import APPLIANCE_LABELS, get_on_thresholds
    raw_thr  = np.array(get_on_thresholds(), dtype=np.float32)
    scaler   = loader.dataset.scaler if hasattr(loader.dataset, "scaler") else \
               loader.dataset.base.scaler
    norm_thr = (raw_thr - scaler.mean) / scaler.std if scaler is not None else raw_thr
    pred_on  = pred_arr >= norm_thr[np.newaxis, :]

    valid_mask = valid_arr > 0
    p    = pred_arr[valid_mask]
    t    = true_arr[valid_mask]
    p_on = pred_on[valid_mask]
    t_on = on_off_arr[valid_mask].astype(bool)

    mae  = float(np.abs(p - t).mean())
    rmse = float(np.sqrt(((p - t) ** 2).mean()))
    sae  = float(np.abs(pred_arr.sum(axis=0) - true_arr.sum(axis=0)).sum()
                 / (true_arr.sum() + 1e-8))
    r2   = float(_r2(p, t))

    tp   = float((p_on & t_on).sum())
    fp   = float((p_on & ~t_on).sum())
    fn   = float((~p_on & t_on).sum())
    f1   = 2 * tp / (2 * tp + fp + fn + 1e-8)

    # ── 22종 개별 지표 ────────────────────────────────────────────────────────
    per_appliance = {}
    for i, name in enumerate(APPLIANCE_LABELS):
        col_valid = valid_arr[:, i] > 0
        if not col_valid.any():
            per_appliance[name] = {"mae": None, "rmse": None, "r2": None, "f1": None}
            continue
        pi    = pred_arr[col_valid, i]
        ti    = true_arr[col_valid, i]
        pi_on = pred_on[col_valid, i]
        ti_on = on_off_arr[col_valid, i].astype(bool)
        tp_i  = float((pi_on & ti_on).sum())
        fp_i  = float((pi_on & ~ti_on).sum())
        fn_i  = float((~pi_on & ti_on).sum())
        per_appliance[name] = {
            "mae":  float(np.abs(pi - ti).mean()),
            "rmse": float(np.sqrt(((pi - ti) ** 2).mean())),
            "r2":   float(_r2(pi, ti)),
            "f1":   2 * tp_i / (2 * tp_i + fp_i + fn_i + 1e-8),
        }

    return {"mae": mae, "rmse": rmse, "sae": sae, "r2": r2, "f1": f1,
            "per_appliance": per_appliance}


def _r2(pred: np.ndarray, true: np.ndarray) -> float:
    """R² (결정계수). 음수면 모델이 평균 예측보다 나쁨 (0 예측 의심)."""
    ss_res = ((pred - true) ** 2).sum()
    ss_tot = ((true - true.mean()) ** 2).sum()
    return 1.0 - ss_res / (ss_tot + 1e-8)


# ── 학습 루프 ─────────────────────────────────────────────────────────────────

def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    model_name: str,
    device: torch.device,
) -> float:
    model.train()
    total_loss = 0.0

    for batch in loader:
        optimizer.zero_grad()

        if model_name == "cnn_tda":
            agg, tda, target, on_off, validity = batch
            agg = agg.unsqueeze(1).to(device)
            tda = tda.to(device)
            pred, _ = model(agg, tda)
        elif model_name == "seq2point":
            agg, target, on_off, validity = batch
            pred = model(agg.unsqueeze(1).to(device))
        else:  # bert4nilm
            agg, target, on_off, validity = batch
            pred = model(agg.to(device))

        center = target.shape[-1] // 2
        target_c = target[:, :, center].to(device)
        on_off_c = on_off[:, :, center].to(device)
        validity = validity.to(device)

        loss = masked_weighted_mse(pred, target_c, on_off_c, validity)
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
    args = parser.parse_args()

    cfg_dir = Path(args.config_dir)
    with open(cfg_dir / "train.yaml")   as f: train_cfg   = yaml.safe_load(f)
    with open(cfg_dir / "dataset.yaml") as f: dataset_cfg = yaml.safe_load(f)

    exp_cfg = train_cfg["experiments"].get(args.exp)
    if exp_cfg is None:
        raise ValueError(f"{args.exp} 가 train.yaml experiments 에 없습니다.")

    data_root   = Path(args.data_root)
    window_size = dataset_cfg["window"]["size"]
    stride      = dataset_cfg["window"]["stride"]
    batch_size  = train_cfg["training"]["batch_size"]
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
                                 scaler=prev_scaler)
        base_val   = NILMDataset(val_houses,   data_root, window_size, stride,
                                 date_range=eval_date_range,
                                 scaler=prev_scaler)
    else:
        base_train = NILMDataset(train_houses, data_root, window_size, stride,
                                 date_range=train_date_range, week=train_week,
                                 fit_scaler=True)
        base_val   = NILMDataset(val_houses,   data_root, window_size, stride,
                                 date_range=eval_date_range,
                                 scaler=base_train.scaler)

    if args.model == "cnn_tda":
        train_ds = _NILMDatasetWithTDA(base_train)
        val_ds   = _NILMDatasetWithTDA(base_val)
    else:
        train_ds, val_ds = base_train, base_val

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,  num_workers=2, pin_memory=True)
    val_loader   = DataLoader(val_ds,   batch_size=batch_size, shuffle=False, num_workers=2, pin_memory=True)

    print(f"[{args.exp}/{args.model}] train={len(train_ds):,}  val={len(val_ds):,} windows")

    # ── 모델 & 옵티마이저 ───────────────────────────────────────────────────
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model  = build_model(args.model, window_size).to(device)

    # 이전 EXP 체크포인트 로드 (추가학습)
    if resume_exp:
        prev_ckpt = ckpt_dir / f"{resume_exp}_{args.model}.pt"
        if prev_ckpt.exists():
            model.load_state_dict(torch.load(prev_ckpt, map_location=device))
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

    # ── 학습 루프 ────────────────────────────────────────────────────────────
    best_val_mae = float("inf")
    best_state   = None
    no_improve   = 0
    epoch_times: list[float] = []
    t_train_start = time.perf_counter()

    for epoch in range(1, epochs + 1):
        t_epoch = time.perf_counter()
        train_loss = train_one_epoch(model, train_loader, optimizer, args.model, device)
        epoch_times.append(time.perf_counter() - t_epoch)

        val_metrics = evaluate(model, val_loader, args.model, device)
        val_mae = val_metrics["mae"]

        scheduler.step(val_mae)
        lr_now = optimizer.param_groups[0]["lr"]

        print(
            f"  epoch {epoch:3d}/{epochs}  "
            f"train_loss={train_loss:.4f}  "
            f"val_mae={val_mae:.2f}W  r2={val_metrics['r2']:.4f}  "
            f"lr={lr_now:.2e}  epoch_time={epoch_times[-1]:.1f}s"
        )

        if mlflow_run:
            import mlflow
            mlflow.log_metrics(
                {"train_loss": train_loss, "val_mae": val_mae,
                 "val_r2": val_metrics["r2"], "val_rmse": val_metrics["rmse"],
                 "epoch_time_s": epoch_times[-1]},
                step=epoch,
            )

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

    if mlflow_run:
        import mlflow
        mlflow.log_metrics(
            {"best_val_mae": final_metrics["mae"], "best_val_r2": final_metrics["r2"]}
        )
        mlflow.end_run()

    print(f"\n[완료] {args.exp}/{args.model}  MAE={final_metrics['mae']:.2f}W  RMSE={final_metrics['rmse']:.2f}W  SAE={final_metrics['sae']:.4f}  R²={final_metrics['r2']:.4f}")
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
