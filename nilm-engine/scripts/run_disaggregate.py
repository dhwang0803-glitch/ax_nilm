"""
실시간 분해 실행 스크립트.

Usage:
    python scripts/run_disaggregate.py \\
        --checkpoint checkpoints/EXP1_cnn_tda.pt \\
        --input      /path/to/power_series.npy \\
        --output     results/disaggregated.json \\
        [--threshold 0.5]   # confidence gate 임계값
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

_NILM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_NILM_ROOT / "src"))

from disaggregator import NILMDisaggregator


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True, help="학습된 .pt 체크포인트 경로")
    parser.add_argument("--input",      required=True, help=".npy 파일 (shape: (N,) 유효전력 [W])")
    parser.add_argument("--output",     required=True, help="결과 저장 경로 (.json)")
    parser.add_argument("--window-size",  type=int,   default=1024)
    parser.add_argument("--stride",       type=int,   default=None, help="기본: window_size // 2")
    parser.add_argument("--threshold",    type=float, default=0.5,
                        help="confidence gate 임계값 (높을수록 TDA 덜 씀, 기본 0.5)")
    parser.add_argument("--device",       default=None, help="cuda / cpu (기본: 자동)")
    args = parser.parse_args()

    power_series = np.load(args.input)
    if power_series.ndim != 1:
        raise ValueError(f"입력은 1D array 여야 합니다. 현재 shape: {power_series.shape}")

    print(f"[disaggregate] 입력: {len(power_series):,} 샘플 ({len(power_series)/30:.1f}s @ 30Hz)")
    print(f"               threshold={args.threshold}  window={args.window_size}  stride={args.stride or args.window_size // 2}")

    disaggregator = NILMDisaggregator(
        model_path=args.checkpoint,
        window_size=args.window_size,
        stride=args.stride,
        confidence_threshold=args.threshold,
        device=args.device,
    )

    t0 = time.perf_counter()
    result = disaggregator.disaggregate(power_series, sample_rate=30)
    elapsed = time.perf_counter() - t0

    print(f"               완료: {elapsed:.2f}s  ({len(power_series)/elapsed/30:.1f}x 실시간)")

    # 각 가전 총 에너지 요약 출력
    print("\n[가전별 추정 에너지]")
    for label, arr in result.items():
        total_wh = float(arr.sum()) / 30 / 3600   # 30Hz → Wh
        if total_wh > 0.01:
            print(f"  {label:20s}: {total_wh:.3f} Wh")

    # JSON 저장 (float32 → Python float)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {k: v.tolist() for k, v in result.items()},
            f, ensure_ascii=False
        )
    print(f"\n결과 저장: {output_path}")


if __name__ == "__main__":
    main()
