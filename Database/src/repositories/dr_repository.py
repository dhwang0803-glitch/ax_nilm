"""DRRepository — dr_events / dr_results / dr_appliance_savings.

KPX UC-2 calc_savings 의 DRSavingsResult 를 DB 에 영속하기 위한 인터페이스.
호출자(KPX 서비스 레이어) 는 dataclass 를 풀어 본 메서드들을 호출.
"""
from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import DRApplianceSavings, DREvent, DRResult


class DRRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ─── dr_events ───────────────────────────────────────────────────
    async def create_event(
        self,
        event_id: str,
        start_ts: datetime,
        end_ts: datetime,
        target_kw: float,
        status: str = "pending",
    ) -> None:
        # KPX 가 같은 event_id 로 재발행할 가능성에 대비해 ON CONFLICT 갱신.
        # status 전이 (pending→active→completed) 도 본 메서드가 아닌
        # update_event_status 로 분리해 의도 명확화.
        stmt = pg_insert(DREvent).values(
            event_id=event_id,
            start_ts=start_ts,
            end_ts=end_ts,
            target_kw=target_kw,
            status=status,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["event_id"],
            set_={
                "start_ts": stmt.excluded.start_ts,
                "end_ts": stmt.excluded.end_ts,
                "target_kw": stmt.excluded.target_kw,
                # status 는 의도적으로 제외 — update_event_status 만 변경.
            },
        )
        await self._s.execute(stmt)

    async def update_event_status(self, event_id: str, status: str) -> None:
        if status not in {"pending", "active", "completed", "cancelled"}:
            raise ValueError(f"invalid DR status: {status}")
        stmt = (
            update(DREvent)
            .where(DREvent.event_id == event_id)
            .values(status=status)
        )
        await self._s.execute(stmt)

    async def get_event(self, event_id: str) -> DREvent | None:
        return await self._s.get(DREvent, event_id)

    # ─── dr_results ──────────────────────────────────────────────────
    async def upsert_result(
        self,
        event_id: str,
        household_id: str,
        cbl_kwh: float,
        actual_kwh: float,
        settlement_rate: float,
        cbl_method: str,
    ) -> None:
        # 정산 공식 — KPX calculator.calc_savings 과 동일 산출.
        savings_kwh = cbl_kwh - actual_kwh
        refund_krw = int(max(0.0, savings_kwh) * settlement_rate)

        stmt = pg_insert(DRResult).values(
            event_id=event_id,
            household_id=household_id,
            cbl_kwh=cbl_kwh,
            actual_kwh=actual_kwh,
            savings_kwh=savings_kwh,
            refund_krw=refund_krw,
            settlement_rate=settlement_rate,
            cbl_method=cbl_method,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["event_id", "household_id"],
            set_={
                "cbl_kwh": stmt.excluded.cbl_kwh,
                "actual_kwh": stmt.excluded.actual_kwh,
                "savings_kwh": stmt.excluded.savings_kwh,
                "refund_krw": stmt.excluded.refund_krw,
                "settlement_rate": stmt.excluded.settlement_rate,
                "cbl_method": stmt.excluded.cbl_method,
            },
        )
        await self._s.execute(stmt)

    async def insert_appliance_savings(
        self,
        event_id: str,
        household_id: str,
        rows: Sequence[tuple[int, str, float, float]],
    ) -> int:
        """rows = [(channel_num, appliance_code, channel_cbl_kwh, channel_actual_kwh), ...]."""
        if not rows:
            return 0
        # PK = (event_id, household_id, channel_num) 이라 같은 호출 내 중복은
        # 호출자가 책임. 재정산 시 PK 충돌이면 호출자가 사전 DELETE.
        records = [
            {
                "event_id": event_id,
                "household_id": household_id,
                "channel_num": ch,
                "appliance_code": code,
                "channel_cbl_kwh": cbl,
                "channel_actual_kwh": actual,
                "channel_savings_kwh": cbl - actual,
            }
            for (ch, code, cbl, actual) in rows
        ]
        await self._s.execute(insert(DRApplianceSavings), records)
        return len(records)

    async def get_results(self, event_id: str) -> Sequence[DRResult]:
        stmt = select(DRResult).where(DRResult.event_id == event_id)
        res = await self._s.execute(stmt)
        return list(res.scalars())
