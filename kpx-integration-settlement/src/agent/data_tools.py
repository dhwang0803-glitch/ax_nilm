"""LLM Agent 데이터 조회 도구 — 전력 에너지 코치 (Tool-use 패턴).

Week 1: 3가구 mock 데이터로 구현. 실제 DB·NILM·KMA·KEPCO API 연결은 4주차 예정.

익명화 원칙:
  - 모든 도구는 household_id(익명화 토큰)만 입력받음
  - 반환값에 실명·실주소·전화번호 미포함
  - LLM(외부 API) 전달 전 개인 식별 정보 제거
"""
from __future__ import annotations

from typing import Any

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

_MOCK_DR_EVENTS: dict[str, list[dict]] = {
    "서울": [
        {
            "event_id": "DR-2026-042-001",
            "date": "2026-04-22",
            "start_time": "14:00",
            "end_time": "16:00",
            "type": "감축요청",
            "target_reduction_pct": 15,
            "incentive_krw_per_kwh": 800,
            "status": "완료",
        },
        {
            "event_id": "DR-2026-042-002",
            "date": "2026-04-27",
            "start_time": "18:00",
            "end_time": "20:00",
            "type": "감축요청",
            "target_reduction_pct": 20,
            "incentive_krw_per_kwh": 1000,
            "status": "완료",
        },
        {
            "event_id": "DR-2026-042-003",
            "date": "2026-04-29",
            "start_time": "13:00",
            "end_time": "15:00",
            "type": "감축요청",
            "target_reduction_pct": 15,
            "incentive_krw_per_kwh": 800,
            "status": "예정",
        },
    ]
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

_KNOWN_HOUSEHOLDS = set(_MOCK_PROFILES.keys())
_KNOWN_LOCATIONS  = set(_MOCK_WEATHER_WEEKLY.keys())


# ─── Tool 함수 ──────────────────────────────────────────────────────────────────

def get_household_profile(household_id: str) -> dict[str, Any]:
    """가구 기본 정보(면적, 가구원 수, 가전 목록, 요금제) 조회."""
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


def get_weather(date_range: tuple[str, str] | list[str], location: str = "서울") -> dict[str, Any]:
    """과거 날씨 데이터(기온, 강수, 습도) 조회."""
    loc     = location if location in _KNOWN_LOCATIONS else "서울"
    records = _MOCK_WEATHER_WEEKLY.get(loc, [])
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
    loc     = location if location in _KNOWN_LOCATIONS else "서울"
    records = _MOCK_FORECAST.get(loc, [])[:days_ahead]
    if not records:
        return {"error": f"예보 데이터 없음: {loc}", "code": "E_NO_DATA"}
    avg_t   = sum(r["tavg"] for r in records) / len(records)
    summary = f"{records[0]['date']}~{records[-1]['date']} {loc} 예상 평균 {avg_t:.1f}°C"
    return {"summary": summary, "raw": records}


def get_consumption_summary(household_id: str, period: str = "week") -> dict[str, Any]:
    """전력 소비 요약(총량, 일평균, 전년 대비, 피크 시간대) 조회."""
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


def get_consumption_hourly(household_id: str, date: str = "2026-04-27") -> dict[str, Any]:
    """하루 24시간 시간대별 전력 소비(kWh/h) 조회."""
    if household_id not in _KNOWN_HOUSEHOLDS:
        return {"error": f"household_id not found: {household_id}", "code": "E_NOT_FOUND"}
    hourly   = _MOCK_HOURLY[household_id]
    base_avg = sum(h["kwh"] for h in hourly[:6]) / 6
    peak_h   = max(hourly, key=lambda h: h["kwh"])
    summary  = (
        f"{date}, 0~5시 기저 평균 {base_avg:.2f}kWh/h, "
        f"피크 {peak_h['hour']}시 {peak_h['kwh']:.2f}kWh/h"
    )
    return {"summary": summary, "raw": hourly}


def get_consumption_breakdown(household_id: str, date: str = "2026-04-27") -> dict[str, Any]:
    """NILM 분해 결과 — 가전별 전력 사용량과 가동 시간대 조회."""
    if household_id not in _KNOWN_HOUSEHOLDS:
        return {"error": f"household_id not found: {household_id}", "code": "E_NOT_FOUND"}
    breakdown = _MOCK_BREAKDOWN[household_id]
    top3      = sorted(breakdown, key=lambda x: x["kwh"], reverse=True)[:3]
    top3_str  = ", ".join(
        f"{a['appliance']} {a['kwh']}kWh({a['share_pct']:.0f}%)" for a in top3
    )
    summary = f"{date} 가전별 NILM 분해: {top3_str} 등"
    return {"summary": summary, "raw": breakdown}


def get_dr_events(
    date_range: tuple[str, str] | list[str],
    region: str = "서울",
) -> dict[str, Any]:
    """DR(수요반응) 이벤트 발령 이력과 예정 이벤트 조회."""
    loc      = region if region in _MOCK_DR_EVENTS else "서울"
    events   = _MOCK_DR_EVENTS.get(loc, [])
    start, end = date_range[0], date_range[1]
    filtered  = [e for e in events if start <= e["date"] <= end]
    if not filtered:
        return {"summary": f"{start}~{end} {loc} DR 이벤트 없음", "raw": []}
    completed = sum(1 for e in filtered if e["status"] == "완료")
    scheduled = sum(1 for e in filtered if e["status"] == "예정")
    summary   = (
        f"{start}~{end} {loc} DR 이벤트 {len(filtered)}건 "
        f"(완료 {completed}건, 예정 {scheduled}건)"
    )
    return {"summary": summary, "raw": filtered}


def get_tariff_info(household_id: str) -> dict[str, Any]:
    """현재 요금제·누진 단계·다음 단계까지 남은 kWh·예상 청구액 조회."""
    if household_id not in _KNOWN_HOUSEHOLDS:
        return {"error": f"household_id not found: {household_id}", "code": "E_NOT_FOUND"}
    t = _MOCK_TARIFF[household_id]
    summary = (
        f"{t['plan']}, 현재 {t['current_tier']}단계 ({t['current_month_kwh']}kWh 사용). "
        f"다음 단계까지 {t['kwh_to_next_tier']}kWh 남음. "
        f"이번 달 예상 청구액 {t['estimated_monthly_bill_krw']:,}원."
    )
    return {"summary": summary, "raw": t}


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
            "name": "get_consumption_hourly",
            "description": "하루 24시간 시간대별 전력 소비(kWh/h)를 조회합니다.",
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
            "name": "get_consumption_breakdown",
            "description": "NILM 분해 결과로 가전별 전력 사용량과 가동 시간대를 조회합니다.",
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
            "name": "get_dr_events",
            "description": "지정 기간의 DR(수요반응) 이벤트 발령 이력과 예정 이벤트를 조회합니다.",
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
                    "region": {
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
]
