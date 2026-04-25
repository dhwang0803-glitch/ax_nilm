"""CBL(Customer Baseline Load) 계산.

공식식 기준: 직전 10 평일 중 상위2·하위2 제외한 6일 가중평균 (Mid 6/10).
신규 가구(10일 미만): 군집 평균 비율 기반 Proxy CBL 적용.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol, Sequence


@dataclass
class DailyUsage:
    day: date
    energy_kwh: float  # ch01 해당 시간대 소비량


class UsageRepository(Protocol):
    async def get_weekday_usage(
        self,
        household_id: str,
        channel_num: int,
        event_start_date: date,
        limit: int = 10,
    ) -> list[DailyUsage]: ...

    async def get_cluster_avg_ratio(
        self,
        cluster_label: int,
        channel_num: int,
    ) -> float: ...


def mid_6_of_10(values: Sequence[float]) -> float:
    """직전 10 평일 중 상위2·하위2 제외 6일 평균 (Mid 6/10).

    값이 6개 미만이면 가용한 전체 평균을 반환한다.
    """
    if len(values) < 6:
        return sum(values) / len(values) if values else 0.0
    sorted_vals = sorted(values)
    mid = sorted_vals[2:-2]  # 하위2 ~ 상위2 제외
    return sum(mid) / len(mid)


async def calc_cbl(
    household_id: str,
    channel_num: int,
    event_date: date,
    cluster_label: int,
    repo: UsageRepository,
) -> tuple[float, str]:
    """CBL(kWh) 반환.

    Returns:
        (cbl_kwh, method)
        method: "mid_6_10" | "proxy_cluster"
    """
    usage_rows = await repo.get_weekday_usage(
        household_id, channel_num, event_date, limit=10
    )
    values = [r.energy_kwh for r in usage_rows]

    if len(values) >= 6:
        return mid_6_of_10(values), "mid_6_10"

    # 신규 가구 fallback: ch01 proxy CBL × 군집 평균 비율
    ch01_rows = await repo.get_weekday_usage(
        household_id, 1, event_date, limit=10
    )
    ch01_values = [r.energy_kwh for r in ch01_rows]
    ch01_cbl = mid_6_of_10(ch01_values) if len(ch01_values) >= 1 else 0.0

    ratio = await repo.get_cluster_avg_ratio(cluster_label, channel_num)
    return ch01_cbl * ratio, "proxy_cluster"
