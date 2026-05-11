"""HouseholdRepository — households + household_channels.

PII (household_pii) 는 권한 분리 원칙상 별도 PIIRepository 가 다룬다.
"""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Household, HouseholdChannel


class HouseholdRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, household_id: str) -> Household | None:
        return await self._s.get(Household, household_id)

    async def list_by_aggregator(
        self, aggregator_id: str
    ) -> Sequence[Household]:
        stmt = select(Household).where(Household.aggregator_id == aggregator_id)
        res = await self._s.execute(stmt)
        return list(res.scalars())

    async def list_by_cluster(self, cluster_label: int) -> Sequence[Household]:
        stmt = select(Household).where(Household.cluster_label == cluster_label)
        res = await self._s.execute(stmt)
        return list(res.scalars())

    async def set_cluster_label(
        self, household_id: str, cluster_label: int | None
    ) -> None:
        stmt = (
            update(Household)
            .where(Household.household_id == household_id)
            .values(cluster_label=cluster_label)
        )
        await self._s.execute(stmt)

    async def set_dr_enrollment(
        self,
        household_id: str,
        enrolled: bool,
        aggregator_id: str | None = None,
    ) -> None:
        values: dict[str, object] = {"dr_enrolled": enrolled}
        if aggregator_id is not None or not enrolled:
            # 미가입으로 전환 시 aggregator_id 도 함께 비움 (정합성)
            values["aggregator_id"] = aggregator_id if enrolled else None
        stmt = (
            update(Household)
            .where(Household.household_id == household_id)
            .values(**values)
        )
        await self._s.execute(stmt)

    async def get_channels(
        self, household_id: str
    ) -> Sequence[HouseholdChannel]:
        stmt = (
            select(HouseholdChannel)
            .where(HouseholdChannel.household_id == household_id)
            .order_by(HouseholdChannel.channel_num)
        )
        res = await self._s.execute(stmt)
        return list(res.scalars())
