import os
from fastapi import APIRouter
from src.agent.data_tools import (
    get_consumption_summary,
    get_cashback_history,
    get_hourly_appliance_breakdown,
)

router = APIRouter()

_DAYS = ["월", "화", "수", "목", "금", "토", "일"]
_DAY_FACTORS = [0.88, 1.00, 0.95, 1.08, 1.05, 1.22, 0.82]


def _make_weekly(daily_avg: float, prev_factor: float = 1.05):
    days = []
    for label, f in zip(_DAYS, _DAY_FACTORS):
        tw = round(daily_avg * f, 2)
        pw = round(tw * prev_factor, 2)
        days.append({"day": label, "thisWeek": tw, "prevWeek": pw})
    tw_total = round(sum(d["thisWeek"] for d in days), 2)
    pw_total = round(sum(d["prevWeek"] for d in days), 2)
    return days, tw_total, pw_total


@router.get("/usage/analysis")
def usage_analysis():
    hh = os.getenv("DEFAULT_HH", "HH001")

    week = get_consumption_summary(hh, period="week")
    week_raw = week.get("raw", {})
    daily_avg = float(week_raw.get("daily_avg_kwh", 6.0))
    days, tw_total, pw_total = _make_weekly(daily_avg)

    breakdown = get_hourly_appliance_breakdown(hh)
    raw_hours = breakdown.get("raw", [])
    daily_summary = breakdown.get("daily_summary", [])
    appliances_list = breakdown.get("appliances", [])

    # Build HourlyDatum: sum all appliances per hour
    hourly_data = []
    for row in raw_hours:
        hour = row["hour"]
        today_kwh = round(
            sum(float(row.get(app, 0)) for app in appliances_list), 3
        )
        # average is simulated as 90% of today for now
        average_kwh = round(today_kwh * 0.9, 3)
        hourly_data.append({"hour": hour, "average": average_kwh, "today": today_kwh})

    # If hourly_data is empty, generate zeros
    if not hourly_data:
        hourly_data = [{"hour": h, "average": 0.0, "today": 0.0} for h in range(24)]

    appliance_breakdown = [
        {
            "name": a["appliance"],
            "kwh": round(a["daily_kwh"], 2),
            "sharePercent": round(a["share_pct"], 1),
            "weekOverWeekPercent": 0,  # no historical comparison available yet
        }
        for a in daily_summary
    ]

    # Monthly from cashback history
    cb_history = get_cashback_history(hh)
    history_records = cb_history.get("raw", [])
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
        "weekly": {
            "days": days,
            "thisWeekTotal": tw_total,
            "prevWeekTotal": pw_total,
        },
        "hourly": {"hours": hourly_data},
        "applianceBreakdown": appliance_breakdown,
        "monthly": {
            "year": 2026,
            "months": months,
            "currentMonth": 4,
        },
    }
