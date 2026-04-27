"""LLM Agent 도구 정의 — 에너지캐시백 월별 절감 권고.

익명화 원칙: household_id·주소·가구원 수 등 PII는 LLM 입력에서 제외.
전달 허용 필드: temperature, cluster_label, savings_kwh, cashback_krw, appliance_code 목록.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

CASHBACK_ENROLLMENT_URL = os.getenv(
    "DR_ENROLLMENT_URL",
    "https://en-ter.co.kr/ec/apply/prsApply/select.do",
)


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    payload: dict[str, Any]


def show_cashback_result(savings_kwh: float, cashback_krw: int) -> ToolResult:
    """이번 달 절감량·캐시백 금액 결과 표시."""
    return ToolResult(
        tool_name="show_cashback_result",
        success=True,
        payload={"savings_kwh": round(savings_kwh, 3), "cashback_krw": cashback_krw},
    )


def show_enrollment_cta(enrollment_url: str | None = None) -> ToolResult:
    """에너지캐시백 미신청 가구 대상 신청 유도 CTA 표시."""
    return ToolResult(
        tool_name="show_enrollment_cta",
        success=True,
        payload={"enrollment_url": enrollment_url or CASHBACK_ENROLLMENT_URL},
    )


def recommend_appliance_action(actions: list[dict[str, str]]) -> ToolResult:
    """가전별 구체적인 절감 행동 방안 표시.

    actions: [{"appliance": "에어컨", "action": "설정온도 1도 높이기"}, ...]
    """
    return ToolResult(
        tool_name="recommend_appliance_action",
        success=True,
        payload={"actions": actions},
    )


def show_monthly_trend(months: list[str], savings_rates: list[float]) -> ToolResult:
    """월별 절감률 추이 차트 표시.

    months:        ["2025-04", "2025-05", "2025-06"]
    savings_rates: [0.05, 0.08, 0.12]
    """
    return ToolResult(
        tool_name="show_monthly_trend",
        success=True,
        payload={"months": months, "savings_rates": savings_rates},
    )


TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "show_cashback_result",
            "description": "이번 달 에너지 절감량과 캐시백 예상 금액을 사용자에게 표시합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "savings_kwh": {"type": "number", "description": "절감량 (kWh)"},
                    "cashback_krw": {"type": "integer", "description": "캐시백 예상 금액 (원)"},
                },
                "required": ["savings_kwh", "cashback_krw"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_enrollment_cta",
            "description": "에너지캐시백을 신청하지 않은 가구에게 신청 유도 버튼을 표시합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "enrollment_url": {
                        "type": "string",
                        "description": "신청 페이지 URL (생략 시 기본값 사용)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_appliance_action",
            "description": "가전별 구체적인 에너지 절감 행동 방안을 제안합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "appliance": {"type": "string"},
                                "action":    {"type": "string"},
                            },
                            "required": ["appliance", "action"],
                        },
                    },
                },
                "required": ["actions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_monthly_trend",
            "description": "최근 월별 절감률 추이 차트를 표시합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "months": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "월 목록 (YYYY-MM 형식)",
                    },
                    "savings_rates": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "월별 절감률 (0.0~1.0)",
                    },
                },
                "required": ["months", "savings_rates"],
            },
        },
    },
]
