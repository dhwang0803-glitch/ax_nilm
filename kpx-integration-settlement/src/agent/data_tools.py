"""LLM Agent 데이터 조회 도구 — 전력 에너지 코치 (Tool-use 패턴).

Week 1: 3가구 mock 데이터로 구현. 실제 DB·NILM·KMA·KEPCO API 연결은 4주차 예정.

익명화 원칙:
  - 모든 도구는 household_id(익명화 토큰)만 입력받음
  - 반환값에 실명·실주소·전화번호 미포함
  - LLM(외부 API) 전달 전 개인 식별 정보 제거
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any

from . import ontology

logger = logging.getLogger(__name__)

# ─── Mock 데이터 ────────────────────────────────────────────────────────────────

_MOCK_PROFILES: dict[str, dict] = {
    "HH001": {
        "house_type": "아파트",
        "area_m2": 85,
        "floor": 24,
        "members": 4,
        "appliances": [
            {"name": "에어컨",   "energy_efficiency": 1,    "estimated_w": 1200},
            {"name": "냉장고",   "energy_efficiency": 2,    "estimated_w": 150},
            {"name": "세탁기",   "energy_efficiency": 3,    "estimated_w": 900},
            {"name": "TV",       "energy_efficiency": 1,    "estimated_w": 130},
            {"name": "전기밥솥", "energy_efficiency": None, "estimated_w": 700},
        ],
        "subscription": "주택용(저압) 누진 3단계",
    },
    "HH002": {
        "house_type": "빌라",
        "area_m2": 52,
        "floor": 2,
        "members": 2,
        "appliances": [
            {"name": "냉장고",     "energy_efficiency": 1,    "estimated_w": 120},
            {"name": "세탁기",     "energy_efficiency": 2,    "estimated_w": 850},
            {"name": "TV",         "energy_efficiency": 2,    "estimated_w": 100},
            {"name": "전자레인지", "energy_efficiency": None, "estimated_w": 1000},
        ],
        "subscription": "주택용(저압) 누진 1단계",
    },
    "HH003": {
        "house_type": "아파트",
        "area_m2": 115,
        "floor": 5,
        "members": 1,
        "appliances": [
            {"name": "에어컨",     "energy_efficiency": 2,    "estimated_w": 1000},
            {"name": "냉장고",     "energy_efficiency": 1,    "estimated_w": 140},
            {"name": "컴퓨터",     "energy_efficiency": None, "estimated_w": 400},
            {"name": "공기청정기", "energy_efficiency": 1,    "estimated_w": 50},
        ],
        "subscription": "주택용(저압) 누진 2단계",
    },
}

_MOCK_WEATHER_WEEKLY: dict[str, list[dict]] = {
    "서울": [
        {"date": "2026-04-21", "tavg": 17.5, "tmax": 23.1, "tmin": 12.3, "wind": 2.1, "rh": 55, "rain_mm": 0.0},
        {"date": "2026-04-22", "tavg": 19.2, "tmax": 25.4, "tmin": 14.1, "wind": 1.8, "rh": 50, "rain_mm": 0.0},
        {"date": "2026-04-23", "tavg": 16.8, "tmax": 21.3, "tmin": 11.5, "wind": 3.2, "rh": 60, "rain_mm": 2.5},
        {"date": "2026-04-24", "tavg": 15.4, "tmax": 19.8, "tmin": 10.2, "wind": 2.8, "rh": 65, "rain_mm": 0.0},
        {"date": "2026-04-25", "tavg": 18.1, "tmax": 23.5, "tmin": 12.8, "wind": 1.5, "rh": 52, "rain_mm": 0.0},
        {"date": "2026-04-26", "tavg": 20.3, "tmax": 26.1, "tmin": 15.2, "wind": 1.2, "rh": 48, "rain_mm": 0.0},
        {"date": "2026-04-27", "tavg": 21.1, "tmax": 27.3, "tmin": 16.4, "wind": 1.0, "rh": 45, "rain_mm": 0.0},
    ]
}

_MOCK_FORECAST: dict[str, list[dict]] = {
    "서울": [
        {"date": "2026-04-28", "tavg": 22.0, "tmax": 28.1, "tmin": 17.3, "wind": 1.3, "rh": 43, "rain_mm": 0.0},
        {"date": "2026-04-29", "tavg": 19.5, "tmax": 24.2, "tmin": 14.8, "wind": 2.5, "rh": 55, "rain_mm": 3.0},
        {"date": "2026-04-30", "tavg": 17.2, "tmax": 21.5, "tmin": 12.1, "wind": 3.0, "rh": 62, "rain_mm": 0.0},
        {"date": "2026-05-01", "tavg": 18.8, "tmax": 24.0, "tmin": 13.5, "wind": 2.2, "rh": 57, "rain_mm": 0.0},
        {"date": "2026-05-02", "tavg": 20.1, "tmax": 25.8, "tmin": 15.3, "wind": 1.8, "rh": 50, "rain_mm": 0.0},
        {"date": "2026-05-03", "tavg": 21.4, "tmax": 27.0, "tmin": 16.2, "wind": 1.5, "rh": 47, "rain_mm": 0.0},
        {"date": "2026-05-04", "tavg": 22.8, "tmax": 29.1, "tmin": 17.5, "wind": 1.1, "rh": 42, "rain_mm": 0.0},
    ]
}

_MOCK_CONSUMPTION_SUMMARY: dict[str, dict] = {
    "HH001": {
        "total_kwh": 92.3,
        "daily_avg_kwh": 13.2,
        "yoy_change_pct": 18.0,
        "peak_hours": [19, 20, 21],
        "peak_avg_w": 2100,
        "weekend_uplift_pct": 22.0,
    },
    "HH002": {
        "total_kwh": 43.5,
        "daily_avg_kwh": 6.2,
        "yoy_change_pct": -5.0,
        "peak_hours": [7, 8, 18],
        "peak_avg_w": 980,
        "weekend_uplift_pct": 5.0,
    },
    "HH003": {
        "total_kwh": 28.1,
        "daily_avg_kwh": 4.0,
        "yoy_change_pct": -12.0,
        "peak_hours": [0, 1, 2],
        "peak_avg_w": 420,
        "weekend_uplift_pct": -8.0,
    },
}

_MOCK_HOURLY: dict[str, list[dict]] = {
    "HH001": [
        {"hour": 0,  "kwh": 0.31}, {"hour": 1,  "kwh": 0.28}, {"hour": 2,  "kwh": 0.25},
        {"hour": 3,  "kwh": 0.24}, {"hour": 4,  "kwh": 0.23}, {"hour": 5,  "kwh": 0.27},
        {"hour": 6,  "kwh": 0.45}, {"hour": 7,  "kwh": 0.82}, {"hour": 8,  "kwh": 0.93},
        {"hour": 9,  "kwh": 0.71}, {"hour": 10, "kwh": 0.65}, {"hour": 11, "kwh": 0.68},
        {"hour": 12, "kwh": 0.90}, {"hour": 13, "kwh": 0.85}, {"hour": 14, "kwh": 0.78},
        {"hour": 15, "kwh": 0.72}, {"hour": 16, "kwh": 0.69}, {"hour": 17, "kwh": 0.88},
        {"hour": 18, "kwh": 1.45}, {"hour": 19, "kwh": 2.10}, {"hour": 20, "kwh": 2.15},
        {"hour": 21, "kwh": 2.08}, {"hour": 22, "kwh": 1.21}, {"hour": 23, "kwh": 0.45},
    ],
    "HH002": [
        {"hour": 0,  "kwh": 0.18}, {"hour": 1,  "kwh": 0.15}, {"hour": 2,  "kwh": 0.14},
        {"hour": 3,  "kwh": 0.13}, {"hour": 4,  "kwh": 0.13}, {"hour": 5,  "kwh": 0.15},
        {"hour": 6,  "kwh": 0.35}, {"hour": 7,  "kwh": 0.98}, {"hour": 8,  "kwh": 0.92},
        {"hour": 9,  "kwh": 0.42}, {"hour": 10, "kwh": 0.35}, {"hour": 11, "kwh": 0.38},
        {"hour": 12, "kwh": 0.55}, {"hour": 13, "kwh": 0.42}, {"hour": 14, "kwh": 0.38},
        {"hour": 15, "kwh": 0.35}, {"hour": 16, "kwh": 0.40}, {"hour": 17, "kwh": 0.45},
        {"hour": 18, "kwh": 0.88}, {"hour": 19, "kwh": 0.75}, {"hour": 20, "kwh": 0.65},
        {"hour": 21, "kwh": 0.52}, {"hour": 22, "kwh": 0.45}, {"hour": 23, "kwh": 0.28},
    ],
    "HH003": [
        {"hour": 0,  "kwh": 0.42}, {"hour": 1,  "kwh": 0.39}, {"hour": 2,  "kwh": 0.35},
        {"hour": 3,  "kwh": 0.22}, {"hour": 4,  "kwh": 0.18}, {"hour": 5,  "kwh": 0.15},
        {"hour": 6,  "kwh": 0.18}, {"hour": 7,  "kwh": 0.22}, {"hour": 8,  "kwh": 0.25},
        {"hour": 9,  "kwh": 0.20}, {"hour": 10, "kwh": 0.18}, {"hour": 11, "kwh": 0.19},
        {"hour": 12, "kwh": 0.21}, {"hour": 13, "kwh": 0.20}, {"hour": 14, "kwh": 0.19},
        {"hour": 15, "kwh": 0.18}, {"hour": 16, "kwh": 0.22}, {"hour": 17, "kwh": 0.25},
        {"hour": 18, "kwh": 0.28}, {"hour": 19, "kwh": 0.30}, {"hour": 20, "kwh": 0.32},
        {"hour": 21, "kwh": 0.28}, {"hour": 22, "kwh": 0.38}, {"hour": 23, "kwh": 0.40},
    ],
}

_MOCK_BREAKDOWN: dict[str, list[dict]] = {
    "HH001": [
        {
            "appliance": "에어컨", "kwh": 4.2, "share_pct": 35.0,
            "active_intervals": [{"start": "13:20", "end": "15:45"}, {"start": "19:10", "end": "22:00"}],
        },
        {
            "appliance": "냉장고", "kwh": 2.3, "share_pct": 19.2,
            "active_intervals": [{"start": "00:00", "end": "23:59"}],
        },
        {
            "appliance": "TV", "kwh": 1.1, "share_pct": 9.2,
            "active_intervals": [{"start": "18:30", "end": "23:00"}],
        },
        {
            "appliance": "전기밥솥", "kwh": 0.9, "share_pct": 7.5,
            "active_intervals": [
                {"start": "06:30", "end": "07:00"},
                {"start": "12:00", "end": "12:20"},
                {"start": "18:00", "end": "18:30"},
            ],
        },
        {
            "appliance": "세탁기", "kwh": 0.8, "share_pct": 6.7,
            "active_intervals": [{"start": "10:15", "end": "11:20"}],
        },
        {
            "appliance": "기타", "kwh": 2.65, "share_pct": 22.1,
            "active_intervals": [],
        },
    ],
    "HH002": [
        {
            "appliance": "냉장고", "kwh": 1.8, "share_pct": 42.9,
            "active_intervals": [{"start": "00:00", "end": "23:59"}],
        },
        {
            "appliance": "세탁기", "kwh": 0.7, "share_pct": 16.7,
            "active_intervals": [{"start": "07:20", "end": "08:15"}],
        },
        {
            "appliance": "전자레인지", "kwh": 0.4, "share_pct": 9.5,
            "active_intervals": [
                {"start": "07:10", "end": "07:15"},
                {"start": "12:30", "end": "12:35"},
                {"start": "18:50", "end": "18:55"},
            ],
        },
        {
            "appliance": "TV", "kwh": 0.4, "share_pct": 9.5,
            "active_intervals": [{"start": "18:30", "end": "22:00"}],
        },
        {
            "appliance": "기타", "kwh": 0.9, "share_pct": 21.4,
            "active_intervals": [],
        },
    ],
    "HH003": [
        {
            "appliance": "컴퓨터", "kwh": 1.8, "share_pct": 48.6,
            "active_intervals": [
                {"start": "22:00", "end": "02:30"},
                {"start": "14:00", "end": "16:00"},
            ],
        },
        {
            "appliance": "냉장고", "kwh": 1.0, "share_pct": 27.0,
            "active_intervals": [{"start": "00:00", "end": "23:59"}],
        },
        {
            "appliance": "공기청정기", "kwh": 0.5, "share_pct": 13.5,
            "active_intervals": [{"start": "00:00", "end": "23:59"}],
        },
        {
            "appliance": "기타", "kwh": 0.4, "share_pct": 10.8,
            "active_intervals": [],
        },
    ],
}

_MOCK_CASHBACK_HISTORY: dict[str, list[dict]] = {
    "HH001": [
        {
            "month": "2026-02",
            "baseline_kwh": 318.5,
            "actual_kwh": 285.2,
            "savings_pct": 10.5,
            "savings_kwh": 33.3,
            "cashback_krw": 3330,
            "cashback_rate_krw_per_kwh": 100,
            "status": "지급완료",
        },
        {
            "month": "2026-03",
            "baseline_kwh": 310.2,
            "actual_kwh": 295.8,
            "savings_pct": 4.6,
            "savings_kwh": 14.4,
            "cashback_krw": 1440,
            "cashback_rate_krw_per_kwh": 100,
            "status": "지급완료",
        },
        {
            "month": "2026-04",
            "baseline_kwh": 298.0,
            "actual_kwh": None,
            "savings_pct": None,
            "savings_kwh": None,
            "cashback_krw": None,
            "cashback_rate_krw_per_kwh": None,
            "status": "집계중",
        },
    ],
    "HH002": [
        {
            "month": "2026-02",
            "baseline_kwh": 152.3,
            "actual_kwh": 148.1,
            "savings_pct": 2.8,
            "savings_kwh": 4.2,
            "cashback_krw": 0,
            "cashback_rate_krw_per_kwh": 0,
            "status": "미달(3% 미만)",
        },
        {
            "month": "2026-03",
            "baseline_kwh": 148.0,
            "actual_kwh": 135.5,
            "savings_pct": 8.4,
            "savings_kwh": 12.5,
            "cashback_krw": 1250,
            "cashback_rate_krw_per_kwh": 100,
            "status": "지급완료",
        },
        {
            "month": "2026-04",
            "baseline_kwh": 145.0,
            "actual_kwh": None,
            "savings_pct": None,
            "savings_kwh": None,
            "cashback_krw": None,
            "cashback_rate_krw_per_kwh": None,
            "status": "집계중",
        },
    ],
    "HH003": [
        {
            "month": "2026-02",
            "baseline_kwh": 98.5,
            "actual_kwh": 82.3,
            "savings_pct": 16.5,
            "savings_kwh": 16.2,
            "cashback_krw": 1620,
            "cashback_rate_krw_per_kwh": 100,
            "status": "지급완료",
        },
        {
            "month": "2026-03",
            "baseline_kwh": 95.0,
            "actual_kwh": 78.8,
            "savings_pct": 17.1,
            "savings_kwh": 16.2,
            "cashback_krw": 1620,
            "cashback_rate_krw_per_kwh": 100,
            "status": "지급완료",
        },
        {
            "month": "2026-04",
            "baseline_kwh": 92.0,
            "actual_kwh": None,
            "savings_pct": None,
            "savings_kwh": None,
            "cashback_krw": None,
            "cashback_rate_krw_per_kwh": None,
            "status": "집계중",
        },
    ],
}

_MOCK_TARIFF: dict[str, dict] = {
    "HH001": {
        "plan": "주택용(저압) 누진요금제",
        "current_tier": 3,
        "current_month_kwh": 305,
        "tier_thresholds_kwh": [200, 400],
        "tier_rates_krw": [93.3, 187.9, 280.6],
        "kwh_to_next_tier": 95,
        "estimated_monthly_bill_krw": 85400,
    },
    "HH002": {
        "plan": "주택용(저압) 누진요금제",
        "current_tier": 1,
        "current_month_kwh": 142,
        "tier_thresholds_kwh": [200, 400],
        "tier_rates_krw": [93.3, 187.9, 280.6],
        "kwh_to_next_tier": 58,
        "estimated_monthly_bill_krw": 18200,
    },
    "HH003": {
        "plan": "주택용(저압) 누진요금제",
        "current_tier": 2,
        "current_month_kwh": 248,
        "tier_thresholds_kwh": [200, 400],
        "tier_rates_krw": [93.3, 187.9, 280.6],
        "kwh_to_next_tier": 152,
        "estimated_monthly_bill_krw": 28900,
    },
}

_MOCK_ANOMALY_EVENTS: dict[str, list[dict]] = {
    "HH001": [
        {
            "event_id": "ANO-HH001-001",
            "appliance": "에어컨",
            "severity": "warning",
            "type": "비정상 소비 패턴",
            "detected_at": "2026-04-29T09:15:00+09:00",
            "description": "평상시 대비 40% 높은 소비량 감지 — 필터 오염 또는 냉매 부족 의심",
            "confidence": 0.87,
            "model_version": "nilm-v2.1",
            "status": "active",
        },
        {
            "event_id": "ANO-HH001-002",
            "appliance": "냉장고",
            "severity": "info",
            "type": "장시간 고출력 가동",
            "detected_at": "2026-04-28T22:10:00+09:00",
            "description": "문 열림 지속 또는 온도 설정 확인 권고",
            "confidence": 0.72,
            "model_version": "nilm-v2.1",
            "status": "active",
        },
    ],
    "HH002": [],
    "HH003": [
        {
            "event_id": "ANO-HH003-001",
            "appliance": "컴퓨터",
            "severity": "info",
            "type": "대기전력 과다",
            "detected_at": "2026-04-29T03:30:00+09:00",
            "description": "03:00~05:00 대기 상태에서 평소보다 높은 소비량 감지",
            "confidence": 0.65,
            "model_version": "nilm-v2.1",
            "status": "active",
        },
    ],
}

_MOCK_ANOMALY_LOG: dict[str, list[dict]] = {
    "HH001": [
        {
            "event_id": "ANO-HH001-001",
            "appliance": "에어컨",
            "severity": "warning",
            "type": "비정상 소비 패턴",
            "detected_at": "2026-04-29T09:15:00+09:00",
            "resolved_at": None,
            "description": "평상시 대비 40% 높은 소비량 감지 — 필터 오염 또는 냉매 부족 의심",
            "confidence": 0.87,
            "model_version": "nilm-v2.1",
            "status": "active",
        },
        {
            "event_id": "ANO-HH001-002",
            "appliance": "냉장고",
            "severity": "info",
            "type": "장시간 고출력 가동",
            "detected_at": "2026-04-28T22:10:00+09:00",
            "resolved_at": None,
            "description": "문 열림 지속 또는 온도 설정 확인 권고",
            "confidence": 0.72,
            "model_version": "nilm-v2.1",
            "status": "active",
        },
        {
            "event_id": "ANO-HH001-003",
            "appliance": "세탁기",
            "severity": "warning",
            "type": "비정상 진동 패턴",
            "detected_at": "2026-04-20T14:25:00+09:00",
            "resolved_at": "2026-04-20T16:00:00+09:00",
            "description": "탈수 구간 전력 급등 후 정상화",
            "confidence": 0.81,
            "model_version": "nilm-v2.1",
            "status": "resolved",
        },
        {
            "event_id": "ANO-HH001-004",
            "appliance": "에어컨",
            "severity": "critical",
            "type": "이상 전력 급등",
            "detected_at": "2026-04-10T15:40:00+09:00",
            "resolved_at": "2026-04-10T15:55:00+09:00",
            "description": "순간 전력 급등(3.2kW) 후 자동 차단 및 재가동",
            "confidence": 0.94,
            "model_version": "nilm-v2.1",
            "status": "resolved",
        },
    ],
    "HH002": [
        {
            "event_id": "ANO-HH002-001",
            "appliance": "전자레인지",
            "severity": "info",
            "type": "대기전력 과다",
            "detected_at": "2026-04-15T23:00:00+09:00",
            "resolved_at": "2026-04-16T07:00:00+09:00",
            "description": "야간 대기전력 20W 지속 — 플러그 미제거",
            "confidence": 0.70,
            "model_version": "nilm-v2.1",
            "status": "resolved",
        },
    ],
    "HH003": [
        {
            "event_id": "ANO-HH003-001",
            "appliance": "컴퓨터",
            "severity": "info",
            "type": "대기전력 과다",
            "detected_at": "2026-04-29T03:30:00+09:00",
            "resolved_at": None,
            "description": "03:00~05:00 대기 상태에서 평소보다 높은 소비량 감지",
            "confidence": 0.65,
            "model_version": "nilm-v2.1",
            "status": "active",
        },
        {
            "event_id": "ANO-HH003-002",
            "appliance": "공기청정기",
            "severity": "info",
            "type": "필터 교체 권고",
            "detected_at": "2026-04-05T12:00:00+09:00",
            "resolved_at": "2026-04-07T09:00:00+09:00",
            "description": "소비전력 증가 추이로 필터 오염 의심",
            "confidence": 0.60,
            "model_version": "nilm-v2.1",
            "status": "resolved",
        },
    ],
}

def _build_synthetic_households(start: int = 4, end: int = 50) -> None:
    """HH004~HH050 합성 mock 데이터 생성 (seed = 가구번호 → 재현 가능)."""
    import random

    _APPLIANCE_POOL = [
        {"name": "에어컨",     "estimated_w": 1200, "eff": (1, 3)},
        {"name": "냉장고",     "estimated_w": 140,  "eff": (1, 3)},
        {"name": "세탁기",     "estimated_w": 900,  "eff": (1, 3)},
        {"name": "TV",         "estimated_w": 120,  "eff": (1, 3)},
        {"name": "전기밥솥",   "estimated_w": 700,  "eff": None},
        {"name": "전자레인지", "estimated_w": 1000, "eff": None},
        {"name": "컴퓨터",     "estimated_w": 400,  "eff": None},
        {"name": "공기청정기", "estimated_w": 50,   "eff": (1, 3)},
        {"name": "전기포트",   "estimated_w": 1500, "eff": None},
        {"name": "의류건조기", "estimated_w": 2000, "eff": (1, 3)},
        {"name": "식기세척기", "estimated_w": 1200, "eff": None},
        {"name": "인덕션",     "estimated_w": 1800, "eff": None},
        {"name": "전기장판",   "estimated_w": 200,  "eff": None},
        {"name": "김치냉장고", "estimated_w": 160,  "eff": (1, 3)},
        {"name": "선풍기",     "estimated_w": 50,   "eff": None},
    ]
    # TV와 컴퓨터는 동일한 "절전 모드·타이머" 권고를 받으므로 한 가구에 동시 존재 금지
    _EXCLUSIVE_GROUPS = [{"TV", "컴퓨터"}]
    _HOUSE_TYPES = ["아파트", "빌라", "단독주택", "오피스텔"]
    _AREAS       = [33, 40, 52, 59, 66, 75, 84, 99, 115, 132]
    _TYPES_ANOM  = [
        ("비정상 소비 패턴", "평상시 대비 {pct}% 높은 소비량 감지 — 필터 오염 또는 설정 이상 의심"),
        ("장시간 고출력 가동", "장시간 고출력 가동 감지 — 점검 권고"),
        ("대기전력 과다", "야간 대기전력 지속 — 플러그 미제거 또는 설정 확인"),
    ]

    for n in range(start, end + 1):
        hh = f"HH{n:03d}"
        rng = random.Random(n * 137)

        # ── 프로필 ──────────────────────────────────────────────────────
        n_app = rng.randint(4, 6)  # 최소 4개 → 권고 다양성 확보
        pool  = rng.sample(_APPLIANCE_POOL, n_app)
        if not any(a["name"] == "냉장고" for a in pool):
            pool[0] = next(a for a in _APPLIANCE_POOL if a["name"] == "냉장고")
        # 동일 권고 그룹(TV·컴퓨터)은 최대 1개만 유지
        for group in _EXCLUSIVE_GROUPS:
            members_in_pool = [a for a in pool if a["name"] in group]
            if len(members_in_pool) > 1:
                for dup in members_in_pool[1:]:
                    pool.remove(dup)
        appliances = [
            {
                "name": a["name"],
                "energy_efficiency": rng.randint(*a["eff"]) if a["eff"] else None,
                "estimated_w": a["estimated_w"],
            }
            for a in pool
        ]
        members = rng.randint(1, 5)
        tier    = rng.randint(1, 3)
        _MOCK_PROFILES[hh] = {
            "house_type":   rng.choice(_HOUSE_TYPES),
            "area_m2":      rng.choice(_AREAS),
            "floor":        rng.randint(1, 15),
            "members":      members,
            "appliances":   appliances,
            "subscription": f"주택용(저압) 누진 {tier}단계",
        }

        # ── 소비 요약 ────────────────────────────────────────────────────
        daily_kwh  = round(2.0 + members * 2.5 + _MOCK_PROFILES[hh]["area_m2"] * 0.04 + rng.uniform(-3, 3), 1)
        peak_hours = sorted(rng.sample(range(24), 3))
        _MOCK_CONSUMPTION_SUMMARY[hh] = {
            "total_kwh":          round(daily_kwh * 7, 1),
            "daily_avg_kwh":      daily_kwh,
            "yoy_change_pct":     round(rng.uniform(-15.0, 25.0), 1),
            "peak_hours":         peak_hours,
            "peak_avg_w":         int(daily_kwh * 1000 * rng.uniform(0.15, 0.25)),
            "weekend_uplift_pct": round(rng.uniform(-10.0, 30.0), 1),
        }

        # ── 시간대별 소비 ────────────────────────────────────────────────
        base = daily_kwh / 24
        hourly = []
        for h in range(24):
            if 0 <= h < 6:
                f = rng.uniform(0.3, 0.6)
            elif 6 <= h < 9:
                f = rng.uniform(1.2, 2.0)
            elif 9 <= h < 17:
                f = rng.uniform(0.6, 1.2)
            elif 17 <= h < 23:
                f = rng.uniform(1.5, 2.5)
            else:
                f = rng.uniform(0.5, 1.0)
            if h in peak_hours:
                f *= 1.4
            hourly.append({"hour": h, "kwh": round(base * f, 2)})
        _MOCK_HOURLY[hh] = hourly

        # ── 기기별 분해 ──────────────────────────────────────────────────
        breakdown  = []
        remaining  = daily_kwh
        for i, a in enumerate(appliances):
            share = rng.uniform(0.08, 0.35) if i < len(appliances) - 1 else rng.uniform(0.4, 0.7)
            kwh   = round(min(remaining * share, remaining - 0.05 * (len(appliances) - i - 1)), 2)
            remaining -= kwh
            intervals = (
                [{"start": "00:00", "end": "23:59"}]
                if a["name"] in ("냉장고", "김치냉장고", "공기청정기")
                else [{"start": f"{rng.randint(6,18):02d}:00", "end": f"{rng.randint(19,23):02d}:59"}]
            )
            breakdown.append({
                "appliance":        a["name"],
                "kwh":              max(kwh, 0.01),
                "share_pct":        round(max(kwh, 0.01) / daily_kwh * 100, 1),
                "active_intervals": intervals,
            })
        if remaining > 0.01:
            breakdown.append({
                "appliance": "기타", "kwh": round(remaining, 2),
                "share_pct": round(remaining / daily_kwh * 100, 1), "active_intervals": [],
            })
        _MOCK_BREAKDOWN[hh] = breakdown

        # ── 캐시백 이력 ──────────────────────────────────────────────────
        monthly_base = round(daily_kwh * 30 * rng.uniform(0.9, 1.15), 1)
        history = []
        for idx, mon in enumerate(["2026-02", "2026-03"]):
            base_m  = round(monthly_base * (1 - idx * 0.03), 1)
            sav_pct = round(rng.uniform(-2.0, 20.0), 1)
            actual  = round(base_m * (1 - sav_pct / 100), 1)
            sav_kwh = round(base_m - actual, 1)
            ok      = sav_pct >= 3.0
            history.append({
                "month":                    mon,
                "baseline_kwh":             base_m,
                "actual_kwh":               actual,
                "savings_pct":              sav_pct,
                "savings_kwh":              sav_kwh,
                "cashback_krw":             int(sav_kwh * 100) if ok else 0,
                "cashback_rate_krw_per_kwh": 100 if ok else 0,
                "status":                   "지급완료" if ok else "미달(3% 미만)",
            })
        history.append({
            "month": "2026-04", "baseline_kwh": round(monthly_base * 0.92, 1),
            "actual_kwh": None, "savings_pct": None, "savings_kwh": None,
            "cashback_krw": None, "cashback_rate_krw_per_kwh": None, "status": "집계중",
        })
        _MOCK_CASHBACK_HISTORY[hh] = history

        # ── 요금 정보 ────────────────────────────────────────────────────
        mon_kwh = int(daily_kwh * 30)
        if mon_kwh <= 200:
            ctier, nxt, bill = 1, 200 - mon_kwh, int(mon_kwh * 93.3)
        elif mon_kwh <= 400:
            ctier, nxt, bill = 2, 400 - mon_kwh, int(200 * 93.3 + (mon_kwh - 200) * 187.9)
        else:
            ctier, nxt, bill = 3, 0, int(200 * 93.3 + 200 * 187.9 + (mon_kwh - 400) * 280.6)
        _MOCK_TARIFF[hh] = {
            "plan":                    "주택용(저압) 누진요금제",
            "current_tier":            ctier,
            "current_month_kwh":       mon_kwh,
            "tier_thresholds_kwh":     [200, 400],
            "tier_rates_krw":          [93.3, 187.9, 280.6],
            "kwh_to_next_tier":        nxt,
            "estimated_monthly_bill_krw": bill,
        }

        # ── 이상 이벤트 ──────────────────────────────────────────────────
        top_app = breakdown[0]["appliance"]
        if rng.random() < 0.6:
            anom_type, anom_tmpl = rng.choice(_TYPES_ANOM)
            pct = rng.randint(20, 55)
            anom_desc = anom_tmpl.format(pct=pct)
            severity  = rng.choice(["info", "warning", "critical"])
            conf      = round(rng.uniform(0.60, 0.95), 2)
            ts        = f"2026-04-{rng.randint(10,29):02d}T{rng.randint(0,23):02d}:{rng.randint(0,59):02d}:00+09:00"
            status    = rng.choice(["active", "resolved"])
            # before/after kW: after = before × (1 + pct/100) → 항상 after > before
            before_kw = round(rng.uniform(0.8, 2.0), 1)
            after_kw  = round(before_kw * (1 + pct / 100), 1)
            event = {
                "event_id":     f"ANO-{hh}-001",
                "appliance":    top_app,
                "severity":     severity,
                "type":         anom_type,
                "detected_at":  ts,
                "description":  anom_desc,
                "before_kw":    before_kw,
                "after_kw":     after_kw,
                "confidence":   conf,
                "model_version": "nilm-v2.1",
                "status":       status,
            }
            _MOCK_ANOMALY_EVENTS[hh] = [event]
            _MOCK_ANOMALY_LOG[hh]    = [{**event, "resolved_at": None}]
        else:
            _MOCK_ANOMALY_EVENTS[hh] = []
            _MOCK_ANOMALY_LOG[hh]    = []


_build_synthetic_households()

_KNOWN_HOUSEHOLDS       = set(_MOCK_PROFILES.keys())
_KNOWN_LOCATIONS        = set(_MOCK_WEATHER_WEEKLY.keys())
_KNOWN_CASHBACK_HH      = set(_MOCK_CASHBACK_HISTORY.keys())


# ─── DB 구현체 ──────────────────────────────────────────────────────────────────

def _get_db_conn():
    """psycopg2 연결 반환. DB_PASSWORD 미설정 시 None (mock fallback 트리거)."""
    pw = os.getenv("DB_PASSWORD")
    if not pw:
        return None
    try:
        import psycopg2
        return psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5436")),
            dbname=os.getenv("DB_NAME", "ax_nilm"),
            user=os.getenv("DB_USER", "ax_nilm_team"),
            password=pw,
            connect_timeout=5,
        )
    except Exception:
        return None


def _db_household_profile(conn, household_id: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT house_type, residential_type, residential_area, co_lighting, cluster_label, dr_enrolled"
            " FROM households WHERE household_id = %s",
            (household_id,),
        )
        row = cur.fetchone()
    if not row:
        conn.close()
        return {"error": f"household_id not found: {household_id}", "code": "E_NOT_FOUND"}
    house_type, res_type, area, co_lighting, cluster, dr_enrolled = row

    with conn.cursor() as cur:
        cur.execute(
            "SELECT channel_num, device_name, brand, power_consumption, energy_efficiency"
            " FROM household_channels WHERE household_id = %s ORDER BY channel_num",
            (household_id,),
        )
        channels = cur.fetchall()
    conn.close()

    appliances = [
        {
            "name": ch[1] or f"ch{ch[0]:02d}",
            "brand": ch[2],
            "estimated_w": ch[3],
            "energy_efficiency": ch[4],
        }
        for ch in channels
    ]
    app_parts = [
        f"{a['name']}{' ' + str(a['energy_efficiency']) + '등급' if a['energy_efficiency'] else ''}"
        for a in appliances[:6]
    ]
    plan = "주택용(저압) 누진요금제"
    summary = (
        f"{area or '?'} {house_type or '?'}, {res_type or '?'}, {plan}. "
        f"주요 가전: {', '.join(app_parts)}"
    )
    return {
        "summary": summary,
        "raw": {
            "house_type":       house_type,
            "residential_type": res_type,
            "residential_area": area,
            "co_lighting":      co_lighting,
            "cluster_label":    cluster,
            "dr_enrolled":      dr_enrolled,
            "appliances":       appliances,
            "subscription":     plan,
        },
    }


def _db_consumption_summary(conn, household_id: str, period: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(hour_bucket) FROM power_1hour WHERE household_id = %s", (household_id,))
        max_ts = cur.fetchone()[0]
    if not max_ts:
        conn.close()
        return {"error": f"소비 데이터 없음: {household_id}", "code": "E_NO_DATA"}

    days = {"today": 1, "week": 7, "month": 30}.get(period, 7)
    start_dt = max_ts - timedelta(days=days)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                ROUND(SUM(energy_wh)::numeric / 1000.0, 2) AS total_kwh,
                COUNT(DISTINCT DATE(hour_bucket AT TIME ZONE 'Asia/Seoul')) AS day_count,
                ROUND(AVG(active_power_avg)::numeric, 0) AS avg_w
            FROM power_1hour
            WHERE household_id = %s AND channel_num = 1
              AND hour_bucket BETWEEN %s AND %s
            """,
            (household_id, start_dt, max_ts),
        )
        agg = cur.fetchone()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXTRACT(HOUR FROM hour_bucket AT TIME ZONE 'Asia/Seoul') AS h,
                   SUM(energy_wh) AS wh
            FROM power_1hour
            WHERE household_id = %s AND channel_num = 1
              AND hour_bucket BETWEEN %s AND %s
            GROUP BY h ORDER BY wh DESC LIMIT 3
            """,
            (household_id, start_dt, max_ts),
        )
        peak_rows = cur.fetchall()
    conn.close()

    total_kwh  = float(agg[0] or 0) if agg else 0.0
    day_count  = int(agg[1] or 1) if agg else 1
    avg_w      = float(agg[2] or 0) if agg else 0.0
    peak_hours = sorted([int(r[0]) for r in peak_rows])
    daily_avg  = round(total_kwh / day_count, 2)
    peak_str   = (
        f"{peak_hours[0]}~{peak_hours[-1]}시"
        if len(peak_hours) > 1
        else (f"{peak_hours[0]}시" if peak_hours else "N/A")
    )
    summary = (
        f"직전 {days}일({max_ts.strftime('%Y-%m-%d')} 기준) 총 {total_kwh}kWh, "
        f"일 평균 {daily_avg}kWh. 피크 {peak_str} 평균 {avg_w:.0f}W."
    )
    return {
        "summary": summary,
        "raw": {
            "total_kwh":     total_kwh,
            "daily_avg_kwh": daily_avg,
            "peak_hours":    peak_hours,
            "peak_avg_w":    avg_w,
            "data_end":      max_ts.strftime("%Y-%m-%d"),
            "period_days":   days,
        },
    }


def _db_hourly_breakdown(conn, household_id: str, date: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DATE(hour_bucket AT TIME ZONE 'Asia/Seoul') AS d,
                   ABS(DATE(hour_bucket AT TIME ZONE 'Asia/Seoul') - %s::date) AS diff
            FROM power_1hour WHERE household_id = %s
            ORDER BY diff LIMIT 1
            """,
            (date, household_id),
        )
        row = cur.fetchone()
    if not row:
        conn.close()
        return {"error": f"데이터 없음: {household_id}", "code": "E_NO_DATA"}
    actual_date = row[0]

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                EXTRACT(HOUR FROM p.hour_bucket AT TIME ZONE 'Asia/Seoul') AS hour,
                COALESCE(hc.device_name, 'ch' || LPAD(p.channel_num::text, 2, '0')) AS device,
                ROUND((p.energy_wh / 1000.0)::numeric, 3) AS kwh
            FROM power_1hour p
            LEFT JOIN household_channels hc
                ON hc.household_id = p.household_id AND hc.channel_num = p.channel_num
            WHERE p.household_id = %s
              AND DATE(p.hour_bucket AT TIME ZONE 'Asia/Seoul') = %s
            ORDER BY hour, kwh DESC
            """,
            (household_id, actual_date),
        )
        rows = cur.fetchall()

    devices_set: set[str] = set()
    by_hour: dict[int, dict[str, float]] = {}
    for hour, device, kwh in rows:
        h = int(hour)
        by_hour.setdefault(h, {})[device] = float(kwh)
        devices_set.add(device)

    appliances = sorted(devices_set)
    result = [
        {"hour": h, **{app: by_hour.get(h, {}).get(app, 0.0) for app in appliances}}
        for h in range(24)
    ]

    totals: dict[str, float] = {}
    for hdata in by_hour.values():
        for app, kwh in hdata.items():
            totals[app] = totals.get(app, 0.0) + kwh
    grand_total = sum(totals.values()) or 1.0

    # 전주 동일 날짜 채널별 합산 (week-over-week 계산용)
    prev_date = actual_date - timedelta(days=7)
    prev_totals: dict[str, float] = {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(hc.device_name, 'ch' || LPAD(p.channel_num::text, 2, '0')) AS device,
                       ROUND(SUM(p.energy_wh / 1000.0)::numeric, 3) AS kwh
                FROM power_1hour p
                LEFT JOIN household_channels hc
                    ON hc.household_id = p.household_id AND hc.channel_num = p.channel_num
                WHERE p.household_id = %s
                  AND DATE(p.hour_bucket AT TIME ZONE 'Asia/Seoul') = %s
                GROUP BY device
                """,
                (household_id, prev_date),
            )
            for dev, kwh in cur.fetchall():
                prev_totals[dev] = float(kwh)
    except Exception as e:
        logger.warning("_db_hourly_breakdown prev-week query failed: %s", e)
    finally:
        conn.close()

    def _wow(app: str, cur_kwh: float) -> float | None:
        prev = prev_totals.get(app)
        if prev and prev > 0:
            return round((cur_kwh - prev) / prev * 100, 1)
        return None

    daily_summary = [
        {
            "appliance": app,
            "daily_kwh": round(kwh, 3),
            "share_pct": round(kwh / grand_total * 100, 1),
            "operating_hours": [],
            "week_over_week_pct": _wow(app, kwh),
        }
        for app, kwh in sorted(totals.items(), key=lambda x: -x[1])
    ]

    top3 = daily_summary[:3]
    top3_str = ", ".join(
        f"{a['appliance']} {a['daily_kwh']}kWh({a['share_pct']:.0f}%)" for a in top3
    )
    date_note = f"(요청: {date}→실측: {actual_date})" if str(actual_date) != date else ""
    summary = (
        f"{actual_date} 채널별 시간대 분해 (채널 {len(appliances)}종){date_note}. "
        f"일일 상위: {top3_str}"
    )
    return {"summary": summary, "raw": result, "appliances": appliances, "daily_summary": daily_summary}


