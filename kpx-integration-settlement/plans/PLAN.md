# energy-cashback — 구현 계획

## 개요

한전(KEPCO) 주택용 에너지캐시백 프로그램 연계 모듈.
NILM으로 분해한 가전별 소비 패턴을 활용해 월별 절감량을 분석하고,
캐시백 예측·가전별 절감 기여 분석·LLM 맥락 권고까지 제공한다.

> 에너지캐시백: 직전 2개년 동월 평균 대비 3% 이상 절감 시 30~100원/kWh 지급
> 신청: https://en-ter.co.kr/ec/apply/prsApply/select.do

---

## 엔티티 및 컬럼명 (DB 실물 기준)

### 가구 (households — 기존 DB 테이블)

| 한글명 | 컬럼명 | 타입 | 비고 |
|--------|--------|------|------|
| 가구 ID | `household_id` | TEXT | PK |
| 가구 유형 | `house_type` | TEXT | 1인/2~3인/4인+ |
| 군집 레이블 | `cluster_label` | SMALLINT | 0=저소비 1=고소비 2=중소비 |
| 캐시백 신청 여부 | `cashback_enrolled` | BOOLEAN | 한전 에너지캐시백 신청 완료 여부 |
| 생성일 | `created_at` | TIMESTAMPTZ | |

> ~~aggregator_id~~ 제거 — 에너지캐시백은 한전 직접 정산, 사업자 중개 없음

---

### 월별 기준선 (monthly_baselines — 신규)

| 한글명 | 컬럼명 | 타입 | 비고 |
|--------|--------|------|------|
| 가구 ID | `household_id` | TEXT | FK → households |
| 기준 연월 | `ref_month` | DATE | 비교 대상 월 (당월 1일) |
| 전년1 사용량 | `prev1_kwh` | DOUBLE PRECISION | 2년 전 동월 ch01 합산 |
| 전년2 사용량 | `prev2_kwh` | DOUBLE PRECISION | 1년 전 동월 ch01 합산 |
| 2개년 평균 | `baseline_kwh` | DOUBLE PRECISION | (prev1 + prev2) / 2 |
| 계산 시각 | `computed_at` | TIMESTAMPTZ | |

> 기준선 = 직전 2개년 동월 평균. 이전 데이터 없는 신규 가구는 군집 평균 Proxy 적용.

---

### 캐시백 정산 결과 (cashback_results — 신규)

| 한글명 | 컬럼명 | 타입 | 비고 |
|--------|--------|------|------|
| 가구 ID | `household_id` | TEXT | FK → households |
| 정산 연월 | `billing_month` | DATE | 해당 월 1일 |
| 기준선 | `baseline_kwh` | DOUBLE PRECISION | monthly_baselines 참조 |
| 실측 사용량 | `actual_kwh` | DOUBLE PRECISION | ch01 해당 월 합산 |
| 절감량 | `savings_kwh` | DOUBLE PRECISION | baseline - actual |
| 절감률 | `savings_rate` | DOUBLE PRECISION | savings / baseline |
| 단가 | `cashback_rate` | DOUBLE PRECISION | 원/kWh (절감률 구간별) |
| 캐시백 금액 | `cashback_krw` | INTEGER | savings_kwh × cashback_rate |
| 기준선 방법 | `baseline_method` | TEXT | "2year_avg" \| "proxy_cluster" |
| 생성일 | `created_at` | TIMESTAMPTZ | |

---

### 가전별 절감 기여 (appliance_savings_monthly — 신규)

| 한글명 | 컬럼명 | 타입 | 비고 |
|--------|--------|------|------|
| 가구 ID | `household_id` | TEXT | FK → households |
| 정산 연월 | `billing_month` | DATE | |
| 채널 번호 | `channel_num` | SMALLINT | ch02~ch23 |
| 가전 코드 | `appliance_code` | TEXT | FK → appliance_types |
| 채널 기준선 | `channel_baseline_kwh` | DOUBLE PRECISION | 해당 채널 2개년 평균 |
| 채널 실측 | `channel_actual_kwh` | DOUBLE PRECISION | 해당 채널 당월 합산 |
| 채널 절감량 | `channel_savings_kwh` | DOUBLE PRECISION | |

> 가전별 분해는 UI 표시 전용. 실제 캐시백은 ch01 전체 기준.

---

## 캐시백 단가 구조

| 절감률 | 단가 (원/kWh) |
|--------|-------------|
| 3% 미만 | 미지급 |
| 3% 이상 ~ 5% 미만 | 30원 |
| 5% 이상 ~ 10% 미만 | 50원 |
| 10% 이상 ~ 20% 미만 | 70원 |
| 20% 이상 (30% 캡) | 100원 |

> 출처: KEPCO 에너지마켓플레이스 기준. 단가·구간은 변경될 수 있으므로 DB 또는 환경변수로 관리 권장.
> 절감률 상한 30% — 초과분은 30% 기준으로 산정.

---

## 유스케이스 구현 스펙

### UC-1. 월별 기준선 계산

```python
def calc_baseline(household_id: str, ref_month: date, repo) -> tuple[float, str]:
    prev1 = repo.get_monthly_usage(household_id, ref_month - 2years)
    prev2 = repo.get_monthly_usage(household_id, ref_month - 1year)
    if prev1 and prev2:
        return (prev1 + prev2) / 2, "2year_avg"
    # 신규 가구 fallback: 군집 평균 kWh 사용
    return repo.get_cluster_avg_monthly(cluster_label), "proxy_cluster"
```

---

### UC-2. 캐시백 산정

