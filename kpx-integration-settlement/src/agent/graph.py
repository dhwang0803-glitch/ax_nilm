"""LangGraph 단일 ReAct 에이전트 — NILM 에너지 코치.

단일 에이전트에 10개 도구를 모두 연결한다.
PII 스크럽은 도구 레벨에서 수행되므로 LLM에 개인 식별 정보가 전달되지 않는다.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from .anonymizer import scrub_tool_output, validate_no_pii
from .data_tools import (
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

logger = logging.getLogger(__name__)


# ── LLM factory ───────────────────────────────────────────────────────────────

def _llm(model: str = "gpt-4o-mini") -> ChatOpenAI:
    return ChatOpenAI(model=model, temperature=0)


# ── PII-safe tool wrapper ──────────────────────────────────────────────────────

def _safe_tool(fn) -> StructuredTool:
    """원본 함수 스키마를 유지하면서 출력에 PII 스크럽을 적용하는 StructuredTool."""
    schema_base = StructuredTool.from_function(fn)

    def safe_run(**kwargs) -> Any:
        result = fn(**kwargs)
        found_pii = validate_no_pii(result)
        if found_pii:
            logger.warning("PII detected in %s: %s", fn.__name__, found_pii)
        return scrub_tool_output(result)

    return StructuredTool(
        name=schema_base.name,
        description=schema_base.description or "",
        args_schema=schema_base.args_schema,
        func=safe_run,
    )


# ── 전체 도구 목록 (단일 에이전트에 모두 연결) ────────────────────────────────

ALL_TOOLS = [_safe_tool(f) for f in (
    get_consumption_summary,
    get_hourly_appliance_breakdown,
    get_weather,
    get_forecast,
    get_cashback_history,
    get_tariff_info,
    get_anomaly_events,
    get_anomaly_log,
    get_household_profile,
    get_dashboard_summary,
)]

# ── 시스템 프롬프트 ───────────────────────────────────────────────────────────

_AGENT_SYSTEM = """\
당신은 한국 가정 전력 절감 전문 코치입니다.
메시지에서 가구 ID(예: H011)를 찾아 도구 호출 시 household_id로 사용하세요.
응답은 한국어로, 수치는 소수 첫째 자리까지 표시하세요.
사용자의 실명·주소·연락처를 추론하거나 언급하지 마세요.

사용 가능한 도구: 전력 소비 분석, 이상 탐지 진단, 에너지캐시백 실적, 가구 프로필 종합 조회.

반드시 아래 JSON 형식으로만 응답하세요 (이상 이벤트가 없어도 동일한 형식 유지):
{
  "anomaly_diagnoses": [
    {"event_id": "...", "diagnosis": "지난주 평균 0.12 → 0.22 kW. 도어 가스켓 점검 권장.", "action": "가스켓 점검"}
  ],
  "recommendations": [
    {"title": "저녁 19-21시 건조기 미사용", "savings_kwh": 2.1, "savings_krw": 210},
    {"title": "에어컨 설정 26 → 27°C", "savings_kwh": 1.4, "savings_krw": 140}
  ]
}

이상 이벤트가 없으면 anomaly_diagnoses는 빈 배열([])로, recommendations는 소비 패턴 기반으로 3~5개 작성.
diagnosis 작성 규칙: "지난주 평균 X → Y kW" 또는 "사용시간 X% 증가" 형식으로 수치 변화를 화살표(→)나 % 로 명시
title 작성 규칙: 시간대("저녁 19-21시"), 수치 변화("26 → 27°C"), 기기명을 조합한 구체적 행동
규칙: recommendations 3~5개 / savings_krw = round(savings_kwh × 100) / 가전 교체·구매 금지 / 의료·안전 권고 금지
- 계절·기온을 고려해 기온이 낮으면 난방 관련 가전(전기장판·전기히터 등), 높으면 냉방 관련 가전(에어컨·선풍기 등) 사용 중단 권고 금지
- recommendations는 get_hourly_appliance_breakdown 데이터에서 kWh 소비가 큰 기기·시간대 순으로 선택, 오전/오후/저녁/야간을 고르게 커버
- 각 recommendations 항목은 서로 다른 시간대여야 함 (동일 시간대 2개 이상 금지)
- 시간당 0.1 kWh 미만 기기는 recommendations에서 제외
- savings_kwh는 실제 도구 데이터 kWh 수치 기반 산정 (해당 기기 시간대 kWh × 절감률 0.5~1.0 × 월 사용일수)
- get_hourly_appliance_breakdown 결과가 E_NOT_FOUND 또는 E_NO_DATA인 경우 데이터 없이 임의로 추천을 생성하지 말고 recommendations는 빈 배열([])로 반환"""


# ── 그래프 빌드 (지연 초기화 — API 키는 첫 호출 시점에 확인) ─────────────────

_graph: list = []


def _get_graph() -> Any:
    if not _graph:
        _graph.append(create_react_agent(
            _llm(),
            ALL_TOOLS,
            prompt=SystemMessage(_AGENT_SYSTEM),
            checkpointer=MemorySaver(),
        ))
    return _graph[0]


# ── 공개 진입점 ───────────────────────────────────────────────────────────────

def run_graph(
    household_id: str,
    user_message: str,
    session_id: str | None = None,
    log_dir: str = "logs/traces",
) -> dict[str, Any]:
    """단일 ReAct 에이전트 실행.

    반환 구조:
      answer, tool_calls, iterations, session_id, trace_path, pii_warnings, validation
    """
    if not os.getenv("OPENAI_API_KEY"):
        raise EnvironmentError("OPENAI_API_KEY 환경변수 필요")

    sid    = session_id or str(uuid.uuid4())
    tracer = TraceLogger(
        session_id=sid,
        household_token=f"HH-{sid[:8]}",
        log_dir=log_dir,
    )

    result = _get_graph().invoke(
        {"messages": [HumanMessage(content=f"[가구 ID: {household_id}] {user_message}")]},
        config={"configurable": {"thread_id": sid}},
    )

    final_msg   = result["messages"][-1]
    raw_content = getattr(final_msg, "content", "") or ""
    try:
        answer = json.loads(raw_content)
    except (json.JSONDecodeError, TypeError):
        answer = {"raw_text": raw_content}

    tool_results: list[dict] = []
    for msg in result["messages"]:
        if isinstance(msg, ToolMessage):
            try:
                tool_results.append(json.loads(msg.content))
            except (json.JSONDecodeError, TypeError):
                tool_results.append({"raw": msg.content})

    ai_turns   = sum(1 for m in result["messages"] if isinstance(m, AIMessage))
    validation = validate_answer(answer, tool_results)

    tracer.log_final_answer(answer, {})
    trace_path = tracer.save()

    return {
        "answer":       answer,
        "tool_calls":   tool_results,
        "iterations":   ai_turns,
        "session_id":   sid,
        "trace_path":   trace_path,
        "pii_warnings": [],
        "validation":   validation,
    }


# ── Insights 출력 스키마 ──────────────────────────────────────────────────────

class AnomalyDiagnosis(BaseModel):
    event_id: str
    diagnosis: str = Field(max_length=100)
    action: str = Field(max_length=15)


class SavingsRec(BaseModel):
    title: str = Field(max_length=30)
    savings_kwh: float = Field(ge=0.1, le=10.0)
    savings_krw: int = Field(ge=10, le=3000)


class InsightsLLMOutput(BaseModel):
    anomaly_diagnoses: list[AnomalyDiagnosis]
    recommendations: list[SavingsRec] = Field(min_length=3, max_length=5)


_INSIGHTS_SYSTEM = """\
당신은 한국 가정 전력 전문 코치입니다. 아래 이상 탐지 데이터를 보고 두 가지를 작성하세요.

