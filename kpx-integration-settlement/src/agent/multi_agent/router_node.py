"""Router — 가구 프로필 기반 활성 에이전트 결정 (라우팅 패턴).

START 직후 실행. household_profile을 LLM으로 분류해 focus를 결정하고,
그에 맞춰 후속 노드(weather, rag)의 실행 여부를 결정한다.
nilm·cashback은 코어라 항상 활성.

소프트 라우팅: 그래프 위상은 유지하고, gated wrapper가 state["routing"]을
읽어 비활성 노드는 즉시 빈 결과 반환. fan-in 셔플링 위험을 피한다.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

from .. import ontology

logger = logging.getLogger(__name__)


# ── 분류 출력 스키마 ─────────────────────────────────────────────────────────

class _RouterDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    focus: Literal["anomaly", "savings", "balanced"]
    reason: str = Field(max_length=80)


_SYSTEM = """\
한국 가정 전력 인사이트 라우터.
household_profile을 보고 분석 초점을 한 가지로 분류한다.

- anomaly: 가전 수 많음(7개 이상) + 노후/저효율 등급이 다수 → 이상 진단 우선
- savings: 가전 수 적음(4개 이하) 또는 1~2등급 고효율 위주 → 절약 권고 우선
- balanced: 그 외 일반 가구

reason은 한 문장(60자 이내)으로 분류 근거 명시.
"""


# ── 노드 함수 ────────────────────────────────────────────────────────────────

def router_node(state: dict[str, Any]) -> dict[str, Any]:
    """가구 프로필 → focus 분류 + active_agents 결정."""
    profile = state.get("household_profile") or {}

    # 1) LLM 분류 (실패 시 balanced로 폴백)
    focus: str = "balanced"
    reason: str = "router fallback"
    if os.getenv("OPENAI_API_KEY"):
        try:
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
            decision: _RouterDecision = (
                llm
                .with_structured_output(_RouterDecision)
                .invoke([
                    SystemMessage(_SYSTEM),
                    HumanMessage(content=json.dumps(profile, ensure_ascii=False, default=str)),
                ])
            )
            focus = decision.focus
            reason = decision.reason
        except Exception as e:
            logger.warning("router LLM 호출 실패 — balanced로 폴백: %s", e)

    # 2) 규칙 기반 active 결정 — 가구 가전 구성으로 명확히 결정 가능한 부분
    appliances = profile.get("appliances") or []
    appliance_names = {
        a.get("name", "") for a in appliances if isinstance(a, dict)
    }
    cooling = set(ontology.cooling_appliances())
    heating = set(ontology.heating_appliances())
    has_thermal = bool(appliance_names & (cooling | heating))

    active_agents = {
        "nilm":     True,                          # 코어
        "cashback": True,                          # 단가 산정에 필요
        "weather":  has_thermal,                   # 냉난방 가전 없으면 불필요
        "rag":      focus in ("savings", "balanced"),  # 절약 컨텍스트 필요할 때만
    }

    logger.info("router: focus=%s active=%s reason=%s", focus, active_agents, reason)

    return {
        "routing": {
            "focus":         focus,
            "active_agents": active_agents,
            "reason":        reason,
        },
    }


# ── 소프트 라우팅 wrapper ────────────────────────────────────────────────────

def gated(node_fn, agent_key: str, default_state: dict):
    """state["routing"]["active_agents"][agent_key]이 False면 default_state 반환.

    LangGraph fan-in이 안전하게 처리될 수 있도록 그래프 위상은 유지하고,
    노드 본문 실행만 건너뛴다.
    """
    def wrapped(state: dict[str, Any]) -> dict[str, Any]:
        active = (
            (state.get("routing") or {})
            .get("active_agents", {})
            .get(agent_key, True)
        )
        if not active:
            logger.info("gated: %s skipped (routing decision)", agent_key)
            return default_state
        return node_fn(state)

    wrapped.__name__ = f"gated_{agent_key}"
    return wrapped
