"""AggregatorRepository — KPX calculator.AggregatorRepository 호환.

settlement_rate 캐싱은 두지 않는다 — 단가 변경(ON CONFLICT DO UPDATE) 직후
구 단가로 정산되는 사고를 막기 위해 매 호출 DB 조회.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Aggregator


class AggregatorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_settlement_rate(self, aggregator_id: str) -> float:
        stmt = select(Aggregator.settlement_rate).where(
            Aggregator.aggregator_id == aggregator_id
        )
        res = await self._s.execute(stmt)
        rate = res.scalar_one_or_none()
        if rate is None:
            raise KeyError(f"aggregator not found: {aggregator_id}")
        return float(rate)

    async def upsert(
        self, aggregator_id: str, name: str, settlement_rate: float
    ) -> None:
        if settlement_rate <= 0:
            # CHECK 제약과 동일하지만 클라이언트 단계에서 막아 예외 메시지 명확화.
            raise ValueError("settlement_rate must be > 0")
        stmt = pg_insert(Aggregator).values(
            aggregator_id=aggregator_id,
            name=name,
            settlement_rate=settlement_rate,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["aggregator_id"],
            set_={
                "name": stmt.excluded.name,
                "settlement_rate": stmt.excluded.settlement_rate,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self._s.execute(stmt)
