"""FK 정책 — CASCADE / RESTRICT 검증.

schemas/001~004 가 정의하는 FK 정책:
- households 삭제 → household_pii / household_channels / household_daily_env CASCADE
- household_channels 삭제 → activity_intervals / appliance_status_intervals CASCADE
- appliance_types 삭제 → household_channels 가 RESTRICT (디폴트). 22가전 마스터를
  실수로 지우는 사고 방지.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


pytestmark = pytest.mark.asyncio


def _ts(minute: int) -> datetime:
    return datetime(2030, 3, 1, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=minute)


async def test_household_delete_cascades_to_dependents(
    session: AsyncSession, isolated_household
) -> None:
    """households 삭제 시 channels/pii/daily_env/activity 모두 동시 삭제."""
    hh, channels = isolated_household
    ch = channels[0]

    # 의존 데이터 채우기
    await session.execute(
        text(
            "INSERT INTO household_pii (household_id, income_dual) "
            "VALUES (:h, TRUE)"
        ),
        {"h": hh},
    )
    await session.execute(
        text(
            "INSERT INTO household_daily_env (household_id, observed_date) "
            "VALUES (:h, '2030-03-01')"
        ),
        {"h": hh},
    )
    await session.execute(
        text(
            "INSERT INTO activity_intervals "
            "(household_id, channel_num, start_ts, end_ts) "
            "VALUES (:h, :c, :s, :e)"
        ),
        {"h": hh, "c": ch, "s": _ts(0), "e": _ts(10)},
    )
    await session.commit()

    # 삭제 시 전부 사라져야 함 — isolated_household 픽스처와 같은 경로 검증
    await session.execute(
        text("DELETE FROM households WHERE household_id = :h"), {"h": hh}
    )
    await session.commit()

    for tbl in (
        "household_pii",
        "household_channels",
        "household_daily_env",
        "activity_intervals",
    ):
        res = await session.execute(
            text(f"SELECT COUNT(*) FROM {tbl} WHERE household_id = :h"),
            {"h": hh},
        )
        assert res.scalar_one() == 0, f"{tbl} 가 CASCADE 삭제되지 않음"

    # 픽스처 cleanup 이 다시 households DELETE 를 시도하지만, 이미 사라졌으므로
    # NO-OP. 픽스처는 commit() 만 호출하므로 안전.


async def test_appliance_types_delete_restricted_by_channels(
    session: AsyncSession, isolated_household
) -> None:
    """가구 채널이 참조 중인 appliance_types 삭제 → RESTRICT (IntegrityError)."""
    hh, _channels = isolated_household
    # isolated_household 픽스처에서 TV(ch02) 와 WASHER(ch06) 를 채널로 등록함

    with pytest.raises(IntegrityError):
        await session.execute(
            text("DELETE FROM appliance_types WHERE appliance_code = 'TV'")
        )
    await session.rollback()
