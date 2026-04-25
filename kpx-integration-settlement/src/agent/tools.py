"""LLM Agent 도구 정의.

익명화 원칙: household_id·주소·가구원 수 등 PII는 LLM 입력에서 제외.
전달 허용 필드: temperature, cluster_label, savings_kwh, appliance_code 목록.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    payload: dict[str, Any]


def send_pre_event_notification(message: str) -> ToolResult:
    """DR 이벤트 30분 전 사전 행동 권고 알림 전송."""
    return ToolResult(
        tool_name="send_pre_event_notification",
        success=True,
        payload={"message": message},
    )


def show_savings_result(savings_kwh: float, refund_krw: int) -> ToolResult:
    """이벤트 종료 후 절감량·환급금 결과 표시."""
    return ToolResult(
        tool_name="show_savings_result",
        success=True,
        payload={"savings_kwh": round(savings_kwh, 3), "refund_krw": refund_krw},
    )


def show_enrollment_modal() -> ToolResult:
    """DR 미가입자 대상 가입 유도 팝업 표시."""
    return ToolResult(
        tool_name="show_enrollment_modal",
        success=True,
        payload={},
    )


def recommend_appliance_action(actions: list[dict[str, str]]) -> ToolResult:
    """가전별 행동 제안 표시.

    actions: [{"appliance": "에어컨", "action": "이벤트 30분 전 설정온도 1도 올리기"}, ...]
    """
    return ToolResult(
        tool_name="recommend_appliance_action",
        success=True,
        payload={"actions": actions},
    )


TOOL_SCHEMAS: list[dict] = [
    {
        "name": "send_pre_event_notification",
        "description": "DR 이벤트 시작 전 사용자에게 사전 행동 권고 알림을 전송합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "알림 메시지 (한국어, 200자 이내)"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "show_savings_result",
        "description": "DR 이벤트 종료 후 절감량과 환급금 결과를 사용자에게 표시합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "savings_kwh": {"type": "number", "description": "절감량 (kWh)"},
                "refund_krw": {"type": "integer", "description": "환급 예상 금액 (원)"},
            },
            "required": ["savings_kwh", "refund_krw"],
        },
    },
    {
        "name": "show_enrollment_modal",
        "description": "DR 프로그램 미가입 가구에게 가입 유도 팝업을 표시합니다.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "recommend_appliance_action",
        "description": "가전별 구체적인 DR 행동 방안을 제안합니다.",
        "input_schema": {
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
]