1. anomaly_diagnoses: 각 이상 이벤트에 대해
   - diagnosis: 수치 변화를 화살표(→)나 %로 명시한 진단 1~2문장
     (예: "지난주 평균 0.12 → 0.22 kW. 도어 가스켓 점검 권장." / "주 3회 → 5회. 환기·필터 점검 시 효율 회복 가능.") — 최대 100자
   - action: 2~6자 명사형 조치어 (예: "가스켓 점검", "필터 청소", "설정 확인") — 최대 15자

2. recommendations: 도구 데이터에서 kWh 소비가 큰 기기·시간대 순으로 선택, 오전/오후/저녁/야간을 고르게 커버하여 3~5개 작성
   - title: 시간대·수치·기기명을 조합한 구체적 행동
     (예: "저녁 19-21시 건조기 미사용" / "에어컨 설정 26 → 27°C" / "대기전력 멀티탭 OFF") — 최대 30자, 즉시 실행 가능한 행동만 — 가전 교체·구매 제외
   - savings_kwh: 예상 월 절감량 (0.1~10.0 kWh, 소수 첫째 자리)
   - savings_krw: round(savings_kwh × 100) — KEPCO 에너지캐시백 기준 100원/kWh (정수, 10~3000원)

규칙:
- savings_kwh 범위: 0.1~10.0 (평균 가정 월 300 kWh 기준, 단일 행동 최대 10 kWh 절감)
- savings_krw = round(savings_kwh × 100) 로 계산 (절대 × 1000 사용 금지)
- 가전 교체·구매·인프라 투자 추천 금지 — 사용 습관 변경만 권고
- 의료·안전 관련 권고(난방 완전 차단 등) 금지
- 계절·기온을 고려해 기온이 낮으면 난방 관련 가전(전기장판·전기히터 등), 높으면 냉방 관련 가전(에어컨·선풍기 등) 사용 중단 권고 금지
- kWh 소수 첫째 자리, 금액 정수로 표시
- recommendations 각 항목은 서로 다른 시간대여야 함 (동일 시간대 2개 이상 금지)
- 시간당 0.1 kWh 미만 기기는 recommendations에서 제외
- savings_kwh는 도구 데이터의 실제 kWh 수치 기반으로 산정 (해당 기기 시간대 kWh × 절감률 0.5~1.0 × 월 사용일수)
- get_hourly_appliance_breakdown 결과가 E_NOT_FOUND 또는 E_NO_DATA인 경우 데이터 없이 임의로 추천을 생성하지 말고 recommendations는 빈 배열([])로 반환"""


def run_insights(household_id: str) -> InsightsLLMOutput:
    """이상 탐지 데이터를 조회해 LLM 진단 + 절약 추천을 반환 (폴백용)."""
    events_data = get_anomaly_events(household_id, status="active")
    log_data    = get_anomaly_log(household_id)

    raw_events = events_data.get("raw", [])
    raw_log    = log_data.get("raw", [])

    payload = {"events": raw_events, "log": raw_log[:20]}

    return (
        _llm()
        .with_structured_output(InsightsLLMOutput)
        .invoke([
            SystemMessage(_INSIGHTS_SYSTEM),
            HumanMessage(content=f"이상 탐지 데이터:\n{json.dumps(payload, ensure_ascii=False)}"),
        ])
    )
