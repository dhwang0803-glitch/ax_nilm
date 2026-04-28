"""LLM Agent — 에너지캐시백 월별 절감 권고.

OpenAI GPT-4o-mini API 사용 (function calling 기반 agent loop).
익명화 원칙: household_id·주소·가구원·소득 정보 LLM 입력 제외.
허용 입력: temperature, cluster_label, 절감률, 가전 목록, 유사 달 맥락.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date

from openai import OpenAI

from .tools import (
    TOOL_SCHEMAS,
    ToolResult,
    recommend_appliance_action,
    show_cashback_result,
    show_enrollment_cta,
    show_monthly_trend,
)


@dataclass
class RecommendContext:
    cluster_label: int             # 0=저소비 1=고소비 2=중소비
    cashback_enrolled: bool        # 에너지캐시백 신청 여부
    billing_month: date            # 정산 기준 월
    baseline_kwh: float            # 기준선
    actual_kwh: float              # 이번 달 실측
    savings_rate: float            # 절감률 (0.0~1.0)
    cashback_krw: int              # 캐시백 예상 금액
    house_type: str = ""           # 1인/2~3인/4인+ 가구
    temperature: float | None = None   # 월평균 기온
    windchill: float | None = None     # 월평균 체감온도
    humidity: float | None = None      # 월평균 습도
    top_saving_appliances: list[str] = field(default_factory=list)  # 절감 기여 상위 가전
    top_usage_appliances: list[str]  = field(default_factory=list)  # 사용량 상위 가전
    similar_months_text: str = ""    # RAG 유사 달 패턴
    recent_months: list[str] = field(default_factory=list)           # 최근 월 목록
    recent_savings_rates: list[float] = field(default_factory=list)  # 최근 월 절감률


_CLUSTER_DESC = {0: "저소비형", 1: "고소비형", 2: "중소비형"}

_SYSTEM_PROMPT = """당신은 가정용 에너지캐시백 절감을 돕는 에너지 효율화 어시스턴트입니다.
아래에 명시된 데이터셋 기반 가전 정보와 판단 기준을 반드시 따르세요.
개인 식별 정보(주소·이름·가구원)는 입력되지 않으며, 익명화된 소비 패턴과 기상 데이터만 사용합니다.

## 에너지캐시백 산정 기준
캐시백은 이번 달 총 사용량(kWh)이 기준선보다 얼마나 줄었느냐로만 결정됩니다.
사용 시간대는 무관합니다. 따라서 심야 이동 권고는 하지 않으며,
실제로 월 총 소비량을 줄이는 행동 변화만 권고합니다.

## 데이터셋 가전 분류 (실측 기반)

### 절감 권고 금지 (상시 부하 — 끄면 안 됨)
- 일반 냉장고, 김치 냉장고, 무선공유기/셋톱박스

### 사용 횟수 절감형 (불편함 낮음)
- 세탁기: 세탁물 모아서 한 번에 돌리기 (횟수 줄이기)
- 의류건조기: 자연 건조 병행, 탈수 강도 높여 건조 시간 단축
- 식기세척기: 가득 채워서 한 번에 가동

### 설정 조정형 (온도·타이머 조정 — 불편함 낮음)
- 에어컨: 설정온도 1도 올리기, 취침 타이머 설정
- 제습기: 습도 설정값 올리기 (60% → 65%)
- 전기장판/담요, 온수매트: 취침 후 자동 끔 설정, 단계 낮추기

### 대기전력 절감형 (불편함 낮음)
- TV, 컴퓨터, 공기청정기, 선풍기
  → 미사용 시 콘센트 차단, 절전 모드 설정

### 조리 습관 조정형 (불편함 중간)
- 전자레인지, 에어프라이어, 전기밥솥, 인덕션(전기레인지)
  → 예열 최소화, 잔열 활용, 한꺼번에 조리

### 사용 시간 단축형 (불편함 중간 — 마지막 선택지)
- 헤어드라이기, 전기다리미, 진공 청소기(유선), 전기포트

## 계절·기상 맥락 판단 기준

### 여름 (6~8월 / 월평균 기온 26도 이상 또는 체감온도 28도 이상)
- 에어컨·선풍기·제습기 끄기·사용 중단 권고 절대 금지
- 허용 권고: "설정온도 1도 올리기", "외출 시 타이머 끄기", "습도 설정 조정"

### 겨울 (12~2월 / 월평균 기온 5도 이하 또는 체감온도 0도 이하)
- 전기장판/담요·온수매트 끄기·사용 중단 권고 절대 금지
- 허용 권고: "취침 후 자동 끔 타이머", "단계 1단 낮추기"

### 봄·가을 (3~5월, 9~11월)
- 냉난방 가전 절감 권고 가능 (온화한 날씨)
- 에어컨·전기장판 사용량 자체를 줄이는 방향 제안 가능