def _db_weather(conn, date_range: list[str], location: str) -> dict[str, Any]:
    start, end = date_range[0][:10], date_range[1][:10]
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT observed_date,
                   ROUND(AVG(temperature_c)::numeric, 1) AS tavg,
                   ROUND(AVG(wind_speed_ms)::numeric, 1) AS wind,
                   ROUND(AVG(humidity_pct)::numeric, 0)  AS rh
            FROM household_daily_env
            WHERE observed_date BETWEEN %s::date AND %s::date
            GROUP BY observed_date ORDER BY observed_date
            """,
            (start, end),
        )
        rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"error": f"날씨 데이터 없음: {start}~{end}", "code": "E_NO_DATA"}

    records = [
        {"date": str(r[0]), "tavg": float(r[1] or 0), "wind": float(r[2] or 0), "rh": float(r[3] or 0)}
        for r in rows
    ]
    avg_t = sum(r["tavg"] for r in records) / len(records)
    summary = f"{start}~{end} {location} 평균 {avg_t:.1f}°C"
    return {"summary": summary, "raw": records}


def _db_forecast(conn, days_ahead: int, location: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT observed_date,
                   ROUND(AVG(temperature_c)::numeric, 1) AS tavg,
                   ROUND(AVG(wind_speed_ms)::numeric, 1) AS wind,
                   ROUND(AVG(humidity_pct)::numeric, 0)  AS rh
            FROM household_daily_env
            WHERE observed_date >= CURRENT_DATE
            GROUP BY observed_date ORDER BY observed_date
            LIMIT %s
            """,
            (days_ahead,),
        )
        rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"error": f"예보 데이터 없음: {location}", "code": "E_NO_DATA"}

    records = [
        {"date": str(r[0]), "tavg": float(r[1] or 0), "wind": float(r[2] or 0), "rh": float(r[3] or 0)}
        for r in rows
    ]
    avg_t   = sum(r["tavg"] for r in records) / len(records)
    summary = f"{records[0]['date']}~{records[-1]['date']} {location} 예상 평균 {avg_t:.1f}°C"
    return {"summary": summary, "raw": records}


