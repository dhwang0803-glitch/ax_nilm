"""PIIRepository — Fernet 라운드트립 + env 강제.

검증 포인트
-----------
1. ``CREDENTIAL_MASTER_KEY`` 미설정 → 인스턴스화 즉시 실패 (lazy 가 아님).
2. 형식 오류 키 → ``RuntimeError`` (원본 ``ValueError`` 메시지 누설 안 함).
3. 정상 키 → upsert/get 라운드트립 평문 일치.
4. address/members BYTEA 컬럼은 평문 문자열을 절대 포함하지 않음 (DB 저장이 정말
   암호화돼있는지 직접 확인).
"""
from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from Database.src.repositories import PIIRepository


pytestmark = pytest.mark.asyncio


async def test_missing_master_key_raises(
    session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.delenv("CREDENTIAL_MASTER_KEY", raising=False)
    with pytest.raises(RuntimeError, match="CREDENTIAL_MASTER_KEY"):
        PIIRepository(session)


async def test_malformed_master_key_raises(
    session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setenv("CREDENTIAL_MASTER_KEY", "not-a-fernet-key")
    with pytest.raises(RuntimeError, match="형식 오류"):
        PIIRepository(session)


async def test_encryption_roundtrip(
    session: AsyncSession, isolated_household, monkeypatch
) -> None:
    hh, _ = isolated_household
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("CREDENTIAL_MASTER_KEY", key)

    repo = PIIRepository(session)
    await repo.upsert_encrypted(
        household_id=hh,
        address="서울시 강남구 테헤란로 1",
        members='{"adults": 2, "kids": 1}',
        income_dual=True,
        utility_facilities=["gas", "elec"],
        extra_appliances=["smart_speaker"],
    )
    await session.commit()

    # 평문 라운드트립
    got = await repo.get_decrypted(hh)
    assert got is not None
    assert got.address == "서울시 강남구 테헤란로 1"
    assert got.members == '{"adults": 2, "kids": 1}'
    assert got.income_dual is True
    assert got.utility_facilities == ["gas", "elec"]
    assert got.extra_appliances == ["smart_speaker"]

    # BYTEA 에 평문이 절대 들어가지 않음 (Fernet ciphertext)
    res = await session.execute(
        text(
            "SELECT address_enc, members_enc FROM household_pii "
            "WHERE household_id = :h"
        ),
        {"h": hh},
    )
    row = res.first()
    assert row is not None
    assert b"\xed\x84\xb0\xed\x97\xa4\xeb\x9e\x80" not in row.address_enc, (
        "address_enc 에 한글 평문(테헤란) 흔적이 보임 — 암호화 실패"
    )
    assert b"adults" not in row.members_enc, (
        "members_enc 에 평문 키 흔적이 보임 — 암호화 실패"
    )
    # Fernet 토큰은 base64 url-safe 로 시작 → "gAAAAAB" 패턴
    assert row.address_enc.startswith(b"gAAAAAB")
    assert row.members_enc.startswith(b"gAAAAAB")


async def test_wrong_key_returns_none_not_garbage(
    session: AsyncSession, isolated_household, monkeypatch
) -> None:
    """키 회전 등으로 복호화 실패 시 평문 추론 막기 위해 None 반환."""
    hh, _ = isolated_household

    # 1) key A 로 INSERT
    key_a = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("CREDENTIAL_MASTER_KEY", key_a)
    repo_a = PIIRepository(session)
    await repo_a.upsert_encrypted(
        household_id=hh,
        address="민감주소",
        members=None,
        income_dual=None,
        utility_facilities=None,
        extra_appliances=None,
    )
    await session.commit()

    # 2) key B 로 SELECT → InvalidToken → None
    key_b = Fernet.generate_key().decode("utf-8")
    assert key_a != key_b
    monkeypatch.setenv("CREDENTIAL_MASTER_KEY", key_b)
    repo_b = PIIRepository(session)
    got = await repo_b.get_decrypted(hh)
    assert got is not None
    assert got.address is None  # 복호화 실패 → None (평문 노출 차단)
