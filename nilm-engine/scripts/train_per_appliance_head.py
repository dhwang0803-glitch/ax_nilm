"""
PerApplianceNILM 학습 스크립트 — 2-Phase training.

Phase 1: Head warm-up (encoder frozen, 5 epochs)
Phase 2: Joint training (encoder unfrozen, differential LR, ES on val_mae)
Phase 3 (optional): Weak head fine-tune (F1_cls < threshold)

Usage:
    python scripts/train_per_appliance_head.py \
        --ckpt checkpoints/EXP_GROUPNORM_cnn_multiscale.pt \
        --segment-dir /path/to/segments \
        --exp EXP_PERHEAD_v3

    # skip Phase 1 warm-up (e.g. when resuming from a prior per-head ckpt)
    python scripts/train_per_appliance_head.py \
        --ckpt checkpoints/EXP_PERHEAD_v3_joint.pt \
        --segment-dir /path/to/segments \
        --exp EXP_PERHEAD_v4 --skip-warmup --source-model per_appliance_head
"""

import argparse
import gc
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

_NILM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_NILM_ROOT / "src"))

from classifier.label_map import N_APPLIANCES, APPLIANCE_LABELS, get_on_thresholds
from features.tda import TDA_DIM
from models.per_appliance_head import PerApplianceNILM, transfer_weights


# ── Segment loader ───────────────────────────────────────────────────────────

def preload_windows(
    pt_files: list[Path], label: str = "",
) -> tuple[torch.Tensor, ...]:
    all_agg, all_tda, all_tc, all_oc, all_val = [], [], [], [], []
    for f in pt_files:
        d = torch.load(f, weights_only=False)
        ws = d["window_starts"].long()
        wsize = int(d["window_size"])
        center = wsize // 2
        n_win = int(d["n_windows"])
        CHUNK = 5000
        for i in range(0, n_win, CHUNK):
            chunk_ws = ws[i:i + CHUNK]
            idx = chunk_ws.unsqueeze(1) + torch.arange(wsize).unsqueeze(0)
            all_agg.append(d["agg"][idx].half())
            all_tda.append(d["tda"][i:i + CHUNK].half())
            center_idx = chunk_ws + center
            t, o = d["target"], d["on_off"]
            if t.dim() == 2:
                all_tc.append(t[:, center_idx].T.half())
                all_oc.append(o[:, center_idx].T.half())
            else:
                all_tc.append(t[i:i + CHUNK, :, center].half())
                all_oc.append(o[i:i + CHUNK, :, center].half())
            v = d["validity"].float().unsqueeze(0).expand(len(chunk_ws), -1)
            all_val.append(v.half())
        print(f"  {label} {f.stem}: {n_win:,} windows")
        del d
        gc.collect()
    return (
        torch.cat(all_agg), torch.cat(all_tda),
        torch.cat(all_tc), torch.cat(all_oc), torch.cat(all_val),
    )


# ── Val house auto-selection ─────────────────────────────────────────────────

def select_val_houses(
    houses: list[str],
    validity: dict[str, torch.Tensor],
    n_windows: dict[str, int],
    n_val: int = 3,
) -> list[str]:
    selected: list[str] = []
    remaining = list(houses)
    for _ in range(min(n_val, len(remaining))):
        current_cov = torch.zeros(N_APPLIANCES, dtype=torch.bool)
        for h in selected:
            current_cov |= validity[h]
        best_h, best_gain = None, -1
        for h in remaining:
            gain = int((validity[h] & ~current_cov).sum())
            if gain > best_gain or (
                gain == best_gain and best_h and n_windows[h] > n_windows.get(best_h, 0)
            ):
                best_gain = gain
                best_h = h
        if best_h:
            selected.append(best_h)
            remaining.remove(best_h)
    return selected


# ── Evaluation ───────────────────────────────────────────────────────────────