def _db_anomaly_events(conn, household_id: str, status: str) -> dict[str, Any]:
    """appliance_status_intervals → 이상 탐지 이벤트 변환.

    'active' = end_ts IS NULL, 'all' = 전체. confidence 구간으로 severity 매핑:
    >= 0.85 → warning, < 0.85 → info (현재 anomaly_events 전용 테이블 미생성 시 heuristic).
    """
    status_filter = "AND asi.end_ts IS NULL" if status == "active" else ""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                asi.id,
                COALESCE(hc.device_name, 'ch' || LPAD(asi.channel_num::text, 2, '0')) AS device,
                asc_.label_ko AS status_label,
                asi.confidence,
                asi.model_version,
                asi.start_ts,
                asi.end_ts,
                asi.created_at
            FROM appliance_status_intervals asi
            LEFT JOIN household_channels hc
                ON hc.household_id = asi.household_id AND hc.channel_num = asi.channel_num
            LEFT JOIN appliance_status_codes asc_
                ON asc_.status_code = asi.status_code
            WHERE asi.household_id = %s
              AND asi.confidence >= 0.6
              {status_filter}
            ORDER BY asi.created_at DESC
            LIMIT 50
            """,
            (household_id,),
        )
        rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"summary": "현재 활성 이상 이벤트 없음", "raw": [], "count": 0}

    events = []
    for row in rows:
        rid, device, label, conf, model_v, start_ts, end_ts, created_at = row
        severity = "warning" if (conf or 0) >= 0.85 else "info"
        ev_status = "active" if end_ts is None else "resolved"
        events.append({
            "event_id":     f"ASI-{household_id}-{rid}",
            "appliance":    device,
            "severity":     severity,
            "type":         label or "상태 감지",
            "detected_at":  start_ts.isoformat() if start_ts else None,
            "description":  f"NILM 모델 감지 (신뢰도 {conf:.2f})" if conf else "신뢰도 정보 없음",
            "confidence":   float(conf) if conf else None,
            "model_version": model_v,
            "status":       ev_status,
        })

    criticals = [e for e in events if e["severity"] == "critical"]
    warnings   = [e for e in events if e["severity"] == "warning"]
    severity_prefix = f"긴급 {len(criticals)}건 포함, " if criticals else ""
    summary = (
        f"이상 이벤트 {len(events)}건 ({severity_prefix}경고 {len(warnings)}건). "
        f"주요: {events[0]['appliance']} — {events[0]['type']}"
    )
    return {"summary": summary, "raw": events, "count": len(events)}


def _db_anomaly_log(
    conn, household_id: str,
    date_range: list[str] | None,
    severity: str,
    appliance: str | None,
) -> dict[str, Any]:
    """appliance_status_intervals → 이상 탐지 이력 로그 (필터 지원)."""
    conditions = ["asi.household_id = %s", "asi.confidence >= 0.6"]
    params: list = [household_id]

    if date_range:
        conditions.append("asi.start_ts >= %s::timestamptz")
        conditions.append("asi.start_ts <= %s::timestamptz + INTERVAL '1 day'")
        params += [date_range[0][:10], date_range[1][:10]]
    if severity != "all":
        # 심각도 기준: warning >= 0.85, info < 0.85
        if severity == "warning":
            conditions.append("asi.confidence >= 0.85")
        elif severity == "info":
            conditions.append("asi.confidence < 0.85")
    if appliance:
        conditions.append("hc.device_name ILIKE %s")
        params.append(f"%{appliance}%")

    where = " AND ".join(conditions)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                asi.id,
                COALESCE(hc.device_name, 'ch' || LPAD(asi.channel_num::text, 2, '0')) AS device,
                asc_.label_ko AS status_label,
                asi.confidence,
                asi.model_version,
                asi.start_ts,
                asi.end_ts
            FROM appliance_status_intervals asi
            LEFT JOIN household_channels hc
                ON hc.household_id = asi.household_id AND hc.channel_num = asi.channel_num
            LEFT JOIN appliance_status_codes asc_
                ON asc_.status_code = asi.status_code
            WHERE {where}
            ORDER BY asi.start_ts DESC
            LIMIT 200
            """,
            params,
        )
        rows = cur.fetchall()
    conn.close()

    records = []
    for row in rows:
        rid, device, label, conf, model_v, start_ts, end_ts = row
        ev_severity = "warning" if (conf or 0) >= 0.85 else "info"
        ev_status   = "active" if end_ts is None else "resolved"
        records.append({
            "event_id":      f"ASI-{household_id}-{rid}",
            "appliance":     device,
            "severity":      ev_severity,
            "type":          label or "상태 감지",
            "detected_at":   start_ts.isoformat() if start_ts else None,
            "resolved_at":   end_ts.isoformat() if end_ts else None,
            "description":   f"NILM 모델 감지 (신뢰도 {conf:.2f})" if conf else "신뢰도 정보 없음",
            "confidence":    float(conf) if conf else None,
            "model_version": model_v,
            "status":        ev_status,
        })

    resolved = sum(1 for r in records if r["status"] == "resolved")
    summary = f"이상 탐지 로그 {len(records)}건 (해결됨 {resolved}건, 활성 {len(records) - resolved}건)"
    return {"summary": summary, "raw": records, "total": len(records)}


