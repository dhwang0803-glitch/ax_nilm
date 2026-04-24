"""
scripts/evaluate.py — 체크포인트 로드 후 테스트셋 정량 평가.

Usage:
    python scripts/evaluate.py \\
        --model cnn_tda \\
        --checkpoint checkpoints/EXP1_cnn_tda.pt \\
        --data-root /path/to/data \\
        [--exp EXP1] [--split test] [--config-dir config/]

출력:
    docs/results/{exp}_{model}_{split}_metrics.json
    콘솔 요약 테이블
"""

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
import yaml

_NILM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_NILM_ROOT / "src"))

from acquisition.dataset import NILMDataset
from classifier.label_map import (
    APPLIANCE_LABELS,
    APPLIANCE_TYPES,
    N_APPLIANCES,
    get_on_thresholds,
)
from features.tda import compute_tda_features
from models.bert4nilm import BERT4NILM
from models.cnn_tda import CNNTDAHybrid
from models.seq2point import Seq2Point


# ── 데이터 클래스 ─────────────────────────────────────────────────────────────


@dataclass
class ApplianceResult:
    name: str
    appliance_type: str
    mae: Optional[float]
    rmse: Optional[float]
    sae: Optional[float]
    f1: Optional[float]


@dataclass
class DisaggregationResult:
    model: str
    exp: str
    split: str
    overall_mae: float
    overall_rmse: float
    overall_sae: float
    overall_f1: float
    inference_time_s: float
    ms_per_window: float
    per_appliance: list[ApplianceResult]
    by_type: dict[str, dict]


# ── TDA 래퍼 ──────────────────────────────────────────────────────────────────


class _TDAWrapper(Dataset):
    def __init__(self, base: NILMDataset):
        self.base = base

    def __len__(self) -> int:
        return len(self.base)

    def __getitem__(self, idx: int):
        agg, target, on_off, validity = self.base[idx]
        tda = torch.from_numpy(compute_tda_features(agg.numpy()))
        return agg, tda, target, on_off, validity


# ── 추론 ──────────────────────────────────────────────────────────────────────


