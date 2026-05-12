"""Module 5 — AI 진단 리포트 에이전트.

Module 2(NILM 모니터링) + Module 3(캐시백 계산) 결과를 받아
이상 진단 + 절감 권고를 최종 생성한다. LLM은 structured_output만 사용.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..data_tools import get_weather
from ..schemas import InsightsLLMOutput


# ── 시스템 프롬프트 ─────────────────────────────────────────────────────────────

_SYSTEM = """\
한국 가정 전력 절감 전문 코치.
NILM 모니터링 결과·캐시백 계산 결과·날씨 데이터를 받아 아래 JSON 형식으로만 응답.

## 출력 형식
{
  "anomaly_diagnoses": [{"event_id": "...", "diagnosis": "...", "action": "..."}],
  "recommendations": [{"title": "...", "savings_kwh": 0.0}]
}

## 진단 규칙
diagnosis: "지난주 평균 X → Y kW" 또는 "사용시간 X% 증가" 형식 (100자 이내).
action: 2~6자 명사형 (예: "가스켓 점검", "필터 청소") — 사용 중단 지시 금지.
이상 이벤트 없으면 anomaly_diagnoses 빈 배열([]).

## 권고 규칙
3~5개. top_consumers에서 daily_kwh 큰 순서로 선택.
title: 시간대·수치·기기명 조합 (30자 이내).
savings_kwh: 해당 기기 daily_kwh × 절감률 0.05~0.10 × 30일 (0.1~10.0 범위).
- 각 항목은 서로 다른 시간대 (peak_hours 참고)
- daily_kwh 0.1 kWh 미만 기기 제외
- 가전 교체·구매·인프라 투자 금지
- 계절 고려: 날씨 데이터 기온 기준으로 냉·난방 가전 권고 방향 결정

가전별 권고 방향 (시간대 이동은 총 kWh 절감 없음 → 제외):
- 설정 조정: 에어컨 → "온도 1°C 조정", 전기장판·온수매트 → "온도 단계 낮추기", 인덕션 → "화력 단계 낮추기"
- 효율 사용: 전기포트 → "필요한 양만", 전기밥솥 → "취사 예약 활용", 전기다리미 → "모아서 한 번에"
- 절전 설정만 (미사용·줄이기 표현 금지): TV·컴퓨터 → "절전 모드·타이머", 선풍기 → "풍속 낮추기·타이머", 공기청정기 → "자동·취침 모드"
- 상시 가동 (점검·설정만): 냉장고·김치냉장고 → "온도 최적화·도어·코일 점검"
- 무선공유기·셋톱박스: 장시간 미사용 시 전원 차단 권고 가능"""


# ── 노드 함수 ──────────────────────────────────────────────────────────────────

def report_node(state: dict[str, Any]) -> dict[str, Any]:
    """Module 5: NILM + 캐시백 데이터를 받아 이상 진단 + 절감 권고 생성."""
    hh              = state["household_id"]
    nilm_output     = state.get("nilm_output") or {}
    cashback_output = state.get("cashback_output") or {}
    rag_chunks      = state.get("rag_context") or []

    today = date.today()
    date_range = [(today - timedelta(days=7)).isoformat(), today.isoformat()]
    weather_data = get_weather(date_range)

    payload = {
        "nilm":        nilm_output,
        "cashback":    cashback_output,
        "weather":     weather_data.get("raw", {}),
        "rag_context": rag_chunks,
    }

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    result: InsightsLLMOutput = (
        llm
        .with_structured_output(InsightsLLMOutput)
        .invoke([
            SystemMessage(_SYSTEM),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ])
    )

    return {"final_output": result.model_dump()}
