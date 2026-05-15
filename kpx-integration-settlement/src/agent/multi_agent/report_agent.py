"""Module 5 — AI 진단 리포트 에이전트.

Module 2(NILM 모니터링) + Module 3(캐시백 계산) 결과를 받아
이상 진단 + 절감 권고를 최종 생성한다. LLM은 structured_output만 사용.
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..schemas import InsightsLLMOutput
from .. import ontology


def _build_system_prompt() -> str:
    guidance = ontology.appliance_guidance_text()
    return f"""\
한국 가정 전력 절감 전문 코치.
NILM 모니터링 결과·캐시백 계산 결과·날씨 데이터를 받아 아래 JSON 형식으로만 응답.

## 출력 형식
{{
  "anomaly_diagnoses": [{{"event_id": "...", "diagnosis": "...", "action": "..."}}],
  "recommendations": [{{"title": "...", "savings_kwh": 0.0}}]
}}

## 진단 규칙
diagnosis: 이벤트의 before_kw·after_kw 값을 사용해 "지난주 평균 X → Y kW (Z%↑)" 형식으로 작성 (100자 이내). before_kw/after_kw 없으면 description 기반으로 작성.
action: 2~6자 명사형 (예: "가스켓 점검", "필터 청소") — 사용 중단 지시 금지.
이상 이벤트 없으면 anomaly_diagnoses 빈 배열([]).

## 가구 컨텍스트 활용
household_profile의 members(가구원 수)·area_m2·appliances 목록을 참고해 권고 실현 가능성 판단.
appliances에 없는 기기는 권고 대상에서 제외.

## 누진 요금 활용
cashback.progressive_tariff를 참고해 권고의 요금 절감 임팩트를 구체화한다.
- current_tier=2이고 kwh_to_next_tier가 50 이하면 "단계 초과 방지" 관점 강조 가능
- current_tier=3이면 한계 요율(tier_rates_krw[2])이 높으므로 절감 권고가 더 강한 효과
- savings_kwh 산정 시 한계 요율을 고려해 실질 절감액(원)을 title에 포함할 수 있음

## 권고 규칙
3~5개. top_consumers에서 daily_kwh 큰 순서로 선택.
title: 시간대·수치·기기명 조합 (30자 이내). 동일 기기명은 절대 중복 사용 금지.
savings_kwh: 해당 기기 daily_kwh × 절감률 0.05~0.10 × 30일 (0.1~10.0 범위).
- 각 항목은 서로 다른 기기 + 서로 다른 시간대 (peak_hours 참고)
- daily_kwh 0.1 kWh 미만 기기 제외
- 가전 교체·구매·인프라 투자 금지
- 계절 고려: 날씨 데이터 기온 기준으로 냉·난방 가전 권고 방향 결정

가전별 권고 방향 (시간대 이동은 총 kWh 절감 없음 → 제외):
{guidance}"""


# ── 노드 함수 ──────────────────────────────────────────────────────────────────

def report_node(state: dict[str, Any]) -> dict[str, Any]:
    """Module 5: NILM + 캐시백 데이터를 받아 이상 진단 + 절감 권고 생성."""
    hh                = state["household_id"]
    nilm_output       = state.get("nilm_output") or {}
    cashback_output   = state.get("cashback_output") or {}
    rag_chunks        = state.get("rag_context") or []
    weather_output    = state.get("weather_output") or {}
    household_profile = state.get("household_profile") or {}

    payload = {
        "household_profile": household_profile,
        "nilm":              nilm_output,
        "cashback":          cashback_output,
        "weather":           weather_output,
        "rag_context":       rag_chunks,
    }

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    result: InsightsLLMOutput = (
        llm
        .with_structured_output(InsightsLLMOutput)
        .invoke([
            SystemMessage(_build_system_prompt()),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ])
    )

    return {"final_output": result.model_dump()}
