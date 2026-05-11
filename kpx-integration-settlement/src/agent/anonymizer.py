"""PII 스크러버 — tool 반환값에서 개인 식별 정보 제거 후 LLM 전달.

실데이터 연결(4주차) 전에도 파이프라인을 통과시켜 PII 누출 방지 습관을 강제.
익명화 원칙: household_id 이외 개인 식별 정보는 LLM 및 로그에 전달 금지.
"""
from __future__ import annotations

import copy
from typing import Any

# LLM·로그에 절대 전달해선 안 되는 필드명
_PII_FIELDS: frozenset[str] = frozenset({
    "real_name",
    "owner_name",
    "address",
    "real_address",
    "phone",
    "phone_number",
    "mobile",
    "email",
    "resident_id",
    "resident_number",
    "ssn",
    "birth_date",
    "birthday",
    "passport_no",
})


def _scrub_value(value: Any) -> Any:
    """재귀적으로 dict·list를 순회하며 PII 필드를 "[REDACTED]"로 교체."""
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if k in _PII_FIELDS else _scrub_value(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    return value


def scrub_tool_output(result: dict[str, Any]) -> dict[str, Any]:
    """tool 반환 dict의 PII 필드를 제거한 복사본 반환.

    원본 dict는 수정하지 않음 (deep copy 후 scrub).
    """
    return _scrub_value(copy.deepcopy(result))


def validate_no_pii(result: dict[str, Any]) -> list[str]:
    """result 안에 PII 필드가 있으면 필드명 목록 반환, 없으면 빈 리스트.

    사전 감사용 — 로그 저장 전에 호출해 PII 잔존 여부를 확인.
    """
    found: list[str] = []
    _collect_pii_keys(result, found)
    return found


def _collect_pii_keys(value: Any, found: list[str]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if k in _PII_FIELDS:
                found.append(k)
            else:
                _collect_pii_keys(v, found)
    elif isinstance(value, list):
        for item in value:
            _collect_pii_keys(item, found)
