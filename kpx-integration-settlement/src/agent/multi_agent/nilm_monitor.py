"""Module 2 — NILM 모니터링 노드.

이상 이벤트 수집 + 가전별 소비 패턴 파악.
도구 호출은 항상 동일하므로 ReAct 없이 직접 호출 후 LLM으로 구조화.
3개 도구(get_anomaly_events, get_hourly_appliance_breakdown, get_consumption_hourly)는
ThreadPoolExecutor로 병렬 실행한다.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    flag_type: Literal["과소비", "장시간", "피크스파이크", "에너지이상"]
    detail: str


class _NilmLLMOutput(BaseModel):
    """LLM 구조화 출력 전용 — anomaly_events·mode_references·recent_events는 코드에서 직접 주입."""
    model_config = ConfigDict(extra="forbid")
    top_consumers: list[TopConsumer]
    peak_hours: list[int]
    anomaly_flags: list[AnomalyFlag] = Field(default_factory=list)


# ── 가전 유형 분류 ────────────────────────────────────────────────────────────
# A: 상시 가동 — 이벤트 비교 제외, 피크스파이크만
# B: 다단계 자동 사이클 — 이벤트 비교 제외, 피크스파이크만
# C: 단발 사용 — 전부 적용 (기본값)
# D: 장시간 세션 — 장시간 제외, 나머지 적용

_APPLIANCE_TYPE: dict[str, str] = {
    "일반 냉장고": "A", "냉장고": "A", "김치냉장고": "A", "무선공유기/셋톱박스": "A",
    "세탁기": "B", "식기세척기/건조기": "B", "식기세척기": "B", "의류건조기": "B",
    "에어컨": "D", "제습기": "D", "전기장판/담요": "D", "온수매트": "D",
    "TV": "D", "컴퓨터": "D", "컴퓨터(데스크탑)": "D", "선풍기": "D", "공기청정기": "D",
    "전기밥솥": "D", "인덕션(전기레인지)": "D", "인덕션": "D",
    "전자레인지": "C", "전기포트": "C", "헤어드라이기": "C",
    "진공청소기": "C", "진공청소기(유선)": "C", "전기다리미": "C", "에어프라이어": "C",
}
_DEFAULT_TYPE = "C"

# ── 사전 필터링 상수 ──────────────────────────────────────────────────────────

_MAIN_BREAKER: frozenset[str] = frozenset({"메인 분전반", "메인분전반", "MAIN"})

_STANDBY_W_THRESHOLD = 5.0
_MIN_DURATION_FLOOR_MIN = 5.0
_MIN_BASELINE_SAMPLES = 30
_MICRO_SEGMENT_ENERGY_WH = 5.0
_MICRO_SEGMENT_SAMPLE_MIN = 100
_PEAK_W_SPIKE = 1000.0
_OUTLIER_ENERGY_RATIO = 5.0

_MODE_SYNONYMS: dict[str, str] = {
    "사용중": "가동",
}


def _normalize_mode(mode: str) -> str:
    return _MODE_SYNONYMS.get(mode, mode)


def _prefilter_events(events: list[dict]) -> list[dict]:
    """대기 세그먼트 제거 + 모드명 정규화."""
    filtered = []
    for evt in events:
        if (evt.get("avg_w") or 0) < _STANDBY_W_THRESHOLD:
            continue
        filtered.append({**evt, "mode": _normalize_mode(evt.get("mode", ""))})
    return filtered


def _annotate_mode_refs(mode_refs: dict) -> dict:
    """저신뢰 baseline 마킹 + duration 임계 바닥값 + 모드명 정규화 + 가전 유형."""
    annotated: dict = {}
    for appliance, ref in mode_refs.items():
        modes = ref.get("modes", {})
        new_modes: dict = {}
        for mode_name, mode_data in modes.items():
            entry = {**mode_data}
            sample_count = entry.get("sample_count") or 0
            avg_energy = entry.get("avg_energy_wh") or 0
            if sample_count < _MIN_BASELINE_SAMPLES:
                entry["low_confidence"] = True
            elif (avg_energy < _MICRO_SEGMENT_ENERGY_WH
                  and sample_count >= _MICRO_SEGMENT_SAMPLE_MIN):
                entry["low_confidence"] = True
            avg_dur = entry.get("avg_duration_min") or 0
            if 0 < avg_dur < 2.0:
                entry["duration_threshold_min"] = _MIN_DURATION_FLOOR_MIN
            new_modes[_normalize_mode(mode_name)] = entry
        atype = _APPLIANCE_TYPE.get(appliance, _DEFAULT_TYPE)
        annotated[appliance] = {**ref, "modes": new_modes, "type": atype}
    return annotated


def _detect_absolute_anomalies(
    events: list[dict], mode_refs: dict,
) -> list[dict]:
    """low_confidence 모드: 가전 유형별 절대 임계값 탐지.

    A/B: 피크스파이크만.  C/D: 피크스파이크 + 에너지이상.
    """
    lc_modes: set[tuple[str, str]] = set()
    app_types: dict[str, str] = {}
    if isinstance(mode_refs, dict):
        for appliance, ref in mode_refs.items():
            app_types[appliance] = ref.get("type", _DEFAULT_TYPE)
            for mode_name, mode_data in ref.get("modes", {}).items():
                if mode_data.get("low_confidence"):
                    lc_modes.add((appliance, mode_name))

    groups: dict[tuple[str, str], list[float]] = {}
    for evt in events:
        key = (evt.get("appliance", ""), evt.get("mode", ""))
        if key in lc_modes:
            groups.setdefault(key, []).append(evt.get("energy_wh") or 0)

    medians: dict[tuple[str, str], float] = {}
    for key, energies in groups.items():
        s = sorted(energies)
        n = len(s)
        medians[key] = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

    seen: set[tuple[str, str, str]] = set()
    flags: list[dict] = []
    for evt in events:
        key = (evt.get("appliance", ""), evt.get("mode", ""))
        if key not in lc_modes:
            continue
        atype = app_types.get(key[0], _DEFAULT_TYPE)
        peak = evt.get("peak_w") or 0
        energy = evt.get("energy_wh") or 0
        med = medians.get(key, 0)

        if peak >= _PEAK_W_SPIKE:
            dedup_key = (key[0], key[1], "피크스파이크")
            if dedup_key not in seen:
                seen.add(dedup_key)
                flags.append({
                    "appliance": key[0], "mode": key[1],
                    "flag_type": "피크스파이크",
                    "detail": f"peak {peak:.0f}W (임계 {_PEAK_W_SPIKE:.0f}W 초과)",
                })
        if (atype in ("C", "D")
              and med > 0
              and energy >= med * _OUTLIER_ENERGY_RATIO):
            dedup_key = (key[0], key[1], "에너지이상")
            if dedup_key not in seen:
                seen.add(dedup_key)
                flags.append({
                    "appliance": key[0], "mode": key[1],
                    "flag_type": "에너지이상",
                    "detail": f"energy {energy:.1f}Wh (중앙값 {med:.1f}Wh의 {energy/med:.1f}배)",
                })

    return flags


# ── 시스템 프롬프트 ─────────────────────────────────────────────────────────────

_SYSTEM = """\
한국 가정 전력 분석 전문가.
제공된 JSON 데이터를 분석해 아래 형식으로 구조화하라.