@torch.no_grad()
def evaluate_preloaded(
    model: nn.Module,
    agg_all: torch.Tensor,
    tda_all: torch.Tensor,
    tc_all: torch.Tensor,
    oc_all: torch.Tensor,
    val_all: torch.Tensor,
    device: torch.device,
    batch_size: int = 512,
) -> dict:
    model.eval()
    n = agg_all.shape[0]
    all_pred, all_logit = [], []

    for i in range(0, n, batch_size):
        agg = agg_all[i:i + batch_size].float().unsqueeze(1)
        tda = tda_all[i:i + batch_size].float()
        if not agg.is_cuda:
            agg, tda = agg.to(device), tda.to(device)
        pred, logit = model(agg, tda)
        all_pred.append(pred.cpu())
        all_logit.append(logit.cpu())

    pred = torch.cat(all_pred).numpy()
    logit = torch.cat(all_logit).numpy()
    true = tc_all.float().cpu().numpy()
    onoff = oc_all.float().cpu().numpy()
    valid = val_all.float().cpu().numpy()

    raw_thr = get_on_thresholds()
    if isinstance(raw_thr, dict):
        on_thr = [raw_thr.get(name, 10) for name in APPLIANCE_LABELS]
    else:
        on_thr = list(raw_thr)

    results: dict = {"per_appliance": {}}
    maes, f1cs = [], []

    for i, name in enumerate(APPLIANCE_LABELS):
        mask = valid[:, i].astype(bool)
        n_pos = int(onoff[mask, i].sum()) if mask.any() else 0
        if not mask.any() or n_pos == 0:
            results["per_appliance"][name] = {"mae": None, "f1_cls": None}
            continue
        p, t = pred[mask, i], true[mask, i]
        mae_i = float(np.abs(p - t).mean())
        rmse_i = float(np.sqrt(((p - t) ** 2).mean()))
        true_on = onoff[mask, i].astype(float)

        pred_on = (np.clip(p, 0, None) > on_thr[i]).astype(float)
        tp = (pred_on * true_on).sum()
        prec = tp / max(tp + (pred_on * (1 - true_on)).sum(), 1)
        rec = tp / max(tp + ((1 - pred_on) * true_on).sum(), 1)
        f1_i = float(2 * prec * rec / max(prec + rec, 1e-8))

        best_f1c, best_thr = 0.0, 0.0
        for thr in np.arange(-3.0, 3.1, 0.1):
            pc = (logit[mask, i] > thr).astype(float)
            tp_c = (pc * true_on).sum()
            pr_c = tp_c / max(tp_c + (pc * (1 - true_on)).sum(), 1)
            re_c = tp_c / max(tp_c + ((1 - pc) * true_on).sum(), 1)
            f1c = float(2 * pr_c * re_c / max(pr_c + re_c, 1e-8))
            if f1c > best_f1c:
                best_f1c, best_thr = f1c, thr

        results["per_appliance"][name] = {
            "mae": round(mae_i, 2), "rmse": round(rmse_i, 2),
            "f1": round(f1_i, 4), "f1_cls": round(best_f1c, 4),
            "n_pos": n_pos, "best_thr": round(best_thr, 2),
        }
        maes.append(mae_i)
        f1cs.append(best_f1c)

    results["mae"] = round(float(np.mean(maes)), 2) if maes else None
    results["f1_cls"] = round(float(np.mean(f1cs)), 4) if f1cs else None
    return results


# ── Fine-tune single head ────────────────────────────────────────────────────

