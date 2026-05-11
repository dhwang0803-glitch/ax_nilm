"""ActivityRepository — EXCLUDE gist (구간 겹침 차단) 검증.

schemas/002 의 EXCLUDE 제약은 ``[start_ts, end_ts]`` 닫힌 구간으로 겹침을 본다.
- 인접 구간 (앞 구간 end == 뒷 구간 start) 은 ``[]`` 닫힘 정의상 겹침으로 판정 → 차단.
- 본 테스트는 명백한 시간 중첩만 검증해 닫힘/열림 정의 변경 시에도 견고하게 함.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from Database.src.repositories import ActivityRepository


pytestmark = pytest.mark.asyncio


def _ts(minute: int) -> datetime:
    return datetime(2030, 2, 1, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=minute)


async def test_insert_intervals_basic(
    session: AsyncSession, isolated_household
) -> None:
    hh, channels = isolated_household
    ch = channels[0]
    repo = ActivityRepository(session)

    n = await repo.insert_intervals(
        hh,
        ch,
        [(_ts(0), _ts(10)), (_ts(20), _ts(30))],
    )
    assert n == 2

    rows = await repo.get_intervals(hh, ch, _ts(-100), _ts(100))
    assert [(s, e) for s, e, _ in rows] == [
        (_ts(0), _ts(10)),
        (_ts(20), _ts(30)),
    ]


async def test_overlap_raises_integrity_error(
    session: AsyncSession, isolated_household
) -> None:
    """명확한 시간 중첩 → EXCLUDE gist 위반."""
    hh, channels = isolated_household
    ch = channels[0]
    repo = ActivityRepository(session)

    await repo.insert_intervals(hh, ch, [(_ts(0), _ts(20))])
    await session.commit()

    with pytest.raises(IntegrityError):
        await repo.insert_intervals(hh, ch, [(_ts(10), _ts(30))])  # 10~20 겹침
    await session.rollback()


async def test_overlap_isolated_per_channel(
    session: AsyncSession, isolated_household
) -> None:
    """같은 시간 구간이라도 다른 채널이면 허용."""
    hh, channels = isolated_household
    ch_a, ch_b = channels[0], channels[1]
    repo = ActivityRepository(session)

    await repo.insert_intervals(hh, ch_a, [(_ts(0), _ts(20))])
    # 다른 채널 동일 시간 — EXCLUDE 제약은 (가구, 채널) 동일성 전제이므로 OK
    await repo.insert_intervals(hh, ch_b, [(_ts(0), _ts(20))])

    res = await session.execute(
        text(
            "SELECT channel_num, COUNT(*) FROM activity_intervals "
            "WHERE household_id = :h GROUP BY channel_num"
        ),
        {"h": hh},
    )
    counts = {row.channel_num: row[1] for row in res}
    assert counts == {ch_a: 1, ch_b: 1}


async def test_check_constraint_start_lt_end(
    session: AsyncSession, isolated_household
) -> None:
    """``start_ts < end_ts`` CHECK 위반 — IntegrityError."""
    hh, channels = isolated_household
    ch = channels[0]
    repo = ActivityRepository(session)

    with pytest.raises(IntegrityError):
        await repo.insert_intervals(hh, ch, [(_ts(20), _ts(10))])
    await session.rollback()
