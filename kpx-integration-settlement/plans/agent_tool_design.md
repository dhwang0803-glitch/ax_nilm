# 전력 에너지 코치 AI Agent — 정보 제공 설계 (Tool-use 패턴)

> 작성일: 2026-04-28  
> 대상: 전력 에너지 코치 LLM Agent 설계 담당 팀원  
> 결정: 임베딩 기반 컨텍스트 주입 → **Tool-use 패턴으로 전환**

---

## 0. 왜 Tool-use 패턴인가 → 임베딩 접근의 문제

기존 계획: 가구 메타/날씨/7일 전력 패턴을 임베딩 → LLM의 컨텍스트로 주입 → 임베딩 모델 3개 비교 후 LLM에게 설명시켜 평가.

**왜 안 되는 이유:**

1. **LLM은 원시 임베딩 벡터를 읽지 못함.** 임베딩 모델과 LLM은 같은 표현 공간을 공유하지 않음. 어댑터(LLaVA류) 없이 float 배열을 system prompt에 넣으면 LLM 입장에서 무의미한 숫자 시퀀스. 틀린 코드가 전달되는 근본 원인.
2. **시계열의 텍스트 임베딩 모델을 통과시키는 건 손실 피해.** 전력 패턴의 구조적 시계열 → 텍스트 임베딩 공간에 매핑할 대기가 약함.
3. **임베딩 모델 평가의 전략이 잘못 정의됨.** "LLM이 잘 설명한다"가 아니라 downstream task 성능(Recall@K, 답변 정확도)으로 측정해야 함.
4. **임베딩 → 원문 복원이라는 이중 구조**는 복잡도만 올리고, 결국 raw 데이터를 다시 주입하는 거라 임베딩 단계의 가치가 없음.

**Tool-use 패턴의 장점:**

- LLM이 필요한 정보만 도구로 호출 → 컨텍스트 윈도우 절약
- 어떤 데이터로 권고하는지 트레이스 명확 → 디버깅·감사 용이
- 임베딩 모델 선택 문제 자체가 사라짐
- 가구별 데이터 접근 제어를 도구 단위에서 차단 → 보안 단순화
- 신 데이터 소스(예: KEPCO 요금제 변경) 추가 시 도구 한 개 추가로 됨

**트레이드오프:**

- tool-call 라운드만큼 latency↑ (보통 1~3 round로 끝남)
- 프롬프트 엔지니어링 비중 커짐 (어떤 도구를 언제 부를지 LLM에게 가르쳐야 함)

---

## 1. 전체 구조

```
───────────────────────────────────────────────
  System Prompt (Persona + Tool 카탈로그)
  - 코치 퍼르소나
  - 사용 가능 도구 목록 (JSON schema)
  - 권고 형식 / 금지사항
─────────────────────┬─────────────────────────
                     │
           ──────────▼───────────
           │  Initial Context    │ ← 매 세션 시작 시 baseline
           │  - 가구 메타 (요약) │
           │  - 직전 7일 요약    │   자연어 + 핵심 수치
           │     (자연어)        │
           ─────────────────────
                     │
              사용자 질문
                     │
           ──────────▼───────────
           │  LLM 추론           │
           │  필요시 tool 호출   │ ← 0~3 라운드
           ─────────────────────
                     │
              응답 (JSON 형식)
                     │
           ──────────▼───────────
           │  핸드오프 처리       │
           │  - schema 검증      │
           │  - 가드레일         │
           │  - 트레이스 로깅    │
           ─────────────────────
```

---

## 2. Tool 카탈로그 설계

도구는 **원자 단위**로 쪼갬. LLM이 필요한 만큼 조합해서 부름. 각 도구는 (a) 자연어 요약 + (b) 구조화된 raw data를 함께 반환해 LLM이 더 다양하게 활용 가능.

> **익명화 원칙**: 모든 도구는 `household_id`(익명화된 토큰)만 입력으로 받으며, 반환값에 개인 식별 정보(실명, 실제 주소, 전화번호 등)를 포함하지 않음. LLM(외부 API)에 전달되는 모든 데이터는 가구 식별 불가 수준으로 익명화된 상태여야 함.

### 2.1 가구 정보

