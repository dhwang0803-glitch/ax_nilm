"""NILMInferenceRepository.record_transition — 단일 트랜잭션 보장.

검증 포인트
-----------
1. 첫 호출: 새 구간 INSERT (end_ts NULL).
2. 두 번째 호출: 기존 구간 end_ts 채움 + 새 구간 INSERT — **단일 트랜잭션**.
3. 같은 (가구·채널·model_version) 시간 겹침 INSERT 시 EXCLUDE gist 위반 →
   IntegrityError. (호출자 직렬화 책임 문서화 검증.)
4. 다른 model_version 은 동일 구간 병존 허용 (A/B 평가).
5. confidence 필터 (REQ-001 기본 0.6) 가 get_history 에서 작동.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from Database.src.repositories import NILMInferenceRepository


pytestmark = pytest.mark.asyncio


# 003 seed 의 status_code 가 아닌, migration 07 으로 시드된 코드 사용.
# 0=off, 1=on (모델 팀 확정안 §5.1).
_OFF = 0
_ON = 1


def _ts(minute: int) -> datetime:
    """테스트 시간축: 2030-01-01 00:00 UTC + minute 분."""
    return datetime(2030, 1, 1, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=minute)


async def test_record_transition_first_call_inserts_open_interval(
    session: AsyncSession, isolated_household
) -> None:
    hh, channels = isolated_household
    ch = channels[0]
    repo = NILMInferenceRepository(session)

    new_id = await repo.record_transition(
        household_id=hh,
        channel_num=ch,
        transition_ts=_ts(0),
        new_status=_ON,
        confidence=0.9,
        model_version="cnn_tda_v1.0.0",
    )
    assert new_id > 0

    cur = await repo.get_current_status(hh, ch, "cnn_tda_v1.0.0")
    assert cur is not None
    status, start, conf = cur
    assert status == _ON
    assert start == _ts(0)
    assert conf == pytest.approx(0.9)


async def test_record_transition_closes_previous_and_opens_new(
    session: AsyncSession, isolated_household
) -> None:
    hh, channels = isolated_household
    ch = channels[0]
    repo = NILMInferenceRepository(session)
    mv = "cnn_tda_v1.0.0"

    await repo.record_transition(hh, ch, _ts(0), _ON, 0.9, mv)
    await repo.record_transition(hh, ch, _ts(10), _OFF, 0.85, mv)

    # 두 행 모두 존재 — 첫 행은 end_ts 채워졌고, 둘째는 진행 중.
    res = await session.execute(
        text(
            "SELECT start_ts, end_ts, status_code "
            "FROM appliance_status_intervals "
            "WHERE household_id = :h AND channel_num = :c "
            "ORDER BY start_ts"
        ),
        {"h": hh, "c": ch},
    )
    rows = list(res)
    assert len(rows) == 2
    assert rows[0].end_ts == _ts(10) and rows[0].status_code == _ON
    assert rows[1].end_ts is None and rows[1].status_code == _OFF


async def test_record_transition_overlap_raises_integrity_error(
    session: AsyncSession, isolated_household
) -> None:
    """동일 (가구·채널·model_version) 의 시간 겹침은 EXCLUDE gist 가 차단.

    record_transition 은 기존 열린 구간만 닫으므로, 닫힌 구간과 시간이 겹치는
    transition 을 호출하면 새 INSERT 가 EXCLUDE gist 위반으로 실패한다 → 호출자
    직렬화 책임 문서화의 근거.
    """
    hh, channels = isolated_household
    ch = channels[0]
    repo = NILMInferenceRepository(session)
    mv = "cnn_tda_v1.0.0"

    # 닫힌 구간 [0, 10) 직접 INSERT
    await session.execute(
        text(
            "INSERT INTO appliance_status_intervals "
            "(household_id, channel_num, start_ts, end_ts, status_code, "
            " confidence, model_version) "
            "VALUES (:h, :c, :s, :e, :st, 0.9, :mv)"
        ),
        {"h": hh, "c": ch, "s": _ts(0), "e": _ts(10), "st": _ON, "mv": mv},
    )
    await session.commit()

    # 닫힌 구간과 시간 겹치는 transition 호출 → IntegrityError
    with pytest.raises(IntegrityError):
        await repo.record_transition(hh, ch, _ts(5), _OFF, 0.8, mv)
    await session.rollback()


async def test_record_transition_isolated_per_model_version(
    session: AsyncSession, isolated_household
) -> None:
    """다른 model_version 은 같은 구간 병존 허용 (A/B 평가)."""
    hh, channels = isolated_household
    ch = channels[0]
    repo = NILMInferenceRepository(session)

    await repo.record_transition(hh, ch, _ts(0), _ON, 0.9, "cnn_tda_v1.0.0")
    # 같은 시간 같은 채널이지만 model_version 다름 — 충돌 없어야 함
    await repo.record_transition(hh, ch, _ts(0), _ON, 0.95, "cnn_tda_v2.0.0")

    res = await session.execute(
        text(
            "SELECT model_version FROM appliance_status_intervals "
            "WHERE household_id = :h AND channel_num = :c"
        ),
        {"h": hh, "c": ch},
    )
    versions = sorted(row.model_version for row in res)
    assert versions == ["cnn_tda_v1.0.0", "cnn_tda_v2.0.0"]


async def test_get_history_filters_low_confidence(
    session: AsyncSession, isolated_household
) -> None:
    hh, channels = isolated_household
    ch = channels[0]
    repo = NILMInferenceRepository(session)
    mv = "cnn_tda_v1.0.0"

    await repo.record_transition(hh, ch, _ts(0), _ON, 0.9, mv)  # 통과
    await repo.record_transition(hh, ch, _ts(10), _OFF, 0.4, mv)  # 컷
    await repo.record_transition(hh, ch, _ts(20), _ON, 0.7, mv)  # 통과

    history = await repo.get_history(
        hh, ch, mv, _ts(-1), _ts(100), min_confidence=0.6
    )
    assert len(history) == 2
    assert all(conf >= 0.6 for _, _, _, conf in history)
