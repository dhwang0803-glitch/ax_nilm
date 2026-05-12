"""수퍼바이저 — LangGraph StateGraph (rule-based, LLM 없음).

흐름:
  START
    ├→ nilm_monitor (Module 2)  ─→ report (Module 5) → END
    └→ cashback (Module 3)      ─↗
Module 2·3은 병렬 실행, 둘 다 완료 후 Module 5 실행.
"""
from __future__ import annotations

import os
from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from ..schemas import InsightsLLMOutput
from .cashback_node import cashback_node_fn, cashback_unit_rate
from .nilm_monitor import nilm_monitor_node
from .report_agent import report_node


# ── 그래프 상태 ────────────────────────────────────────────────────────────────

class MultiAgentState(TypedDict):
    household_id: str
    nilm_output: dict        # NilmMonitorOutput.model_dump()
    cashback_output: dict    # CashbackNodeOutput.model_dump()
    final_output: dict       # InsightsLLMOutput.model_dump()


# ── 그래프 빌드 (지연 초기화) ─────────────────────────────────────────────────

_graph: list = []


def _get_graph():
    if not _graph:
        builder = StateGraph(MultiAgentState)

        builder.add_node("nilm_monitor", nilm_monitor_node)
        builder.add_node("cashback",     cashback_node_fn)
        builder.add_node("report",       report_node)

        # Module 2·3 병렬 실행 (START에서 동시 fan-out)
        builder.add_edge(START, "nilm_monitor")
        builder.add_edge(START, "cashback")

        # 두 노드 모두 완료 후 report 실행 (fan-in)
        builder.add_edge("nilm_monitor", "report")
        builder.add_edge("cashback",     "report")

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

    result: dict[str, Any] = _get_graph().invoke(
        {
            "household_id":   household_id,
            "nilm_output":    {},
            "cashback_output": {},
            "final_output":   {},
        }
    )

    final = result.get("final_output") or {}
    output = InsightsLLMOutput(**final)

    # savings_krw 후처리 — 가구 캐시백 이력 단가 적용
    unit_rate = cashback_unit_rate(household_id)
    for rec in output.recommendations:
        rec.savings_krw = round(rec.savings_kwh * unit_rate)

    return output