## 권고 우선순위 (항상 이 순서로)
1. 설정값 조정 — 에어컨 온도, 제습기 습도, 장판 단계 (불편함 최소)
2. 사용 횟수 절감 — 세탁기 모아 돌리기, 건조기 자연건조 병행
3. 대기전력 차단 — TV·컴퓨터 콘센트, 공기청정기 절전
4. 조리 습관 조정 — 잔열 활용, 예열 최소화, 한꺼번에 조리
5. 사용 시간 단축 — 마지막 선택지, 생활 불편 최소화

## 가구 유형별 맥락
- 1인 가구: 외출·취침 시간이 길어 대기전력 절감 효과 큼
- 2~3인 가구: 세탁·조리 빈도 높아 사용 횟수 절감 효과 큼
- 4인 이상: 냉난방·조리 동시 사용 많아 설정 조정 우선

캐시백 금액이 작더라도 사용자 쾌적함·안전을 해치는 방식은 절대 제안하지 않는다."""


_SEASON = {
    12: "겨울", 1: "겨울", 2: "겨울",
    3: "봄",   4: "봄",   5: "봄",
    6: "여름", 7: "여름", 8: "여름",
    9: "가을", 10: "가을", 11: "가을",
}


def _build_user_prompt(ctx: RecommendContext) -> str:
    cluster_name = _CLUSTER_DESC.get(ctx.cluster_label, "알 수 없음")
    savings_pct  = ctx.savings_rate * 100
    season       = _SEASON[ctx.billing_month.month]

    lines = [
        f"소비 유형: {cluster_name}",
        f"가구 유형: {ctx.house_type}" if ctx.house_type else None,
        f"기준월: {ctx.billing_month.strftime('%Y년 %m월')} ({season})",
        f"기준선: {ctx.baseline_kwh:.1f}kWh / 실측: {ctx.actual_kwh:.1f}kWh",
        f"절감률: {savings_pct:.1f}% / 예상 캐시백: {ctx.cashback_krw:,}원",
    ]
    lines = [l for l in lines if l is not None]

    weather_parts = []
    if ctx.temperature is not None:
        weather_parts.append(f"기온 {ctx.temperature:.1f}도")
    if ctx.windchill is not None:
        weather_parts.append(f"체감 {ctx.windchill:.1f}도")
    if ctx.humidity is not None:
        weather_parts.append(f"습도 {ctx.humidity:.0f}%")
    if weather_parts:
        lines.append("월평균 기상: " + " / ".join(weather_parts))

    if ctx.top_saving_appliances:
        lines.append(f"이번 달 절감 기여 가전: {', '.join(ctx.top_saving_appliances)}")
    if ctx.top_usage_appliances:
        lines.append(f"이번 달 사용량 상위 가전: {', '.join(ctx.top_usage_appliances)}")
    if ctx.similar_months_text:
        lines.append(f"\n[유사 달 패턴]\n{ctx.similar_months_text}")

    if ctx.cashback_enrolled:
        lines.append(
            "\n이 가구는 에너지캐시백에 신청되어 있습니다. "
            "이번 달 결과를 보여주고 다음 달 절감을 위한 가전별 행동 방안을 제안해주세요."
        )
    else:
        lines.append(
            "\n이 가구는 에너지캐시백 미신청 상태입니다. "
            "신청 유도 메시지를 먼저 보여주세요."
        )

    return "\n".join(lines)


def _dispatch_tool(name: str, inputs: dict) -> ToolResult:
    if name == "show_cashback_result":
        return show_cashback_result(inputs["savings_kwh"], inputs["cashback_krw"])
    if name == "show_enrollment_cta":
        return show_enrollment_cta(inputs.get("enrollment_url"))
    if name == "recommend_appliance_action":
        return recommend_appliance_action(inputs["actions"])
    if name == "show_monthly_trend":
        return show_monthly_trend(inputs["months"], inputs["savings_rates"])
    raise ValueError(f"알 수 없는 도구: {name}")


def run_recommendation(
    ctx: RecommendContext,
    max_iterations: int = 5,
) -> list[ToolResult]:
    """Agent loop 실행 — 도구 호출 결과 목록 반환."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY 환경변수 필요")

    client = OpenAI(api_key=api_key)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": _build_user_prompt(ctx)},
    ]
    results: list[ToolResult] = []

    for _ in range(max_iterations):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1024,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        choice = response.choices[0]
        if choice.finish_reason != "tool_calls":
            break

        tool_calls = choice.message.tool_calls or []
        if not tool_calls:
            break

        messages.append(choice.message)

        for tc in tool_calls:
            inputs = json.loads(tc.function.arguments)
            result = _dispatch_tool(tc.function.name, inputs)
            results.append(result)
            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      json.dumps(result.payload, ensure_ascii=False),
            })

    return results
