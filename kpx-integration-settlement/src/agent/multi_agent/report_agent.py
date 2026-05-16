"""Module 5 — AI 진단 리포트 에이전트.

Module 2(NILM 모니터링) + Module 3(캐시백 계산) 결과를 받아
이상 진단 + 절감 권고를 최종 생성한다. LLM은 structured_output만 사용.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any


def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..schemas import InsightsLLMOutput
from .. import ontology


def _build_system_prompt() -> str:
    guidance         = ontology.appliance_guidance_text()
    essential        = "·".join(ontology.essential_appliances())
    essential_verbs  = "·".join(ontology.essential_forbidden_verbs())
    cooling          = "·".join(ontology.cooling_appliances())
    heating          = "·".join(ontology.heating_appliances())
    forbidden        = "·".join(ontology.forbidden_phrases())
    hot_t            = ontology.hot_threshold()
    cold_t           = ontology.cold_threshold()

    return f"""\
한국 가정 전력 절감 전문 코치.
NILM 모니터링 결과·캐시백 계산 결과·날씨 데이터를 받아 아래 JSON 형식으로만 응답.

## 입력 데이터
- nilm.anomaly_events: 실시간 이상 이벤트 (before_kw, after_kw 포함)
- nilm.top_consumers: 가전별 일일 kWh 상위
- nilm.peak_hours: 피크 시간대
- nilm.anomaly_flags: 비정상 플래그. 4가지 타입:
  과소비/장시간 = baseline 대비 비교 (C/D 유형, 신뢰 baseline만).
  피크스파이크 = peak_w ≥ 1000W (모든 유형). 에너지이상 = 그룹 중앙값 5배 초과 (C/D만).
  각 플래그는 appliance·mode·flag_type·detail 필드를 포함:
    - mode: 이상이 발생한 운전 모드 (예: 냉방·제습·송풍·난방·취사·제습 등)
    - flag_type: "과소비" (에너지 과다) 또는 "장시간" (지속 시간 과다)
- nilm.mode_references: 가전별 모드 baseline + type 필드 (A상시/B다단계/C단발/D장시간).
  low_confidence: true이면 sample 부족 또는 마이크로 세그먼트 — 진단 시 단정적 표현 자제.
  duration_threshold_min 있으면 해당 값이 장시간 판정 임계 (마이크로 세그먼트 보정).
- nilm.recent_events: 최근 가전 사용 이벤트 (avg_w < 5W 대기 세그먼트 제거 완료)
- cashback: 캐시백 절감 계산 결과
- weather: 최근 날씨 데이터

## 출력 형식
{{
  "anomaly_diagnoses": [{{"event_id": "...", "diagnosis": "...", "action": "..."}}],
  "recommendations": [{{"title": "...", "savings_kwh": 0.0}}]
}}

## 진단 규칙
diagnosis: 이벤트의 before_kw·after_kw 값을 사용해 "지난주 평균 X → Y kW (Z%↑)" 형식으로 작성 (100자 이내). before_kw/after_kw 없으면 description 기반으로 작성.
mode_references 있으면 baseline 대비 실제 에너지 초과율을 진단에 포함 (예: "baseline 120Wh 대비 210Wh (75%↑)").
low_confidence 모드의 진단은 "baseline 신뢰도 낮음" 접미 표기.
anomaly_flags에 플래그가 있으면 해당 가전의 진단을 우선 작성. 동일 가전에 여러 플래그가 있으면 병합해 단일 진단으로 작성.
flag_type별 action 방향:
  - 과소비 + 냉방·제습·고온 모드: 필터·코일 막힘 등 성능 저하 의심 → action 예: "필터 청소", "코일 점검"
  - 과소비 + 기타 모드: 기기 이상 의심 → action 예: "점검 의뢰", "가스켓 점검"
  - 장시간 (모드 무관): 사용 습관 개선 → action 예: "타이머 설정", "자동 꺼짐"
  - diagnosis에 mode 명시: "에어컨 냉방 모드 과소비" 형식으로 모드명 포함.
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

## 안전 규칙 [MANDATORY]
1. 필수 가전({essential})은 어떤 경우에도 {essential_verbs} 표현 사용 금지. 사용 시간 단축·줄이기 등도 포함. 유일하게 허용되는 권고 방향: 도어·코일·가스켓 등 성능 점검.
2. 다음 표현은 title·action·diagnosis 어디에도 사용 금지: {forbidden}

## 계절 제약 [MANDATORY]
- 냉방 가전({cooling}): 기온 ≥ {hot_t}°C 시즌에만 권고. weather 기온이 미달이면 해당 가전은 권고 목록에서 제외.
- 난방 가전({heating}): 기온 ≤ {cold_t}°C 시즌에만 권고. weather 기온이 초과면 해당 가전은 권고 목록에서 제외.

## 권고 규칙
3~5개. top_consumers에서 daily_kwh 큰 순서로 선택.
title: 시간대·수치·기기명 조합 (30자 이내).
- 동일 기기명은 시간대(아침/저녁/밤 등)를 달리해도 절대 중복 사용 금지 — 기기명 기준으로 전체 권고 목록에서 단 1회만 등장.
- "메인 분전반"은 특정 가전이 아닌 집계 채널이므로 권고 대상에서 제외.
savings_kwh: 해당 기기 daily_kwh × 절감률 0.05~0.10 × 30일 (0.1~10.0 범위).
- 각 항목은 서로 다른 기기 (peak_hours 참고해 시간대 명시)
- daily_kwh 0.1 kWh 미만 기기 제외
- 가전 교체·구매·인프라 투자 금지
- mode_references 있으면 standby_avg_w가 높은 가전의 대기전력 절감 권고 추가 고려

## 가전별 권고 방향 [NILM 기반 적용 규칙]
NILM은 전력 파형만 측정 → 가동 시간·소비량·대기전력만 관찰 가능. 기기 내부 설정값(온도·화력 단계 등) 측정 불가.
허용 권고 방향: 사용 시간 단축·대기전력 절감 (실제 kWh 감소 수반).
금지 권고 방향: 시간대 이동·피크 회피 — 총 kWh 절감 없으므로 title·action에 절대 사용 금지.
title은 관찰된 소비 패턴(daily_kwh·사용 시간)을 근거로 작성한다.
예) TV "피크 시간대 사용 조정" 금지 → "저녁 TV 2시간 단축 X원" (관찰된 사용 시간 기반)
예) 에어컨 "설정 조정" 금지 → "저녁 에어컨 2시간 단축 X원" (관찰된 사용 시간 기반)
예) 전기장판 "설정 조정" 금지 → "취침 전기장판 1시간 단축 X원" (관찰된 야간 사용 기반)
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
            HumanMessage(content=json.dumps(payload, ensure_ascii=False, default=_json_default)),
        ])
    )

    return {"final_output": result.model_dump()}
