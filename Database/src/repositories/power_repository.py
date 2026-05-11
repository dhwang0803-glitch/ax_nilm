"""PowerRepository 구현 — power_1min / power_1hour / power_efficiency_30min.

KPX UsageRepository (cbl.py) 도 본 클래스가 충족.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PowerEfficiency30Min, PowerHour, PowerMinute
from .protocols import DailyUsage


class PowerRepository:
    """PostgreSQL/TimescaleDB 구현. 모든 메서드는 외부 트랜잭션 내에서 동작.

    cluster 평균 비율은 power_1hour 가 cold tier 임을 활용해 7일 이상 데이터를
    사용한다 (power_1min retention 7일 → 일자별 평일 평균은 cold tier 에서만
    안전).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ─── 단순 시계열 조회 ────────────────────────────────────────────
    async def get_recent_minutes(
        self, household_id: str, channel_num: int, hours: int = 1
    ) -> Sequence[tuple[datetime, float | None]]:
        sql = text(
            """
            SELECT bucket_ts, active_power_avg
              FROM power_1min
             WHERE household_id = :h AND channel_num = :c
               AND bucket_ts >= NOW() - (:hours * INTERVAL '1 hour')
             ORDER BY bucket_ts
            """
        )
        res = await self._s.execute(
            sql, {"h": household_id, "c": channel_num, "hours": hours}
        )
        return [(row.bucket_ts, row.active_power_avg) for row in res]

    async def get_hour_range(
        self,
        household_id: str,
        channel_num: int,
        start: datetime,
        end: datetime,
    ) -> Sequence[tuple[datetime, float | None, float | None]]:
        sql = text(
            """
            SELECT hour_bucket, energy_wh, active_power_avg
              FROM power_1hour
             WHERE household_id = :h AND channel_num = :c
               AND hour_bucket >= :start AND hour_bucket < :end
             ORDER BY hour_bucket
            """
        )
        res = await self._s.execute(
            sql,
            {"h": household_id, "c": channel_num, "start": start, "end": end},
        )
        return [
            (row.hour_bucket, row.energy_wh, row.active_power_avg) for row in res
        ]

    # ─── KPX UsageRepository 호환 ────────────────────────────────────
    async def get_weekday_usage(
        self,
        household_id: str,
        channel_num: int,
        event_start_date: date,
        limit: int = 10,
    ) -> list[DailyUsage]:
        """직전 N 평일 일별 소비량 (kWh). EXTRACT(isodow) 1~5 = 월~금.

        cold tier (power_1hour) 에서 일 단위 합산. event_start_date 당일은
        제외 (KPX 표준: 이벤트 발생일 직전까지).
        """
        sql = text(
            """
            SELECT date_trunc('day', hour_bucket)::date AS day,
                   SUM(energy_wh) / 1000.0           AS energy_kwh
              FROM power_1hour
             WHERE household_id = :h AND channel_num = :c
               AND hour_bucket <  :event_date::timestamptz
               AND EXTRACT(isodow FROM hour_bucket) BETWEEN 1 AND 5
             GROUP BY date_trunc('day', hour_bucket)
             ORDER BY day DESC
             LIMIT :lim
            """
        )
        res = await self._s.execute(
            sql,
            {
                "h": household_id,
                "c": channel_num,
                "event_date": event_start_date,
                "lim": limit,
            },
        )
        # 호출자(KPX cbl) 는 정렬 무관 — 그대로 반환.
        return [DailyUsage(day=row.day, energy_kwh=float(row.energy_kwh)) for row in res]

    async def get_cluster_avg_ratio(
        self, cluster_label: int, channel_num: int
    ) -> float:
        """동일 cluster 가구의 (channel / ch01) 사용량 비율 평균.

        ch01=0 인 가구는 분모에서 제외. 빈 결과는 0.0 반환 (KPX cbl 에서
        proxy_cluster CBL = ch01_cbl × 0 = 0 으로 흘러 의도된 fallback).
        """
        sql = text(
            """
            WITH per_household AS (
                SELECT h.household_id,
                       SUM(p.energy_wh) FILTER (WHERE p.channel_num = :c)   AS ch_wh,
                       SUM(p.energy_wh) FILTER (WHERE p.channel_num = 1)    AS main_wh
                  FROM households h
                  JOIN power_1hour p ON p.household_id = h.household_id
                 WHERE h.cluster_label = :cl
                   AND p.hour_bucket >= NOW() - INTERVAL '30 days'
                 GROUP BY h.household_id
            )
            SELECT COALESCE(AVG(ch_wh / NULLIF(main_wh, 0)), 0.0) AS ratio
              FROM per_household
             WHERE main_wh IS NOT NULL AND main_wh > 0
            """
        )
        res = await self._s.execute(sql, {"cl": cluster_label, "c": channel_num})
        return float(res.scalar_one() or 0.0)

    # ─── power_efficiency_30min UPSERT ───────────────────────────────
    async def upsert_efficiency_30min(
        self,
        household_id: str,
        channel_num: int,
        bucket_ts: datetime,
        energy_wh: float,
        cbl_wh: float | None,
        is_dr_window: bool,
        event_id: str | None,
    ) -> None:
        savings_wh = (cbl_wh - energy_wh) if cbl_wh is not None else 0.0

        stmt = pg_insert(PowerEfficiency30Min).values(
            household_id=household_id,
            channel_num=channel_num,
            bucket_ts=bucket_ts,
            energy_wh=energy_wh,
            cbl_wh=cbl_wh,
            savings_wh=savings_wh,
            is_dr_window=is_dr_window,
            event_id=event_id,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["household_id", "channel_num", "bucket_ts"],
            set_={
                "energy_wh": stmt.excluded.energy_wh,
                "cbl_wh": stmt.excluded.cbl_wh,
                "savings_wh": stmt.excluded.savings_wh,
                "is_dr_window": stmt.excluded.is_dr_window,
                "event_id": stmt.excluded.event_id,
                "computed_at": text("NOW()"),
            },
        )
        await self._s.execute(stmt)
