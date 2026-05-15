"""Module HITL — 고위험 이상 이벤트 인간 검토 노드.

nilm_monitor 완료 후 실행. critical/high/error 심각도 이벤트가 있으면
LangGraph interrupt()로 그래프를 일시 중단하고 인간 결정을 기다린다.
이상 없거나 이벤트 없으면 자동 승인 후 통과.
"""
from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

_REVIEW_SEVERITIES = {"critical", "high", "error"}


def human_review_node(state: dict[str, Any]) -> dict[str, Any]:
    """HITL: 고위험 이상 발견 시 interrupt()로 그래프 중단 후 인간 결정 대기."""
    events: list[dict] = (state.get("nilm_output") or {}).get("anomaly_events", [])
    severe = [
        e for e in events
        if e.get("severity", "").lower() in _REVIEW_SEVERITIES
    ]

    if not severe:
        return {"human_review": {"approved": True, "auto": True, "note": ""}}

    # 그래프 일시 중단 — 반환값은 resume 시 인간이 전달하는 dict
    decision: dict = interrupt({
        "anomaly_events": severe,
        "message": f"{len(severe)}개 고위험 이상 이벤트 검토 필요",
    })

    return {"human_review": decision}
