import os
from fastapi import APIRouter
from src.agent.data_tools import get_cashback_history, get_consumption_summary, get_household_profile

router = APIRouter()

_DAYS = ["월", "화", "수", "목", "금", "토", "일"]
_DAY_FACTORS = [0.88, 1.00, 0.95, 1.08, 1.05, 1.22, 0.82]

# (가전명 키워드, 미션 제목, 기본 절감 kWh)
_MISSION_RULES: list[tuple[str, str, float]] = [
    ("에어컨",    "에어컨 설정 온도 1℃ 올리기",              0.8),
    ("건조기",    "저온 코스 사용 (주 2회 기준)",              0.9),
    ("냉장고",    "냉장고 온도 2단계 → 1단계",               0.7),
    ("세탁기",    "찬물 세탁 빈도 증가 (주 2회 추가)",         0.5),
    ("TV",        "대기전력 차단 멀티탭 사용",                 0.4),
    ("전기밥솥",  "보온 최소화 — 여열 활용",                  0.5),
    ("컴퓨터",    "대기 시 모니터 전원 차단",                  0.3),
    ("인덕션",    "여열 활용 — 종료 1분 전 차단",              0.2),
    ("공기청정기","자동 모드 전환으로 불필요 가동 최소화",      0.3),
]

# 에너지효율 등급 → 절감 여지 배율 (1등급=최고효율, 5등급=최저효율)
_EFF_MULTIPLIER = {1: 0.5, 2: 0.75, 3: 1.0, 4: 1.3, 5: 1.6}

_FALLBACK_MISSIONS: list[tuple[str, float]] = [
    ("저녁 19–21시 대기전력 차단",  1.4),
    ("조명 LED 교체 (형광등 2개)",  0.9),
    ("사용 안 하는 가전 플러그 뽑기", 0.6),
]


def _generate_missions(household_id: str) -> list[dict]:
    """가구 프로필 기반 규칙 테이블로 절감 미션 3개 동적 생성.

    에너지효율 등급이 낮을수록 절감 여지가 크므로 예상 절감량을 높게 산정.
    가전 목록이 부족하면 범용 fallback으로 보완.
    spec(PLAN_05): 상위 2개 pending, 가장 낮은 1개 done.
    """
    profile = get_household_profile(household_id)
    appliances: list[dict] = profile.get("raw", {}).get("appliances", [])

    matched: list[tuple[str, float]] = []  # (title, expected_kwh)
    seen: set[str] = set()

    for appliance in appliances:
        name = (appliance.get("name") or "").strip()
        eff  = appliance.get("energy_efficiency")
        mult = _EFF_MULTIPLIER.get(int(eff), 1.0) if eff else 1.0

        for keyword, title, base_kwh in _MISSION_RULES:
            if keyword in name and keyword not in seen:
                seen.add(keyword)
                matched.append((title, round(base_kwh * mult, 1)))
                break

    # 절감량 내림차순 → 상위 3개 선출
    matched.sort(key=lambda x: x[1], reverse=True)
    top3 = matched[:3]

    # 3개 미만이면 fallback으로 보완
    for fb_title, fb_kwh in _FALLBACK_MISSIONS:
        if len(top3) >= 3:
            break
        if not any(t == fb_title for t, _ in top3):
            top3.append((fb_title, fb_kwh))

    # PLAN_05 spec: 2 pending + 1 done (절감량 최소 항목을 done으로)
    return [
        {
            "id":                 f"m{i + 1}",
            "title":              title,
            "expectedSavingsKwh": kwh,
            "status":             "done" if i == len(top3) - 1 else "pending",
        }
        for i, (title, kwh) in enumerate(top3)
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

    current_savings_pct = float(current_rec.get("savings_pct") or 8.4) if current_rec else 8.4
    expected_savings_pct = round(current_savings_pct * 1.13, 1)
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
        "missions": _generate_missions(hh),
    }