def finetune_head(
    model: nn.Module,
    head_idx: int,
    agg_all: torch.Tensor,
    tda_all: torch.Tensor,
    tc_all: torch.Tensor,
    oc_all: torch.Tensor,
    val_all: torch.Tensor,
    device: torch.device,
    epochs: int = 20,
    lr: float = 1e-4,
    batch_size: int = 256,
) -> None:
    for p in model.encoder.parameters():
        p.requires_grad = False
    for j, head in enumerate(model.heads):
        for p in head.parameters():
            p.requires_grad = (j == head_idx)

    optimizer = torch.optim.Adam(model.heads[head_idx].parameters(), lr=lr)
    n = agg_all.shape[0]

    model.train()
    for epoch in range(1, epochs + 1):
        perm = torch.randperm(n, device=agg_all.device if agg_all.is_cuda else "cpu")
        for i in range(0, n, batch_size):
            idx = perm[i:i + batch_size]
            v = val_all[idx, head_idx].float()
            if not v.any():
                continue
            agg = agg_all[idx].float().unsqueeze(1)
            tda = tda_all[idx].float()
            tc = tc_all[idx, head_idx].float()
            oc = oc_all[idx, head_idx].float()
            if not agg.is_cuda:
                agg, tda = agg.to(device), tda.to(device)
                tc, oc, v = tc.to(device), oc.to(device), v.to(device)

            optimizer.zero_grad()
            with torch.no_grad():
                feat = model.encoder(agg, tda)
            pred, logit = model.heads[head_idx](feat)
            mse = ((pred - tc) ** 2 * v).sum() / v.sum().clamp(min=1)
            bce = F.binary_cross_entropy_with_logits(logit, oc, reduction="none")
            bce = (bce * v).sum() / v.sum().clamp(min=1)
            loss = bce + mse
            loss.backward()
            optimizer.step()

    for p in model.parameters():
        p.requires_grad = True


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt", required=True, help="CNNMultiScaleHybrid or PerApplianceNILM checkpoint path")
    parser.add_argument("--segment-dir", required=True, help="Directory with per-house .pt segments")
    parser.add_argument("--exp", required=True, help="Experiment name (e.g. EXP_PERHEAD_v3)")
    parser.add_argument("--output-dir", default=str(_NILM_ROOT / "checkpoints"))
    parser.add_argument("--results-dir", default=str(_NILM_ROOT / "docs" / "results"))
    parser.add_argument("--source-model", default="cnn_multiscale",
                        choices=["cnn_multiscale", "per_appliance_head"],
                        help="Source checkpoint model type for weight loading")
    parser.add_argument("--skip-warmup", action="store_true", help="Skip Phase 1 warm-up")
    parser.add_argument("--warmup-epochs", type=int, default=5)
    parser.add_argument("--joint-epochs", type=int, default=50)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr-encoder", type=float, default=1e-5)
    parser.add_argument("--lr-head", type=float, default=5e-4)
    parser.add_argument("--finetune-threshold", type=float, default=0.6,
                        help="F1_cls threshold below which heads get fine-tuned")
    parser.add_argument("--finetune-epochs", type=int, default=20)
    parser.add_argument("--n-val", type=int, default=3)
    parser.add_argument("--no-finetune", action="store_true")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt_dir = Path(args.output_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    segment_dir = Path(args.segment_dir)

    # ── Load segments & split ────────────────────────────────────────────────
    all_seg_files = sorted(list(segment_dir.glob("*.pt")))
    if not all_seg_files:
        raise FileNotFoundError(f"No .pt files found in {segment_dir}")

    house_to_files: dict[str, list[Path]] = {}
    for f in all_seg_files:
        m = re.match(r"(house_\d+)", f.stem)
        h_id = m.group(1) if m else f.stem.rsplit("_", 1)[0]
        house_to_files.setdefault(h_id, []).append(f)

    house_validity: dict[str, torch.Tensor] = {}
    house_n_windows: dict[str, int] = {}
    for h_id in sorted(house_to_files.keys()):
        f = house_to_files[h_id][0]
        d = torch.load(f, weights_only=False)
        house_validity[h_id] = d["validity"].clone()
        house_n_windows[h_id] = int(d["n_windows"])
        del d

    all_houses = sorted(house_to_files.keys())
    val_houses = select_val_houses(all_houses, house_validity, house_n_windows, args.n_val)
    train_houses = [h for h in all_houses if h not in val_houses]

    val_cov = torch.zeros(N_APPLIANCES, dtype=torch.bool)
    for h in val_houses:
        val_cov |= house_validity[h]
    missing = [APPLIANCE_LABELS[i] for i in range(N_APPLIANCES) if not val_cov[i]]

    print(f"Train ({len(train_houses)}): {train_houses}")
    print(f"Val   ({len(val_houses)}): {val_houses}")
    if missing:
        print(f"  Missing in val: {missing}")

    train_files = [f for h in train_houses for f in house_to_files[h]]
    val_files = [f for h in val_houses for f in house_to_files[h]]

    print("\nLoading train data...")
    tr_agg, tr_tda, tr_tc, tr_oc, tr_val = preload_windows(train_files, "train")
    print(f"  -> {tr_agg.shape[0]:,} windows")

    print("Loading val data...")
    va_agg, va_tda, va_tc, va_oc, va_val = preload_windows(val_files, "val")
    print(f"  -> {va_agg.shape[0]:,} windows")

    # GPU prefetch if fits
    data_on_gpu = False
    if device.type == "cuda":
        total_bytes = sum(
            t.nbytes for t in [tr_agg, tr_tda, tr_tc, tr_oc, tr_val,
                               va_agg, va_tda, va_tc, va_oc, va_val]
        )
        gpu_free = torch.cuda.mem_get_info()[0]
        if total_bytes < gpu_free * 0.7:
            tr_agg, tr_tda = tr_agg.to(device), tr_tda.to(device)
            tr_tc, tr_oc, tr_val = tr_tc.to(device), tr_oc.to(device), tr_val.to(device)
            va_agg, va_tda = va_agg.to(device), va_tda.to(device)
            va_tc, va_oc, va_val = va_tc.to(device), va_oc.to(device), va_val.to(device)
            data_on_gpu = True
            print(f"  GPU prefetch: {total_bytes / 1e9:.2f} GB")

    # ── Build model ──────────────────────────────────────────────────────────
    model = PerApplianceNILM(window_size=1024).to(device)

    ckpt_path = Path(args.ckpt)
    if args.source_model == "cnn_multiscale":
        model = transfer_weights(ckpt_path, model, device)
    else:
        ckpt = torch.load(str(ckpt_path), map_location=device, weights_only=True)
        state = ckpt["model_state"] if "model_state" in ckpt else ckpt
        model.load_state_dict(state)
        print(f"Loaded per_appliance_head checkpoint: {ckpt_path.name}")

    n_train = tr_agg.shape[0]
    n_val = va_agg.shape[0]
    t0 = time.time()

    # ── Phase 1: Head warm-up ────────────────────────────────────────────────
    if not args.skip_warmup:
        print(f"\n{'=' * 60}")
        print(f"Phase 1: Head warm-up (encoder frozen, {args.warmup_epochs} epochs)")
        print(f"{'=' * 60}")

        for p in model.encoder.parameters():
            p.requires_grad = False

        head_params = list(model.heads.parameters())
        opt_p1 = torch.optim.Adam(head_params, lr=args.lr_head, weight_decay=1e-5)

        for epoch in range(1, args.warmup_epochs + 1):
            model.train()
            perm = torch.randperm(
                n_train, device=tr_agg.device if data_on_gpu else "cpu"
            )
            total_loss, n_batches = 0.0, 0

            for i in range(0, n_train, args.batch_size):
                idx = perm[i:i + args.batch_size]
                agg = tr_agg[idx].float().unsqueeze(1)
                tda = tr_tda[idx].float()
                tc = tr_tc[idx].float()
                oc = tr_oc[idx].float()
                val = tr_val[idx].float()
                if not data_on_gpu:
                    agg, tda = agg.to(device), tda.to(device)
                    tc, oc, val = tc.to(device), oc.to(device), val.to(device)

                opt_p1.zero_grad()
                with torch.no_grad():
                    feat = model.encoder(agg, tda)
                preds, logits = [], []
                for head in model.heads:
                    p, l = head(feat)
                    preds.append(p)
                    logits.append(l)
                pred = torch.stack(preds, dim=-1)
                logit = torch.stack(logits, dim=-1)

                mse = ((pred - tc) ** 2 * val).sum() / val.sum().clamp(min=1)
                bce = F.binary_cross_entropy_with_logits(logit, oc, reduction="none")
                bce = (bce * val).sum() / val.sum().clamp(min=1)
                loss = bce + mse

                loss.backward()
                nn.utils.clip_grad_norm_(head_params, 1.0)
                opt_p1.step()
                total_loss += loss.item()
                n_batches += 1

            print(
                f"  P1 ep {epoch}/{args.warmup_epochs}  "
                f"loss={total_loss / max(n_batches, 1):.4f}  "
                f"[{(time.time() - t0) / 60:.1f}min]"
            )
        del opt_p1

    # ── Phase 2: Joint training ──────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"Phase 2: Joint training (differential LR, {args.joint_epochs} epochs)")
    print(f"{'=' * 60}")

    for p in model.encoder.parameters():
        p.requires_grad = True

    optimizer = torch.optim.Adam([
        {"params": model.encoder.parameters(), "lr": args.lr_encoder},
        {"params": model.heads.parameters(), "lr": args.lr_head},
    ], weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, "min", factor=0.5, patience=5,
    )

    best_mae = float("inf")
    best_state = None
    no_improve = 0

    for epoch in range(1, args.joint_epochs + 1):
        model.train()
        perm = torch.randperm(
            n_train, device=tr_agg.device if data_on_gpu else "cpu"
        )
        total_loss, n_batches = 0.0, 0

        for i in range(0, n_train, args.batch_size):
            idx = perm[i:i + args.batch_size]
            agg = tr_agg[idx].float().unsqueeze(1)
            tda = tr_tda[idx].float()
            tc = tr_tc[idx].float()
            oc = tr_oc[idx].float()
            val = tr_val[idx].float()
            if not data_on_gpu:
                agg, tda = agg.to(device), tda.to(device)
                tc, oc, val = tc.to(device), oc.to(device), val.to(device)

            optimizer.zero_grad()
            pred, logit = model(agg, tda)

            mse = ((pred - tc) ** 2 * val).sum() / val.sum().clamp(min=1)
            bce = F.binary_cross_entropy_with_logits(logit, oc, reduction="none")
            bce = (bce * val).sum() / val.sum().clamp(min=1)
            loss = bce + mse

            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item()
            n_batches += 1

        avg_loss = total_loss / max(n_batches, 1)

        # Validation
        model.eval()
        val_errs = []
        with torch.no_grad():
            eval_bs = args.batch_size * 2
            for i in range(0, n_val, eval_bs):
                agg = va_agg[i:i + eval_bs].float().unsqueeze(1)
                tda = va_tda[i:i + eval_bs].float()
                tc = va_tc[i:i + eval_bs].float()
                vm = va_val[i:i + eval_bs].float()
                if not data_on_gpu:
                    agg, tda = agg.to(device), tda.to(device)
                    tc, vm = tc.to(device), vm.to(device)
                pred, _ = model(agg, tda)
                val_errs.append(((pred - tc).abs() * vm).cpu())

        ve = torch.cat(val_errs)
        vm_all = torch.cat([
            va_val[i:i + args.batch_size * 2].float()
            for i in range(0, n_val, args.batch_size * 2)
        ])
        mae = float(ve.sum() / vm_all.sum().clamp(min=1))

        scheduler.step(mae)
        lr_enc = optimizer.param_groups[0]["lr"]
        lr_head = optimizer.param_groups[1]["lr"]
        print(
            f"  P2 ep {epoch:3d}/{args.joint_epochs}  loss={avg_loss:.4f}  "
            f"val_mae={mae:.4f}  lr_enc={lr_enc:.2e} lr_head={lr_head:.2e}  "
            f"[{(time.time() - t0) / 60:.1f}min]"
        )

        if mae < best_mae:
            best_mae = mae
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= args.patience:
                print(f"  Early stopping ({args.patience}ep no improve)")
                break

    if best_state:
        model.load_state_dict({k: v.to(device) for k, v in best_state.items()})

    elapsed = time.time() - t0
    print(f"\nPhase 2 done: {elapsed / 60:.1f}min, best val_mae={best_mae:.4f}")

    # Save joint checkpoint
    joint_ckpt_path = ckpt_dir / f"{args.exp}_joint.pt"
    torch.save({
        "model_state": model.state_dict(),
        "best_mae": best_mae,
        "training_time_s": elapsed,
        "train_houses": train_houses,
        "val_houses": val_houses,
    }, joint_ckpt_path)
    print(f"Saved: {joint_ckpt_path.name}")

    # Evaluate
    metrics = evaluate_preloaded(
        model, va_agg, va_tda, va_tc, va_oc, va_val, device,
    )

    print(f"\n{'=' * 70}")
    print(f"  Overall MAE: {metrics['mae']}W | F1_cls: {metrics['f1_cls']}")
    print(f"{'=' * 70}")
    print(f"{'Appliance':<20s} {'MAE(W)':>8s} {'RMSE':>8s} {'F1':>8s} {'F1_cls':>8s}")
    print("-" * 60)
    for name in APPLIANCE_LABELS:
        r = metrics["per_appliance"][name]
        if r.get("mae") is None:
            print(f"{name:<20s} {'--':>8s} {'--':>8s} {'--':>8s} {'--':>8s}")
        else:
            print(
                f"{name:<20s} {r['mae']:>8.1f} {r['rmse']:>8.1f} "
                f"{r['f1']:>8.4f} {r['f1_cls']:>8.4f}"
            )

    metrics["exp"] = args.exp
    metrics["model"] = "per_appliance_head"
    metrics["train_houses"] = train_houses
    metrics["val_houses"] = val_houses
    metrics_path = results_dir / f"{args.exp}_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print(f"Saved: {metrics_path.name}")

    # ── Phase 3: Fine-tune weak heads ────────────────────────────────────────
    if not args.no_finetune:
        weak_heads = []
        for i, name in enumerate(APPLIANCE_LABELS):
            r = metrics["per_appliance"].get(name, {})
            f1c = r.get("f1_cls")
            if f1c is not None and f1c < args.finetune_threshold:
                weak_heads.append((i, name, f1c))

        if weak_heads:
            print(f"\n{'=' * 60}")
            print(f"Phase 3: Fine-tune {len(weak_heads)} weak heads (F1_cls < {args.finetune_threshold})")
            print(f"{'=' * 60}")

            t0_ft = time.time()
            for idx, name, f1c in weak_heads:
                finetune_head(
                    model, idx, tr_agg, tr_tda, tr_tc, tr_oc, tr_val,
                    device, epochs=args.finetune_epochs, lr=1e-4,
                )
                print(f"  Head[{idx}] ({name}, F1_cls={f1c:.4f}) fine-tuned")

            elapsed_ft = time.time() - t0_ft
            print(f"Fine-tune done: {elapsed_ft / 60:.1f}min")

            metrics_ft = evaluate_preloaded(
                model, va_agg, va_tda, va_tc, va_oc, va_val, device,
            )

            print(f"\n  After fine-tune: MAE={metrics_ft['mae']}W | F1_cls={metrics_ft['f1_cls']}")
            print(f"  Before:          MAE={metrics['mae']}W | F1_cls={metrics['f1_cls']}")

            print(f"\n{'Appliance':<20s} {'Before':>10s} {'After':>10s} {'Delta':>8s}")
            print("-" * 50)
            for idx, name, old_f1c in weak_heads:
                new_r = metrics_ft["per_appliance"].get(name, {})
                new_f1c = new_r.get("f1_cls") or 0
                delta = new_f1c - old_f1c
                print(f"{name:<20s} {old_f1c:>10.4f} {new_f1c:>10.4f} {delta:>+8.4f}")

            ft_ckpt_path = ckpt_dir / f"{args.exp}_finetune.pt"
            torch.save({
                "model_state": model.state_dict(),
                "training_time_s": elapsed_ft,
                "weak_heads": [(idx, name) for idx, name, _ in weak_heads],
                "finetune_threshold": args.finetune_threshold,
                "train_houses": train_houses,
                "val_houses": val_houses,
            }, ft_ckpt_path)

            metrics_ft["exp"] = f"{args.exp}_finetune"
            metrics_ft["model"] = "per_appliance_head"
            ft_metrics_path = results_dir / f"{args.exp}_finetune_metrics.json"
            with open(ft_metrics_path, "w", encoding="utf-8") as f:
                json.dump(metrics_ft, f, indent=2, ensure_ascii=False)
            print(f"Saved: {ft_ckpt_path.name}, {ft_metrics_path.name}")
        else:
            print(f"\nAll heads F1_cls >= {args.finetune_threshold} — skipping fine-tune")

    print(f"\n[Done] Total: {(time.time() - t0) / 60:.1f}min")


if __name__ == "__main__":
    main()
