"""LLM Agent — DR 참여 옵션 추천.

Anthropic Claude API 사용 (tool_use 기반 agent loop).
익명화 원칙: household_id·주소·가구원·소득 정보 LLM 입력 제외.
허용 입력: temperature, cluster_label, event 구간, 예측 절감량, 가전 목록, 유사 날 맥락.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

import anthropic

from .tools import (
    TOOL_SCHEMAS,
    ToolResult,
    recommend_appliance_action,
    send_pre_event_notification,
    show_enrollment_modal,
    show_savings_result,
)


@dataclass
class RecommendContext:
    cluster_label: int           # 0=저소비 1=고소비 2=중소비
    dr_enrolled: bool
    event_start: datetime
    event_end: datetime
    temperature: float | None
    humidity: float | None
    predicted_savings_kwh: float
    top_appliances: list[str]    # DR 가능 가전 목록 (appliance_code)
    similar_days_text: str       # RAG 검색 결과 텍스트


_CLUSTER_DESC = {0: "저소비형", 1: "고소비형", 2: "중소비형"}

_SYSTEM_PROMPT = """당신은 가정용 DR(수요반응) 참여를 돕는 에너지 절감 어시스턴트입니다.
제공된 전력 소비 패턴과 기상 데이터를 바탕으로 구체적이고 실행 가능한 행동 방안을 제안하세요.
개인 식별 정보는 입력되지 않으며, 익명화된 소비 패턴만 사용합니다."""


def _build_user_prompt(ctx: RecommendContext) -> str:
    cluster_name = _CLUSTER_DESC.get(ctx.cluster_label, "알 수 없음")
    event_range  = f"{ctx.event_start.strftime('%H:%M')}~{ctx.event_end.strftime('%H:%M')}"

    lines = [
        f"소비 유형: {cluster_name}",
        f"DR 이벤트 구간: {event_range}",
        f"예측 절감 가능량: {ctx.predicted_savings_kwh:.2f}kWh",
        f"DR 참여 가능 가전: {', '.join(ctx.top_appliances) if ctx.top_appliances else '없음'}",
    ]
    if ctx.temperature is not None:
        lines.append(f"현재 기온: {ctx.temperature:.1f}도")
    if ctx.humidity is not None:
        lines.append(f"현재 습도: {ctx.humidity:.1f}%")
    if ctx.similar_days_text:
        lines.append(f"\n[유사 날 패턴]\n{ctx.similar_days_text}")

    if ctx.dr_enrolled:
        lines.append("\n이 가구는 DR 프로그램에 가입되어 있습니다. 사전 알림과 가전별 행동 방안을 제안해주세요.")
    else:
        lines.append("\n이 가구는 DR 프로그램에 미가입 상태입니다. 가입 유도 메시지를 먼저 표시해주세요.")

    return "\n".join(lines)


def _dispatch_tool(name: str, inputs: dict) -> ToolResult:
    if name == "send_pre_event_notification":
        return send_pre_event_notification(inputs["message"])
    if name == "show_savings_result":
        return show_savings_result(inputs["savings_kwh"], inputs["refund_krw"])
    if name == "show_enrollment_modal":
        return show_enrollment_modal()
    if name == "recommend_appliance_action":
        return recommend_appliance_action(inputs["actions"])
    raise ValueError(f"알 수 없는 도구: {name}")


async def run_recommendation(
    ctx: RecommendContext,
    max_iterations: int = 5,
) -> list[ToolResult]:
    """Agent loop 실행 — 도구 호출 결과 목록 반환."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY 환경변수 필요")

    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": _build_user_prompt(ctx)}]
    results: list[ToolResult] = []

    for _ in range(max_iterations):
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            break

        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if not tool_calls:
            break

        tool_results_content = []
        for tc in tool_calls:
            result = _dispatch_tool(tc.name, tc.input)
            results.append(result)
            tool_results_content.append({
                "type":        "tool_result",
                "tool_use_id": tc.id,
                "content":     str(result.payload),
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user",      "content": tool_results_content})

    return results