def _db_consumption_hourly(conn, household_id: str, date: str) -> dict[str, Any]:
    """power_1hour ch01 기준 24시간 총 소비량 (가전 분해 없음)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXTRACT(HOUR FROM hour_bucket AT TIME ZONE 'Asia/Seoul') AS h,
                   ROUND((energy_wh / 1000.0)::numeric, 3) AS kwh
            FROM power_1hour
            WHERE household_id = %s AND channel_num = 1
              AND DATE(hour_bucket AT TIME ZONE 'Asia/Seoul') = %s::date
            ORDER BY h
            """,
            (household_id, date),
        )
        rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"error": f"데이터 없음: {household_id} {date}", "code": "E_NO_DATA"}

    hourly = [{"hour": int(r[0]), "kwh": float(r[1] or 0)} for r in rows]
    # 누락 시간대 0으로 채우기
    hour_map = {r["hour"]: r["kwh"] for r in hourly}
    full = [{"hour": h, "kwh": hour_map.get(h, 0.0)} for h in range(24)]
    total = round(sum(r["kwh"] for r in full), 2)
    return {
        "summary": f"{date} 시간대별 총 소비량 {total}kWh (24시간).",
        "raw": full,
    }


def _db_consumption_breakdown(conn, household_id: str, date: str) -> dict[str, Any]:
    """power_1hour 채널별 일일 합산 → 가전 분해 (share_pct 포함)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                p.channel_num,
                COALESCE(hc.device_name, 'ch' || LPAD(p.channel_num::text, 2, '0')) AS device,
                ROUND(SUM(p.energy_wh / 1000.0)::numeric, 3) AS kwh
            FROM power_1hour p
            LEFT JOIN household_channels hc
                ON hc.household_id = p.household_id AND hc.channel_num = p.channel_num
            WHERE p.household_id = %s
              AND p.channel_num != 1
              AND DATE(p.hour_bucket AT TIME ZONE 'Asia/Seoul') = %s::date
            GROUP BY p.channel_num, device
            ORDER BY kwh DESC
            """,
            (household_id, date),
        )
        rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"error": f"데이터 없음: {household_id} {date}", "code": "E_NO_DATA"}

    grand = sum(float(r[2] or 0) for r in rows) or 1.0
    breakdown = [
        {
            "appliance":        r[1],
            "kwh":              float(r[2] or 0),
            "share_pct":        round(float(r[2] or 0) / grand * 100, 1),
            "active_intervals": [],
        }
        for r in rows
    ]
    top = breakdown[:3]
    top_str = ", ".join(f"{a['appliance']} {a['kwh']}kWh" for a in top)
    summary = f"{date} 가전 분해 ({len(breakdown)}종). 상위 소비: {top_str}"
    return {"summary": summary, "raw": breakdown}


