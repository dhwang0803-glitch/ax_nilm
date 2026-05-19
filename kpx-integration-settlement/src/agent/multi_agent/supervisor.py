"""수퍼바이저 — LangGraph StateGraph (rule-based 위상 + LLM 라우터·평가자).

흐름:
  START → router (LLM 분류, household_profile 기반)
    ├→ nilm_monitor (Module 2) → human_review (HITL) ──────────→ report (Module 5)
    ├→ cashback (Module 3) → rag_retriever (Module 4, 게이트) ─↗      ↓
    └→ weather (Module 6, 게이트) ─────────────────────────────↗  evaluator
                                                                    ↓
                                                            approve / regenerate (최대 1회)

router_node: household_profile을 LLM이 분류 → focus(anomaly/savings/balanced)와
            active_agents 결정. weather·rag는 라우팅 결과에 따라 본문 실행 스킵.
human_review: 고위험 이상 있으면 interrupt()로 중단, 없으면 즉시 통과.
evaluator_node: report 출력 품질 평가 → 임계 미달 시 1회 재실행 (Evaluator-Optimizer 패턴).
"""
from __future__ import annotations

import os
import re
import uuid
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from typing_extensions import TypedDict

from ..schemas import InsightsLLMOutput
from ..data_tools import get_household_profile
from .cashback_node import cashback_node_fn, cashback_unit_rate
from .diagnosis_gate import diagnosis_gate, gate_route, report_lite_node
from .evaluator_node import evaluator_node, evaluator_route
from .human_review_node import human_review_node
from .nilm_monitor import nilm_monitor_node
from .rag_node import rag_node
from .report_agent import report_node
from .router_node import gated, router_node
from .weather_node import weather_node


# ── 그래프 상태 ────────────────────────────────────────────────────────────────

class MultiAgentState(TypedDict, total=False):
    household_id: str
    household_profile: dict       # get_household_profile() raw 결과
    routing: dict                 # router_node: {focus, active_agents, reason}
    nilm_output: dict             # NilmMonitorOutput.model_dump()
    cashback_output: dict         # CashbackNodeOutput.model_dump()
    rag_context: list             # retrieve() 결과 청크 문자열 리스트
    weather_output: dict          # get_weather() raw 결과
    human_review: dict            # HITL 결정: {approved, auto, note}
    gate_decision: str            # diagnosis_gate: "full" | "lite"
    final_output: dict            # InsightsLLMOutput.model_dump()
    evaluator: dict               # evaluator_node: {approved, score, issues, summary}
    evaluator_retry_count: int    # 재생성 횟수 (max 1)
    evaluator_feedback: list      # 재시도 시 report_node가 참고할 이슈 목록


# ── 그래프 빌드 (지연 초기화) ─────────────────────────────────────────────────

_graph: list = []
_checkpointer = MemorySaver()


def _get_graph():
    if not _graph:
        builder = StateGraph(MultiAgentState)

        builder.add_node("router",          router_node)
        builder.add_node("nilm_monitor",    nilm_monitor_node)
        builder.add_node("human_review",    human_review_node)
        builder.add_node("diagnosis_gate",  diagnosis_gate)
        builder.add_node("cashback",        cashback_node_fn)
        # 라우터가 False로 결정하면 본문 실행 스킵 (소프트 라우팅)
        builder.add_node("rag_retriever",   gated(rag_node,     "rag",     {"rag_context": []}))
        builder.add_node("weather",         gated(weather_node, "weather", {"weather_output": {}}))
        builder.add_node("report",          report_node)
        builder.add_node("report_lite",     report_lite_node)
        builder.add_node("evaluator",       evaluator_node)

        # START → router → 3개 노드 fan-out
        builder.add_edge(START,            "router")
        builder.add_edge("router",         "nilm_monitor")
        builder.add_edge("router",         "cashback")
        builder.add_edge("router",         "weather")

        # nilm → HITL 검토 → diagnosis_gate (프롬프트 체이닝 게이트)
        builder.add_edge("nilm_monitor",   "human_review")
        builder.add_edge("human_review",   "diagnosis_gate")

        # 게이트 분기: full(LLM 진단·권고) / lite(LLM 없음, 코드 일반 권고)
        builder.add_conditional_edges(
            "diagnosis_gate",
            gate_route,
            {"report": "report", "report_lite": "report_lite"},
        )

        # cashback 완료 → RAG 즉시 시작 (nilm·weather와 병렬)
        builder.add_edge("cashback",       "rag_retriever")

        # rag_retriever + weather → report fan-in (full 경로만 사용; lite는 즉시 진행)
        builder.add_edge("rag_retriever",  "report")
        builder.add_edge("weather",        "report")

        # 두 경로 모두 evaluator로 합류
        builder.add_edge("report",         "evaluator")
        builder.add_edge("report_lite",    "evaluator")
        # evaluator → END 또는 report 재실행 (Evaluator-Optimizer)
        builder.add_conditional_edges(
            "evaluator",
            evaluator_route,
            {"report": "report", "__end__": END},
        )

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
            "household_id":          household_id,
            "household_profile":     profile.get("raw") or {},
            "routing":               {},
            "nilm_output":           {},
            "cashback_output":       {},
            "rag_context":           [],
            "weather_output":        {},
            "human_review":          {},
            "gate_decision":         "",
            "final_output":          {},
            "evaluator":             {},
            "evaluator_retry_count": 0,
            "evaluator_feedback":    [],
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


