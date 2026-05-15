"""수퍼바이저 — LangGraph StateGraph (rule-based, LLM 없음).

흐름:
  START
    ├→ nilm_monitor (Module 2) → human_review (HITL) ──────────→ report (Module 5) → END
    ├→ cashback (Module 3) → rag_retriever (Module 4) ─────────↗
    └→ weather (Module 6)  ─────────────────────────────────────↗

nilm_monitor·cashback·weather 세 노드 동시 fan-out.
cashback 완료 즉시 rag_retriever 시작 (nilm·weather와 병렬).
human_review: 고위험 이상 있으면 interrupt()로 중단, 없으면 즉시 통과.
report는 human_review + rag_retriever + weather 셋 다 완료 후 실행 (fan-in).
"""
from __future__ import annotations

import os
import uuid
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from typing_extensions import TypedDict

from ..schemas import InsightsLLMOutput
from ..data_tools import get_household_profile
from .cashback_node import cashback_node_fn, cashback_unit_rate
from .human_review_node import human_review_node
from .nilm_monitor import nilm_monitor_node
from .rag_node import rag_node
from .report_agent import report_node
from .weather_node import weather_node


# ── 그래프 상태 ────────────────────────────────────────────────────────────────

class MultiAgentState(TypedDict):
    household_id: str
    household_profile: dict       # get_household_profile() raw 결과
    nilm_output: dict             # NilmMonitorOutput.model_dump()
    cashback_output: dict         # CashbackNodeOutput.model_dump()
    rag_context: list             # retrieve() 결과 청크 문자열 리스트
    weather_output: dict          # get_weather() raw 결과
    human_review: dict            # HITL 결정: {approved, auto, note}
    final_output: dict            # InsightsLLMOutput.model_dump()


# ── 그래프 빌드 (지연 초기화) ─────────────────────────────────────────────────

_graph: list = []
_checkpointer = MemorySaver()


def _get_graph():
    if not _graph:
        builder = StateGraph(MultiAgentState)

        builder.add_node("nilm_monitor",   nilm_monitor_node)
        builder.add_node("human_review",   human_review_node)
        builder.add_node("cashback",       cashback_node_fn)
        builder.add_node("rag_retriever",  rag_node)
        builder.add_node("weather",        weather_node)
        builder.add_node("report",         report_node)

        # nilm_monitor·cashback·weather 동시 fan-out
        builder.add_edge(START,          "nilm_monitor")
        builder.add_edge(START,          "cashback")
        builder.add_edge(START,          "weather")

        # nilm → HITL 검토 → report
        builder.add_edge("nilm_monitor", "human_review")
        builder.add_edge("human_review", "report")

        # cashback 완료 → RAG 즉시 시작 (nilm·weather와 병렬)
        builder.add_edge("cashback",     "rag_retriever")

        # rag_retriever + weather → report fan-in
        builder.add_edge("rag_retriever", "report")
        builder.add_edge("weather",        "report")

        builder.add_edge("report", END)

        _graph.append(builder.compile(checkpointer=_checkpointer))
    return _graph[0]


# ── 보류 중 리뷰 저장소 ───────────────────────────────────────────────────────

_pending: dict[str, dict] = {}  # hh → {thread_id, interrupt_data}


def get_pending_review(household_id: str) -> dict | None:
    """보류 중인 인간 검토 데이터 반환. 없으면 None."""
    return _pending.get(household_id)


# ── 공개 진입점 ───────────────────────────────────────────────────────────────

def run_multi_agent(household_id: str) -> InsightsLLMOutput | None:
    """수퍼바이저 그래프 실행.

    고위험 이상 이벤트가 있으면 None을 반환하고 _pending에 저장.
    정상 완료 시 InsightsLLMOutput 반환 (savings_krw 후처리 포함).
    """
    if not os.getenv("OPENAI_API_KEY"):
        raise EnvironmentError("OPENAI_API_KEY 환경변수 필요")

    profile = get_household_profile(household_id)
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    result: dict[str, Any] = _get_graph().invoke(
        {
            "household_id":      household_id,
            "household_profile": profile.get("raw") or {},
            "nilm_output":       {},
            "cashback_output":   {},
            "rag_context":       [],
            "weather_output":    {},
            "human_review":      {},
            "final_output":      {},
        },
        config=config,
    )

    # interrupt() 호출 시 __interrupt__ 키가 결과에 포함됨
    interrupts = result.get("__interrupt__")
    if interrupts:
        interrupt_val = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
        _pending[household_id] = {"thread_id": thread_id, "interrupt_data": interrupt_val}
        return None

    return _build_output(household_id, result)


def resume_multi_agent(household_id: str, decision: dict) -> InsightsLLMOutput:
    """보류 중인 그래프를 인간 결정으로 재개.

    decision: {"approved": bool, "note": str}
    """
    pending = _pending.pop(household_id, None)
    if not pending:
        raise ValueError(f"보류 중인 검토 없음: {household_id}")

    config = {"configurable": {"thread_id": pending["thread_id"]}}
    result: dict[str, Any] = _get_graph().invoke(Command(resume=decision), config=config)

    return _build_output(household_id, result)


def _build_output(household_id: str, result: dict[str, Any]) -> InsightsLLMOutput:
    final = result.get("final_output") or {}
    output = InsightsLLMOutput(**final)

    # savings_krw 후처리 — 가구 캐시백 이력 단가 적용
    unit_rate = cashback_unit_rate(household_id)
    for rec in output.recommendations:
        rec.savings_krw = round(rec.savings_kwh * unit_rate)

    return output
