"""Diagnosis Gate — 프롬프트 체이닝 게이트.

nilm_monitor + HITL 직후 실행. nilm_output의 신호 강도를 코드로 측정해
report 단계로 갈 때 full / lite 두 경로 중 하나로 분기한다.

- full: 신호 있음 → 기존 report_node (진단 LLM + 권고 LLM 2회 호출)
- lite: 신호 없음 → report_lite_node (LLM 0회, top_consumers 기반 일반 권고)

기대 효과:
- 평이한 가구(이상·WoW 신호 모두 없음)는 LLM 호출 2회 절감 → 응답 1~2s 단축
- evaluator 단계와 역할 분담: gate는 사전 차단, evaluator는 사후 검증
"""
from __future__ import annotations

import logging
from typing import Any, Literal

logger = logging.getLogger(__name__)


# ── 게이트 임계 ──────────────────────────────────────────────────────────────

# 신호 합계가 이 값 미만이면 lite 경로
_LITE_SIGNAL_THRESHOLD = 1

# lite 경로에서 사용할 보수적 절감률 (이상 신호 없는 일반 사용 가정)
_LITE_SAVINGS_RATE = 0.05

_LITE_UNIT_KRW_FALLBACK = 140  # _DEFAULT_TIER_KRW와 동일, 의존 줄이려 복제


# ── 게이트 노드 ──────────────────────────────────────────────────────────────

def diagnosis_gate(state: dict[str, Any]) -> dict[str, Any]:
    """nilm_output 신호 강도를 측정해 full/lite 경로 결정."""
    nilm = state.get("nilm_output") or {}
    signals = (
        len(nilm.get("anomaly_flags") or [])
        + len(nilm.get("anomaly_events") or [])
        + len(nilm.get("appliance_wow") or [])
    )
    decision: str = "full" if signals >= _LITE_SIGNAL_THRESHOLD else "lite"
    logger.info("diagnosis_gate: signals=%d decision=%s", signals, decision)
    return {"gate_decision": decision}


def gate_route(state: dict[str, Any]) -> Literal["report", "report_lite"]:
    """게이트 결정에 따른 conditional edge target."""
    return "report_lite" if state.get("gate_decision") == "lite" else "report"


# ── 경량 리포트 노드 (LLM 없음) ─────────────────────────────────────────────

def _resolve_unit_krw_local(cashback: dict[str, Any]) -> int:
    """cashback에서 한계 요율 추출. report_agent._resolve_unit_krw의 경량 사본 — 순환 import 회피."""
    if not isinstance(cashback, dict):
        return _LITE_UNIT_KRW_FALLBACK
    tariff = cashback.get("progressive_tariff") or cashback.get("tariff") or {}
    rates = tariff.get("tier_rates_krw") or tariff.get("rates") or []
    tier  = tariff.get("current_tier") or 1
    if isinstance(rates, list) and rates and 1 <= tier <= len(rates):
        try:
            return int(rates[tier - 1]) or _LITE_UNIT_KRW_FALLBACK
        except (TypeError, ValueError):
            return _LITE_UNIT_KRW_FALLBACK
    return _LITE_UNIT_KRW_FALLBACK


def _build_lite_recommendations(top_consumers: list[dict], unit_krw: int) -> list[dict]:
    """신호 없는 가구를 위한 일반 절약 권고 — top_consumers의 대기전력 차단 중심.

    InsightsLLMOutput.recommendations: min_length=3 충족 필수.
    """
    valid = [
        tc for tc in (top_consumers or [])
        if tc.get("daily_kwh", 0) >= 0.01 and "분전반" not in (tc.get("appliance") or "")
    ][:3]

    recs: list[dict] = []
    for tc in valid:
        app = tc.get("appliance") or "기타"
        daily_kwh = float(tc.get("daily_kwh") or 0.5)
        kwh = max(0.01, min(200.0, round(daily_kwh * _LITE_SAVINGS_RATE * 30, 2)))
        krw = int(kwh * unit_krw)
        recs.append({
            "title":       f"{app} 대기전력 차단 멀티탭"[:30],
            "savings_kwh": kwh,
            "savings_krw": max(0, krw),
            "description": (
                f"{app}이(가) 일일 평균 {daily_kwh:.1f}kWh로 가정 내 상위에 해당합니다. "
                f"사용하지 않는 시간에 대기전력을 차단하면 월 기준 약 {krw:,}원 절약이 예상됩니다."
            )[:300],
        })

    # min_length=3 충족용 일반 권고 패딩
    while len(recs) < 3:
        default_kwh = 0.5
        default_krw = int(default_kwh * unit_krw)
        recs.append({
            "title":       "사용 안 하는 멀티탭 끄기",
            "savings_kwh": default_kwh,
            "savings_krw": max(0, default_krw),
            "description": (
                "사용하지 않는 가전의 대기전력만 차단해도 가구당 월 평균 절약 효과가 있습니다. "
                f"월 기준 약 {default_krw:,}원 절약이 예상됩니다."
            )[:300],
        })

    return recs


def report_lite_node(state: dict[str, Any]) -> dict[str, Any]:
    """LLM 없이 top_consumers·tariff만으로 일반 권고 생성. 진단은 빈 배열."""
    nilm     = state.get("nilm_output") or {}
    cashback = state.get("cashback_output") or {}

    top_consumers = nilm.get("top_consumers") or []
    unit_krw      = _resolve_unit_krw_local(cashback)
    recs          = _build_lite_recommendations(top_consumers, unit_krw)

    logger.info("report_lite: 권고 %d건 생성 (LLM 호출 없음)", len(recs))

    return {"final_output": {
        "anomaly_diagnoses": [],
        "recommendations":   recs,
    }}
