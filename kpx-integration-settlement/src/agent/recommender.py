"""LLM Agent — 에너지캐시백 월별 절감 권고.

OpenAI GPT-4o-mini API 사용 (function calling 기반 agent loop).
익명화 원칙: household_id·주소·가구원·소득 정보 LLM 입력 제외.
허용 입력: temperature, cluster_label, 절감률, 가전 목록, 유사 달 맥락.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date

from openai import OpenAI

from .tools import (
    TOOL_SCHEMAS,
    ToolResult,
    recommend_appliance_action,
    show_cashback_result,
    show_enrollment_cta,
    show_monthly_trend,
)


@dataclass
class RecommendContext:
    cluster_label: int             # 0=저소비 1=고소비 2=중소비
    cashback_enrolled: bool        # 에너지캐시백 신청 여부
    billing_month: date            # 정산 기준 월
    baseline_kwh: float            # 기준선
    actual_kwh: float              # 이번 달 실측
    savings_rate: float            # 절감률 (0.0~1.0)
    cashback_krw: int              # 캐시백 예상 금액
    temperature: float | None      # 월평균 기온
    top_saving_appliances: list[str] = field(default_factory=list)  # 절감 기여 상위 가전
    top_usage_appliances: list[str]  = field(default_factory=list)  # 사용량 상위 가전
    similar_months_text: str = ""    # RAG 유사 달 패턴
    recent_months: list[str] = field(default_factory=list)           # 최근 월 목록
    recent_savings_rates: list[float] = field(default_factory=list)  # 최근 월 절감률


_CLUSTER_DESC = {0: "저소비형", 1: "고소비형", 2: "중소비형"}

_SYSTEM_PROMPT = """당신은 가정용 에너지캐시백 절감을 돕는 에너지 효율화 어시스턴트입니다.
제공된 전력 소비 패턴과 기상 데이터를 바탕으로 구체적이고 실행 가능한 절감 방안을 제안하세요.
개인 식별 정보는 입력되지 않으며, 익명화된 소비 패턴만 사용합니다."""


def _build_user_prompt(ctx: RecommendContext) -> str:
    cluster_name = _CLUSTER_DESC.get(ctx.cluster_label, "알 수 없음")
    savings_pct  = ctx.savings_rate * 100

    lines = [
        f"소비 유형: {cluster_name}",
        f"기준월: {ctx.billing_month.strftime('%Y년 %m월')}",
        f"기준선: {ctx.baseline_kwh:.1f}kWh / 실측: {ctx.actual_kwh:.1f}kWh",
        f"절감률: {savings_pct:.1f}% / 예상 캐시백: {ctx.cashback_krw:,}원",
    ]
    if ctx.temperature is not None:
        lines.append(f"월평균 기온: {ctx.temperature:.1f}도")
    if ctx.top_saving_appliances:
        lines.append(f"이번 달 절감 기여 가전: {', '.join(ctx.top_saving_appliances)}")
    if ctx.top_usage_appliances:
        lines.append(f"이번 달 사용량 상위 가전: {', '.join(ctx.top_usage_appliances)}")
    if ctx.similar_months_text:
        lines.append(f"\n[유사 달 패턴]\n{ctx.similar_months_text}")

    if ctx.cashback_enrolled:
        lines.append(
            "\n이 가구는 에너지캐시백에 신청되어 있습니다. "
            "이번 달 결과를 보여주고 다음 달 절감을 위한 가전별 행동 방안을 제안해주세요."
        )
    else:
        lines.append(
            "\n이 가구는 에너지캐시백 미신청 상태입니다. "
            "신청 유도 메시지를 먼저 보여주세요."
        )

    return "\n".join(lines)


def _dispatch_tool(name: str, inputs: dict) -> ToolResult:
    if name == "show_cashback_result":
        return show_cashback_result(inputs["savings_kwh"], inputs["cashback_krw"])
    if name == "show_enrollment_cta":
        return show_enrollment_cta(inputs.get("enrollment_url"))
    if name == "recommend_appliance_action":
        return recommend_appliance_action(inputs["actions"])
    if name == "show_monthly_trend":
        return show_monthly_trend(inputs["months"], inputs["savings_rates"])
    raise ValueError(f"알 수 없는 도구: {name}")


def run_recommendation(
    ctx: RecommendContext,
    max_iterations: int = 5,
) -> list[ToolResult]:
    """Agent loop 실행 — 도구 호출 결과 목록 반환."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY 환경변수 필요")

    client = OpenAI(api_key=api_key)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": _build_user_prompt(ctx)},
    ]
    results: list[ToolResult] = []

    for _ in range(max_iterations):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1024,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        choice = response.choices[0]
        if choice.finish_reason != "tool_calls":
            break

        tool_calls = choice.message.tool_calls or []
        if not tool_calls:
            break

        messages.append(choice.message)

        for tc in tool_calls:
            inputs = json.loads(tc.function.arguments)
            result = _dispatch_tool(tc.function.name, inputs)
            results.append(result)
            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      json.dumps(result.payload, ensure_ascii=False),
            })

    return results
