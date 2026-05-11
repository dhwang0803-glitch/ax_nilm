"""샘플 데이터 파싱 검증 — AI Hub 71685.

CSV 원천과 JSON 라벨의 구조, 타임스탬프 연속성, 수치 범위, 결측, 중복을
확인하고 문서 스펙과의 갭을 표면화한다.

실행: python Database/scripts/validate_sample.py
출력: Database/dataset_staging/aihub_71685/_validate_report.txt 동시 기록
"""
import io
import json
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


SAMPLE_ROOT = Path("Database/dataset_staging/aihub_71685/samples")
RAW = SAMPLE_ROOT / "01.원천데이터"
LBL = SAMPLE_ROOT / "02.라벨링데이터"
REPORT = Path("Database/dataset_staging/aihub_71685/_validate_report.txt")

EXPECTED_COLS = [
    "date_time", "active_power", "voltage", "current",
    "frequency", "apparent_power", "reactive_power",
    "power_factor", "phase_difference", "current_phase",
    "voltage_phase",
]
EXPECTED_ROWS = 2_592_000
EXPECTED_INTERVAL_MS = 1000 / 30


def check_csv(csv_path: Path) -> dict:
    df = pd.read_csv(csv_path, parse_dates=["date_time"])
    deltas_ms = df["date_time"].diff().dropna().dt.total_seconds() * 1000
    result = {
        "file": csv_path.name,
        "rows": len(df),
        "cols_match": list(df.columns) == EXPECTED_COLS,
        "cols_actual": list(df.columns),
        "first_ts": str(df["date_time"].iloc[0]),
        "last_ts": str(df["date_time"].iloc[-1]),
        "null_counts": {k: int(v) for k, v in df.isnull().sum().items()},
        "dup_ts": int(df["date_time"].duplicated().sum()),
        "interval_ms_mean": float(deltas_ms.mean()),
        "interval_ms_std": float(deltas_ms.std()),
        "interval_ms_min": float(deltas_ms.min()),
        "interval_ms_max": float(deltas_ms.max()),
        "interval_gaps_over_50ms": int((deltas_ms > 50).sum()),
    }
    for col in ["active_power", "voltage", "current", "frequency",
                "apparent_power", "reactive_power", "power_factor",
                "phase_difference", "current_phase", "voltage_phase"]:
        result[f"{col}_min"] = float(df[col].min())
        result[f"{col}_max"] = float(df[col].max())
        result[f"{col}_mean"] = float(df[col].mean())
    return result


def check_json(json_path: Path) -> dict:
    with json_path.open(encoding="utf-8") as f:
        data = json.load(f)
    meta = data.get("meta", {})
    labels = data.get("labels", {})
    ai = labels.get("active_inactive", [])
    return {
        "file": json_path.name,
        "meta_key_count": len(meta),
        "meta_keys": list(meta.keys()),
        "meta_type": meta.get("type"),
        "meta_type_pytype": type(meta.get("type")).__name__,
        "meta_sampling_freq": meta.get("sampling_frequency"),
        "meta_sampling_freq_pytype": type(meta.get("sampling_frequency")).__name__,
        "meta_name": meta.get("name"),
        "meta_power_category": meta.get("power_category"),
        "meta_power_consumption": meta.get("power_consumption"),
        "meta_brand": meta.get("brand"),
        "meta_energy_efficiency": meta.get("energy_efficiency"),
        "meta_address": meta.get("address"),
        "meta_members": meta.get("members"),
        "meta_income": meta.get("income"),
        "meta_temperature": meta.get("temperature"),
        "meta_temperature_pytype": type(meta.get("temperature")).__name__,
        "meta_windchill": meta.get("windchill"),
        "meta_humidity": meta.get("humidity"),
        "meta_humidity_pytype": type(meta.get("humidity")).__name__,
        "meta_extra_appliances": meta.get("extra_appliances"),
        "labels_id": labels.get("id"),
        "ai_intervals": len(ai),
        "ai_first": ai[0] if ai else None,
        "ai_last": ai[-1] if ai else None,
    }


