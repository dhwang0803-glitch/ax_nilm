"""Module 2 — NILM 모니터링 노드.

이상 이벤트 수집 + 가전별 소비 패턴 파악.
도구 호출은 항상 동일하므로 ReAct 없이 직접 호출 후 LLM으로 구조화.
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from ..data_tools import (
    get_anomaly_events,
    get_consumption_hourly,
    get_hourly_appliance_breakdown,
)


# ── 출력 스키마 ────────────────────────────────────────────────────────────────

class TopConsumer(BaseModel):
    appliance: str
    daily_kwh: float
    share_pct: float = Field(ge=0.0, le=100.0)


class NilmMonitorOutput(BaseModel):
    anomaly_events: list[dict]      # get_anomaly_events raw
    top_consumers: list[TopConsumer]  # 소비 상위 가전 (daily_kwh 내림차순)
    peak_hours: list[int]           # 소비 피크 시간대 (0~23)


# ── 시스템 프롬프트 ─────────────────────────────────────────────────────────────

_SYSTEM = """\
한국 가정 전력 분석 전문가.
제공된 JSON 데이터를 분석해 아래 형식으로 구조화하라.

top_consumers: daily_summary에서 daily_kwh 상위 5개 이하 추출.
  - daily_kwh 0.0이면 제외.
peak_hours: hourly_data에서 kwh 상위 3개 시간대의 hour 값 (정수 리스트).
anomaly_events: 입력의 events 배열 그대로 전달 (빈 배열이면 []).
"""


# ── 노드 함수 ──────────────────────────────────────────────────────────────────

def nilm_monitor_node(state: dict[str, Any]) -> dict[str, Any]:
    """Module 2: 이상 이벤트 + 가전 소비 패턴 수집 후 NilmMonitorOutput 반환."""
    hh = state["household_id"]

    events_data    = get_anomaly_events(hh, status="active")
    breakdown_data = get_hourly_appliance_breakdown(hh)
    hourly_data    = get_consumption_hourly(hh)

    raw_events   = events_data.get("raw", [])
    daily_summary = breakdown_data.get("daily_summary", [])
    hourly_raw   = hourly_data.get("raw", [])

    payload = {
        "events":       raw_events,
        "daily_summary": daily_summary,
        "hourly_data":  hourly_raw,
    }

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    result: NilmMonitorOutput = (
        llm
        .with_structured_output(NilmMonitorOutput)
        .invoke([
            SystemMessage(_SYSTEM),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ])
    )

    return {"nilm_output": result.model_dump()}
