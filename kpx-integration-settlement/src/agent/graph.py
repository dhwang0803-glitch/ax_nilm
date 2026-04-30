"""LangGraph 슈퍼바이저 — NILM 에너지 코치 멀티에이전트 그래프.

슈퍼바이저가 사용자 의도를 분류해 전문 에이전트로 라우팅한다:
  consumption → 소비량·피크·날씨
  cashback    → 캐시백·요금제·누진
  anomaly     → 이상탐지·AI진단
  profile     → 가구정보·대시보드

각 에이전트는 독립적인 도구 집합을 가진 ReAct 서브그래프로 동작한다.
PII 스크럽은 도구 레벨에서 수행되므로 LLM에 개인 식별 정보가 전달되지 않는다.
"""
from __future__ import annotations

import json
import logging
import operator
import os
import uuid
from typing import Annotated, Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command
from pydantic import BaseModel
from typing_extensions import TypedDict

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

# ── State ─────────────────────────────────────────────────────────────────────

AgentName = Literal["consumption", "cashback", "anomaly", "profile"]


class SupervisorState(TypedDict):
    messages: Annotated[list, add_messages]
    household_id: str
    next: str                                          # 슈퍼바이저가 마지막으로 선택한 에이전트
    worker_results: Annotated[list[dict], operator.add]  # 각 에이전트가 추가한 결과 집계


# 하위 호환 별칭
NilmState = SupervisorState


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


# ── 에이전트별 도구 집합 ──────────────────────────────────────────────────────

CONSUMPTION_TOOLS = [_safe_tool(f) for f in (
    get_consumption_summary,
    get_hourly_appliance_breakdown,
    get_weather,
    get_forecast,
)]

CASHBACK_TOOLS = [_safe_tool(f) for f in (
    get_cashback_history,
    get_tariff_info,
)]

ANOMALY_TOOLS = [_safe_tool(f) for f in (
    get_anomaly_events,
    get_anomaly_log,
)]

PROFILE_TOOLS = [_safe_tool(f) for f in (
    get_household_profile,
    get_dashboard_summary,
)]

# ── 시스템 프롬프트 ───────────────────────────────────────────────────────────

_BASE_SYSTEM = (
    "당신은 한국 가정 전력 절감 전문 코치입니다. "
    "메시지에서 가구 ID(예: H011)를 찾아 도구 호출 시 household_id로 사용하세요. "
    "응답은 한국어로, 수치는 소수 첫째 자리까지 표시하세요. "
    "사용자의 실명·주소·연락처를 추론하거나 언급하지 마세요."
)

_AGENT_SYSTEMS: dict[str, str] = {
    "consumption": _BASE_SYSTEM + " 전문: 전력 소비량 분석, 피크 시간대, 날씨 연관 패턴.",
    "cashback":    _BASE_SYSTEM + " 전문: 에너지캐시백 실적, 누진 요금제, 예상 청구액.",
    "anomaly":     _BASE_SYSTEM + " 전문: 이상 탐지 이벤트, 가전 비정상 동작 진단.",
    "profile":     _BASE_SYSTEM + " 전문: 가구 프로필, 대시보드 종합 요약.",
}

_SUPERVISOR_SYSTEM = """\
사용자 메시지를 분석해 담당 에이전트를 결정하세요.

- consumption : 소비량, 사용량, 피크, 날씨 관련
- cashback    : 캐시백, 요금, 누진, 청구액 관련
- anomaly     : 이상 탐지, AI 진단, 가전 고장 관련
- profile     : 가구 정보, 대시보드, 종합 요약

반드시 JSON만 반환: {"next": "<agent_name>"}"""


# ── 슈퍼바이저 노드 ───────────────────────────────────────────────────────────

class _Route(TypedDict):
    next: AgentName


def supervisor_node(state: SupervisorState) -> Command[AgentName]:
    """의도 분류 후 전문 에이전트로 라우팅."""
    result: _Route = _llm().with_structured_output(_Route).invoke(
        [SystemMessage(_SUPERVISOR_SYSTEM), *state["messages"]]
    )
    logger.debug("supervisor → %s", result["next"])
    return Command(
        goto=result["next"],
        update={"next": result["next"]},  # state에 라우팅 결정 기록
    )


# ── 에이전트 노드 팩토리 ──────────────────────────────────────────────────────

