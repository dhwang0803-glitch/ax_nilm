"""NILMInferenceRepository — appliance_status_intervals.

핵심: ``record_transition`` 은 단일 트랜잭션으로 (1) 기존 열린 구간 종료
+ (2) 새 구간 INSERT 를 수행. 외부 세션의 commit/rollback 정책을 따른다
(``session_scope`` 사용 시 자동 commit).

EXCLUDE gist 제약 (schemas/004) 이 동일 (가구·채널·model_version) 의 시간
겹침을 DB 레벨에서 차단하므로, 동시 record_transition 두 호출이 순서가
꼬이면 IntegrityError 가 발생 — 호출자(Execution Engine) 가 가구·채널 단위
직렬 처리하거나 advisory lock 을 사용해야 한다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ApplianceStatusInterval


class NILMInferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def record_transition(
        self,
        household_id: str,
        channel_num: int,
        transition_ts: datetime,
        new_status: int,
        confidence: float | None,
        model_version: str,
    ) -> int:
        # (1) 기존 열린 구간(end_ts NULL) 종료
        await self._s.execute(
            update(ApplianceStatusInterval)
            .where(
                ApplianceStatusInterval.household_id == household_id,
                ApplianceStatusInterval.channel_num == channel_num,
                ApplianceStatusInterval.model_version == model_version,
                ApplianceStatusInterval.end_ts.is_(None),
            )
            .values(end_ts=transition_ts)
        )

        # (2) 새 구간 INSERT (end_ts NULL = 진행 중)
        stmt = (
            insert(ApplianceStatusInterval)
            .values(
                household_id=household_id,
                channel_num=channel_num,
                start_ts=transition_ts,
                end_ts=None,
                status_code=new_status,
                confidence=confidence,
                model_version=model_version,
            )
            .returning(ApplianceStatusInterval.id)
        )
        res = await self._s.execute(stmt)
        return int(res.scalar_one())

    async def get_current_status(
        self, household_id: str, channel_num: int, model_version: str
    ) -> tuple[int, datetime, float | None] | None:
        # idx_status_open partial index (end_ts IS NULL) 사용.
        stmt = (
            select(
                ApplianceStatusInterval.status_code,
                ApplianceStatusInterval.start_ts,
                ApplianceStatusInterval.confidence,
            )
            .where(
                ApplianceStatusInterval.household_id == household_id,
                ApplianceStatusInterval.channel_num == channel_num,
                ApplianceStatusInterval.model_version == model_version,
                ApplianceStatusInterval.end_ts.is_(None),
            )
            .limit(1)
        )
        res = await self._s.execute(stmt)
        row = res.first()
        if row is None:
            return None
        return (int(row.status_code), row.start_ts, row.confidence)

    async def get_history(
        self,
        household_id: str,
        channel_num: int,
        model_version: str,
        start: datetime,
        end: datetime,
        min_confidence: float | None = 0.6,
    ) -> Sequence[tuple[datetime, datetime | None, int, float | None]]:
        # confidence 필터: REQ-001 기본 0.6. 호출자가 None 으로 전체 포함 가능.
        conds = [
            ApplianceStatusInterval.household_id == household_id,
            ApplianceStatusInterval.channel_num == channel_num,
            ApplianceStatusInterval.model_version == model_version,
            ApplianceStatusInterval.start_ts < end,
            # 진행 중 구간(end_ts NULL)도 시간창에 포함 — COALESCE 로 무한대.
            (
                ApplianceStatusInterval.end_ts.is_(None)
                | (ApplianceStatusInterval.end_ts > start)
            ),
        ]
        if min_confidence is not None:
            conds.append(ApplianceStatusInterval.confidence >= min_confidence)
        stmt = (
            select(
                ApplianceStatusInterval.start_ts,
                ApplianceStatusInterval.end_ts,
                ApplianceStatusInterval.status_code,
                ApplianceStatusInterval.confidence,
            )
            .where(*conds)
            .order_by(ApplianceStatusInterval.start_ts)
        )
        res = await self._s.execute(stmt)
        return [
            (r.start_ts, r.end_ts, int(r.status_code), r.confidence) for r in res
        ]
