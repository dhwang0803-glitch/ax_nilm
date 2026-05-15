"""Module 2 — NILM 모니터링 노드.

이상 이벤트 수집 + 가전별 소비 패턴 파악.
도구 호출은 항상 동일하므로 ReAct 없이 직접 호출 후 LLM으로 구조화.
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..data_tools import (
    get_anomaly_events,
    get_consumption_hourly,
    get_hourly_appliance_breakdown,
    get_nilm_mode_references,
    get_nilm_recent_events,
)


# ── 출력 스키마 ────────────────────────────────────────────────────────────────

class TopConsumer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    appliance: str
    daily_kwh: float
    share_pct: float = Field(ge=0.0, le=100.0)


class AnomalyFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    appliance: str
    mode: str
    flag_type: Literal["과소비", "장시간"]
    detail: str


class _NilmLLMOutput(BaseModel):
    """LLM 구조화 출력 전용 — anomaly_events·mode_references·recent_events는 코드에서 직접 주입."""
    model_config = ConfigDict(extra="forbid")
    top_consumers: list[TopConsumer]
    peak_hours: list[int]
    anomaly_flags: list[AnomalyFlag] = Field(default_factory=list)


# ── 시스템 프롬프트 ─────────────────────────────────────────────────────────────

_SYSTEM = """\
한국 가정 전력 분석 전문가.
제공된 JSON 데이터를 분석해 아래 형식으로 구조화하라.

top_consumers: daily_summary에서 daily_kwh 상위 5개 이하 추출.
  - daily_kwh 0.0이면 제외.
  - mode_references가 있으면 해당 가전의 baseline avg_energy_wh와 비교해 초과율 기록.
peak_hours: hourly_data에서 kwh 상위 3개 시간대의 hour 값 (정수 리스트).
anomaly_flags: recent_events에서 mode_references baseline 대비 비정상 패턴 요약 (있을 때만).
  - energy_wh가 baseline avg_energy_wh의 1.5배 이상이면 "과소비" 플래그.
  - duration이 baseline avg_duration_min의 2배 이상이면 "장시간" 플래그.
"""


# ── 노드 함수 ──────────────────────────────────────────────────────────────────

def nilm_monitor_node(state: dict[str, Any]) -> dict[str, Any]:
    """Module 2: 이상 이벤트 + 가전 소비 패턴 + GCS baseline/이벤트 수집."""
    hh = state["household_id"]

    events_data    = get_anomaly_events(hh, status="active")
    breakdown_data = get_hourly_appliance_breakdown(hh)
    hourly_data    = get_consumption_hourly(hh)

    mode_ref_data    = get_nilm_mode_references(hh)
    recent_evt_data  = get_nilm_recent_events(hh, limit=30)

    raw_events     = events_data.get("raw", [])
    daily_summary  = breakdown_data.get("daily_summary", [])
    hourly_raw     = hourly_data.get("raw", [])
    mode_refs_raw  = mode_ref_data.get("raw", {})
    recent_evts    = recent_evt_data.get("raw", [])

    active_appliances = {item.get("appliance") for item in daily_summary if item.get("daily_kwh", 0) > 0}
    filtered_refs = {k: v for k, v in mode_refs_raw.items() if k in active_appliances} if isinstance(mode_refs_raw, dict) else mode_refs_raw

    payload = {
        "events":           raw_events,
        "daily_summary":    daily_summary,
        "hourly_data":      hourly_raw,
        "mode_references":  filtered_refs,
        "recent_events":    recent_evts,
    }

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    result: _NilmLLMOutput = (
        llm
        .with_structured_output(_NilmLLMOutput)
        .invoke([
            SystemMessage(_SYSTEM),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ])
    )

    output = result.model_dump()
    output["anomaly_events"]   = raw_events
    output["mode_references"]  = mode_refs_raw
    output["recent_events"]    = recent_evts
    return {"nilm_output": output}
