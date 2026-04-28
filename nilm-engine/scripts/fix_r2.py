"""
기존 *_metrics.json 의 전체 r2 를 per_appliance 평균으로 재계산해 덮어씀.

Usage:
    python scripts/fix_r2.py --results-dir /path/to/results
    python scripts/fix_r2.py --results-dir .   # 현재 디렉토리
"""

import argparse
import json
from pathlib import Path


def recalc_r2(metrics: dict) -> float | None:
    per = metrics.get("per_appliance", {})
    values = [v["r2"] for v in per.values() if v.get("r2") is not None]
    if not values:
        return None
    return sum(values) / len(values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True, help="*_metrics.json 이 있는 디렉토리")
    parser.add_argument("--dry-run", action="store_true", help="파일 수정 없이 결과만 출력")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    files = sorted(results_dir.glob("*_metrics.json"))

    if not files:
        print(f"metrics.json 파일 없음: {results_dir}")
        return

    print(f"{'파일':<35} {'기존 r2':>10} {'재계산 r2':>10} {'차이':>10}")
    print("-" * 68)

    for path in files:
        with open(path, encoding="utf-8") as f:
            metrics = json.load(f)

        old_r2 = metrics.get("r2")
        new_r2 = recalc_r2(metrics)

        if new_r2 is None:
            print(f"{path.name:<35} {'없음':>10} {'없음':>10}")
            continue

        diff = new_r2 - old_r2 if old_r2 is not None else float("nan")
        print(f"{path.name:<35} {old_r2:>10.4f} {new_r2:>10.4f} {diff:>+10.4f}")

        if not args.dry_run:
            metrics["r2"] = new_r2
            with open(path, "w", encoding="utf-8") as f:
                json.dump(metrics, f, ensure_ascii=False, indent=2)

    if args.dry_run:
        print("\n[dry-run] 파일 수정 없음")
    else:
        print(f"\n{len(files)}개 파일 업데이트 완료")


if __name__ == "__main__":
    main()