def _make_agent_node(name: str, tools: list):
    """create_react_agent 서브그래프를 NilmState 노드 함수로 래핑.

    household_id를 첫 Human 메시지 앞에 주입하고,
    서브그래프가 반환한 새 메시지만 상위 상태에 추가한다.
    LLM은 첫 호출 시점에 초기화된다 (API 키 지연 로드).
    """
    _inner: list = []  # 가변 컨테이너로 지연 초기화

    def _get_inner():
        if not _inner:
            _inner.append(create_react_agent(
                _llm(),
                tools,
                prompt=SystemMessage(_AGENT_SYSTEMS[name]),
            ))
        return _inner[0]

    def node(state: SupervisorState) -> dict:
        hh = state["household_id"]
        msgs = list(state["messages"])

        # 가구 ID를 첫 Human 메시지에 prefix로 삽입
        if msgs and isinstance(msgs[0], HumanMessage):
            msgs[0] = HumanMessage(content=f"[가구 ID: {hh}] {msgs[0].content}")

        n_before = len(msgs)
        result = _get_inner().invoke({"messages": msgs})

        # 서브그래프가 반환한 신규 메시지만 추가 (기존 메시지 중복 방지)
        new_messages = result["messages"][n_before:]

        # 에이전트 결과를 worker_results에 추가
        final_content = getattr(new_messages[-1], "content", "") if new_messages else ""
        worker_result = {"agent": name, "output": final_content}

        return {"messages": new_messages, "worker_results": [worker_result]}

    node.__name__ = f"{name}_node"
    return node


# ── 그래프 빌드 ───────────────────────────────────────────────────────────────

def _build() -> Any:
    builder = StateGraph(SupervisorState)

    builder.add_node("supervisor",  supervisor_node)
    builder.add_node("consumption", _make_agent_node("consumption", CONSUMPTION_TOOLS))
    builder.add_node("cashback",    _make_agent_node("cashback",    CASHBACK_TOOLS))
    builder.add_node("anomaly",     _make_agent_node("anomaly",     ANOMALY_TOOLS))
    builder.add_node("profile",     _make_agent_node("profile",     PROFILE_TOOLS))

    builder.add_edge(START, "supervisor")
    for name in ("consumption", "cashback", "anomaly", "profile"):
        builder.add_edge(name, END)

    return builder.compile(checkpointer=MemorySaver())


graph = _build()


# ── 공개 진입점 ───────────────────────────────────────────────────────────────

def run_graph(
    household_id: str,
    user_message: str,
    session_id: str | None = None,
    log_dir: str = "logs/traces",
) -> dict[str, Any]:
    """LangGraph 멀티에이전트 실행.

    반환 구조는 coach.run_coach와 동일:
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

    result = graph.invoke(
        {
            "messages":       [HumanMessage(content=user_message)],
            "household_id":   household_id,
            "next":           "",
            "worker_results": [],
        },
        config={"configurable": {"thread_id": sid}},
    )

    # 최종 AI 메시지에서 답변 추출
    final_msg    = result["messages"][-1]
    raw_content  = getattr(final_msg, "content", "") or ""
    try:
        answer = json.loads(raw_content)
    except (json.JSONDecodeError, TypeError):
        answer = {"raw_text": raw_content}

    # ToolMessage에서 도구 결과 수집 (검증용)
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
    diagnosis: str  # 수치 포함 진단 문장 1~2개
    action: str     # 짧은 조치어


class SavingsRec(BaseModel):
    title: str
    savings_kwh: float
    savings_krw: int


class InsightsLLMOutput(BaseModel):
    anomaly_diagnoses: list[AnomalyDiagnosis]
    recommendations: list[SavingsRec]


_INSIGHTS_SYSTEM = """\
당신은 한국 가정 전력 전문 코치입니다. 아래 이상 탐지 데이터를 보고 두 가지를 작성하세요.

1. anomaly_diagnoses: 각 이상 이벤트에 대해
   - diagnosis: 수치를 포함한 진단 문장 1~2개 (예: "평균 대비 40% 높은 소비. 필터 점검 권장.")
   - action: 짧은 조치어 (예: "필터 점검")

2. recommendations: 데이터 기반 절약 추천 5개 이내
   - title: 추천 행동
   - savings_kwh: 예상 월 절감량 (소수 첫째 자리)
   - savings_krw: 예상 월 절약 금액 (정수, 원)

규칙:
- 주어진 데이터에 없는 수치를 추측하지 마세요.
- kWh는 소수 첫째 자리, 금액은 정수로 표시하세요.
- 의료·안전 관련 권고(난방 완전 차단 등)는 하지 마세요."""


def run_insights(household_id: str) -> InsightsLLMOutput:
    """이상 탐지 데이터를 조회해 LLM 진단 + 절약 추천을 반환."""
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
