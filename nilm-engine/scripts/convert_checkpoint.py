"""
CNNMultiScaleHybrid -> PerApplianceNILM checkpoint converter.

Usage:
    python scripts/convert_checkpoint.py \
        --src checkpoints/EXP_GROUPNORM_cnn_multiscale.pt \
        --dst checkpoints/EXP_GROUPNORM_per_appliance_head.pt
"""

import argparse
import sys
from pathlib import Path

import torch

_NILM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_NILM_ROOT / "src"))

from models.per_appliance_head import PerApplianceNILM, transfer_weights


def main():
    parser = argparse.ArgumentParser(
        description="Convert CNNMultiScaleHybrid checkpoint to PerApplianceNILM",
    )
    parser.add_argument("--src", required=True, help="Source CNNMultiScaleHybrid .pt file")
    parser.add_argument("--dst", required=True, help="Output PerApplianceNILM .pt file")
    parser.add_argument("--window-size", type=int, default=1024)
    args = parser.parse_args()

    src_path = Path(args.src)
    dst_path = Path(args.dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    model = PerApplianceNILM(window_size=args.window_size)
    model = transfer_weights(src_path, model, device="cpu")

    src_ckpt = torch.load(str(src_path), map_location="cpu", weights_only=True)
    save_data = {
        "model_state": model.state_dict(),
        "converted_from": src_path.name,
    }
    if "best_cls_thresholds" in src_ckpt:
        save_data["best_cls_thresholds"] = src_ckpt["best_cls_thresholds"]

    torch.save(save_data, str(dst_path))
    print(f"Saved: {dst_path}")

    total_params = sum(p.numel() for p in model.parameters())
    enc_params = sum(p.numel() for p in model.encoder.parameters())
    head_params = sum(p.numel() for p in model.heads.parameters())
    print(f"Params — encoder: {enc_params:,} | heads: {head_params:,} | total: {total_params:,}")


if __name__ == "__main__":
    main()
