"""월별 기준선(Baseline) 계산.

에너지캐시백 기준: 직전 2개년 동월 평균.
  예) 2025년 7월 기준선 = (2023년 7월 + 2024년 7월) / 2

신규 가구(2개년 데이터 미보유): 소비 패턴 임베딩으로 유사 가구 top-k를 찾아
  그 가구들의 동월 평균을 기준선으로 사용 (proxy_similar_household).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

import numpy as np


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

    async def get_similar_households_monthly_avg(
        self,
        query_vector: np.ndarray,
        month: int,
        top_k: int = 5,
    ) -> float:
        """소비 패턴 임베딩 유사도로 찾은 가구들의 동월 평균 kWh."""
        ...


async def calc_baseline(
    household_id: str,
    ref_month: date,
    repo: BaselineRepository,
    query_vector: np.ndarray | None = None,
) -> tuple[float, str]:
    """월별 기준선(kWh) 반환.

    Args:
        query_vector: 신규 가구의 소비 패턴 임베딩 — proxy 경로에서만 사용.

    Returns:
        (baseline_kwh, method)
        method: "2year_avg" | "proxy_similar_household"
    """
    prev1 = await repo.get_monthly_usage(
        household_id, ref_month.year - 2, ref_month.month
    )
    prev2 = await repo.get_monthly_usage(
        household_id, ref_month.year - 1, ref_month.month
    )

    if prev1 and prev2:
        return (prev1.energy_kwh + prev2.energy_kwh) / 2.0, "2year_avg"

    if prev2:
        return prev2.energy_kwh, "2year_avg"
    if prev1:
        return prev1.energy_kwh, "2year_avg"

    # 신규 가구 fallback: 유사 가구 동월 평균
    if query_vector is None:
        raise ValueError("신규 가구 기준선 계산에는 query_vector(소비 패턴 임베딩) 필요")

    avg_kwh = await repo.get_similar_households_monthly_avg(
        query_vector, ref_month.month, top_k=5
    )
    return avg_kwh, "proxy_similar_household"