_TIER_THRESHOLDS = [200, 400]
_TIER_RATES      = [93.3, 187.9, 280.6]
_BASE_CHARGES    = [910, 1600, 7300]


def _db_tariff_info(conn, household_id: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(hour_bucket) FROM power_1hour WHERE household_id = %s", (household_id,))
        max_ts = cur.fetchone()[0]
    if not max_ts:
        conn.close()
        return {"error": f"소비 데이터 없음: {household_id}", "code": "E_NO_DATA"}

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ROUND(SUM(energy_wh)::numeric / 1000.0, 0)
            FROM power_1hour
            WHERE household_id = %s AND channel_num = 1
              AND DATE_TRUNC('month', hour_bucket AT TIME ZONE 'Asia/Seoul')
                  = DATE_TRUNC('month', %s AT TIME ZONE 'Asia/Seoul')
            """,
            (household_id, max_ts),
        )
        kwh_val = cur.fetchone()[0]
    conn.close()

    mtd = int(kwh_val or 0)
    if mtd <= 200:
        tier = 1
        bill = _BASE_CHARGES[0] + mtd * _TIER_RATES[0]
        to_next = 200 - mtd
    elif mtd <= 400:
        tier = 2
        bill = _BASE_CHARGES[1] + 200 * _TIER_RATES[0] + (mtd - 200) * _TIER_RATES[1]
        to_next = 400 - mtd
    else:
        tier = 3
        bill = _BASE_CHARGES[2] + 200 * _TIER_RATES[0] + 200 * _TIER_RATES[1] + (mtd - 400) * _TIER_RATES[2]
        to_next = 0

    bill_krw = round(bill)
    plan = "주택용(저압) 누진요금제"
    return {
        "summary": (
            f"{plan}, 현재 {tier}단계 ({mtd}kWh 사용). "
            f"{'다음 단계까지 ' + str(to_next) + 'kWh 남음. ' if to_next else ''}"
            f"예상 {bill_krw:,}원."
        ),
        "raw": {
            "plan":                       plan,
            "current_tier":               tier,
            "current_month_kwh":          mtd,
            "tier_thresholds_kwh":        _TIER_THRESHOLDS,
            "tier_rates_krw":             _TIER_RATES,
            "kwh_to_next_tier":           to_next,
            "estimated_monthly_bill_krw": bill_krw,
        },
    }


def _db_cashback_history(conn, household_id: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                DATE_TRUNC('month', hour_bucket AT TIME ZONE 'Asia/Seoul') AS month,
                ROUND(SUM(energy_wh)::numeric / 1000.0, 1) AS total_kwh
            FROM power_1hour
            WHERE household_id = %s AND channel_num = 1
            GROUP BY month ORDER BY month
            """,
            (household_id,),
        )
        rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"error": f"소비 데이터 없음: {household_id}", "code": "E_NO_DATA"}

    kwh_list = [(r[0], float(r[1] or 0)) for r in rows]
    records: list[dict] = []
    for i, (month_dt, actual_kwh) in enumerate(kwh_list):
        month_str = month_dt.strftime("%Y-%m")
        prior = [kwh for _, kwh in kwh_list[max(0, i - 12) : i]]
        baseline_kwh = round(sum(prior) / len(prior), 1) if len(prior) >= 2 else None

        if baseline_kwh:
            savings_kwh = round(baseline_kwh - actual_kwh, 1)
            savings_pct = round(savings_kwh / baseline_kwh * 100, 1)
            qualifies   = savings_pct >= 3.0 and savings_kwh > 0
            rate        = 100
            cb_krw      = round(savings_kwh * rate) if qualifies else 0
            status      = "지급완료" if qualifies else "미달(3% 미만)"
        else:
            savings_kwh = None
            savings_pct = None
            cb_krw      = None
            rate        = None
            status      = "집계중"

        records.append({
            "month":                     month_str,
            "baseline_kwh":              baseline_kwh,
            "actual_kwh":                actual_kwh,
            "savings_pct":               savings_pct,
            "savings_kwh":               savings_kwh,
            "cashback_krw":              cb_krw,
            "cashback_rate_krw_per_kwh": rate,
            "status":                    status,
        })

    paid      = [r for r in records if r["status"] == "지급완료"]
    total_kwh = sum(r["savings_kwh"] for r in paid if r["savings_kwh"])
    total_krw = sum(r["cashback_krw"] for r in paid if r["cashback_krw"])
    summary   = (
        f"캐시백 이력 {len(records)}개월: 지급완료 {len(paid)}개월, "
        f"누적 절감 {total_kwh:.1f}kWh, 누적 캐시백 {total_krw:,}원"
    )
    return {"summary": summary, "raw": records}