top_consumers: daily_summary에서 daily_kwh 상위 5개 이하 추출.
  - daily_kwh 0.0이면 제외.
  - mode_references가 있으면 해당 가전의 baseline avg_energy_wh와 비교해 초과율 기록.
peak_hours: hourly_data에서 kwh 상위 3개 시간대의 hour 값 (정수 리스트).
anomaly_flags: recent_events에서 mode_references baseline 대비 비정상 패턴 요약.
  가전 유형(type 필드)별 규칙:
  - A(상시 가동)/B(다단계 사이클): baseline 비교 전면 제외. 코드에서 피크스파이크만 탐지.
  - C(단발 사용): 과소비 + 장시간 적용.
  - D(장시간 세션): 과소비만 적용. 장시간 제외 (사용 시간은 사용자 선택).
  공통:
  - 과소비: energy_wh > baseline avg_energy_wh × 1.5.
  - 장시간: duration_threshold_min이 있으면 해당 값, 없으면 avg_duration_min × 2.
  - low_confidence: true인 모드는 baseline 비교 제외. 절대 임계(피크스파이크/에너지이상)는 코드에서 수행.
  - 매칭되는 모드가 없으면 스킵.
  주의: 대기 세그먼트(avg_w < 5W)와 모드명 동의어는 코드에서 사전 처리 완료 상태.
