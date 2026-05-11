"""PIIRepository — household_pii (Fernet AES-256, BYTEA 저장).

🔒 보안 원칙
    1. Fernet 키는 환경변수 ``CREDENTIAL_MASTER_KEY`` 만으로 주입. 클래스
       초기화 시 키가 없거나 형식 오류면 즉시 실패 (lazy 가 아님 — 운영 시
       암호화 누락 방지).
    2. 평문 PII 는 어떤 경우에도 로그/예외 메시지에 포함하지 않는다.
    3. 본 클래스는 분석 역할의 코드 경로에서 import 금지 — 관리자 전용 API
       엔드포인트에서만 사용.
"""
from __future__ import annotations

import json
import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import HouseholdPII
from .protocols import DecryptedPII


def _load_fernet() -> Fernet:
    key = os.getenv("CREDENTIAL_MASTER_KEY")
    if not key:
        raise RuntimeError(
            "CREDENTIAL_MASTER_KEY 환경변수가 비어 있습니다 — PII 암호화 비활성. "
            "운영 환경에서 PIIRepository 를 인스턴스화하기 전에 반드시 설정."
        )
    try:
        return Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        # Fernet 키 형식 오류 — 평문 노출 방지를 위해 원본 메시지 그대로
        # 누설하지 않고 일반화.
        raise RuntimeError("CREDENTIAL_MASTER_KEY 형식 오류 (Fernet base64 32B 필요).") from exc


class PIIRepository:
    """🔒 권한 분리 — 본 클래스를 분석 역할 코드에서 사용 금지."""

    def __init__(self, session: AsyncSession, fernet: Fernet | None = None) -> None:
        self._s = session
        self._fernet = fernet or _load_fernet()

    # ─── 암호화 helpers (평문 노출 차단) ─────────────────────────────
    def _enc_str(self, value: str | None) -> bytes | None:
        if value is None:
            return None
        return self._fernet.encrypt(value.encode("utf-8"))

    def _dec_str(self, blob: bytes | None) -> str | None:
        if blob is None:
            return None
        try:
            return self._fernet.decrypt(blob).decode("utf-8")
        except InvalidToken:
            # 키 회전 등으로 복호화 실패 — 평문 추론 막기 위해 None 반환.
            return None

    # ─── upsert / get ───────────────────────────────────────────────
    async def upsert_encrypted(
        self,
        household_id: str,
        address: str | None,
        members: str | None,
        income_dual: bool | None,
        utility_facilities: list[str] | None,
        extra_appliances: list[str] | None,
    ) -> None:
        # members 가 dict/list 인 경우 호출 측에서 직렬화 후 전달하라는
        # 가이드. 본 메서드는 str | None 만 받음 — JSON 형태가 자연스러우면
        # 호출 측에서 json.dumps 해서 넘긴다.
        stmt = pg_insert(HouseholdPII).values(
            household_id=household_id,
            address_enc=self._enc_str(address),
            members_enc=self._enc_str(members),
            income_dual=income_dual,
            utility_facilities=utility_facilities,
            extra_appliances=extra_appliances,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["household_id"],
            set_={
                "address_enc": stmt.excluded.address_enc,
                "members_enc": stmt.excluded.members_enc,
                "income_dual": stmt.excluded.income_dual,
                "utility_facilities": stmt.excluded.utility_facilities,
                "extra_appliances": stmt.excluded.extra_appliances,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self._s.execute(stmt)

    async def get_decrypted(self, household_id: str) -> DecryptedPII | None:
        row = await self._s.get(HouseholdPII, household_id)
        if row is None:
            return None
        return DecryptedPII(
            household_id=row.household_id,
            address=self._dec_str(row.address_enc),
            members=self._dec_str(row.members_enc),
            income_dual=row.income_dual,
            utility_facilities=row.utility_facilities,
            extra_appliances=row.extra_appliances,
        )
