"""
trial용 학습 스크립트 — val 없이 train + test만 수행.

Usage:
    python scripts/train_trial.py --model seq2point --exp EXP1
    python scripts/train_trial.py --model bert4nilm  --exp EXP2
    python scripts/train_trial.py --model cnn_tda    --exp EXP1

dataset 설정: config/dataset_trial.yaml (train/test split)
출력:
    checkpoints/{exp}_{model}.pt
    docs/results/{exp}_{model}_metrics.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
import yaml

_NILM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_NILM_ROOT / "src"))

from acquisition.dataset import NILMDataset
from classifier.label_map import N_APPLIANCES, get_on_thresholds
from features.tda import compute_tda_features
from models.seq2point import Seq2Point
from models.bert4nilm import BERT4NILM
from models.cnn_tda import CNNTDAHybrid


def _compute_tda_one(agg_np: np.ndarray) -> np.ndarray:
    return compute_tda_features(agg_np)


class _NILMDatasetWithTDA(Dataset):
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


def build_model(model_name: str, window_size: int) -> nn.Module:
    if model_name == "seq2point":
        return Seq2Point(window_size=window_size)
    elif model_name == "bert4nilm":
        return BERT4NILM(window_size=window_size)
    elif model_name == "cnn_tda":
        return CNNTDAHybrid(window_size=window_size)
    else:
        raise ValueError(f"Unknown model: {model_name}")


def masked_mse(pred: torch.Tensor, target: torch.Tensor, validity: torch.Tensor) -> torch.Tensor:
    mask = validity.float()
    diff = (pred - target) ** 2 * mask
    return diff.sum() / mask.sum().clamp(min=1.0)


def train_one_epoch(model, loader, optimizer, model_name, device) -> float:
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
        else:
            agg, target, on_off, validity = batch
            pred = model(agg.to(device))
        center = target.shape[-1] // 2
        loss = masked_mse(pred, target[:, :, center].to(device), validity.to(device))
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        total_loss += loss.item()
    return total_loss / max(len(loader), 1)


@torch.no_grad()
def evaluate(model, loader, model_name, device) -> dict:
    from classifier.label_map import APPLIANCE_LABELS
    model.eval()
    all_pred, all_true, all_on_off, all_valid = [], [], [], []
    for batch in loader:
        if model_name == "cnn_tda":
            agg, tda, target, on_off, validity = batch
            pred, _ = model(agg.unsqueeze(1).to(device), tda.to(device))
        elif model_name == "seq2point":
            agg, target, on_off, validity = batch
            pred = model(agg.unsqueeze(1).to(device))
        else:
            agg, target, on_off, validity = batch
            pred = model(agg.to(device))
        center = target.shape[-1] // 2
        all_pred.append(pred.cpu().numpy())
        all_true.append(target[:, :, center].numpy())
        all_on_off.append(on_off[:, :, center].numpy())
        all_valid.append(validity.float().numpy())

    pred_arr   = np.concatenate(all_pred)
    true_arr   = np.concatenate(all_true)
    on_off_arr = np.concatenate(all_on_off)
    valid_arr  = np.concatenate(all_valid)

    raw_thr  = np.array(get_on_thresholds(), dtype=np.float32)
    scaler   = loader.dataset.scaler if hasattr(loader.dataset, "scaler") else \
               loader.dataset.base.scaler
    norm_thr = (raw_thr - scaler.mean) / scaler.std  # 정규화 공간으로 변환
    pred_on  = pred_arr >= norm_thr[np.newaxis, :]
    valid_mask = valid_arr > 0
    p, t       = pred_arr[valid_mask], true_arr[valid_mask]
    p_on       = pred_on[valid_mask]
    t_on       = on_off_arr[valid_mask].astype(bool)

    ss_res = ((p - t) ** 2).sum()
    ss_tot = ((t - t.mean()) ** 2).sum()
    r2 = float(1.0 - ss_res / (ss_tot + 1e-8))

    tp = float((p_on & t_on).sum())
    fp = float((p_on & ~t_on).sum())
    fn = float((~p_on & t_on).sum())

    return {
        "mae":  float(np.abs(p - t).mean()),
        "rmse": float(np.sqrt(((p - t) ** 2).mean())),
        "sae":  float(np.abs(pred_arr.sum(0) - true_arr.sum(0)).sum() / (true_arr.sum() + 1e-8)),
        "r2":   r2,
        "f1":   2 * tp / (2 * tp + fp + fn + 1e-8),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=["seq2point", "bert4nilm", "cnn_tda"])
    parser.add_argument("--exp",   required=True)
    parser.add_argument("--data-root",  default=str(_NILM_ROOT / "datasets"))
    parser.add_argument("--config-dir", default=str(_NILM_ROOT / "config"))
    args = parser.parse_args()

    cfg_dir = Path(args.config_dir)
    with open(cfg_dir / "train.yaml")         as f: train_cfg   = yaml.safe_load(f)
    with open(cfg_dir / "dataset_trial.yaml") as f: dataset_cfg = yaml.safe_load(f)

    exp_cfg = train_cfg["experiments"].get(args.exp)
    if exp_cfg is None:
        raise ValueError(f"{args.exp} 가 train.yaml 에 없습니다.")

    data_root   = Path(args.data_root)
    window_size = dataset_cfg["window"]["size"]
    stride      = dataset_cfg["window"]["stride"]
    batch_size  = train_cfg["training"]["batch_size"]
    epochs      = train_cfg["training"]["epochs"]
    lr          = train_cfg["training"]["learning_rate"]
    wd          = train_cfg["optimizer"]["weight_decay"]
    train_week  = exp_cfg.get("week")

    train_houses = dataset_cfg["split"]["train"]
    test_houses  = dataset_cfg["split"]["test"]

    ckpt_dir = _NILM_ROOT / "checkpoints"
    ckpt_dir.mkdir(exist_ok=True)

    base_train = NILMDataset(train_houses, data_root, window_size, stride,
                             week=train_week, fit_scaler=True)
    base_train.scaler.save(ckpt_dir / f"{args.exp}_{args.model}_scaler.json")
    print(f"  scaler — mean={base_train.scaler.mean:.2f}W  std={base_train.scaler.std:.2f}W")

    base_test  = NILMDataset(test_houses,  data_root, window_size, stride,
                             week=train_week, scaler=base_train.scaler)

    if args.model == "cnn_tda":
        train_ds = _NILMDatasetWithTDA(base_train)
        test_ds  = _NILMDatasetWithTDA(base_test)
    else:
        train_ds, test_ds = base_train, base_test

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,  num_workers=2, pin_memory=True)
    test_loader  = DataLoader(test_ds,  batch_size=batch_size, shuffle=False, num_workers=2, pin_memory=True)

    print(f"[{args.exp}/{args.model}] train={len(train_ds):,}  test={len(test_ds):,} windows")

    if torch.cuda.is_available():
        device = torch.device("cuda")
        print(f"  device: cuda  ({torch.cuda.get_device_name(0)}, "
              f"VRAM {torch.cuda.get_device_properties(0).total_memory // 2**20} MB)")
    else:
        device = torch.device("cpu")
        print("  [경고] GPU 없음 — CPU로 학습 계속 진행 (Colab 세션 전환 감지됨)")

    model = build_model(args.model, window_size).to(device)

    resume_exp = exp_cfg.get("resume_from")
    if resume_exp:
        prev_ckpt = ckpt_dir / f"{resume_exp}_{args.model}.pt"
        if prev_ckpt.exists():
            model.load_state_dict(torch.load(prev_ckpt, map_location=device))
            print(f"  └─ 체크포인트 로드: {prev_ckpt.name}")
        else:
            print(f"  └─ 경고: {prev_ckpt.name} 없음 — 처음부터 학습")

    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=wd)

    t_start = time.perf_counter()
    for epoch in range(1, epochs + 1):
        t0 = time.perf_counter()
        train_loss = train_one_epoch(model, train_loader, optimizer, args.model, device)
        print(f"  epoch {epoch:3d}/{epochs}  train_loss={train_loss:.4f}  ({time.perf_counter()-t0:.1f}s)")

    training_time_s = time.perf_counter() - t_start

    ckpt_path = ckpt_dir / f"{args.exp}_{args.model}.pt"
    torch.save(model.state_dict(), ckpt_path)
    print(f"  체크포인트 저장: {ckpt_path.name}")

    print("  test 평가 중...")
    test_metrics = evaluate(model, test_loader, args.model, device)
    test_metrics["exp"]             = args.exp
    test_metrics["model"]           = args.model
    test_metrics["training_time_s"] = round(training_time_s, 1)
    test_metrics["n_epochs"]        = epochs

    results_dir = _NILM_ROOT / "docs" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = results_dir / f"{args.exp}_{args.model}_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(test_metrics, f, ensure_ascii=False, indent=2)

    print(f"\n[완료] {args.exp}/{args.model}  MAE={test_metrics['mae']:.2f}W  RMSE={test_metrics['rmse']:.2f}W  R²={test_metrics['r2']:.4f}  F1={test_metrics['f1']:.3f}")


if __name__ == "__main__":
    main()
