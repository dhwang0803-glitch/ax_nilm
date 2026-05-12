"""Module 3 — 캐시백 계산 노드 (LLM 없음, Python 함수만).

get_cashback_history + get_tariff_info 결과를 이용해
현재 월의 절감률·예상 캐시백을 계산한다.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel

from ..data_tools import get_cashback_history, get_tariff_info


# KEPCO 에너지캐시백 단가 테이블 (절감률 → 원/kWh)
_CASHBACK_TIERS: list[tuple[float, float]] = [
    (0.20, 100.0),
    (0.10,  80.0),
    (0.05,  60.0),
    (0.03,  30.0),
]


def _tier_rate(savings_rate: float) -> float:
    """절감률에 따른 캐시백 단가(원/kWh) 반환. 미달 시 0."""
    for threshold, rate in _CASHBACK_TIERS:
        if savings_rate >= threshold:
            return rate
    return 0.0


def cashback_unit_rate(household_id: str) -> float:
    """가구의 최근 지급완료 캐시백 이력에서 단가(원/kWh) 조회. 없으면 50 반환."""
    history = get_cashback_history(household_id)
    paid = [r for r in history.get("raw", []) if r.get("status") == "지급완료"]
    if paid:
        rate = paid[-1].get("cashback_rate_krw_per_kwh")
        if rate is not None:
            return float(rate)
    return 50.0


# ── 출력 스키마 ────────────────────────────────────────────────────────────────

class CashbackNodeOutput(BaseModel):
    baseline_kwh: float                # 2개년 동월 평균 기준선
    actual_kwh: float                  # 당월 실측(또는 MTD 페이스 추정)
    savings_rate: float                # 절감률 (savings / baseline)
    cashback_rate_krw_per_kwh: float   # 적용 단가 (0/30/50/70/100)
    projected_cashback_krw: int        # 예상 캐시백 금액
    enrolled: bool                     # 에너지캐시백 신청 여부
    baseline_method: str               # "2year_avg" | "proxy_cluster" | "unknown"


# ── 노드 함수 ──────────────────────────────────────────────────────────────────

def cashback_node_fn(state: dict[str, Any]) -> dict[str, Any]:
    """Module 3: 캐시백 산정 — 기준선·절감률·단가·예상 금액 계산."""
    hh = state["household_id"]

    cb_data     = get_cashback_history(hh)
    tariff_data = get_tariff_info(hh)

    history     = cb_data.get("raw", [])
    tariff_raw  = tariff_data.get("raw", {})

    # 현재 월 집계중 레코드에서 기준선 추출
    this_month = date.today().strftime("%Y-%m")
    current_rec = next(
        (r for r in history if r.get("month", "")[:7] == this_month),
        None,
    )

    if current_rec:
        baseline_kwh   = float(current_rec.get("baseline_kwh") or 0)
        baseline_method = current_rec.get("baseline_method", "2year_avg")
        enrolled       = bool(current_rec.get("enrolled", True))
    else:
        # 이력 없으면 가장 최근 레코드의 기준선 사용
        last_rec       = history[-1] if history else {}
        baseline_kwh   = float(last_rec.get("baseline_kwh") or 0)
        baseline_method = "unknown"
        enrolled       = True

    # 당월 실측: tariff MTD 사용량 → 월말 페이스 추산
    mtd_kwh      = float(tariff_raw.get("current_month_kwh") or 0)
    day_elapsed  = date.today().day
    days_in_month = 30
    if day_elapsed > 0 and mtd_kwh > 0:
        actual_kwh = round(mtd_kwh / day_elapsed * days_in_month, 1)
    else:
        actual_kwh = mtd_kwh

    if baseline_kwh > 0:
        savings_kwh  = baseline_kwh - actual_kwh
        savings_rate = round(max(savings_kwh / baseline_kwh, 0.0), 4)
    else:
        savings_rate = 0.0

    rate_per_kwh       = _tier_rate(savings_rate)
    effective_savings  = baseline_kwh * min(savings_rate, 0.30)
    projected_krw      = int(effective_savings * rate_per_kwh)

    output = CashbackNodeOutput(
        baseline_kwh=baseline_kwh,
        actual_kwh=actual_kwh,
        savings_rate=savings_rate,
        cashback_rate_krw_per_kwh=rate_per_kwh,
        projected_cashback_krw=projected_krw,
        enrolled=enrolled,
        baseline_method=baseline_method,
    )
    return {"cashback_output": output.model_dump()}
