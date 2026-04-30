import os
from fastapi import APIRouter
from src.agent.data_tools import get_cashback_history, get_consumption_summary

router = APIRouter()

_DAYS = ["월", "화", "수", "목", "금", "토", "일"]
_DAY_FACTORS = [0.88, 1.00, 0.95, 1.08, 1.05, 1.22, 0.82]

_DEFAULT_MISSIONS = [
    {"id": "m1", "title": "저녁 19–21시 대기전력 차단", "expectedSavingsKwh": 1.4, "status": "pending"},
    {"id": "m2", "title": "냉장고 온도 2단계 → 1단계", "expectedSavingsKwh": 0.7, "status": "pending"},
    {"id": "m3", "title": "조명 LED 교체 (형광등 2개)", "expectedSavingsKwh": 0.9, "status": "done"},
]


def _make_weekly(daily_avg: float, prev_factor: float = 1.05):
    days = []
    for label, f in zip(_DAYS, _DAY_FACTORS):
        tw = round(daily_avg * f, 2)
        pw = round(tw * prev_factor, 2)
        days.append({"day": label, "thisWeek": tw, "prevWeek": pw})
    return days


@router.get("/cashback/tracker")
def cashback_tracker():
    hh = os.getenv("DEFAULT_HH", "HH001")

    cb_history = get_cashback_history(hh)
    history_records = cb_history.get("raw", [])

    current_rec = next(
        (r for r in history_records if r.get("month") == "2026-04"), None
    )
    baseline_kwh = float(current_rec.get("baseline_kwh", 0)) if current_rec else 0.0
    target_savings_pct = 3.0
    target_cashback_kwh = round(baseline_kwh * (target_savings_pct / 100), 1)
    # KEPCO 에너지캐시백 기준: 절감 kWh × 단가
    cb_rate = 100  # 원/kWh (기본)
    completed = [r for r in history_records if r.get("status") == "지급완료"]
    if completed:
        cb_rate = int(completed[-1].get("cashback_rate_krw_per_kwh") or 100)
    target_cashback_krw = round(target_cashback_kwh * cb_rate)

    # Use actual savings_pct from current month record if available
    current_savings_pct = float(current_rec.get("savings_pct") or 8.4) if current_rec else 8.4
    expected_savings_pct = round(current_savings_pct * 1.13, 1)  # project to month-end
    progress_pct = min(round(current_savings_pct / target_savings_pct * 100), 100)
    expected_progress_pct = min(round(expected_savings_pct / target_savings_pct * 100), 100)

    # Weekly
    week = get_consumption_summary(hh, period="week")
    daily_avg = float(week.get("raw", {}).get("daily_avg_kwh", 6.0))
    weekly_days = _make_weekly(daily_avg)

    # Monthly from history
    hist_by_month = {r["month"]: r for r in history_records}
    current_month_kwh = daily_avg * 30
    months = []
    for m in range(1, 13):
        key = f"2026-{m:02d}"
        rec = hist_by_month.get(key)
        if rec:
            kwh = rec.get("actual_kwh") or (current_month_kwh if m == 4 else 0)
        elif m == 4:
            kwh = current_month_kwh
        else:
            kwh = 0
        months.append({"month": m, "kwh": round(kwh, 1)})

    return {
        "goal": {
            "month": 4,
            "targetSavingsPercent": target_savings_pct,
            "targetCashbackKrw": target_cashback_krw,
            "daysRemaining": 2,
            "currentSavingsPercent": current_savings_pct,
            "expectedSavingsPercent": expected_savings_pct,
            "progressPercent": progress_pct,
            "expectedProgressPercent": expected_progress_pct,
        },
        "weekly": {"days": weekly_days},
        "monthly": {"year": 2026, "months": months, "currentMonth": 4},
        "missions": _DEFAULT_MISSIONS,
    }