```python
get_household_profile(household_id: str) -> dict
"""
반환:
  {
    "summary": "85㎡ 24층 아파트, 4인 가구, 1등급 에어컨/2등급 냉장고",
    "raw": {
      "house_type": "아파트", "area_m2": 85, "members": 4,
      "appliances": [
        {"name": "에어컨", "energy_efficiency": 1, "estimated_w": 1200},
        ...
      ],
      "subscription": "주택용(저압) 누진 3단계"
    }
  }
"""
```

### 2.2 날씨 / 일기예보

```python
get_weather(date_range: tuple[str, str], location: str) -> dict
"""
과거 날씨 데이터.
반환:
  {
    "summary": "2026-04-21~27 평균 18°C(평년 +2.1°C), 강수 0mm",
    "raw": [
      {"date": "2026-04-21", "tavg": 17.5, "tmax": 23.1, "tmin": 12.3,
       "wind": 2.1, "rh": 55},
      ...
    ]
  }
"""

get_forecast(days_ahead: int = 7, location: str) -> dict
"""
일기예보. 동일 형식.
"""
```

### 2.3 전력 소비

```python
get_consumption_summary(household_id: str, period: str) -> dict
"""
period: "today" | "week" | "month" | "ISO date range"
반환:
  {
    "summary": "직전 7일 총 92.3kWh, 일 평균 13.2kWh, 전년 동기 대비 +18%.
                피크 19~21시 평균 2.1kW. 주말 +22%.",
    "raw": {
      "total_kwh": 92.3, "daily_avg_kwh": 13.2,
      "yoy_change_pct": 18.0,
      "peak_hours": [19, 20, 21],
      "peak_avg_w": 2100,
      "weekend_uplift_pct": 22.0
    }
  }
"""

get_consumption_hourly(household_id: str, date: str) -> dict
"""
하루 24시간 시간대별 kWh.
반환:
  {
    "summary": "2026-04-27, 0~6시 0.3kWh/h(기저), 19~21시 2.1kWh/h(피크)",
    "raw": [
      {"hour": 0, "kwh": 0.31}, ..., {"hour": 23, "kwh": 0.45}
    ]
  }
"""

get_consumption_breakdown(household_id: str, date: str) -> dict
"""
NILM 분해 결과 → 가전별 사용량.
반환:
  {
    "summary": "2026-04-27 에어컨 4.2kWh(35%), 냉장고 2.3kWh(19%), TV 1.1kWh(9%)",
    "raw": [
      {"appliance": "에어컨", "kwh": 4.2, "share_pct": 35.0,
       "active_intervals": [{"start": "13:20", "end": "15:45"}]},
      ...
    ]
  }
"""
```

### 2.4 외부 컨텍스트

```python
get_cashback_history(household_id: str, date_range: tuple[str, str] | None = None) -> dict
"""
에너지캐시백 월별 절감 실적·지급 내역. KEPCO 주택용 에너지캐시백 프로그램.
직전 2개년 동월 평균 대비 3% 이상 절감 시 30~100원/kWh 지급.
반환:
  {
    "summary": "캐시백 이력 3개월: 지급완료 2개월, 누적 절감 49.5kWh, 누적 캐시백 4,950원",
    "raw": [
      {
        "month": "2026-03",
        "baseline_kwh": 310.2,
        "actual_kwh": 295.8,
        "savings_pct": 4.6,
        "savings_kwh": 14.4,
        "cashback_krw": 1440,
        "cashback_rate_krw_per_kwh": 100,
        "status": "지급완료"
      },
      ...
    ]
  }
"""

get_tariff_info(household_id: str) -> dict
"""현재 요금제 + 누진 단계 + 다음 단계까지 남은 kWh."""

get_similar_households(household_id: str, k: int = 5) -> dict
"""
유사 가구 사례 (선택적, 나중 단계).
같은 유형/가구 규모에서 절감 성공 사례 retrieval.
이 부분에만 임베딩/RAG 도입 고려.
"""
```

### 2.5 도구 설계 원칙

| 원칙 | 이유 |
|------|------|
| **원자 단위로 쪼갬** | LLM이 필요한 것만 부르도록. 한 도구가 너무 많이 반환하면 컨텍스트 낭비 |
| **자연어 summary + raw 둘 다 반환** | summary로 빠른 판단, raw로 정밀 분석 |
| **household_id를 모든 도구의 첫 인수로** | 가구별 접근 제어를 도구 단위에서 강제 |
| **실패 시 명확한 오류** | `{"error": "household_id not found", "code": "E_NOT_FOUND"}` 형식. LLM이 다른 경로 시도 가능 |
| **결정론적으로** | 같은 인수 → 같은 응답. 캐시·재현 용이 |
| **JSON schema 엄격 정의** | tool-use API 호환 + 출력 검증 |
| **익명화 후 전달** | LLM(외부 API)에 넘기기 전 household_id 이외 개인 식별 정보 제거 |