"""


# ── 노드 함수 ──────────────────────────────────────────────────────────────────

def nilm_monitor_node(state: dict[str, Any]) -> dict[str, Any]:
    """Module 2: 이상 이벤트 + 가전 소비 패턴 + GCS baseline/이벤트 수집."""
    hh = state["household_id"]

    # 3개 도구를 병렬 실행 — LLM 호출 전 데이터 수집 시간 단축
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_events    = pool.submit(get_anomaly_events, hh, status="active")
        f_breakdown = pool.submit(get_hourly_appliance_breakdown, hh)
        f_hourly    = pool.submit(get_consumption_hourly, hh)
        events_data    = f_events.result()
        breakdown_data = f_breakdown.result()
        hourly_data    = f_hourly.result()

    mode_ref_data    = get_nilm_mode_references(hh)
    recent_evt_data  = get_nilm_recent_events(hh, limit=30)

    raw_events     = events_data.get("raw", [])
    daily_summary  = breakdown_data.get("daily_summary", [])
    hourly_raw     = hourly_data.get("raw", [])
    mode_refs_raw  = mode_ref_data.get("raw", {})
    recent_evts    = recent_evt_data.get("raw", [])

    # before_kw가 명시적으로 0(평소 미사용 → 신규 사용)일 때만 제외.
    # 필드 자체가 없는 케이스(_db_anomaly_events 출력)는 통과해야 진단 대상에 포함됨.
    raw_events = [e for e in raw_events if not ("before_kw" in e and (e.get("before_kw") or 0) == 0)]
    # 메인 분전반은 집계 채널 — 모든 가전 분석 경로에서 제외
    raw_events = [e for e in raw_events if e.get("appliance") not in _MAIN_BREAKER]
    daily_summary = [item for item in daily_summary if item.get("appliance") not in _MAIN_BREAKER]
    recent_evts = [e for e in recent_evts if e.get("appliance") not in _MAIN_BREAKER]
    if isinstance(mode_refs_raw, dict):
        mode_refs_raw = {k: v for k, v in mode_refs_raw.items() if k not in _MAIN_BREAKER}

    active_appliances = {item.get("appliance") for item in daily_summary if item.get("daily_kwh", 0) > 0}
    filtered_refs = {k: v for k, v in mode_refs_raw.items() if k in active_appliances} if isinstance(mode_refs_raw, dict) else mode_refs_raw

    annotated_refs = _annotate_mode_refs(filtered_refs) if isinstance(filtered_refs, dict) else filtered_refs
    filtered_evts = _prefilter_events(recent_evts)

    payload = {
        "events":           raw_events,
        "daily_summary":    daily_summary,
        "hourly_data":      hourly_raw,
        "mode_references":  annotated_refs,
        "recent_events":    filtered_evts,
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
    abs_flags = _detect_absolute_anomalies(filtered_evts, annotated_refs)
    output["anomaly_flags"] = output.get("anomaly_flags", []) + abs_flags
    output["anomaly_events"]   = raw_events
    output["mode_references"]  = annotated_refs if isinstance(annotated_refs, dict) else mode_refs_raw
    output["recent_events"]    = filtered_evts
    return {"nilm_output": output}