```python
def calc_cashback(baseline_kwh, actual_kwh) -> tuple[float, int]:
    savings_kwh = baseline_kwh - actual_kwh
    if savings_kwh <= 0:
        return 0.0, 0
    rate = savings_kwh / baseline_kwh
    capped_rate = min(rate, 0.30)                     # 30% 상한
    effective_savings = baseline_kwh * capped_rate
    cashback_rate = get_cashback_unit_rate(capped_rate)
    return effective_savings, int(effective_savings * cashback_rate)
```

---

### UC-3. 가전별 절감 기여 분석

```
ch02~ch23 월별 합산 vs 동월 2개년 평균 비교
→ 절감 기여 상위 가전 순위 산출
→ UI 가전별 기여 파이차트 표시용
```

가전별 절감 유형 분류 (에너지캐시백 맥락):
- **설정 조정형** (실제 kWh 절감): 에어컨(온도 1°C 조정), 전기장판·온수매트(온도 단계 낮추기), 인덕션(화력 단계 낮추기)
- **효율 사용형** (실제 kWh 절감): 전기포트(필요한 양만), 전기밥솥(취사 예약 활용), 전기다리미(모아서 한 번에)
- **절전 설정형** (실제 kWh 절감): TV·컴퓨터(절전 모드·취침 타이머), 선풍기(풍속 낮추기), 공기청정기(자동·취침 모드)
- **대기전력 차단형** (실제 kWh 절감): 무선공유기·셋톱박스(장시간 미사용 시 전원 차단)
- **상시 가동형** (절감 대상 외): 냉장고·김치냉장고(온도 설정 최적화·도어·코일 점검만)

> 시간대 이동(심야/오전 예약)은 총 kWh를 줄이지 않으므로 에너지캐시백 절감 권고에서 제외.

---

### UC-4. LLM Agent 진단 리포트 생성

현재 구현: LangGraph `create_react_agent` 기반 단일 ReAct 에이전트 (GPT-4o-mini)

```
에이전트 입력:
  household_id → 도구 자동 호출로 필요 데이터 조회

사용 도구 (10개):
  get_consumption_summary       ← power_1hour 기반 월별 소비 요약
  get_hourly_appliance_breakdown ← 가전별 시간대별 kWh (22ch × 24h)
  get_consumption_hourly        ← 시간대별 총 소비량
  get_consumption_breakdown     ← 가전별 소비 비중
  get_cashback_history          ← 월별 캐시백 실적·절감률
  get_tariff_info               ← 요금제·누진 단계·예상 청구액
  get_anomaly_events            ← 활성 이상 이벤트
  get_anomaly_log               ← 이상 탐지 이력
  get_weather                   ← 가구 위치 날씨·기온
  get_forecast                  ← 7일 예보

에이전트 출력 (InsightsLLMOutput):
  anomaly_diagnoses: 이상 이벤트 진단 + 조치
  recommendations:   절감 행동 3~5개 (savings_kwh만 LLM 생성)

Python 후처리:
  savings_krw = round(savings_kwh × cashback_unit_rate(household_id))
  → 가구 이력 기반 단가 적용으로 모든 항목 동일 단가 보장
```

---

## 폴더 구조

```
kpx-integration-settlement/
├── plans/
│   ├── PLAN.md
│   └── project_and_work_summary.md
├── src/
│   ├── agent/
│   │   ├── graph.py          ← LangGraph ReAct 에이전트 + InsightsLLMOutput 스키마
│   │   ├── data_tools.py     ← 10개 데이터 조회 도구 (실DB + mock fallback)
│   │   ├── anonymizer.py     ← PII 스크럽 (도구 출력 레벨)
│   │   ├── validator.py      ← LLM 출력 검증
│   │   └── trace_logger.py   ← 로컬 트레이스 저장
│   ├── api/
│   │   └── routers/
│   │       ├── dashboard.py  ← GET /api/dashboard/summary
│   │       ├── usage.py      ← GET /api/usage/analysis
│   │       ├── auth.py       ← 인증
│   │       ├── settings.py   ← GET /api/settings/account
│   │       ├── cashback.py   ← GET /api/cashback/tracker
│   │       └── insights.py   ← GET /api/insights/summary (에이전트 연동)
│   └── settlement/
│       ├── cbl.py            ← 기준선 계산 (2개년 동월 평균)
│       ├── calculator.py     ← 캐시백 산정 (절감률 → 단가 → 금액)
│       └── appliance.py      ← 가전별 절감 기여 분석
├── scripts/
│   └── seed_anomaly.sql      ← appliance_status_intervals 목업 시드
├── tests/
│   └── run_target_households.py ← 9가구 통합 검증 (LangSmith 트레이싱)
├── config/
│   └── .env.example
└── CLAUDE.md
```

---

## 확정 사항

- [x] 기준선: 직전 2개년 동월 평균 (전년 데이터 부족 시 군집 Proxy)
- [x] 캐시백 단가: 절감률 구간별 30~100원/kWh, 30% 상한
- [x] 정산 주기: 월별 (한전 자동 청구 차감)
- [x] 신청 URL: https://en-ter.co.kr/ec/apply/prsApply/select.do
- [x] Aggregator 없음 — KEPCO 직접
- [x] savings_krw Python 후처리 — LLM은 savings_kwh만 생성, 단가는 cashback_unit_rate()로 적용
- [x] 시간대 이동 권고 제외 — 총 kWh 절감 없음, 에너지캐시백 기준 미충족

## 미결 사항

- [ ] 캐시백 단가 구간 KEPCO 공식 확인 (현재 추정값)
- [ ] 신규 가구 기준선 Proxy: 군집 평균 kWh 기준값 측정 필요
- [ ] monthly_baselines 사전 계산 시점 (매월 1일 배치)
- [ ] appliance_status_intervals 실데이터 연결 (현재 목업 12건 — NILM 엔진 실 추론 결과 대기)