---

## 3. System Prompt 구조

```
# 퍼르소나
당신은 한국 가정의 전력 절감을 돕는 전문 코치입니다. 사용자의 전력 소비
패턴, 가구 특성, 날씨를 종합해 실행 가능한 절감 권고를 제공합니다.

# 익명화 원칙
- household_id는 익명화된 식별자입니다. 사용자의 실명·주소·연락처를 추론하거나 언급하지 마세요.
- 유사 가구 데이터 인용 시 "유사 가구 평균" 형태로만 언급하고
  특정 가구를 식별할 수 있는 정보를 노출하지 마세요.
- 도구에서 반환된 데이터에 개인 식별 정보가 포함된 경우 해당 부분을 무시하고 답변하세요.

# 도구
- get_household_profile(id): 가구 정보
- get_weather(range, loc): 과거 날씨
- get_forecast(days, loc): 일기예보
- get_consumption_summary(id, period): 전력 소비 요약
- get_consumption_hourly(id, date): 시간대별 소비
- get_consumption_breakdown(id, date): 가전별 NILM 분해
- get_cashback_history(id, range): 에너지캐시백 절감 실적·지급 내역
- get_tariff_info(id): 요금제

# 원칙
- 답변 전 필요한 정보를 도구로 확인하세요. 추측하지 마세요.
- 권고는 [기대 절감량(kWh/월)], [실행 난이도], [근거] 세 항목으로 구성합니다.
- 의료·위험 관련 권고(예: 난방 완전 끄기)는 하지 마세요.
- 절감 효과가 불확실하면 "추가 데이터가 필요합니다"라고 답하세요.

# 출력 형식
JSON: {"recommendations": [...], "reasoning": "...", "data_used": [...]}
```

첫 메시지에 **baseline 컨텍스트 주입** (도구 호출 절약):

```
[현재 가구 baseline]
- 85㎡ 4인 아파트, 주택용(저압) 누진 2단계 (305kWh/월 사용 중)
- 직전 7일: 92.3kWh, 일평균 13.2kWh, 피크 19~21시
- 기온: 평년 +2.1°C, 4월 말 기준 이상고온

(추가 정보가 필요하면 도구를 사용하세요)
```

---

## 4. 평가 방법 (임베딩 비교 대신)

### 4.1 단위 평가 → Tool-use 정확성

각 task에 대해 **올바른 도구 호출 sequence**를 골든으로 정의:

| Task | 골든 sequence |
|------|--------------|
| "이번 달 전기 비싼?" | breakdown → weather → answer |
| "어제 뭐가 많이 켜졌어?" | breakdown(yesterday) → answer |
| "캐시백 얼마나 받았어?" | cashback_history(HH) → tariff_info → answer |
| "이번 달 캐시백 받을 수 있을까?" | cashback_history(HH) → consumption_summary → answer |

평가 지표:
- **Tool precision/recall**: 호출한 도구 / 골든 도구 일치도
- **Argument accuracy**: 인수 (날짜·기간) 정확도
- **No-hallucination check**: 도구 호출 없이 숫자를 만들어냈는지 여부

### 4.2 답변 평가 → 사람 점수 매김

코치 패널 2~3명이 각 답변을 5점 척도로 점수:
- **정확성**: 데이터와 일치하는가
- **실행 가능성**: 권고가 실제 행동으로 옮길 만한가
- **개인화**: 가구 특성을 반영하는가

목표: 평균 4.0/5.0 이상.

### 4.3 LLM 모델 선택

임베딩 모델 비교 대신 **LLM 모델 비교**를 동일 task로:
- **OpenAI**: GPT-4o / GPT-4o-mini (primary)
- 기타 비교군: Gemini 2.5 Pro / Claude Sonnet 4.6 (선택)
- 동일 system prompt + 동일 task set → 4.1·4.2 지표 비교
- 비용/latency 트레이드오프 반영해 production 모델 선택

---

## 5. 핸드오프 엔지니어링 항목

