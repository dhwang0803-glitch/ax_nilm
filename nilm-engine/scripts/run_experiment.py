"""
실험 오케스트레이터 — 3개 모델 학습 + 성능 기록 MD 생성.

Usage:
    python scripts/run_experiment.py --exp EXP1 --data-root /path/to/data
    python scripts/run_experiment.py --exp EXP2 --data-root /path/to/data

실행 흐름:
    1. seq2point / bert4nilm / cnn_tda 순서로 train_model.py 호출
    2. 각 모델의 metrics JSON 수집
    3. 이전 EXP 대비 개선율 계산 (포화점 판단)
    4. docs/results/{exp}_results.md 작성
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

_NILM_ROOT = Path(__file__).resolve().parent.parent

MODELS = ["seq2point", "bert4nilm", "cnn_tda"]


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def load_metrics(exp: str, model: str) -> dict | None:
    path = _NILM_ROOT / "docs" / "results" / f"{exp}_{model}_metrics.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def prev_exp_name(exp: str, train_cfg: dict) -> str | None:
    return train_cfg["experiments"][exp].get("resume_from")


def improvement_pct(old_mae: float, new_mae: float) -> float:
    """old → new 개선율 (양수 = 개선)."""
    return (old_mae - new_mae) / (old_mae + 1e-8) * 100


def saturation_flag(improvements: list[float], threshold_pct: float) -> str:
    avg = sum(improvements) / len(improvements) if improvements else 0.0
    if avg < threshold_pct * 100:
        return f"⚠️ 포화 의심 (평균 개선 {avg:.1f}% < 기준 {threshold_pct*100:.0f}%)"
    return f"✅ 개선 중 (평균 개선 {avg:.1f}%)"


# ── MD 생성 ───────────────────────────────────────────────────────────────────

def write_md_report(
    exp: str,
    exp_cfg: dict,
    all_metrics: dict[str, dict],
    prev_metrics: dict[str, dict | None],
    saturation_threshold: float,
) -> Path:
    results_dir = _NILM_ROOT / "docs" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    md_path = results_dir / f"{exp}_results.md"

    week = exp_cfg.get("week", "?")
    resume_from = exp_cfg.get("resume_from") or "처음부터 학습"

    lines = [
        f"# {exp} 실험 결과",
        "",
        f"| 항목 | 값 |",
        f"|------|-----|",
        f"| 학습 주차 | week {week} (house별 시작일 기준 {(week-1)*7+1 if isinstance(week, int) else '?'}~{week*7 if isinstance(week, int) else '?'}일차) |",
        f"| 이전 체크포인트 | {resume_from} |",
        f"| 기록 일시 | {datetime.now().strftime('%Y-%m-%d %H:%M')} |",
        "",
        "---",
        "",
        "## 전체 성능 비교",
        "",
        "| 모델 | MAE (W) | RMSE (W) | SAE | F1 |",
        "|------|---------|----------|-----|----|",
    ]

    for model in MODELS:
        m = all_metrics.get(model)
        if m:
            lines.append(
                f"| {model} | {m['mae']:.2f} | {m['rmse']:.2f} | {m['sae']:.4f} | {m['f1']:.3f} |"
            )
        else:
            lines.append(f"| {model} | — | — | — | — |")

    lines += ["", "---", "", "## 이전 EXP 대비 개선율 (Val MAE 기준)"]

    if all(v is None for v in prev_metrics.values()):
        lines.append("", "> 첫 번째 실험 — 비교 대상 없음")
    else:
        lines += [
            "",
            "| 모델 | 이전 MAE | 현재 MAE | 개선율 |",
            "|------|---------|---------|--------|",
        ]
        improvements = []
        for model in MODELS:
            cur = all_metrics.get(model)
            prv = prev_metrics.get(model)
            if cur and prv:
                imp = improvement_pct(prv["mae"], cur["mae"])
                improvements.append(imp)
                trend = "↓" if imp > 0 else "↑"
                lines.append(
                    f"| {model} | {prv['mae']:.2f}W | {cur['mae']:.2f}W | {trend} {abs(imp):.1f}% |"
                )
            else:
                lines.append(f"| {model} | — | — | — |")

        lines += [
            "",
            f"**포화점 판단**: {saturation_flag(improvements, saturation_threshold)}",
        ]

    lines += [
        "",
        "---",
        "",
        "## 메모",
        "",
        "> 여기에 실험 중 특이사항, 하이퍼파라미터 변경 내역 등을 기록하세요.",
        "",
    ]

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp",        required=True, help="예: EXP1, EXP2, ...")
    parser.add_argument("--data-root",  required=True)
    parser.add_argument("--config-dir", default=str(_NILM_ROOT / "config"))
    parser.add_argument("--skip-train", action="store_true", help="학습 건너뛰고 기존 metrics만 집계")
    parser.add_argument("--no-mlflow",  action="store_true")
    args = parser.parse_args()

    cfg_dir = Path(args.config_dir)
    with open(cfg_dir / "train.yaml") as f:
        train_cfg = yaml.safe_load(f)

    if args.exp not in train_cfg["experiments"]:
        raise ValueError(f"{args.exp} 가 train.yaml 에 없습니다.")

    saturation_threshold = train_cfg.get("saturation_threshold", 0.05)

    # ── 학습 ────────────────────────────────────────────────────────────────
    if not args.skip_train:
        for model in MODELS:
            print(f"\n{'='*60}")
            print(f"  {args.exp} / {model} 학습 시작")
            print(f"{'='*60}")

            cmd = [
                sys.executable,
                str(_NILM_ROOT / "scripts" / "train_model.py"),
                "--model",     model,
                "--exp",       args.exp,
                "--data-root", args.data_root,
                "--config-dir", str(cfg_dir),
            ]
            if args.no_mlflow:
                cmd.append("--no-mlflow")

            result = subprocess.run(cmd)
            if result.returncode != 0:
                print(f"  ❌ {model} 학습 실패 (returncode={result.returncode})")

    # ── 지표 수집 ────────────────────────────────────────────────────────────
    all_metrics: dict[str, dict]       = {}
    prev_metrics: dict[str, dict|None] = {}

    prev_exp = prev_exp_name(args.exp, train_cfg)
    for model in MODELS:
        m = load_metrics(args.exp, model)
        all_metrics[model] = m

        prev_metrics[model] = load_metrics(prev_exp, model) if prev_exp else None

    # ── MD 보고서 ────────────────────────────────────────────────────────────
    exp_cfg = train_cfg["experiments"][args.exp]
    md_path = write_md_report(
        args.exp, exp_cfg, all_metrics, prev_metrics, saturation_threshold
    )
    print(f"\n📄 보고서 저장: {md_path.relative_to(_NILM_ROOT)}")

    # ── 요약 출력 ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  {args.exp} 결과 요약")
    print(f"{'='*60}")
    for model in MODELS:
        m = all_metrics.get(model)
        if m:
            print(f"  {model:12s}  MAE={m['mae']:.2f}W  RMSE={m['rmse']:.2f}W  "
                  f"SAE={m['sae']:.4f}  F1={m['f1']:.3f}")
        else:
            print(f"  {model:12s}  (metrics 없음)")

    if prev_exp and any(v is not None for v in prev_metrics.values()):
        improvements = []
        for model in MODELS:
            cur = all_metrics.get(model)
            prv = prev_metrics.get(model)
            if cur and prv:
                improvements.append(improvement_pct(prv["mae"], cur["mae"]))
        if improvements:
            print(f"\n{saturation_flag(improvements, saturation_threshold)}")


if __name__ == "__main__":
    main()
