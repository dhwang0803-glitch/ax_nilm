"""수퍼바이저 — LangGraph StateGraph (rule-based, LLM 없음).

흐름:
  START
    ├→ nilm_monitor (Module 2)  ─────────────────────────→ report (Module 5) → END
    ├→ cashback (Module 3) → rag_retriever (Module 4) ───↗
    └→ weather (Module 6)  ───────────────────────────────↗

nilm_monitor·cashback·weather 세 노드 동시 fan-out.
cashback 완료 즉시 rag_retriever 시작 (nilm·weather와 병렬).
report는 nilm_monitor + rag_retriever + weather 셋 다 완료 후 실행 (fan-in).
"""
from __future__ import annotations

import os
from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from ..schemas import InsightsLLMOutput
from ..data_tools import get_household_profile
from .cashback_node import cashback_node_fn, cashback_unit_rate
from .nilm_monitor import nilm_monitor_node
from .rag_node import rag_node
from .report_agent import report_node
from .weather_node import weather_node


# ── 그래프 상태 ────────────────────────────────────────────────────────────────

class MultiAgentState(TypedDict):
    household_id: str
    household_profile: dict  # get_household_profile() raw 결과
    nilm_output: dict        # NilmMonitorOutput.model_dump()
    cashback_output: dict    # CashbackNodeOutput.model_dump()
    rag_context: list        # retrieve() 결과 청크 문자열 리스트
    weather_output: dict     # get_weather() raw 결과
    final_output: dict       # InsightsLLMOutput.model_dump()


# ── 그래프 빌드 (지연 초기화) ─────────────────────────────────────────────────

_graph: list = []


def _get_graph():
    if not _graph:
        builder = StateGraph(MultiAgentState)

        builder.add_node("nilm_monitor",   nilm_monitor_node)
        builder.add_node("cashback",       cashback_node_fn)
        builder.add_node("rag_retriever",  rag_node)
        builder.add_node("weather",        weather_node)
        builder.add_node("report",         report_node)

        # nilm_monitor·cashback·weather 동시 fan-out
        builder.add_edge(START, "nilm_monitor")
        builder.add_edge(START, "cashback")
        builder.add_edge(START, "weather")

        # cashback 완료 → RAG 즉시 시작 (nilm·weather와 병렬)
        builder.add_edge("cashback", "rag_retriever")

        # nilm_monitor + rag_retriever + weather 셋 다 완료 → report fan-in
        builder.add_edge("nilm_monitor",  "report")
        builder.add_edge("rag_retriever", "report")
        builder.add_edge("weather",       "report")

        builder.add_edge("report", END)

        _graph.append(builder.compile())
    return _graph[0]


# ── 공개 진입점 ───────────────────────────────────────────────────────────────

def run_multi_agent(household_id: str) -> InsightsLLMOutput:
    """수퍼바이저 그래프 실행.

    InsightsLLMOutput 반환 (savings_krw는 호출자 측에서 후처리).
    """
    if not os.getenv("OPENAI_API_KEY"):
        raise EnvironmentError("OPENAI_API_KEY 환경변수 필요")

    profile = get_household_profile(household_id)

    result: dict[str, Any] = _get_graph().invoke(
        {
            "household_id":      household_id,
            "household_profile": profile.get("raw") or {},
            "nilm_output":       {},
            "cashback_output":   {},
            "rag_context":       [],
            "weather_output":    {},
            "final_output":      {},
        }
    )

    final = result.get("final_output") or {}
    output = InsightsLLMOutput(**final)

    # savings_krw 후처리 — 가구 캐시백 이력 단가 적용
    unit_rate = cashback_unit_rate(household_id)
    for rec in output.recommendations:
        rec.savings_krw = round(rec.savings_kwh * unit_rate)

    return output