| 항목 | 구현 방향 |
|------|----------|
| **입력 가드레일** | household_id 권한 검증 (사용자가 자기 가구만 조회), prompt injection 패턴 차단 |
| **출력 가드레일** | JSON schema 검증, "의료·위험" 키워드 필터, 수치 sanity check (절감량 > 사용량 등) |
| **트레이스 로깅** | session_id, tool_calls, tool_responses, final_answer를 모두 기록. 재학습·감사 용도 |
| **프롬프트 캐싱** | system prompt + tool 카탈로그 부분 캐시. 가구별 baseline은 ephemeral |
| **비용 모니터링** | 세션별 token (input/output/cached) + tool-call 횟수 대시보드. 가구별 일 한도 설정 |
| **타임아웃** | tool 호출 5초, LLM 추론 30초, 전체 세션 60초 |
| **재시도 정책** | tool 실패 시 LLM에게 오류 전달 (재시도 여부 LLM 판단), API 5xx는 1회 자동 재시도 |
| **A/B 실험 인프라** | 프롬프트 버전 / LLM 모델 / 도구 set을 변수로 두고 실험군 비교 |
| **익명화 파이프라인** | 도구 반환값에서 개인 식별 정보 필터링 후 LLM에 전달. 로그에도 식별 정보 미기록 |

---

## 6. 다음 단계 → 팀원이 코드로 시작할 순서

**1주차: Tool 인터페이스 정의 (mock으로 시작)**
- 전 도구 8개의 Python 함수 시그니처 + JSON schema 작성
- raw 데이터는 mock으로 (DB·NILM 결과 연결 전): 가구 1~3개의 sample data 하드코딩
- 단위 테스트: 각 도구 호출 시 schema 일치 검증

**2주차: LLM 통합 prototype**
- **OpenAI SDK의 function calling API로 첫 prototype (GPT-4o-mini 권장)**
- system prompt + baseline + 1~2개 사용자 질문으로 end-to-end 동작 확인
- 트레이스 로깅 (JSON 파일로 우선 저장)
- 익명화 파이프라인 적용 확인 (LLM 전달 전 개인 식별 정보 제거 검증)

**3주차: 평가 데이터셋 + 평가 루프**
- 골든 task 20~30개 구축 (질문 + 기대 도구 sequence + 기대 답변 핵심 항목)
- 4.1·4.2 평가 자동화 (4.2는 일단 자동 평가 가능한 부분만, 사람 평가는 spot-check)

**4주차: 실데이터 연결 + 가드레일**
- mock → 실제 DB·NILM·KMA·KEPCO API 연결
- 핸드오프 가드레일 항목 추가
- 1~2개 가구로 alpha 테스트

**우선 1주차에 마친 뒤 임베딩 코드는 폐기**하고 tool 인터페이스부터 짜기 시작하면 즉시 진행 가능.

---

## 7. 임베딩이 정말 필요한 케이스 (나중 단계)

Tool-use가 메인이지만, 다음 두 케이스에는 임베딩 RAG 도입 검토:

1. **유사 사례 검색** (`get_similar_households`): 같은 유형·가구 규모에서 절감 성공 사례 retrieve. 이때만 가구 패턴을 벡터화해 cosine similarity로 검색.
2. **권고 라이브러리 검색**: 절감 권고 템플릿 수백 가지를 임베딩해두고 컨텍스트에 맞는 것 retrieve.

이 두 경우에만 임베딩 모델 비교가 의미 있고, 평가 지표도 **Recall@K** (관련 사례 검색 정확도). LLM에게 임베딩을 보여주는 평가는 여기서도 무효.

---

## 8. 핵심 메시지 요약

1. **임베딩 + LLM 설명 평가**는 동작하지 않음 → LLM은 원시 임베딩 못 읽음
2. **Tool-use 패턴**으로 전환 → 정보 제공을 도구 호출로 분리
3. 도구는 **자연어 summary + raw data 동시 반환**, 원자 단위로 쪼갬
4. baseline 정보는 **자연어로 system prompt에 직접 주입** (임베딩 우회)
5. **LLM에 전달하는 모든 데이터는 익명화** 처리 후 전송 (household_id 기준, 개인 식별 정보 제거)
6. 평가는 **tool-call 정확성 + 사람 점수** → LLM 모델 비교에 동일 framework 재사용
7. 1주차부터 **mock tool 인터페이스**로 코딩 시작 가능 → 임베딩 코드 폐기
8. 임베딩은 `get_similar_households` 내부 RAG에만 국한
