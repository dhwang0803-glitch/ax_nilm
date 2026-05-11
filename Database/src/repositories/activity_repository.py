"""ActivityRepository — activity_intervals (AI Hub ground truth)."""
from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ActivityInterval


class ActivityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def insert_intervals(
        self,
        household_id: str,
        channel_num: int,
        intervals: Sequence[tuple[datetime, datetime]],
        source: str = "aihub_71685",
    ) -> int:
        """배치 INSERT. EXCLUDE gist 제약(겹침 차단) 위반 시 IntegrityError.

        호출자는 사전에 정렬·중복 제거를 권장. ETL 단계에서 같은 source 중복
        적재가 발생하면 ingestion_log unique 위반으로 막히므로 여기서는
        정합성 보장 책임을 적게 둔다.
        """
        if not intervals:
            return 0
        rows = [
            {
                "household_id": household_id,
                "channel_num": channel_num,
                "start_ts": s,
                "end_ts": e,
                "source": source,
            }
            for s, e in intervals
        ]
        await self._s.execute(insert(ActivityInterval), rows)
        return len(rows)

    async def get_intervals(
        self,
        household_id: str,
        channel_num: int,
        start: datetime,
        end: datetime,
    ) -> Sequence[tuple[datetime, datetime, str]]:
        stmt = (
            select(
                ActivityInterval.start_ts,
                ActivityInterval.end_ts,
                ActivityInterval.source,
            )
            .where(
                ActivityInterval.household_id == household_id,
                ActivityInterval.channel_num == channel_num,
                ActivityInterval.end_ts > start,
                ActivityInterval.start_ts < end,
            )
            .order_by(ActivityInterval.start_ts)
        )
        res = await self._s.execute(stmt)
        return [(r.start_ts, r.end_ts, r.source) for r in res]
