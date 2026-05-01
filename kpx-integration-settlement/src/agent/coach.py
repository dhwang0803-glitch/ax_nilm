"""전력 에너지 코치 LLM Agent.

기본: LangGraph 슈퍼바이저 멀티에이전트 (graph.py).
폴백: OpenAI function calling 단일 루프 (use_graph=False).

익명화 원칙: household_id만 입력받으며 LLM에 전달하는 모든 데이터는 개인 식별 불가 수준.
트레이스 로그는 logs/traces/{session_id}.json에 저장.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any, Callable

from openai import OpenAI

from .anonymizer import scrub_tool_output, validate_no_pii
from .context_engine import build_smart_context, maybe_compress_messages
from .data_tools import (
    TOOL_SCHEMAS,
    get_anomaly_events,
    get_anomaly_log,
    get_cashback_history,
    get_consumption_summary,
    get_dashboard_summary,
    get_forecast,
    get_hourly_appliance_breakdown,
    get_household_profile,
    get_tariff_info,
    get_weather,
)
from .trace_logger import TraceLogger
from .validator import validate_answer

# HITL 콜백: ("before_tool" | "before_answer", 페이로드) → True 계속, False 중단
HitlCallback = Callable[[str, dict[str, Any]], bool]

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
- get_consumption_summary(household_id, period): 전력 소비 요약 (주간·월간·연간)
- get_cashback_history(household_id, date_range): 에너지캐시백 월별 절감 실적·지급 내역
- get_tariff_info(household_id): 요금제·누진 단계·예상 청구액
- get_dashboard_summary(household_id, month): 홈 대시보드 요약 — 월간 사용량·캐시백 추정(상세 포함)·알림 수 한 번에 조회
- get_anomaly_events(household_id, status): 현재 활성 이상감지 이벤트 목록 (/insights 화면)
- get_anomaly_log(household_id, date_range, severity, appliance): 이상감지 이력 조회·필터 (/settings/anomaly-log 화면)
- get_hourly_appliance_breakdown(household_id, date): 24시간 × 가전별 kWh 행렬 + 가전별 일일 총량·점유율·가동 시간대

# 원칙
- 답변 전 필요한 정보를 도구로 확인하세요. 추측하지 마세요.
- 권고는 [기대 절감량(kWh/월)], [실행 난이도], [근거] 세 항목으로 구성합니다.
- 의료·위험 관련 권고(예: 난방 완전 끄기)는 하지 마세요.
- 절감 효과가 불확실하면 "추가 데이터가 필요합니다"라고 답하세요.

# 출력 형식
JSON: {"recommendations": [...], "reasoning": "...", "data_used": [...]}"""


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
    if name == "get_cashback_history":
        return get_cashback_history(inputs["household_id"], inputs.get("date_range"))
    if name == "get_tariff_info":
        return get_tariff_info(inputs["household_id"])
    if name == "get_dashboard_summary":
        return get_dashboard_summary(inputs["household_id"], inputs.get("month", "2026-04"))
    if name == "get_anomaly_events":
        return get_anomaly_events(inputs["household_id"], inputs.get("status", "active"))
    if name == "get_anomaly_log":
        return get_anomaly_log(
            inputs["household_id"],
            inputs.get("date_range"),
            inputs.get("severity", "all"),
            inputs.get("appliance"),
        )
    if name == "get_hourly_appliance_breakdown":
        return get_hourly_appliance_breakdown(inputs["household_id"], inputs.get("date", "2026-04-27"))
    return {"error": f"알 수 없는 도구: {name}", "code": "E_UNKNOWN_TOOL"}


def run_coach(
    household_id: str,
    user_message: str,
    location: str = "서울",
    max_iterations: int = 5,
    model: str = "gpt-4o-mini",
    session_id: str | None = None,
    log_dir: str = "logs/traces",
    hitl_callback: HitlCallback | None = None,
    use_graph: bool = True,
) -> dict[str, Any]:
    """Coach agent 실행.

    use_graph=True(기본): LangGraph 슈퍼바이저 멀티에이전트 사용.
    use_graph=False: 기존 OpenAI function calling 단일 루프 사용 (HITL 지원).

    반환:
      {
        "answer":       dict,              # LLM 최종 JSON 응답
        "tool_calls":   list[ToolCall],    # 트레이스: 호출 도구·인수·결과
        "iterations":   int,
        "session_id":   str,
        "trace_path":   str | None,        # 저장된 트레이스 파일 경로
        "pii_warnings": list[str],         # PII 누출 경고
        "validation":   ValidationResult,  # 스키마 + 수치 교차 검증 결과
      }
    """
    if use_graph:
        from .graph import run_graph
        return run_graph(
            household_id=household_id,
            user_message=user_message,
            session_id=session_id,
            log_dir=log_dir,
        )
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
    baseline = build_smart_context(household_id, user_message, location)

    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": f"{baseline}\n\n{user_message}"},
    ]

    pii_warnings: list[str] = []
    collected_tool_results: list[dict[str, Any]] = []
    iterations = 0

    for _ in range(max_iterations):
        messages = maybe_compress_messages(messages)
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

            # HITL: 최종 답변 전 사람 검토
            if hitl_callback and not hitl_callback("before_answer", {"answer": answer}):
                validation = validate_answer({}, collected_tool_results)
                tracer.log_final_answer({}, {})
                trace_path = tracer.save()
                return {
                    "answer":       {},
                    "tool_calls":   tracer._tool_calls,
                    "iterations":   iterations,
                    "session_id":   sid,
                    "trace_path":   trace_path,
                    "pii_warnings": pii_warnings,
                    "validation":   validation,
                }

            validation = validate_answer(answer, collected_tool_results)

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
                "validation":   validation,
            }

        tool_calls = choice.message.tool_calls or []
        if not tool_calls:
            break

        messages.append(choice.message)

        for tc in tool_calls:
            inputs = json.loads(tc.function.arguments)

            # HITL: 도구 실행 전 사람 검토
            if hitl_callback and not hitl_callback("before_tool", {"tool": tc.function.name, "inputs": inputs}):
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      json.dumps(
                        {"error": "도구 실행이 사용자에 의해 중단되었습니다.", "code": "E_HITL_REJECTED"},
                        ensure_ascii=False,
                    ),
                })
                continue

            raw_result = _dispatch_tool(tc.function.name, inputs)

            # PII 감사 → 스크럽 → LLM 전달
            found_pii = validate_no_pii(raw_result)
            if found_pii:
                pii_warnings.extend(found_pii)
            safe_result = scrub_tool_output(raw_result)

            collected_tool_results.append(safe_result)
            tracer.log_tool_call(tc.function.name, inputs, safe_result)
            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      json.dumps(safe_result, ensure_ascii=False),
            })

    validation = validate_answer({}, collected_tool_results)
    tracer.log_final_answer({})
    trace_path = tracer.save()
    return {
        "answer":       {},
        "tool_calls":   tracer._tool_calls,
        "iterations":   iterations,
        "session_id":   sid,
        "trace_path":   trace_path,
        "pii_warnings": pii_warnings,
        "validation":   validation,
    }
