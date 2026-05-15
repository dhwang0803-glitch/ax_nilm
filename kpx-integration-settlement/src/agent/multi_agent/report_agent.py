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

## 입력 데이터
- nilm.anomaly_events: 실시간 이상 이벤트 (before_kw, after_kw 포함)
- nilm.top_consumers: 가전별 일일 kWh 상위
- nilm.peak_hours: 피크 시간대
- nilm.anomaly_flags: 비정상 플래그. 4가지 타입:
  과소비/장시간 = baseline 대비 비교 (C/D 유형, 신뢰 baseline만).
  피크스파이크 = peak_w ≥ 1000W (모든 유형). 에너지이상 = 그룹 중앙값 5배 초과 (C/D만).
- nilm.mode_references: 가전별 모드 baseline + type 필드 (A상시/B다단계/C단발/D장시간).
  low_confidence: true이면 sample 부족 또는 마이크로 세그먼트 — 진단 시 단정적 표현 자제.
  duration_threshold_min 있으면 해당 값이 장시간 판정 임계 (마이크로 세그먼트 보정).
- nilm.recent_events: 최근 가전 사용 이벤트 (avg_w < 5W 대기 세그먼트 제거 완료)
- cashback: 캐시백 절감 계산 결과
- weather: 최근 날씨 데이터

## 출력 형식
{
  "anomaly_diagnoses": [{"event_id": "...", "diagnosis": "...", "action": "..."}],
  "recommendations": [{"title": "...", "savings_kwh": 0.0}]
}

## 진단 규칙
diagnosis: 이벤트의 before_kw·after_kw 값을 사용해 "지난주 평균 X → Y kW (Z%↑)" 형식으로 작성 (100자 이내). before_kw/after_kw 없으면 description 기반으로 작성.
mode_references 있으면 baseline 대비 실제 에너지 초과율을 진단에 포함 (예: "baseline 120Wh 대비 210Wh (75%↑)").
low_confidence 모드의 진단은 "baseline 신뢰도 낮음" 접미 표기.
anomaly_flags에 플래그가 있으면 해당 가전의 진단을 우선 작성.
action: 2~6자 명사형 (예: "가스켓 점검", "필터 청소") — 사용 중단 지시 금지.
이상 이벤트 없으면 anomaly_diagnoses 빈 배열([]).

## 권고 규칙
3~5개. top_consumers에서 daily_kwh 큰 순서로 선택.
title: 시간대·수치·기기명 조합 (30자 이내). 동일 기기명은 절대 중복 사용 금지.
savings_kwh: 해당 기기 daily_kwh × 절감률 0.05~0.10 × 30일 (0.1~10.0 범위).
- 각 항목은 서로 다른 기기 + 서로 다른 시간대 (peak_hours 참고)
- daily_kwh 0.1 kWh 미만 기기 제외
- 가전 교체·구매·인프라 투자 금지
- 계절 고려: 날씨 데이터 기온 기준으로 냉·난방 가전 권고 방향 결정
- mode_references 있으면 standby_avg_w가 높은 가전의 대기전력 절감 권고 추가 고려

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
