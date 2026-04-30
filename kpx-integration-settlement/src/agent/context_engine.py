"""컨텍스트 엔지니어링 — 의도 기반 선택적 컨텍스트 주입 + 대화 압축.

의도 분류 → 필요한 도구만 사전 호출해 토큰·지연 절감.
대화가 길어지면 중간 이력을 압축해 컨텍스트 창 관리.
"""
from __future__ import annotations

import re
from typing import Any

from .data_tools import (
    _calc_cashback_potential,
    get_consumption_summary,
    get_forecast,
    get_household_profile,
    get_tariff_info,
)

# 의도별 사전 주입 도구 (agent loop에서 추가 호출 가능)
_INTENT_TOOLS: dict[str, list[str]] = {
    "cashback":    ["profile", "cashback_potential"],
    "tariff":      ["tariff"],
    "consumption": ["summary", "tariff"],
    "weather":     ["forecast"],
    "breakdown":   ["profile", "summary"],
    "profile":     ["profile"],
    "general":     ["profile", "summary", "tariff", "forecast"],
}

_INTENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("cashback",    re.compile(r"캐시백|cashback|절감률|기준선|절감.목표|몇.kWh")),
    ("tariff",      re.compile(r"요금|단계|누진|청구|kWh.*원")),
    ("consumption", re.compile(r"전기.*(?:사용|얼마|썼|소비)|사용량|kWh|전기세")),
    ("weather",     re.compile(r"날씨|기온|비.왔|예보|forecast")),
    ("breakdown",   re.compile(r"가전|에어컨|냉장고|세탁기|냉방|난방|NILM|분해|어떤.*많이")),
    ("profile",     re.compile(r"우리.집|가구.정보|몇.인|몇.평|어떤.가전|집.정보")),
]

_MAX_HISTORY_CHARS = 8_000


def classify_intent(user_message: str) -> str:
    """키워드 패턴 매칭으로 사용자 의도를 분류. 복수 매칭 시 첫 번째 반환."""
    for intent, pattern in _INTENT_PATTERNS:
        if pattern.search(user_message):
            return intent
    return "general"


def build_smart_context(
    household_id: str,
    user_message: str,
    location: str = "서울",
) -> str:
    """의도 기반 선택적 컨텍스트 빌드.

    build_baseline_context 대비 불필요 tool 호출을 줄여 첫 응답 지연 단축.
    """
    intent = classify_intent(user_message)
    tools_needed = _INTENT_TOOLS.get(intent, _INTENT_TOOLS["general"])

    parts = [f"[현재 가구 baseline — 의도: {intent}]"]

    if "profile" in tools_needed:
        result = get_household_profile(household_id)
        if "summary" in result:
            parts.append(f"- {result['summary']}")

    if "summary" in tools_needed:
        result = get_consumption_summary(household_id, "week")
        if "summary" in result:
            parts.append(f"- {result['summary']}")

    if "tariff" in tools_needed:
        result = get_tariff_info(household_id)
        if "summary" in result:
            parts.append(f"- {result['summary']}")

    if "forecast" in tools_needed:
        result = get_forecast(3, location)
        if "summary" in result:
            parts.append(f"- 향후 3일 예보: {result['summary']}")

    if "cashback_potential" in tools_needed:
        result = _calc_cashback_potential(household_id)
        if "summary" in result:
            parts.append(f"- 캐시백 추산: {result['summary']}")

    parts.append("\n(추가 정보가 필요하면 도구를 사용하세요)")
    return "\n".join(parts)


def maybe_compress_messages(
    messages: list[dict[str, Any]],
    max_chars: int = _MAX_HISTORY_CHARS,
) -> list[dict[str, Any]]:
    """총 메시지 문자 수가 max_chars 초과 시 중간 이력을 요약 메시지로 압축.

    system 메시지와 최초 user 메시지(baseline 포함), 마지막 4턴은 항상 보존.
    """
    total = sum(len(str(m.get("content", ""))) for m in messages)
    if total <= max_chars:
        return messages

    system_msgs = [m for m in messages if m["role"] == "system"]
    non_system  = [m for m in messages if m["role"] != "system"]

    preserve_head = non_system[:1]
    preserve_tail = non_system[-4:]
    middle        = non_system[1:-4]

    if not middle:
        return messages

    compressed_text = "[이전 대화 요약] " + " / ".join(
        m["content"][:80]
        for m in middle
        if isinstance(m.get("content"), str) and m["content"]
    )
    return system_msgs + preserve_head + [{"role": "system", "content": compressed_text}] + preserve_tail
