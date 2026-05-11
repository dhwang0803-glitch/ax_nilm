"""pytest 공통 픽스처.

전제
----
- IAP 터널이 ``localhost:${LOCAL_PG_PORT}`` 로 활성 상태여야 한다.
  (예: ``gcloud compute start-iap-tunnel ax-nilm-db-dev 5432 --local-host-port=localhost:5436 ...``)
- ``DATABASE_URL`` 가 export 되어 있거나 ``Database/.env`` 에 정의되어야 한다.

격리 전략
---------
실제 DB(공유) 위에서 도는 통합 테스트이므로 가구ID prefix ``H9XX`` 를 격리
공간으로 예약한다. AI Hub 적재 데이터는 ``H001 ~ H110`` 범위만 존재하므로
충돌 없음. 매 테스트가 끝나면 ``isolated_household`` 픽스처가
households 만 삭제 → 의존 테이블(channels/pii/intervals 등) 은 ``ON DELETE
CASCADE`` 로 자동 정리된다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# repo root 를 sys.path 최상단에 추가해 ``from Database.src...`` import 가능.
# Database 가 패키지가 아니므로 (의도) sys.path 주입이 표준 패턴.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ─── .env 자동 로드 (python-dotenv 비의존, 단순 KEY=VALUE 파서) ─────────
_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
if _ENV_PATH.exists():
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        # 이미 셸에서 export 된 값을 덮어쓰지 않는다.
        os.environ.setdefault(k, v)

# APP_PASSWORD 미설정 시 Secret Manager 에서 1회 lazy fetch 시도.
# (gcp_setup.md §4.2 표준 패턴 — 실패 시 조용히 패스, 사용자가 명시 export 가능.)
if not os.environ.get("DATABASE_URL") and not os.environ.get("APP_PASSWORD"):
    secret_name = os.environ.get("SECRET_NAME")
    if secret_name:
        import shutil
        import subprocess

        # Windows 의 ``gcloud`` 는 .cmd wrapper 라 ``subprocess`` 가
        # 그대로 찾지 못한다 → ``shutil.which`` 로 절대 경로 조회.
        gcloud_path = shutil.which("gcloud") or shutil.which("gcloud.cmd")
        if gcloud_path:
            try:
                pwd = subprocess.check_output(
                    [
                        gcloud_path, "secrets", "versions", "access", "latest",
                        f"--secret={secret_name}",
                    ],
                    text=True,
                    stderr=subprocess.DEVNULL,
                    timeout=20,
                ).strip()
                if pwd:
                    os.environ["APP_PASSWORD"] = pwd
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass

# DATABASE_URL 미설정 시 IAP 터널 + .env(LOCAL_PG_PORT/DB_NAME/APP_USER)로 합성.
if not os.environ.get("DATABASE_URL"):
    user = os.environ.get("APP_USER")
    pwd = os.environ.get("APP_PASSWORD")
    port = os.environ.get("LOCAL_PG_PORT", "5436")
    dbname = os.environ.get("DB_NAME")
    if user and pwd and dbname:
        os.environ["DATABASE_URL"] = (
            f"postgresql+asyncpg://{user}:{pwd}@localhost:{port}/{dbname}"
        )


def pytest_collection_modifyitems(config, items):  # noqa: D401
    """DATABASE_URL 미설정이면 모든 통합 테스트 skip."""
    if os.environ.get("DATABASE_URL"):
        return
    skip = pytest.mark.skip(
        reason="DATABASE_URL 미설정 — IAP 터널 활성 후 export 필요"
    )
    for item in items:
        item.add_marker(skip)


# ─── 비동기 세션 스코프 ────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def session() -> AsyncSession:
    """함수 스코프 비동기 세션. 정상 종료 시 commit, 예외 시 rollback."""
    from Database.src.db import dispose_engine, get_session_factory

    factory = get_session_factory()
    s = factory()
    try:
        yield s
        await s.commit()
    except Exception:
        await s.rollback()
        raise
    finally:
        await s.close()
        # 엔진은 모듈 단위로 살려두면 다음 테스트에서 재사용 가능하나, env
        # 변경(예: CREDENTIAL_MASTER_KEY 토글) 테스트 격리를 위해 dispose 는
        # 별도 픽스처(__no_pii_key)에서만 호출.
        del dispose_engine  # noqa: F841 (참조만)


# ─── H9XX 격리 가구 픽스처 ─────────────────────────────────────────────


@pytest_asyncio.fixture()
async def isolated_household(session: AsyncSession):
    """H9XX 격리 영역의 가구 + 채널을 만들고 테스트 종료 시 정리.

    반환값:
        ``(household_id, [channel_num, ...])``

    채널은 기본으로 ``[2 (TV), 6 (WASHER)]`` 두 개를 만든다 — 단순 ON/OFF +
    다중상태 조합이라 NILM 테스트에 두루 쓰기 좋음.
    """
    hh = "H901"
    # 사전 정리(이전 실패 잔여물 대비). CASCADE 로 의존 테이블 동시 삭제.
    await session.execute(
        text("DELETE FROM households WHERE household_id = :h"), {"h": hh}
    )
    await session.execute(
        text(
            "INSERT INTO households (household_id, house_type) VALUES (:h, 'apt')"
        ),
        {"h": hh},
    )
    channels = [(2, "TV"), (6, "WASHER")]
    for ch, code in channels:
        await session.execute(
            text(
                "INSERT INTO household_channels "
                "(household_id, channel_num, appliance_code) "
                "VALUES (:h, :c, :code)"
            ),
            {"h": hh, "c": ch, "code": code},
        )
    await session.commit()

    yield hh, [c for c, _ in channels]

    # 사후 정리. CASCADE 가 channels/pii/intervals/status_intervals 모두 정리.
    await session.execute(
        text("DELETE FROM households WHERE household_id = :h"), {"h": hh}
    )
    await session.commit()
