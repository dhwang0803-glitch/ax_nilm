"""스모크 테스트 — 확장/시드/마이그레이션 적용 상태 검증.

목적
----
새 환경(개발 머신, CI 컨테이너) 에서 DB 부트스트랩이 모두 정상인지 한 번에
확인. 이후 Repository 단위 테스트는 모두 본 스모크가 통과한 상태를 전제로 함.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


pytestmark = pytest.mark.asyncio


async def test_extensions_loaded(session: AsyncSession) -> None:
    res = await session.execute(
        text(
            "SELECT extname FROM pg_extension "
            "WHERE extname IN ('timescaledb', 'btree_gist', 'vector')"
        )
    )
    names = {row.extname for row in res}
    assert names == {"timescaledb", "btree_gist", "vector"}, names


async def test_appliance_types_seed(session: AsyncSession) -> None:
    """003_seed: ch01 메인 + ch02~ch23 22가전 = 23행."""
    res = await session.execute(text("SELECT COUNT(*) FROM appliance_types"))
    assert res.scalar_one() == 23


async def test_appliance_types_nilm_label_index_backfilled(
    session: AsyncSession,
) -> None:
    """migration 06: nilm_label_index 컬럼 백필 — 모델 인덱스 0~21 (22 행).
    MAIN 행만 NULL (모델 출력 인덱스 없음).
    """
    res = await session.execute(
        text(
            "SELECT COUNT(*) FROM appliance_types "
            "WHERE nilm_label_index IS NOT NULL"
        )
    )
    assert res.scalar_one() == 22

    res = await session.execute(
        text("SELECT nilm_label_index FROM appliance_types WHERE appliance_code = 'MAIN'")
    )
    assert res.scalar_one() is None

    # 인덱스 유일성 (UNIQUE NULL 허용)
    res = await session.execute(
        text(
            "SELECT COUNT(DISTINCT nilm_label_index) FROM appliance_types "
            "WHERE nilm_label_index IS NOT NULL"
        )
    )
    assert res.scalar_one() == 22


async def test_appliance_status_codes_seed(session: AsyncSession) -> None:
    """migration 07: 모델 팀 확정 12개 코드."""
    res = await session.execute(text("SELECT COUNT(*) FROM appliance_status_codes"))
    assert res.scalar_one() == 12


async def test_aggregators_seed(session: AsyncSession) -> None:
    """migration 01 + KPX seed: 3개 (PARAN/BYUKSAN/LG)."""
    res = await session.execute(
        text("SELECT aggregator_id FROM aggregators ORDER BY aggregator_id")
    )
    ids = [row.aggregator_id for row in res]
    assert ids == ["AGG_BYUKSAN", "AGG_LG", "AGG_PARAN"]


async def test_power_1min_is_hypertable(session: AsyncSession) -> None:
    """002 schema: TimescaleDB hypertable 등록 확인."""
    res = await session.execute(
        text(
            "SELECT 1 FROM timescaledb_information.hypertables "
            "WHERE hypertable_name = 'power_1min'"
        )
    )
    assert res.scalar() == 1


async def test_power_1hour_is_continuous_aggregate(session: AsyncSession) -> None:
    """002 schema: power_1hour 가 continuous aggregate (cagg) 인지."""
    res = await session.execute(
        text(
            "SELECT 1 FROM timescaledb_information.continuous_aggregates "
            "WHERE view_name = 'power_1hour'"
        )
    )
    assert res.scalar() == 1


async def test_phase_b_data_loaded(session: AsyncSession) -> None:
    """Phase B-1 / B-5 적재 결과 sanity check.
    79 가구 메타 + 7M+ 1분 행. 회귀 안전망 — 레코드가 실종됐다면 즉시 알림.
    """
    res = await session.execute(text("SELECT COUNT(*) FROM households"))
    assert res.scalar_one() >= 79

    res = await session.execute(text("SELECT COUNT(*) FROM power_1min"))
    # dev10 적재 7,499,520 rows. 이후 추가 적재 가능성 있어 하한만 검증.
    assert res.scalar_one() >= 7_499_520
