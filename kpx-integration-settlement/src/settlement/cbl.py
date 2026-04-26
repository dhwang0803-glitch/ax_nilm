"""월별 기준선(Baseline) 계산.

에너지캐시백 기준: 직전 2개년 동월 평균.
  예) 2025년 7월 기준선 = (2023년 7월 + 2024년 7월) / 2

신규 가구(2개년 데이터 미보유): 군집 평균 월 사용량으로 Proxy 적용.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass
class MonthlyUsage:
    year: int
    month: int
    energy_kwh: float  # ch01 해당 월 합산


class BaselineRepository(Protocol):
    async def get_monthly_usage(
        self,
        household_id: str,
        year: int,
        month: int,
    ) -> MonthlyUsage | None: ...

    async def get_cluster_avg_monthly_kwh(
        self,
        cluster_label: int,
        month: int,
    ) -> float: ...


async def calc_baseline(
    household_id: str,
    ref_month: date,
    cluster_label: int,
    repo: BaselineRepository,
) -> tuple[float, str]:
    """월별 기준선(kWh) 반환.

    Returns:
        (baseline_kwh, method)
        method: "2year_avg" | "proxy_cluster"
    """
    prev1 = await repo.get_monthly_usage(
        household_id, ref_month.year - 2, ref_month.month
    )
    prev2 = await repo.get_monthly_usage(
        household_id, ref_month.year - 1, ref_month.month
    )

    if prev1 and prev2:
        return (prev1.energy_kwh + prev2.energy_kwh) / 2.0, "2year_avg"

    # 한 해만 있는 경우 단년도 사용
    if prev2:
        return prev2.energy_kwh, "2year_avg"
    if prev1:
        return prev1.energy_kwh, "2year_avg"

    # 신규 가구 fallback: 군집 평균 월 사용량
    cluster_avg = await repo.get_cluster_avg_monthly_kwh(cluster_label, ref_month.month)
    return cluster_avg, "proxy_cluster"
