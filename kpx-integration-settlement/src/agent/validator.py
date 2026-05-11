"""답변 검증 하네스 — 스키마 검사 + tool 결과 교차 검증.

스키마 검사: 필수 키(recommendations, reasoning, data_used) 존재 여부.
교차 검증: 답변에 등장하는 3자리 이상 수치가 tool 반환 데이터에서 확인 가능한지 경고.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_REQUIRED_KEYS: frozenset[str] = frozenset({"recommendations", "reasoning", "data_used"})
_NUMBER_RE = re.compile(r"\b\d+(?:[,.]\d+)?\b")


@dataclass
class ValidationResult:
    passed: bool                                  # 스키마 에러 없으면 True
    schema_errors: list[str] = field(default_factory=list)
    cross_warnings: list[str] = field(default_factory=list)

    @property
    def warnings(self) -> list[str]:
        return self.schema_errors + self.cross_warnings

    def __str__(self) -> str:
        if self.passed and not self.cross_warnings:
            return "검증 통과"
        lines = ["검증 결과:"]
        for w in self.warnings:
            lines.append(f"  ⚠ {w}")
        return "\n".join(lines)


def _extract_numbers(text: str) -> set[str]:
    """텍스트에서 숫자 토큰 추출 (쉼표·점 포함)."""
    return set(_NUMBER_RE.findall(text))


def validate_answer(
    answer: dict[str, Any],
    tool_results: list[dict[str, Any]] | None = None,
) -> ValidationResult:
    """answer dict의 스키마 검사 및 tool 결과와의 수치 교차 검증.

    Args:
        answer:       LLM 최종 응답 dict.
        tool_results: 해당 세션에서 호출된 tool 원본 결과 목록.

    Returns:
        ValidationResult — passed=False 이면 schema_errors 에 원인 기재.
    """
    schema_errors: list[str] = []
    cross_warnings: list[str] = []

    # 1. 필수 키 검사
    for key in _REQUIRED_KEYS:
        if key not in answer:
            schema_errors.append(f"필수 키 누락: '{key}'")

    recommendations = answer.get("recommendations", [])
    if not isinstance(recommendations, list):
        schema_errors.append("'recommendations'가 list 타입이어야 합니다")
    elif len(recommendations) == 0 and "raw_text" not in answer:
        schema_errors.append("'recommendations'가 비어 있습니다")

    # 2. tool 결과 교차 검증
    if tool_results:
        tool_number_pool = set()
        for r in tool_results:
            tool_number_pool |= _extract_numbers(str(r))

        answer_numbers = _extract_numbers(str(answer))
        # 3자리 이상 수치 중 tool 결과에 없는 것 경고
        unverified = {
            n for n in answer_numbers
            if len(n.replace(",", "").replace(".", "")) >= 3
            and n not in tool_number_pool
        }
        if unverified:
            cross_warnings.append(
                f"tool 결과로 확인되지 않은 수치: {', '.join(sorted(unverified))}"
            )

    return ValidationResult(
        passed=len(schema_errors) == 0,
        schema_errors=schema_errors,
        cross_warnings=cross_warnings,
    )
