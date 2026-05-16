"""합성 anomaly 4시나리오를 H015 nilm_output에 주입하고 report_node를 직접 호출.

진단 카테고리 분류(이상/사용변화/정상)·cause·expected_savings 동작 검증용.
DB·GCS 변경 없음 — nilm_output·cashback·weather·profile 모두 합성.
"""
from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv("config/.env", override=True)
sys.path.insert(0, os.path.abspath("."))

# Windows cp949 콘솔에서 em-dash 등 유니코드 출력 시 죽지 않도록 강제 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

from src.agent.multi_agent.report_agent import report_node


# 시나리오: (event_id, appliance, mode, flag_type, peak_w, energy_wh, duration_min, before_kw, after_kw, severity, description)
SYNTH_EVENTS = [
    # 1) TV — D유형 + low_confidence + peak 6190W (사용변화 기대)
    ("syn-tv-1", "TV", "시청", "피크스파이크", 6190, 6190, 60, 0.0, 6.19, "warning",
     "TV 일일 사용량 6.19kWh로 전주 평균 0kWh에서 급증"),
    # 2) 에어컨 — D유형 + 신뢰 baseline + 과소비 (이상 기대)
    ("syn-ac-1", "에어컨", "냉방", "과소비", 1450, 2520, 180, 1.2, 2.52, "warning",
     "에어컨 냉방 모드 energy_wh가 baseline 평균의 2.1배"),
    # 3) 김치냉장고 — A유형 + 피크스파이크 반복 1240W (이상 기대)
    ("syn-kf-1", "김치냉장고", "가동", "피크스파이크", 1240, 30, 2, 0.8, 0.95, "critical",
     "김치냉장고 컴프레서 peak 1240W 반복 관측 — 모터 부하 의심"),
    # 4) 전자레인지 — C유형 + 신뢰 baseline + 장시간 (사용변화 기대 — 사용 습관 변화)
    ("syn-mw-1", "전자레인지", "가열", "장시간", 1100, 250, 12, 0.05, 0.08, "info",
     "전자레인지 평균 가열 시간이 baseline 4분에서 12분으로 증가"),
]


def _build_anomaly_events() -> list[dict]:
    out = []
    for eid, app, mode, ftype, peak, energy, dur, before, after, sev, desc in SYNTH_EVENTS:
        out.append({
            "event_id":    eid,
            "appliance":   app,
            "mode":        mode,
            "flag_type":   ftype,
            "peak_w":      peak,
            "energy_wh":   energy,
            "duration_min": dur,
            "before_kw":   before,
            "after_kw":    after,
            "severity":    sev,
            "description": desc,
            "detected_at": "2026-05-15 14:00",
            "confidence":  0.85,
        })
    return out


def _build_anomaly_flags() -> list[dict]:
    return [
        {"appliance": "TV", "mode": "시청", "flag_type": "피크스파이크",
         "detail": "peak 6190W (임계 1000W 초과)"},
        {"appliance": "에어컨", "mode": "냉방", "flag_type": "과소비",
         "detail": "energy 2520Wh (baseline 1200Wh의 2.1배)"},
        {"appliance": "김치냉장고", "mode": "가동", "flag_type": "피크스파이크",
         "detail": "peak 1240W (임계 1000W 초과)"},
        {"appliance": "전자레인지", "mode": "가열", "flag_type": "장시간",
         "detail": "duration 12min (baseline 4min × 2 초과)"},
    ]


def _build_mode_references() -> dict:
    return {
        "TV":         {"type": "D", "modes": {
            "시청": {"avg_energy_wh": 50, "avg_duration_min": 60, "sample_count": 8, "low_confidence": True},
        }},
        "에어컨":     {"type": "D", "modes": {
            "냉방": {"avg_energy_wh": 1200, "avg_duration_min": 90, "sample_count": 120, "low_confidence": False},
        }},
        "김치냉장고": {"type": "A", "modes": {
            "가동": {"avg_energy_wh": 25, "avg_duration_min": 3, "sample_count": 800, "low_confidence": False},
        }},
        "전자레인지": {"type": "C", "modes": {
            "가열": {"avg_energy_wh": 90, "avg_duration_min": 4, "sample_count": 60,
                     "low_confidence": False, "duration_threshold_min": 8},
        }},
    }


