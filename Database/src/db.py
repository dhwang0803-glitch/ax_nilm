"""비동기 엔진 / 세션 부트스트랩.

환경변수만으로 구성하며, 코드 내부에 자격증명을 절대 두지 않는다 (루트
CLAUDE.md 보안 규칙). 단일 프로세스에서 엔진은 1회만 생성하고 세션은
요청/작업 단위로 발급한다.

환경변수
--------
DATABASE_URL
    asyncpg DSN. 예: ``postgresql+asyncpg://user:pwd@host:5432/ax_nilm``.
    미설정 시 ``RuntimeError`` 로 즉시 실패해 운영 누락을 막는다.
DATABASE_ECHO
    "1" 이면 SQL 로그 출력 (개발 환경 한정).
DATABASE_POOL_SIZE / DATABASE_POOL_OVERFLOW
    기본 10 / 5. 10K 가구 트래픽 가정 시 상향.

사용 예
--------
.. code-block:: python

    from Database.src.db import session_scope

    async with session_scope() as session:
        repo = PowerRepository(session)
        rows = await repo.get_recent_minutes("H001", 1, hours=1)
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# pgvector SQLAlchemy 통합. 모듈 임포트만으로 SQLAlchemy 어댑터 등록 효과를
# 보장하기 위해 db.py 에서 강제 로드한다 (모델 모듈에서만 import 하면 사용
# 직전까지 등록 누락 가능).
from pgvector.sqlalchemy import Vector  # noqa: F401  (side-effect import)


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _read_env_dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "DATABASE_URL 환경변수가 설정되지 않았습니다. "
            "예: postgresql+asyncpg://user:pwd@host:5432/ax_nilm"
        )
    if "+asyncpg" not in dsn:
        # 동기 드라이버 DSN 으로 비동기 엔진을 만들면 부팅 시점이 아닌 첫
        # 쿼리에서 에러가 터져 디버깅이 어렵다 → 부팅에서 막는다.
        raise RuntimeError(
            "DATABASE_URL 은 asyncpg 드라이버를 지정해야 합니다 "
            "(postgresql+asyncpg://...)."
        )
    return dsn


def get_engine() -> AsyncEngine:
    """프로세스 단일 엔진을 lazy 생성.

    pytest 등에서 환경변수를 동적으로 바꾸는 경우 ``dispose_engine()`` 으로
    명시적 폐기 후 재생성한다.
    """
    global _engine, _session_factory
    if _engine is not None:
        return _engine

    pool_size = int(os.getenv("DATABASE_POOL_SIZE", "10"))
    pool_overflow = int(os.getenv("DATABASE_POOL_OVERFLOW", "5"))
    echo = os.getenv("DATABASE_ECHO") == "1"

    _engine = create_async_engine(
        _read_env_dsn(),
        echo=echo,
        pool_size=pool_size,
        max_overflow=pool_overflow,
        pool_pre_ping=True,  # 죽은 커넥션 자동 폐기 — Timescale 서버 재시작 대응
    )
    _session_factory = async_sessionmaker(
        _engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """트랜잭션 스코프 세션. 정상 종료 commit, 예외 시 rollback."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def dispose_engine() -> None:
    """엔진/세션팩토리 폐기 — 테스트 간 격리 또는 graceful shutdown 용."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
