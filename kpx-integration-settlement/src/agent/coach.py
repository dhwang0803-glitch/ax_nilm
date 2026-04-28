"""전력 에너지 코치 LLM Agent — Tool-use 패턴.

OpenAI GPT-4o-mini function calling 기반 agent loop.
익명화 원칙: household_id만 입력받으며 LLM에 전달하는 모든 데이터는 개인 식별 불가 수준.
트레이스 로그는 logs/traces/{session_id}.json에 저장.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

from openai import OpenAI

from .anonymizer import scrub_tool_output, validate_no_pii
from .data_tools import (
    TOOL_SCHEMAS,
    get_consumption_breakdown,
    get_consumption_hourly,
    get_consumption_summary,
    get_dr_events,
    get_forecast,
    get_household_profile,
    get_tariff_info,
    get_weather,
)
from .trace_logger import TraceLogger

_SYSTEM_PROMPT = """# 퍼르소나
당신은 한국 가정의 전력 절감을 돕는 전문 코치입니다. 사용자의 전력 소비
패턴, 가구 특성, 날씨를 종합해 실행 가능한 절감 권고를 제공합니다.

# 익명화 원칙
- household_id는 익명화된 식별자입니다. 사용자의 실명·주소·연락처를 추론하거나 언급하지 마세요.
- 유사 가구 데이터 인용 시 "유사 가구 평균" 형태로만 언급하고 특정 가구를 식별할 수 있는 정보를 노출하지 마세요.
- 도구에서 반환된 데이터에 개인 식별 정보가 포함된 경우 해당 부분을 무시하고 답변하세요.

# 도구
- get_household_profile(household_id): 가구 정보
- get_weather(date_range, location): 과거 날씨
- get_forecast(days_ahead, location): 일기예보
- get_consumption_summary(household_id, period): 전력 소비 요약
- get_consumption_hourly(household_id, date): 시간대별 소비
- get_consumption_breakdown(household_id, date): 가전별 NILM 분해
- get_dr_events(date_range, region): DR 이벤트
- get_tariff_info(household_id): 요금제

# 원칙
- 답변 전 필요한 정보를 도구로 확인하세요. 추측하지 마세요.
- 권고는 [기대 절감량(kWh/월)], [실행 난이도], [근거] 세 항목으로 구성합니다.
- 의료·위험 관련 권고(예: 난방 완전 끄기)는 하지 마세요.
- 절감 효과가 불확실하면 "추가 데이터가 필요합니다"라고 답하세요.

# 출력 형식
JSON: {"recommendations": [...], "reasoning": "...", "data_used": [...]}"""


def build_baseline_context(household_id: str, location: str = "서울") -> str:
    """세션 시작 시 baseline 컨텍스트를 자연어로 생성 (tool-call 라운드 절약)."""
    profile  = get_household_profile(household_id)
    summary  = get_consumption_summary(household_id, "week")
    tariff   = get_tariff_info(household_id)
    forecast = get_forecast(3, location)

    parts = ["[현재 가구 baseline]"]
    if "summary" in profile:
        parts.append(f"- {profile['summary']}")
    if "summary" in summary:
        parts.append(f"- {summary['summary']}")
    if "summary" in tariff:
        parts.append(f"- {tariff['summary']}")
    if "summary" in forecast:
        parts.append(f"- 향후 3일 예보: {forecast['summary']}")
    parts.append("\n(추가 정보가 필요하면 도구를 사용하세요)")
    return "\n".join(parts)


def _dispatch_tool(name: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """LLM이 호출한 도구 이름을 실제 함수에 라우팅."""
    if name == "get_household_profile":
        return get_household_profile(inputs["household_id"])
    if name == "get_weather":
        return get_weather(inputs["date_range"], inputs.get("location", "서울"))
    if name == "get_forecast":
        return get_forecast(inputs.get("days_ahead", 7), inputs.get("location", "서울"))
    if name == "get_consumption_summary":
        return get_consumption_summary(inputs["household_id"], inputs.get("period", "week"))
    if name == "get_consumption_hourly":
        return get_consumption_hourly(inputs["household_id"], inputs.get("date", "2026-04-27"))
    if name == "get_consumption_breakdown":
        return get_consumption_breakdown(inputs["household_id"], inputs.get("date", "2026-04-27"))
    if name == "get_dr_events":
        return get_dr_events(inputs["date_range"], inputs.get("region", "서울"))
    if name == "get_tariff_info":
        return get_tariff_info(inputs["household_id"])
    return {"error": f"알 수 없는 도구: {name}", "code": "E_UNKNOWN_TOOL"}


def run_coach(
    household_id: str,
    user_message: str,
    location: str = "서울",
    max_iterations: int = 5,
    model: str = "gpt-4o-mini",
    session_id: str | None = None,
    log_dir: str = "logs/traces",
) -> dict[str, Any]:
    """Coach agent loop 실행.

    반환:
      {
        "answer":      dict,           # LLM 최종 JSON 응답
        "tool_calls":  list[dict],     # 트레이스: 호출 도구·인수·결과
        "iterations":  int,
        "session_id":  str,
        "trace_path":  str | None,     # 저장된 트레이스 파일 경로
        "pii_warnings": list[str],     # PII 누출 경고 (있으면 비어 있지 않음)
      }
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY 환경변수 필요")

    sid    = session_id or str(uuid.uuid4())
    tracer = TraceLogger(
        session_id=sid,
        household_token=f"HH-{sid[:8]}",
        log_dir=log_dir,
    )

    client   = OpenAI(api_key=api_key)
    baseline = build_baseline_context(household_id, location)

    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": f"{baseline}\n\n{user_message}"},
    ]

    pii_warnings: list[str] = []
    iterations = 0

    for _ in range(max_iterations):
        iterations += 1
        response = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        choice = response.choices[0]

        if choice.finish_reason != "tool_calls":
            raw_content = choice.message.content or "{}"
            try:
                answer = json.loads(raw_content)
            except json.JSONDecodeError:
                answer = {"raw_text": raw_content}

            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens":     response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens":      response.usage.total_tokens,
                }
            tracer.log_final_answer(answer, usage)
            trace_path = tracer.save()
            return {
                "answer":       answer,
                "tool_calls":   tracer._tool_calls,
                "iterations":   iterations,
                "session_id":   sid,
                "trace_path":   trace_path,
                "pii_warnings": pii_warnings,
            }

        tool_calls = choice.message.tool_calls or []
        if not tool_calls:
            break

        messages.append(choice.message)

        for tc in tool_calls:
            inputs = json.loads(tc.function.arguments)
            raw_result = _dispatch_tool(tc.function.name, inputs)

            # PII 감사 → 스크럽 → LLM 전달
            found_pii = validate_no_pii(raw_result)
            if found_pii:
                pii_warnings.extend(found_pii)
            safe_result = scrub_tool_output(raw_result)

            tracer.log_tool_call(tc.function.name, inputs, safe_result)
            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      json.dumps(safe_result, ensure_ascii=False),
            })

    tracer.log_final_answer({})
    trace_path = tracer.save()
    return {
        "answer":       {},
        "tool_calls":   tracer._tool_calls,
        "iterations":   iterations,
        "session_id":   sid,
        "trace_path":   trace_path,
        "pii_warnings": pii_warnings,
    }