def _db_dashboard_summary(household_id: str) -> dict[str, Any]:
    conn = _get_db_conn()
    if not conn:
        return {
            "summary": "DB 연결 없음",
            "raw": {
                "month": "", "monthly_kwh_so_far": 0, "baseline_kwh": None,
                "cashback_qualifies": False, "cashback_expected_krw": 0,
                "notification_count": 0, "cashback_detail": {},
            },
        }

    # 단일 연결로 월별 전력 합계 전체 조회 (연결 실패 이중화 방지)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                DATE_TRUNC('month', hour_bucket AT TIME ZONE 'Asia/Seoul') AS month,
                ROUND(SUM(energy_wh)::numeric / 1000.0, 1) AS total_kwh
            FROM power_1hour
            WHERE household_id = %s AND channel_num = 1
            GROUP BY month ORDER BY month
            """,
            (household_id,),
        )
        rows = cur.fetchall()
    conn.close()

    if not rows:
        return {
            "summary": f"소비 데이터 없음: {household_id}",
            "raw": {
                "month": "", "monthly_kwh_so_far": 0, "baseline_kwh": None,
                "cashback_qualifies": False, "cashback_expected_krw": 0,
                "notification_count": 0, "cashback_detail": {},
            },
        }

    kwh_list = [(r[0].strftime("%Y-%m"), float(r[1] or 0)) for r in rows]
    max_month_str = kwh_list[-1][0]
    mtd_kwh       = kwh_list[-1][1]

    # 현재 데이터 월 기준으로 직전 최대 12개월 평균 → baseline
    prior = [kwh for _, kwh in kwh_list[max(0, len(kwh_list) - 13) : len(kwh_list) - 1]]
    baseline = round(sum(prior) / len(prior), 1) if len(prior) >= 1 else None

    import sys
    print(
        f"[dashboard_debug] hh={household_id} months={len(kwh_list)} "
        f"max_month={max_month_str} mtd={mtd_kwh} prior_months={len(prior)} "
        f"baseline={baseline}",
        file=sys.stderr, flush=True,
    )

    # 현재 달(오늘 월)이면 부분 월 투영, 이전 완성 월이면 그대로 사용
    today = date.today()
    if baseline and mtd_kwh > 0:
        if max_month_str == today.strftime("%Y-%m"):
            elapsed_days  = max(1, today.day)
            projected_kwh = round(mtd_kwh / elapsed_days * 30, 1)
        else:
            projected_kwh = mtd_kwh
        savings_kwh = round(baseline - projected_kwh, 1)
    elif baseline:
        projected_kwh = baseline
        savings_kwh   = 0.0
    else:
        projected_kwh = mtd_kwh
        savings_kwh   = 0.0

    savings_pct = round(savings_kwh / baseline * 100, 1) if baseline else 0.0
    qualifies   = savings_pct >= 3.0 and savings_kwh > 0

    # 온톨로지 기반 단가
    cb_rate = ontology.cashback_fallback_rate()
    for threshold, rate in ontology.cashback_tiers():
        if (savings_pct / 100) >= threshold:
            cb_rate = rate
            break
    exp_krw = round(savings_kwh * cb_rate) if qualifies else 0

    cashback_detail = {
        "baseline_kwh":           baseline,
        "projected_kwh":          projected_kwh,
        "savings_kwh":            max(savings_kwh, 0.0),
        "savings_pct":            max(savings_pct, 0.0),
        "qualifies_for_cashback": qualifies,
        "expected_cashback_krw":  exp_krw,
    }
    summary = (
        f"이달 사용량 {mtd_kwh}kWh (예상 {projected_kwh}kWh). "
        f"캐시백 {'예상 ' + f'{exp_krw:,}원' if qualifies else '미달 전망'}."
    )
    return {
        "summary": summary,
        "raw": {
            "month":                 max_month_str,
            "monthly_kwh_so_far":    mtd_kwh,
            "baseline_kwh":          baseline,
            "cashback_qualifies":    qualifies,
            "cashback_expected_krw": exp_krw,
            "notification_count":    0,
            "cashback_detail":       cashback_detail,
        },
    }


# ─── Tool 함수 ──────────────────────────────────────────────────────────────────

def get_household_profile(household_id: str) -> dict[str, Any]:
    """가구 기본 정보(면적, 가구원 수, 가전 목록, 요금제) 조회."""
    conn = _get_db_conn()
    if conn:
        return _db_household_profile(conn, household_id)
    # mock fallback
    if household_id not in _KNOWN_HOUSEHOLDS:
        return {"error": f"household_id not found: {household_id}", "code": "E_NOT_FOUND"}
    p = _MOCK_PROFILES[household_id]
    app_parts = []
    for a in p["appliances"]:
        label = a["name"]
        if a["energy_efficiency"] is not None:
            label += f" {a['energy_efficiency']}등급"
        app_parts.append(label)
    summary = (
        f"{p['area_m2']}㎡ {p['house_type']}, {p['members']}인 가구, "
        f"{p['subscription']}. 주요 가전: {', '.join(app_parts)}"
    )
    return {"summary": summary, "raw": p}


def get_weather(date_range: list[str], location: str = "서울") -> dict[str, Any]:
    """과거 날씨 데이터(기온, 강수, 습도) 조회."""
    conn = _get_db_conn()
    if conn:
        return _db_weather(conn, list(date_range), location)
    # mock fallback
    loc      = location if location in _KNOWN_LOCATIONS else "서울"
    records  = _MOCK_WEATHER_WEEKLY.get(loc, [])
    start, end = date_range[0], date_range[1]
    filtered = [r for r in records if start <= r["date"] <= end]
    if not filtered:
        return {"error": f"날씨 데이터 없음: {start}~{end}, {loc}", "code": "E_NO_DATA"}
    avg_t      = sum(r["tavg"] for r in filtered) / len(filtered)
    total_rain = sum(r["rain_mm"] for r in filtered)
    summary    = f"{start}~{end} {loc} 평균 {avg_t:.1f}°C(평년 +2.1°C), 강수 {total_rain:.1f}mm"
    return {"summary": summary, "raw": filtered}


def get_forecast(days_ahead: int = 7, location: str = "서울") -> dict[str, Any]:
    """향후 N일간 날씨 예보(기온, 강수) 조회."""
    loc  = location if location in _KNOWN_LOCATIONS else "서울"
    conn = _get_db_conn()
    if conn:
        result = _db_forecast(conn, days_ahead, loc)
        if "error" not in result:
            return result
    # mock fallback
    records = _MOCK_FORECAST.get(loc, [])[:days_ahead]
    if not records:
        return {"error": f"예보 데이터 없음: {loc}", "code": "E_NO_DATA"}
    avg_t   = sum(r["tavg"] for r in records) / len(records)
    summary = f"{records[0]['date']}~{records[-1]['date']} {loc} 예상 평균 {avg_t:.1f}°C"
    return {"summary": summary, "raw": records}


def get_consumption_summary(household_id: str, period: str = "week") -> dict[str, Any]:
    """전력 소비 요약(총량, 일평균, 전년 대비, 피크 시간대) 조회."""
    conn = _get_db_conn()
    if conn:
        return _db_consumption_summary(conn, household_id, period)
    # mock fallback
    if household_id not in _KNOWN_HOUSEHOLDS:
        return {"error": f"household_id not found: {household_id}", "code": "E_NOT_FOUND"}
    raw      = _MOCK_CONSUMPTION_SUMMARY[household_id]
    yoy_sign = "+" if raw["yoy_change_pct"] >= 0 else ""
    peak_str = f"{raw['peak_hours'][0]}~{raw['peak_hours'][-1]}시"
    wknd_sign = "+" if raw["weekend_uplift_pct"] >= 0 else ""
    summary  = (
        f"직전 7일 총 {raw['total_kwh']}kWh, 일 평균 {raw['daily_avg_kwh']}kWh, "
        f"전년 동기 대비 {yoy_sign}{raw['yoy_change_pct']}%. "
        f"피크 {peak_str} 평균 {raw['peak_avg_w']}W. "
        f"주말 {wknd_sign}{raw['weekend_uplift_pct']}%."
    )
    return {"summary": summary, "raw": raw}




def get_cashback_history(
    household_id: str,
    date_range: list[str] | None = None,
) -> dict[str, Any]:
    """에너지캐시백 월별 절감 실적·캐시백 지급 내역 조회.

    직전 2개년 동월 평균 대비 3% 이상 절감 시 KEPCO가 30~100원/kWh 지급.
    date_range가 없으면 전체 이력 반환.
    """
    conn = _get_db_conn()
    if conn:
        return _db_cashback_history(conn, household_id)
    # mock fallback
    if household_id not in _KNOWN_CASHBACK_HH:
        return {"error": f"household_id not found: {household_id}", "code": "E_NOT_FOUND"}
    records = _MOCK_CASHBACK_HISTORY[household_id]
    if date_range:
        start, end = date_range[0][:7], date_range[1][:7]  # YYYY-MM 비교
        records = [r for r in records if start <= r["month"] <= end]
    if not records:
        return {"summary": "조회 기간 내 캐시백 이력 없음", "raw": []}
    paid   = [r for r in records if r["status"] == "지급완료"]
    total_kwh = sum(r["savings_kwh"] for r in paid if r["savings_kwh"])
    total_krw = sum(r["cashback_krw"] for r in paid if r["cashback_krw"])
    summary = (
        f"캐시백 이력 {len(records)}개월: 지급완료 {len(paid)}개월, "
        f"누적 절감 {total_kwh:.1f}kWh, 누적 캐시백 {total_krw:,}원"
    )
    return {"summary": summary, "raw": records}


def get_tariff_info(household_id: str) -> dict[str, Any]:
    """현재 요금제·누진 단계·다음 단계까지 남은 kWh·예상 청구액 조회."""
    conn = _get_db_conn()
    if conn:
        return _db_tariff_info(conn, household_id)
    # mock fallback
    if household_id not in _KNOWN_HOUSEHOLDS:
        return {"error": f"household_id not found: {household_id}", "code": "E_NOT_FOUND"}
    t = _MOCK_TARIFF[household_id]
    summary = (
        f"{t['plan']}, 현재 {t['current_tier']}단계 ({t['current_month_kwh']}kWh 사용). "
        f"다음 단계까지 {t['kwh_to_next_tier']}kWh 남음. "
        f"이번 달 예상 청구액 {t['estimated_monthly_bill_krw']:,}원."
    )
    return {"summary": summary, "raw": t}


def _calc_cashback_potential(
    household_id: str,
    reference_month: str = "2026-04",
) -> dict[str, Any]:
    """캐시백 수령 가능 여부·예상 금액 내부 계산 (LLM 미노출 private 함수).

    tariff month-to-date 사용량을 기반으로 월말 예상 총 소비를 추산하고
    baseline 대비 3% 절감 충족 여부를 판단한다.
    """
    # DB가 연결되어 있으면 실 데이터 사용
    cb_data    = get_cashback_history(household_id)
    tariff_data = get_tariff_info(household_id)
    if "error" in cb_data or "error" in tariff_data:
        if household_id not in _KNOWN_HOUSEHOLDS:
            return {"error": f"household_id not found: {household_id}", "code": "E_NOT_FOUND"}
        cb_data    = {"raw": _MOCK_CASHBACK_HISTORY.get(household_id, [])}
        tariff_data = {"raw": _MOCK_TARIFF.get(household_id, {})}

    history = cb_data.get("raw", [])
    rec = next((r for r in history if r.get("month", "") == reference_month), None)
    if rec is None or rec.get("status") != "집계중":
        return {"error": f"{reference_month} 집계중 데이터 없음", "code": "E_NO_CURRENT"}

    baseline_kwh = rec["baseline_kwh"]
    if baseline_kwh is None:
        return {"error": f"{reference_month} 기준선 미설정", "code": "E_NO_BASELINE"}

    mtd_kwh      = tariff_data.get("raw", {}).get("current_month_kwh", 0)

    from datetime import date as _date
    today          = _date.today()
    _DAYS_ELAPSED  = today.day
    _DAYS_IN_MONTH = 30

    daily_pace    = round(mtd_kwh / _DAYS_ELAPSED, 1)
    projected_kwh = round(mtd_kwh / _DAYS_ELAPSED * _DAYS_IN_MONTH, 1)
    savings_kwh   = round(baseline_kwh - projected_kwh, 1)
    savings_pct   = round(savings_kwh / baseline_kwh * 100, 1)
    qualifies     = savings_pct >= 3.0
    target_kwh    = round(baseline_kwh * 0.97, 1)
    remaining     = _DAYS_IN_MONTH - _DAYS_ELAPSED

    if qualifies:
        expected_krw = round(savings_kwh * 100)  # mock rate: 100원/kWh
        summary = (
            f"현재 페이스(일 {daily_pace}kWh) 기준 예상 {projected_kwh}kWh. "
            f"기준 {baseline_kwh}kWh 대비 {savings_pct}% 절감 → 캐시백 수령 가능. "
            f"예상 캐시백: 약 {expected_krw:,}원."
        )
    else:
        expected_krw = 0
        if mtd_kwh >= target_kwh:
            gap_note = f"이미 기준치({baseline_kwh}kWh)를 초과해 이번 달 캐시백 수령 불가."
        else:
            budget   = round(target_kwh - mtd_kwh, 1)
            daily_tg = round(budget / remaining, 1) if remaining > 0 else 0
            gap_note = (
                f"3% 목표({target_kwh}kWh) 달성하려면 "
                f"남은 {remaining}일간 일 {daily_tg}kWh 이하 유지 필요."
            )
        summary = (
            f"현재 페이스(일 {daily_pace}kWh) 기준 예상 {projected_kwh}kWh. "
            f"기준 {baseline_kwh}kWh 대비 {abs(savings_pct)}% 초과 전망. {gap_note}"
        )

    return {
        "summary": summary,
        "raw": {
            "reference_month":        reference_month,
            "baseline_kwh":           baseline_kwh,
            "mtd_kwh":                mtd_kwh,
            "days_elapsed":           _DAYS_ELAPSED,
            "daily_pace_kwh":         daily_pace,
            "projected_kwh":          projected_kwh,
            "savings_kwh":            savings_kwh,
            "savings_pct":            savings_pct,
            "qualifies_for_cashback": qualifies,
            "expected_cashback_krw":  expected_krw,
            "target_kwh_for_3pct":    target_kwh,
            "remaining_days":         remaining,
        },
    }


def estimate_cashback_potential(
    household_id: str,
    reference_month: str = "2026-04",
) -> dict[str, Any]:
    """캐시백 수령 가능 여부·예상 금액 공개 도구 (LLM 노출용).

    내부 계산은 _calc_cashback_potential 위임. 월말 예상 소비량을 기준 대비 비교해
    3% 절감 달성 여부와 예상 캐시백 금액을 반환한다.
    """
    return _calc_cashback_potential(household_id, reference_month)


def get_consumption_hourly(
    household_id: str,
    date: str = "2026-04-27",
) -> dict[str, Any]:
    """24시간 총 전력 소비량 시계열 조회 (가전 분해 없음).

    raw: [{"hour": 0~23, "kwh": float}, ...] 24개 행.
    """
    conn = _get_db_conn()
    if conn and household_id not in _KNOWN_HOUSEHOLDS:
        return _db_consumption_hourly(conn, household_id, date)
    # mock fallback
    if household_id not in _KNOWN_HOUSEHOLDS:
        return {"error": f"household_id not found: {household_id}", "code": "E_NOT_FOUND"}

    hourly = _MOCK_HOURLY.get(household_id, [])
    total  = round(sum(r["kwh"] for r in hourly), 2)
    summary = f"{date} 시간대별 총 소비량 {total}kWh (24시간)."
    return {
        "summary": summary,
        "raw": [{"hour": r["hour"], "kwh": r["kwh"]} for r in hourly],
    }


def get_consumption_breakdown(
    household_id: str,
    date: str = "2026-04-27",
) -> dict[str, Any]:
    """가전별 전력 소비 분해 결과 조회 (power_1hour 채널별 기반).

    raw: [{"appliance": str, "kwh": float, "share_pct": float, "active_intervals": list}]
    """
    conn = _get_db_conn()
    if conn:
        return _db_consumption_breakdown(conn, household_id, date)
    # mock fallback
    if household_id not in _KNOWN_HOUSEHOLDS:
        return {"error": f"household_id not found: {household_id}", "code": "E_NOT_FOUND"}

    breakdown = _MOCK_BREAKDOWN.get(household_id, [])
    top = sorted(breakdown, key=lambda x: x["kwh"], reverse=True)[:3]
    top_str = ", ".join(f"{a['appliance']} {a['kwh']}kWh" for a in top)
    summary = f"{date} 가전 분해 ({len(breakdown)}종). 상위 소비: {top_str}"
    return {
        "summary": summary,
        "raw": [
            {
                "appliance":        a["appliance"],
                "kwh":              a["kwh"],
                "share_pct":        a["share_pct"],
                "active_intervals": a.get("operating_hours", []),
            }
            for a in breakdown
        ],
    }


def get_dashboard_summary(household_id: str, month: str = "2026-04") -> dict[str, Any]:
    """대시보드 요약 — 월간 사용량·캐시백 추정·미확인 알림 수 한 번에 조회.

    /home 화면 첫 진입 시 사용. 내부적으로 tariff, cashback_history, anomaly_events를 집계.
    """
    conn = _get_db_conn()
    if conn:
        return _db_dashboard_summary(household_id)
    # mock fallback
    if household_id not in _KNOWN_HOUSEHOLDS:
        return {"error": f"household_id not found: {household_id}", "code": "E_NOT_FOUND"}

    tariff    = _MOCK_TARIFF[household_id]
    mtd_kwh   = tariff["current_month_kwh"]

    history   = _MOCK_CASHBACK_HISTORY.get(household_id, [])
    rec       = next((r for r in history if r["month"] == month), None)
    baseline  = rec["baseline_kwh"] if rec else None

    cb_est       = _calc_cashback_potential(household_id, month)
    cb_raw       = cb_est.get("raw", {})
    qualifies    = cb_raw.get("qualifies_for_cashback", False)
    exp_krw      = cb_raw.get("expected_cashback_krw", 0)
    cashback_str = f"예상 {exp_krw:,}원" if qualifies else "미달 전망"

    active_count = sum(
        1 for e in _MOCK_ANOMALY_EVENTS.get(household_id, []) if e["status"] == "active"
    )

    summary = (
        f"{month} 이달 사용량 {mtd_kwh}kWh (28일 기준). "
        f"캐시백 {cashback_str}. 미확인 알림 {active_count}건."
    )
    return {
        "summary": summary,
        "raw": {
            "month":                  month,
            "monthly_kwh_so_far":     mtd_kwh,
            "baseline_kwh":           baseline,
            "cashback_qualifies":     qualifies,
            "cashback_expected_krw":  exp_krw,
            "notification_count":     active_count,
            "cashback_detail":        cb_raw,
        },
    }


def get_anomaly_events(household_id: str, status: str = "active") -> dict[str, Any]:
    """실시간 이상 탐지 이벤트 조회 (appliance_status_intervals 기반).

    /insights 화면 — 모델 신뢰도·가전별 이상 유형·LLM 절약 권고 컨텍스트 제공.
    status: 'active' | 'all'
    """
    conn = _get_db_conn()
    if conn and household_id not in _KNOWN_HOUSEHOLDS:
        return _db_anomaly_events(conn, household_id, status)
    # mock fallback
    if household_id not in _KNOWN_HOUSEHOLDS:
        return {"error": f"household_id not found: {household_id}", "code": "E_NOT_FOUND"}

    events = _MOCK_ANOMALY_EVENTS.get(household_id, [])
    if status == "active":
        events = [e for e in events if e["status"] == "active"]

    if not events:
        return {"summary": "현재 활성 이상 이벤트 없음", "raw": [], "count": 0}

    criticals = [e for e in events if e["severity"] == "critical"]
    warnings  = [e for e in events if e["severity"] == "warning"]
    severity_prefix = f"긴급 {len(criticals)}건 포함, " if criticals else ""
    summary = (
        f"이상 이벤트 {len(events)}건 ({severity_prefix}경고 {len(warnings)}건). "
        f"주요: {events[0]['appliance']} — {events[0]['type']}"
    )
    return {"summary": summary, "raw": events, "count": len(events)}


def get_anomaly_log(
    household_id: str,
    date_range: list[str] | None = None,
    severity: str = "all",
    appliance: str | None = None,
) -> dict[str, Any]:
    """이상 탐지 로그 조회 — /settings/anomaly-log 화면용.

    date_range: [YYYY-MM-DD, YYYY-MM-DD] 기간 필터 (생략 시 전체)
    severity: 'all' | 'info' | 'warning' | 'critical'
    appliance: 가전명 필터 (생략 시 전체)
    """
    conn = _get_db_conn()
    if conn:
        return _db_anomaly_log(conn, household_id, list(date_range) if date_range else None, severity, appliance)
    # mock fallback
    if household_id not in _KNOWN_HOUSEHOLDS:
        return {"error": f"household_id not found: {household_id}", "code": "E_NOT_FOUND"}

    records = list(_MOCK_ANOMALY_LOG.get(household_id, []))

    if date_range:
        start, end = date_range[0][:10], date_range[1][:10]
        records = [r for r in records if start <= r["detected_at"][:10] <= end]
    if severity != "all":
        records = [r for r in records if r["severity"] == severity]
    if appliance:
        records = [r for r in records if r["appliance"] == appliance]

    resolved = sum(1 for r in records if r["status"] == "resolved")
    summary  = (
        f"이상 탐지 로그 {len(records)}건 (해결됨 {resolved}건, 활성 {len(records) - resolved}건)"
    )
    return {"summary": summary, "raw": records, "total": len(records)}


def get_hourly_appliance_breakdown(household_id: str, date: str = "2026-04-27") -> dict[str, Any]:
    """24시간 × 가전별 전력 소비 행렬 + 일일 가전 요약 조회.

    raw: 24시간 × 가전별 kWh (Recharts 스택 차트용).
    daily_summary: 가전별 일일 총량·점유율·가동 시간대 (NILM 분해 결과).
    4주차 appliance_status_intervals 연결 후 실측치로 교체 예정.
    """
    conn = _get_db_conn()
    if conn and household_id not in _KNOWN_HOUSEHOLDS:
        return _db_hourly_breakdown(conn, household_id, date)
    # mock fallback
    if household_id not in _KNOWN_HOUSEHOLDS:
        return {"error": f"household_id not found: {household_id}", "code": "E_NOT_FOUND"}

    hourly     = _MOCK_HOURLY[household_id]
    breakdown  = _MOCK_BREAKDOWN[household_id]
    appliances = [a["appliance"] for a in breakdown]
    shares     = {a["appliance"]: a["share_pct"] / 100.0 for a in breakdown}

    result = []
    for h in hourly:
        row: dict[str, Any] = {"hour": h["hour"]}
        for app, share in shares.items():
            row[app] = round(h["kwh"] * share, 3)
        result.append(row)

    daily_summary = [
        {
            "appliance":       a["appliance"],
            "daily_kwh":       a["kwh"],
            "share_pct":       a["share_pct"],
            "operating_hours": a.get("operating_hours", []),
        }
        for a in breakdown
    ]

    top3     = sorted(breakdown, key=lambda x: x["kwh"], reverse=True)[:3]
    top3_str = ", ".join(f"{a['appliance']} {a['kwh']}kWh({a['share_pct']:.0f}%)" for a in top3)
    summary  = f"{date} 시간대별 가전 분해 (가전 {len(appliances)}종, 24시간). 일일 상위: {top3_str}"
    return {"summary": summary, "raw": result, "appliances": appliances, "daily_summary": daily_summary}


# ─── NILM 모드 레퍼런스 / 최근 이벤트 (GCS → DB → mock 폴백) ────────────────────

def get_nilm_mode_references(household_id: str) -> dict[str, Any]:
    """가전별 모드 레퍼런스(baseline) 조회 — GCS long_term → DB → mock 순 폴백.

    각 가전의 정상 운전 모드별 평균 에너지·지속시간·대기전력 기준값.
    Agent가 현재 소비와 비교해 이상 여부를 판단하는 데 사용.
    """
    from . import gcs_memory

    gcs_data = gcs_memory.get_long_term(household_id)
    if gcs_data:
        appliances = list(gcs_data.keys()) if isinstance(gcs_data, dict) else []
        modes_count = sum(
            len(v.get("modes", {})) for v in gcs_data.values()
        ) if isinstance(gcs_data, dict) else 0
        summary = f"가전 {len(appliances)}종, 모드 {modes_count}개 레퍼런스 로드 (GCS)"
        return {"summary": summary, "raw": gcs_data, "source": "gcs"}

    conn = _get_db_conn()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT r.appliance_code, t.type_name_ko, r.mode_name,
                       r.avg_energy_wh, r.avg_duration_min, r.sample_count,
                       r.standby_avg_w, r.standby_avg_duration_min
                FROM appliance_mode_references r
                JOIN appliance_types t ON t.appliance_code = r.appliance_code
                WHERE r.household_id = %s
                ORDER BY r.appliance_code, r.mode_name
                """,
                (household_id,),
            )
            rows = cur.fetchall()
            if rows:
                result: dict[str, dict] = {}
                for code, name_ko, mode, energy, dur, cnt, sb_w, sb_dur in rows:
                    if name_ko not in result:
                        result[name_ko] = {"appliance": name_ko, "appliance_code": code, "modes": {}}
                    result[name_ko]["modes"][mode] = {
                        "avg_energy_wh": float(energy) if energy else None,
                        "avg_duration_min": float(dur) if dur else None,
                        "sample_count": cnt,
                        "standby_avg_w": float(sb_w) if sb_w else None,
                        "standby_avg_duration_min": float(sb_dur) if sb_dur else None,
                    }
                appliances = list(result.keys())
                modes_count = sum(len(v["modes"]) for v in result.values())
                summary = f"가전 {len(appliances)}종, 모드 {modes_count}개 레퍼런스 로드 (DB)"
                return {"summary": summary, "raw": result, "source": "db"}
        except Exception as e:
            logger.warning("get_nilm_mode_references DB fallback: %s", e)
        finally:
            conn.close()

    return {
        "summary": f"모드 레퍼런스 없음 (household_id={household_id})",
        "raw": {},
        "source": "none",
    }