def emit(buf: io.StringIO, line: str = "") -> None:
    print(line)
    buf.write(line + "\n")


def main() -> int:
    buf = io.StringIO()

    emit(buf, "=" * 72)
    emit(buf, "AI Hub 71685 — 샘플 데이터 파싱 검증 리포트")
    emit(buf, "=" * 72)

    emit(buf, "\n[1] CSV 원천 데이터")
    emit(buf, "-" * 72)
    for csv in sorted(RAW.rglob("*.csv")):
        res = check_csv(csv)
        emit(buf, f"\n▶ {res['file']}")
        emit(buf, f"  rows={res['rows']:,} (expected {EXPECTED_ROWS:,} + 1 header = {EXPECTED_ROWS+1:,})")
        emit(buf, f"  cols_match={res['cols_match']}")
        if not res["cols_match"]:
            emit(buf, f"  cols_actual={res['cols_actual']}")
        emit(buf, f"  first_ts={res['first_ts']}")
        emit(buf, f"  last_ts ={res['last_ts']}")
        emit(buf, f"  null_counts={res['null_counts']}")
        emit(buf, f"  dup_ts={res['dup_ts']}")
        emit(buf, f"  interval_ms: mean={res['interval_ms_mean']:.3f} std={res['interval_ms_std']:.3f} "
                  f"min={res['interval_ms_min']:.3f} max={res['interval_ms_max']:.3f} "
                  f"(expected≈{EXPECTED_INTERVAL_MS:.3f})")
        emit(buf, f"  gaps>50ms: {res['interval_gaps_over_50ms']}")
        for col in ["active_power", "voltage", "current", "frequency",
                    "apparent_power", "reactive_power", "power_factor",
                    "phase_difference", "current_phase", "voltage_phase"]:
            emit(buf, f"  {col}: [{res[f'{col}_min']:.3f} .. {res[f'{col}_max']:.3f}] "
                      f"mean={res[f'{col}_mean']:.3f}")

    emit(buf, "\n\n[2] JSON 라벨 데이터")
    emit(buf, "-" * 72)
    for js in sorted(LBL.rglob("*.json")):
        res = check_json(js)
        emit(buf, f"\n▶ {res['file']}")
        emit(buf, f"  meta_key_count={res['meta_key_count']}")
        emit(buf, f"  meta.type = {res['meta_type']!r}  ({res['meta_type_pytype']})")
        emit(buf, f"  meta.sampling_frequency = {res['meta_sampling_freq']!r}  "
                  f"({res['meta_sampling_freq_pytype']})")
        emit(buf, f"  meta.name = {res['meta_name']!r}")
        emit(buf, f"  meta.power_category = {res['meta_power_category']!r}")
        emit(buf, f"  meta.power_consumption = {res['meta_power_consumption']!r}")
        emit(buf, f"  meta.brand = {res['meta_brand']!r}")
        emit(buf, f"  meta.energy_efficiency = {res['meta_energy_efficiency']!r}")
        emit(buf, f"  meta.address = {res['meta_address']!r}  [🔒 PII]")
        emit(buf, f"  meta.members = {res['meta_members']!r}  [🔒 PII]")
        emit(buf, f"  meta.income = {res['meta_income']!r}  [🔒 sensitive]")
        emit(buf, f"  meta.temperature = {res['meta_temperature']!r}  ({res['meta_temperature_pytype']})")
        emit(buf, f"  meta.windchill = {res['meta_windchill']!r}  (문서는 체감온도, 실제는 평균풍속)")
        emit(buf, f"  meta.humidity = {res['meta_humidity']!r}  ({res['meta_humidity_pytype']})")
        emit(buf, f"  meta.extra_appliances = {res['meta_extra_appliances']!r}")
        emit(buf, f"  labels.id = {res['labels_id']!r}")
        emit(buf, f"  active_inactive intervals: {res['ai_intervals']}")
        emit(buf, f"    first: {res['ai_first']}")
        emit(buf, f"    last : {res['ai_last']}")

    REPORT.write_text(buf.getvalue(), encoding="utf-8")
    print(f"\n[ok] 리포트 저장: {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
