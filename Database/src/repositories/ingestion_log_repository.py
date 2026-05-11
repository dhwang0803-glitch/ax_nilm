"""IngestionLogRepository — ETL 파일별 적재 이력 (중복 차단)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import IngestionLog


class IngestionLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def record(
        self,
        source_file: str,
        household_id: str,
        channel_num: int,
        file_date: date,
        raw_row_count: int,
        agg_row_count: int,
        intervals_count: int | None,
        status: str = "ok",
        notes: str | None = None,
    ) -> int:
        stmt = (
            insert(IngestionLog)
            .values(
                source_file=source_file,
                household_id=household_id,
                channel_num=channel_num,
                file_date=file_date,
                raw_row_count=raw_row_count,
                agg_row_count=agg_row_count,
                intervals_count=intervals_count,
                status=status,
                notes=notes,
            )
            .returning(IngestionLog.id)
        )
        res = await self._s.execute(stmt)
        return int(res.scalar_one())

    async def is_already_ingested(self, source_file: str) -> bool:
        # source_file UNIQUE 인덱스 활용. SELECT 1 LIMIT 1.
        stmt = select(IngestionLog.id).where(
            IngestionLog.source_file == source_file
        )
        res = await self._s.execute(stmt)
        return res.first() is not None