@torch.no_grad()
def run_inference(
    model: torch.nn.Module,
    loader: DataLoader,
    model_name: str,
    device: torch.device,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns:
        pred_arr   : (N, 22) — 예측 전력 [W]
        true_arr   : (N, 22) — 실제 전력 [W] (center point)
        on_off_arr : (N, 22) — 실제 ON/OFF (center point)
        valid_arr  : (N, 22) — validity 마스크
    """
    model.eval()
    all_pred, all_true, all_on_off, all_valid = [], [], [], []

    for batch in loader:
        if model_name == "cnn_tda":
            agg, tda, target, on_off, validity = batch
            agg = agg.unsqueeze(1).to(device)
            tda = tda.to(device)
            pred = model(agg, tda)
        elif model_name == "seq2point":
            agg, target, on_off, validity = batch
            pred = model(agg.unsqueeze(1).to(device))
        else:  # bert4nilm
            agg, target, on_off, validity = batch
            pred = model(agg.to(device))

        center = target.shape[-1] // 2
        all_pred.append(pred.cpu().numpy())
        all_true.append(target[:, :, center].numpy())
        all_on_off.append(on_off[:, :, center].numpy())
        all_valid.append(validity.numpy())

    return (
        np.concatenate(all_pred,   axis=0),   # (N, 22)
        np.concatenate(all_true,   axis=0),
        np.concatenate(all_on_off, axis=0),
        np.concatenate(all_valid,  axis=0),
    )


# ── 지표 계산 ─────────────────────────────────────────────────────────────────


def _f1(pred_on: np.ndarray, true_on: np.ndarray) -> float:
    tp = float((pred_on & true_on).sum())
    fp = float((pred_on & ~true_on).sum())
    fn = float((~pred_on & true_on).sum())
    return 2 * tp / (2 * tp + fp + fn + 1e-8)


def compute_metrics(
    pred_arr: np.ndarray,    # (N, 22)
    true_arr: np.ndarray,
    on_off_arr: np.ndarray,  # (N, 22) bool
    valid_arr: np.ndarray,   # (N, 22) bool
    model_name: str,
    exp: str,
    split: str,
    inference_time_s: float = 0.0,
) -> DisaggregationResult:
    thresholds = np.array(get_on_thresholds(), dtype=np.float32)  # (22,)
    pred_on = pred_arr >= thresholds[np.newaxis, :]               # (N, 22)
    true_on = on_off_arr.astype(bool)
    valid   = valid_arr.astype(bool)

    # ── 전체 평균 ─────────────────────────────────────────────────────────────
    p = pred_arr[valid]
    t = true_arr[valid]
    overall_mae  = float(np.abs(p - t).mean())
    overall_rmse = float(np.sqrt(((p - t) ** 2).mean()))
    overall_sae  = float(
        np.abs(pred_arr.sum(axis=0) - true_arr.sum(axis=0)).sum()
        / (true_arr.sum() + 1e-8)
    )
    overall_f1 = _f1(pred_on[valid], true_on[valid])

    # ── 가전별 ────────────────────────────────────────────────────────────────
    per_app: list[ApplianceResult] = []
    for i, name in enumerate(APPLIANCE_LABELS):
        col_mask = valid[:, i]
        if not col_mask.any():
            per_app.append(ApplianceResult(name, APPLIANCE_TYPES[name], None, None, None, None))
            continue

        pi    = pred_arr[col_mask, i]
        ti    = true_arr[col_mask, i]
        pi_on = pred_on[col_mask, i]
        ti_on = true_on[col_mask, i]

        mae  = float(np.abs(pi - ti).mean())
        rmse = float(np.sqrt(((pi - ti) ** 2).mean()))
        sae  = float(abs(pi.sum() - ti.sum()) / (ti.sum() + 1e-8))
        f1   = _f1(pi_on, ti_on)

        per_app.append(ApplianceResult(name, APPLIANCE_TYPES[name], mae, rmse, sae, f1))

    # ── Type별 집계 ───────────────────────────────────────────────────────────
    by_type: dict[str, dict] = {}
    for type_name in ("type1", "type2", "type3", "type4"):
        subset = [r for r in per_app if r.appliance_type == type_name and r.mae is not None]
        if not subset:
            by_type[type_name] = {"mae": None, "rmse": None, "sae": None, "f1": None, "n": 0}
            continue
        by_type[type_name] = {
            "mae":  float(np.mean([r.mae  for r in subset])),
            "rmse": float(np.mean([r.rmse for r in subset])),
            "sae":  float(np.mean([r.sae  for r in subset])),
            "f1":   float(np.mean([r.f1   for r in subset])),
            "n":    len(subset),
        }

    n_windows = len(pred_arr)
    ms_per_window = (inference_time_s * 1000 / n_windows) if n_windows > 0 else 0.0

    return DisaggregationResult(
        model=model_name,
        exp=exp,
        split=split,
        overall_mae=overall_mae,
        overall_rmse=overall_rmse,
        overall_sae=overall_sae,
        overall_f1=overall_f1,
        inference_time_s=round(inference_time_s, 3),
        ms_per_window=round(ms_per_window, 4),
        per_appliance=per_app,
        by_type=by_type,
    )


# ── 출력 ──────────────────────────────────────────────────────────────────────


def print_summary(result: DisaggregationResult) -> None:
    print(f"\n{'='*60}")
    print(f"  {result.exp} / {result.model} / {result.split}")
    print(f"{'='*60}")
    print(f"  MAE  : {result.overall_mae:.2f} W")
    print(f"  RMSE : {result.overall_rmse:.2f} W")
    print(f"  SAE  : {result.overall_sae:.4f}")
    print(f"  F1   : {result.overall_f1:.3f}")
    print(f"  추론  : {result.inference_time_s:.1f}s 총 / {result.ms_per_window:.4f} ms/window")
    print()
    print(f"  {'Type':<8} {'MAE(W)':>8} {'RMSE(W)':>9} {'SAE':>8} {'F1':>7}  N")
    print(f"  {'-'*50}")
    for t_name, v in result.by_type.items():
        if v["mae"] is None:
            print(f"  {t_name:<8}   (데이터 없음)")
            continue
        print(
            f"  {t_name:<8} {v['mae']:>8.2f} {v['rmse']:>9.2f} "
            f"{v['sae']:>8.4f} {v['f1']:>7.3f}  {v['n']}"
        )
    print()
    print(f"  {'가전':<22} {'Type':<8} {'MAE(W)':>8} {'F1':>7}")
    print(f"  {'-'*52}")
    for r in result.per_appliance:
        if r.mae is None:
            print(f"  {r.name:<22} {r.appliance_type:<8}   (없음)")
        else:
            print(f"  {r.name:<22} {r.appliance_type:<8} {r.mae:>8.2f} {r.f1:>7.3f}")
    print()


# ── 메인 ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model",      required=True, choices=["seq2point", "bert4nilm", "cnn_tda"])
    parser.add_argument("--checkpoint", required=True, help="체크포인트 .pt 파일 경로")
    parser.add_argument("--data-root",  required=True)
    parser.add_argument("--exp",        default="EXP0")
    parser.add_argument("--split",      default="test", choices=["val", "test"])
    parser.add_argument("--config-dir", default=str(_NILM_ROOT / "config"))
    args = parser.parse_args()

    cfg_dir = Path(args.config_dir)
    with open(cfg_dir / "dataset.yaml") as f:
        dataset_cfg = yaml.safe_load(f)

    window_size = dataset_cfg["window"]["size"]
    stride      = dataset_cfg["window"]["stride"]
    houses      = dataset_cfg["split"][args.split]

    base_ds = NILMDataset(houses, Path(args.data_root), window_size, stride)
    ds      = _TDAWrapper(base_ds) if args.model == "cnn_tda" else base_ds
    loader  = DataLoader(ds, batch_size=64, shuffle=False, num_workers=2, pin_memory=True)
    print(f"[evaluate] {args.split} {houses}  windows={len(ds):,}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if args.model == "seq2point":
        model = Seq2Point(window_size=window_size)
    elif args.model == "bert4nilm":
        model = BERT4NILM(window_size=window_size)
    else:
        model = CNNTDAHybrid(window_size=window_size)

    model.load_state_dict(torch.load(args.checkpoint, map_location=device))
    model.to(device)
    print(f"  체크포인트 로드: {args.checkpoint}")

    t0 = time.perf_counter()
    pred_arr, true_arr, on_off_arr, valid_arr = run_inference(
        model, loader, args.model, device
    )
    inference_time_s = time.perf_counter() - t0

    result = compute_metrics(
        pred_arr, true_arr, on_off_arr, valid_arr,
        model_name=args.model, exp=args.exp, split=args.split,
        inference_time_s=inference_time_s,
    )
    print_summary(result)

    results_dir = _NILM_ROOT / "docs" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    out_path = results_dir / f"{args.exp}_{args.model}_{args.split}_metrics.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(asdict(result), f, ensure_ascii=False, indent=2)
    print(f"  저장: {out_path.relative_to(_NILM_ROOT)}")


if __name__ == "__main__":
    main()
