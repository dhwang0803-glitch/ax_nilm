import os
from fastapi import APIRouter
from src.agent.data_tools import (
    get_dashboard_summary,
    get_tariff_info,
    get_cashback_history,
    get_consumption_summary,
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


@router.get("/dashboard/summary")
def dashboard_summary():
    hh = os.getenv("DEFAULT_HH", "HH001")

    ds = get_dashboard_summary(hh)
    ds_raw = ds.get("raw", {})
    if "error" in ds:
        ds_raw = {}

    cb_detail = ds_raw.get("cashback_detail", {})
    monthly_kwh = float(ds_raw.get("monthly_kwh_so_far", 0))
    est_cashback = float(ds_raw.get("cashback_expected_krw", 0))

    baseline = cb_detail.get("baseline_kwh") or monthly_kwh
    projected = cb_detail.get("projected_kwh") or monthly_kwh
    delta_pct = round((projected - baseline) / baseline * 100, 1) if baseline else 0.0

    tariff = get_tariff_info(hh)
    tariff_raw = tariff.get("raw", {})
    est_bill = float(tariff_raw.get("estimated_monthly_bill_krw", 0))

    cb_history = get_cashback_history(hh)
    history_records = cb_history.get("raw", [])
    completed = [r for r in history_records if r.get("status") == "지급완료"]
    cb_rate = int(completed[-1].get("cashback_rate_krw_per_kwh") or 100) if completed else 100

    # If not available from get_dashboard_summary (DB household), use tariff directly
    if monthly_kwh == 0:
        monthly_kwh = float(tariff_raw.get("current_month_kwh", 0))

    week = get_consumption_summary(hh, period="week")
    daily_avg = float(week.get("raw", {}).get("daily_avg_kwh", 0) or monthly_kwh / 30)
    days, tw_total, pw_total = _make_weekly(daily_avg)

    hist_by_month = {r["month"]: r for r in history_records}
    months = []
    for m in range(1, 13):
        key = f"2026-{m:02d}"
        rec = hist_by_month.get(key)
        if rec:
            kwh = rec.get("actual_kwh") or (monthly_kwh if m == 4 else 0)
        elif m == 4:
            kwh = monthly_kwh
        else:
            kwh = 0
        months.append({"month": m, "kwh": round(kwh, 1)})

    breakdown = get_hourly_appliance_breakdown(hh)
    daily_summary = breakdown.get("daily_summary", [])
    appliance_breakdown = [
        {"name": a["appliance"], "sharePercent": round(a["share_pct"], 1)}
        for a in daily_summary
    ]

    return {
        "kpis": {
            "monthlyUsageKwh": monthly_kwh,
            "monthlyDeltaPercent": delta_pct,
            "estimatedCashbackKrw": est_cashback,
            "cashbackRateKrwPerKwh": cb_rate,
            "estimatedBillKrw": est_bill,
        },
        "weekly": {
            "days": days,
            "thisWeekTotal": tw_total,
            "prevWeekTotal": pw_total,
            "avgPerDay": round(tw_total / 7, 2),
        },
        "monthly": {
            "year": 2026,
            "months": months,
            "currentMonth": 4,
        },
        "applianceBreakdown": appliance_breakdown,
    }