def get_nilm_recent_events(household_id: str, limit: int = 50) -> dict[str, Any]:
    """최근 NILM 이벤트 로그 조회 — GCS short_term → DB → mock 순 폴백.

    상태 모니터링 모델이 감지한 최근 가전 사용 이벤트 목록.
    Agent가 baseline(long_term)과 비교해 비정상 패턴을 진단하는 데 사용.
    """
    from . import gcs_memory

    gcs_data = gcs_memory.get_short_term(household_id)
    if gcs_data and isinstance(gcs_data, list):
        events = gcs_data[:limit]
        appliances = list({e.get("appliance", "unknown") for e in events})
        summary = (
            f"최근 이벤트 {len(events)}건 (가전 {len(appliances)}종: "
            f"{', '.join(appliances[:5])}). (GCS)"
        )
        return {"summary": summary, "raw": events, "count": len(events), "source": "gcs"}

    conn = _get_db_conn()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT si.start_ts, si.end_ts,
                       t.type_name_ko AS appliance,
                       sc.label_ko AS mode,
                       si.energy_wh, si.avg_w, si.peak_w,
                       si.confidence, si.model_version
                FROM appliance_status_intervals si
                JOIN household_channels hc
                    ON hc.household_id = si.household_id
                   AND hc.channel_num = si.channel_num
                JOIN appliance_types t ON t.appliance_code = hc.appliance_code
                JOIN appliance_status_codes sc ON sc.status_code = si.status_code
                WHERE si.household_id = %s
                ORDER BY si.start_ts DESC
                LIMIT %s
                """,
                (household_id, limit),
            )
            rows = cur.fetchall()
            if rows:
                events = []
                for start, end, appl, mode, energy, avg, peak, conf, ver in rows:
                    events.append({
                        "appliance": appl,
                        "mode": mode,
                        "started_at": start.isoformat() if start else None,
                        "ended_at": end.isoformat() if end else None,
                        "energy_wh": float(energy) if energy else None,
                        "avg_w": float(avg) if avg else None,
                        "peak_w": float(peak) if peak else None,
                        "confidence": float(conf) if conf else None,
                    })
                appliances = list({e["appliance"] for e in events})
                summary = (
                    f"최근 이벤트 {len(events)}건 (가전 {len(appliances)}종: "
                    f"{', '.join(appliances[:5])}). (DB)"
                )
                return {"summary": summary, "raw": events, "count": len(events), "source": "db"}
        except Exception as e:
            logger.warning("get_nilm_recent_events DB fallback: %s", e)
        finally:
            conn.close()

    return {
        "summary": f"최근 이벤트 없음 (household_id={household_id})",
        "raw": [],
        "count": 0,
        "source": "none",
    }


# ─── OpenAI function calling 스키마 ─────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_household_profile",
            "description": "가구 기본 정보(면적, 가구원 수, 가전 목록, 요금제)를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "household_id": {
                        "type": "string",
                        "description": "익명화된 가구 식별자 (예: HH001)",
                    }
                },
                "required": ["household_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "지정 기간의 과거 날씨 데이터(기온, 강수, 습도)를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_range": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "날짜 범위 [시작일, 종료일] (YYYY-MM-DD 형식)",
                    },
                    "location": {
                        "type": "string",
                        "description": "지역명 (예: 서울)",
                        "default": "서울",
                    },
                },
                "required": ["date_range"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_forecast",
            "description": "향후 N일간 날씨 예보(기온, 강수)를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "예보 일수 (기본값 7)",
                        "default": 7,
                    },
                    "location": {
                        "type": "string",
                        "description": "지역명 (예: 서울)",
                        "default": "서울",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_consumption_summary",
            "description": "가구의 전력 소비 요약(총량, 일평균, 전년 대비, 피크 시간대)을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "household_id": {
                        "type": "string",
                        "description": "익명화된 가구 식별자",
                    },
                    "period": {
                        "type": "string",
                        "description": "조회 기간: 'today' | 'week' | 'month' | 'YYYY-MM-DD/YYYY-MM-DD'",
                        "default": "week",
                    },
                },
                "required": ["household_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cashback_history",
            "description": "에너지캐시백 월별 절감 실적과 캐시백 지급 내역을 조회합니다. 직전 2개년 동월 평균 대비 3% 이상 절감 시 KEPCO가 지급합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "household_id": {
                        "type": "string",
                        "description": "익명화된 가구 식별자 (예: HH001)",
                    },
                    "date_range": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "조회 기간 [시작월, 종료월] (YYYY-MM-DD 형식). 생략 시 전체 이력 반환.",
                    },
                },
                "required": ["household_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tariff_info",
            "description": "현재 요금제, 누진 단계, 다음 단계까지 남은 kWh, 예상 청구액을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "household_id": {
                        "type": "string",
                        "description": "익명화된 가구 식별자",
                    }
                },
                "required": ["household_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dashboard_summary",
            "description": (
                "대시보드(/home) 요약을 조회합니다. 월간 사용량, 캐시백 추정, 미확인 알림 수를 "
                "한 번에 반환합니다. '오늘 현황 알려줘', '이번 달 얼마나 썼어?' 같은 질문에 사용합니다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "household_id": {
                        "type": "string",
                        "description": "익명화된 가구 식별자 (예: HH001)",
                    },
                    "month": {
                        "type": "string",
                        "description": "조회 월 (YYYY-MM 형식, 기본값: 2026-04)",
                        "default": "2026-04",
                    },
                },
                "required": ["household_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_anomaly_events",
            "description": (
                "실시간 이상 탐지 이벤트를 조회합니다 (appliance_status_intervals 기반). "
                "/insights AI 진단 화면용 — 모델 신뢰도, 가전별 이상 유형, LLM 절약 권고 컨텍스트."
                "'어떤 가전이 이상해?', '에어컨 왜 이상한 거야?', '지금 이상 있는 거 있어?' 질문에 사용합니다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "household_id": {
                        "type": "string",
                        "description": "익명화된 가구 식별자",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["active", "all"],
                        "description": "이벤트 상태 필터: 'active'(진행 중) | 'all'(전체)",
                        "default": "active",
                    },
                },
                "required": ["household_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_anomaly_log",
            "description": (
                "이상 탐지 이력 로그를 조회합니다. /settings/anomaly-log 화면용 — "
                "날짜·심각도·가전별 필터를 지원합니다. "
                "'지난달 이상 있었어?', '세탁기 이상 기록 보여줘' 같은 과거 이력 질문에 사용합니다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "household_id": {
                        "type": "string",
                        "description": "익명화된 가구 식별자",
                    },
                    "date_range": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "조회 기간 [시작일, 종료일] (YYYY-MM-DD). 생략 시 전체.",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["all", "info", "warning", "critical"],
                        "description": "심각도 필터 (기본값: 'all')",
                        "default": "all",
                    },
                    "appliance": {
                        "type": "string",
                        "description": "가전명 필터 (예: '에어컨'). 생략 시 전체.",
                    },
                },
                "required": ["household_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hourly_appliance_breakdown",
            "description": (
                "24시간 × 가전별 전력 소비 행렬과 NILM 분해 일일 요약을 함께 조회합니다. "
                "raw: Recharts 스택 차트(/usage)용 시간대별 데이터. "
                "daily_summary: 가전별 일일 총량·점유율·가동 시간대(operating_hours). "
                "'시간대별로 어떤 가전이 얼마나 썼어?', '에어컨 몇 시에 많이 돌아갔어?', "
                "'어떤 가전이 전기 제일 많이 써?', '에어컨 몇 시간 가동됐어?' 질문에 사용합니다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "household_id": {
                        "type": "string",
                        "description": "익명화된 가구 식별자",
                    },
                    "date": {
                        "type": "string",
                        "description": "조회 날짜 (YYYY-MM-DD 형식)",
                        "default": "2026-04-27",
                    },
                },
                "required": ["household_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_nilm_mode_references",
            "description": (
                "가전별 모드 레퍼런스(baseline)를 조회합니다. "
                "각 가전의 정상 운전 모드별 평균 에너지·지속시간·대기전력 기준값을 반환합니다. "
                "현재 소비와 비교해 이상 여부를 판단할 때 사용합니다. "
                "'에어컨 정상 소비량이 얼마야?', '세탁기 모드별 기준이 뭐야?' 질문에 사용합니다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "household_id": {
                        "type": "string",
                        "description": "익명화된 가구 식별자",
                    },
                },
                "required": ["household_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_nilm_recent_events",
            "description": (
                "NILM 상태 모니터링 모델이 감지한 최근 가전 사용 이벤트를 조회합니다. "
                "가전별 모드·에너지·지속시간을 포함하며, baseline 대비 비정상 패턴을 진단할 때 사용합니다. "
                "'최근에 어떤 가전이 작동했어?', '에어컨 최근 사용 패턴 보여줘' 질문에 사용합니다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "household_id": {
                        "type": "string",
                        "description": "익명화된 가구 식별자",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "조회할 최근 이벤트 수 (기본값 50)",
                        "default": 50,
                    },
                },
                "required": ["household_id"],
            },
        },
    },
]