def _build_recent_events() -> list[dict]:
    return [
        {"appliance": "TV", "mode": "시청", "energy_wh": 6190, "duration_min": 60,
         "peak_w": 6190, "avg_w": 103, "started_at": "2026-05-15 20:00"},
        {"appliance": "에어컨", "mode": "냉방", "energy_wh": 2520, "duration_min": 180,
         "peak_w": 1450, "avg_w": 840, "started_at": "2026-05-15 14:00"},
        {"appliance": "에어컨", "mode": "냉방", "energy_wh": 2410, "duration_min": 175,
         "peak_w": 1430, "avg_w": 826, "started_at": "2026-05-14 15:30"},
        {"appliance": "김치냉장고", "mode": "가동", "energy_wh": 30, "duration_min": 2,
         "peak_w": 1240, "avg_w": 900, "started_at": "2026-05-15 11:20"},
        {"appliance": "김치냉장고", "mode": "가동", "energy_wh": 28, "duration_min": 2,
         "peak_w": 1210, "avg_w": 880, "started_at": "2026-05-15 09:45"},
        {"appliance": "전자레인지", "mode": "가열", "energy_wh": 250, "duration_min": 12,
         "peak_w": 1100, "avg_w": 1250, "started_at": "2026-05-15 19:10"},
    ]


def _build_state() -> dict:
    return {
        "household_id":      "H015",
        "household_profile": {
            "members": 3, "area_m2": 84,
            "appliances": ["TV", "에어컨", "김치냉장고", "전자레인지", "냉장고", "세탁기"],
        },
        "nilm_output": {
            "top_consumers": [
                {"appliance": "에어컨",     "daily_kwh": 5.04, "share_pct": 38.0},
                {"appliance": "TV",         "daily_kwh": 6.19, "share_pct": 46.7},
                {"appliance": "전자레인지", "daily_kwh": 0.50, "share_pct": 3.8},
                {"appliance": "김치냉장고", "daily_kwh": 0.95, "share_pct": 7.2},
            ],
            "peak_hours":      [14, 15, 20],
            "anomaly_flags":   _build_anomaly_flags(),
            "anomaly_events":  _build_anomaly_events(),
            "mode_references": _build_mode_references(),
            "recent_events":   _build_recent_events(),
        },
        "cashback_output": {
            "baseline_kwh": 280, "current_kwh": 320, "saving_kwh": -40,
            "estimated_cashback_krw": 0,
            "progressive_tariff": {
                "tier_rates_krw": [120, 215, 320],
                "current_tier": 2,
                "kwh_to_next_tier": 80,
            },
        },
        "weather_output": {
            "current_temp_c": 27.5, "humidity": 65,
            "forecast": [{"date": "2026-05-16", "high_c": 29, "low_c": 21}],
        },
        "rag_context": [],
    }


def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY 미설정")

    state = _build_state()
    result = report_node(state)["final_output"]

    print("=" * 70)
    print("진단 카테고리 분류 결과")
    print("=" * 70)
    for d in result.get("anomaly_diagnoses", []):
        print(f"\n[{d.get('category')}] event_id={d.get('event_id')} ({d.get('expected_savings_krw_per_month')}원/월)")
        print(f"  diagnosis: {d.get('diagnosis')}")
        print(f"  cause:     {d.get('cause')}")
        print(f"  action:    {d.get('action')}")

    print("\n" + "=" * 70)
    print("권고")
    print("=" * 70)
    for r in result.get("recommendations", []):
        print(f"\n- {r.get('title')}  |  {r.get('savings_krw'):,}원  ({r.get('savings_kwh')} kWh)")
        print(f"  {r.get('description')}")

    out_path = "resp_synthetic.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n→ saved: {out_path}")


if __name__ == "__main__":
    main()