_KRW_PATTERN = re.compile(r"\s*([\d,]+(?:\.\d+)?)원")
# "단축하면 1,000원 절약 가능" 형태의 절약 구문 — "하면"부터 문자열 끝까지 제거
_SAVING_CLAUSE = re.compile(r"하면\s*([\d,]+(?:\.\d+)?)원[가-힣\s]*$")
# description 안 "N원" 절약 금액 — 최종 savings_krw로 일치시키기 위한 패턴
_DESC_KRW_PATTERN = re.compile(r"(\d{1,3}(?:,\d{3})*|\d+)\s*원")
# 메인 분전반은 집계 채널 — 권고 제목에 등장하면 그 권고 자체를 제외
_MAIN_BREAKER_TOKENS = ("메인 분전반", "메인분전반", "MAIN")


def _strip_title(title: str) -> tuple[str, float | None]:
    """제목에서 LLM이 잘못 삽입한 원화 절약 구문·금액을 제거한다."""
    # 1) "단축하면 1,000원 절약" 형태: "하면" 앞까지만 보존
    m = _SAVING_CLAUSE.search(title)
    if m:
        try:
            value: float | None = float(m.group(1).replace(",", ""))
        except ValueError:
            value = None
        return title[:m.start()].strip(), value

    # 2) 남은 "숫자원" 형태 (예: "0.93원") 제거
    m2 = _KRW_PATTERN.search(title)
    if m2:
        try:
            value = float(m2.group(1).replace(",", ""))
        except ValueError:
            value = None
        return _KRW_PATTERN.sub("", title).strip(), value

    return title, None


def _match_consumer_kwh(title: str, top_consumers: list[dict]) -> float | None:
    """제목 내 가전명을 top_consumers에서 찾아 daily_kwh 반환. 없으면 None."""
    for tc in sorted(top_consumers, key=lambda x: -x.get("daily_kwh", 0)):
        app = tc.get("appliance", "")
        if app and app in title:
            return tc.get("daily_kwh")
    return None


def _build_output(household_id: str, result: dict[str, Any]) -> InsightsLLMOutput:
    final = result.get("final_output") or {}
    output = InsightsLLMOutput(**final)

    unit_rate = cashback_unit_rate(household_id)
    top_consumers: list[dict] = (result.get("nilm_output") or {}).get("top_consumers") or []

    # 메인 분전반은 집계 채널 — 권고 목록에서 제외
    output.recommendations = [
        rec for rec in output.recommendations
        if not any(tok in rec.title for tok in _MAIN_BREAKER_TOKENS)
    ]

    for rec in output.recommendations:
        clean_title, extracted_kwh = _strip_title(rec.title)
        rec.title = clean_title

        # savings_kwh 우선순위: NILM 매칭(daily_kwh×0.075×30) > 제목 추출(소규모) > LLM 원본
        matched_kwh = _match_consumer_kwh(clean_title, top_consumers)
        if matched_kwh is not None and matched_kwh >= 0.01:
            rec.savings_kwh = max(0.01, min(10.0, round(matched_kwh * 0.075 * 30, 2)))
        elif extracted_kwh is not None and 0.01 <= extracted_kwh <= 10.0:
            rec.savings_kwh = round(extracted_kwh, 2)

        rec.savings_krw = round(rec.savings_kwh * unit_rate)

        # description 안 "N원" 절약 금액을 최종 savings_krw와 일치시킴 (표 금액과 본문 모순 방지)
        if rec.savings_krw > 0 and rec.description:
            rec.description = _DESC_KRW_PATTERN.sub(f"{rec.savings_krw:,}원", rec.description)

    return output
