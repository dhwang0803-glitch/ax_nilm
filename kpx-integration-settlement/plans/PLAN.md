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
│   │   ├── graph.py              ← 단일 ReAct 에이전트 (하위 호환 유지)
│   │   ├── data_tools.py         ← 10개 데이터 조회 도구 (모든 에이전트 공유)
│   │   ├── anonymizer.py         ← PII 스크럽 (도구 출력 레벨)
│   │   ├── validator.py          ← LLM 출력 검증
│   │   ├── trace_logger.py       ← 로컬 트레이스 저장
│   │   └── multi_agent/          ← 멀티에이전트 (수퍼바이저 패턴)
│   │       ├── __init__.py
│   │       ├── supervisor.py     ← LangGraph 수퍼바이저 그래프 + 상태 스키마
│   │       ├── nilm_monitor.py   ← Module 2: NILM 모니터링 에이전트
│   │       ├── cashback_node.py  ← Module 3: 캐시백 계산 노드 (Python 함수)
│   │       └── report_agent.py   ← Module 5: AI 진단 리포트 에이전트
│   ├── api/
│   │   └── routers/
│   │       ├── dashboard.py      ← GET /api/dashboard/summary
│   │       ├── usage.py          ← GET /api/usage/analysis
│   │       ├── auth.py           ← 인증
│   │       ├── settings.py       ← GET /api/settings/account
│   │       ├── cashback.py       ← GET /api/cashback/tracker
│   │       └── insights.py       ← GET /api/insights/summary (에이전트 연동)
│   └── settlement/
│       ├── cbl.py                ← 기준선 계산 (2개년 동월 평균)
│       ├── calculator.py         ← 캐시백 산정 (절감률 → 단가 → 금액)
│       └── appliance.py          ← 가전별 절감 기여 분석
├── scripts/
│   └── seed_anomaly.sql          ← appliance_status_intervals 목업 시드
├── tests/
│   └── run_target_households.py  ← 9가구 통합 검증 (LangSmith 트레이싱)
├── config/
│   └── .env.example
└── CLAUDE.md
```

---

---

## 멀티에이전트 아키텍처 (수퍼바이저 패턴)

> Module 4 (지식 검색 RAG)는 문서 소싱 후 별도 추가 예정. 현재는 4개 모듈만 구현.

### 전체 흐름

```
사용자 요청 (household_id)
        ↓
  Supervisor (rule-based, LLM 없음)
        ↓ 병렬 실행
┌───────────────────┐   ┌──────────────────────┐
│ Module 2          │   │ Module 3             │
│ NILM 모니터링     │   │ 캐시백 계산          │
│ (ReAct 에이전트)  │   │ (Python 함수 노드)   │
└────────┬──────────┘   └──────────┬───────────┘
         │                         │
         └──────────┬──────────────┘
                    ↓
             Module 5
         AI 진단 리포트 에이전트
         (구조화 출력 LLM)
                    ↓
          InsightsLLMOutput
    (anomaly_diagnoses + recommendations)
                    ↓
          Python 후처리: savings_krw 계산
```

---

### 모듈별 설계

#### Module 1 — 전력 데이터 조회 (공유 도구층)

에이전트가 아닌 공유 도구 레이어. `data_tools.py`의 10개 함수를 모든 에이전트가 공유한다.

| 도구 | 용도 |
|------|------|
| `get_consumption_summary` | 월별 총 소비량 |
| `get_hourly_appliance_breakdown` | 채널별 시간대별 kWh |
| `get_consumption_hourly` | 시간대별 총 소비 |
| `get_consumption_breakdown` | 가전별 소비 비중 |
| `get_cashback_history` | 월별 캐시백 실적 |
| `get_tariff_info` | 요금제·누진단계 |
| `get_anomaly_events` | 활성 이상 이벤트 |
| `get_anomaly_log` | 이상 탐지 이력 |
| `get_weather` | 현재 날씨·기온 |
| `get_forecast` | 7일 예보 |

---

#### Module 2 — NILM 모니터링 에이전트

- **파일**: `src/agent/multi_agent/nilm_monitor.py`
- **타입**: LangGraph ReAct 에이전트
- **담당 도구**: `get_anomaly_events`, `get_anomaly_log`, `get_hourly_appliance_breakdown`, `get_consumption_hourly`, `get_consumption_breakdown`

**출력 스키마 `NilmMonitorOutput`**:
```python
class TopConsumer(BaseModel):
    appliance: str        # 가전명
    channel: int          # 채널 번호
    kwh: float            # 월간 추정 kWh

class NilmMonitorOutput(BaseModel):
    anomaly_events: list[dict]   # get_anomaly_events raw 결과
    top_consumers: list[TopConsumer]  # 소비 상위 3~5개 가전
    peak_hours: list[int]        # 소비 피크 시간대 (0~23)
```

**역할**: 이상 이벤트 수집 + 어떤 가전이 얼마나 쓰는지 파악 → Module 5에 구조화된 형태로 전달.

---

#### Module 3 — 캐시백 계산 노드

- **파일**: `src/agent/multi_agent/cashback_node.py`
- **타입**: Python 함수 노드 (LLM 없음 — settlement/ 함수 직접 호출)
- **입력**: `household_id`
- **사용 함수**: `get_cashback_history`, `get_consumption_summary`, `cashback_unit_rate()`

**출력 스키마 `CashbackNodeOutput`**:
```python
class CashbackNodeOutput(BaseModel):
    baseline_kwh: float           # 2개년 동월 평균 기준선
    actual_kwh: float             # 당월 실측 사용량
    savings_rate: float           # 절감률 (savings/baseline)
    cashback_rate_krw_per_kwh: float  # 적용 단가 (30/50/70/100)
    projected_cashback_krw: int   # 이번 달 예상 캐시백
    enrolled: bool                # 에너지캐시백 신청 여부
```

**역할**: 기준선·절감률·단가를 계산해 Module 5가 수치 기반 권고를 생성할 수 있도록 컨텍스트 제공.

---

#### Module 5 — AI 진단 리포트 에이전트

- **파일**: `src/agent/multi_agent/report_agent.py`
- **타입**: 구조화 출력 LLM (`with_structured_output(InsightsLLMOutput)`)
- **입력**: `NilmMonitorOutput` + `CashbackNodeOutput` + `get_weather` 결과
- **담당 도구**: `get_weather`, `get_forecast` (날씨 컨텍스트)

**역할**: Module 2·3에서 받은 구조화 데이터를 바탕으로 이상 진단 + 절감 권고 최종 생성.
Module 2가 이미 이상 이벤트·가전 소비 패턴을 정리해서 전달하므로 이 에이전트는 도구를 최소한으로 호출하고 LLM 집중.

---

#### Supervisor — 수퍼바이저 노드

- **파일**: `src/agent/multi_agent/supervisor.py`
- **타입**: LangGraph `StateGraph` (LLM 없음, rule-based 라우팅)
- **상태 스키마**:

```python
class MultiAgentState(TypedDict):
    household_id: str
    nilm_output: NilmMonitorOutput | None      # Module 2 결과
    cashback_output: CashbackNodeOutput | None  # Module 3 결과
    final_output: InsightsLLMOutput | None      # Module 5 결과
```

**그래프 구조**:
```
START
  └→ nilm_monitor_node  ─→ report_node → END
  └→ cashback_node      ─↗
```
> Module 2·3은 병렬 실행. 둘 다 완료되면 Module 5 실행.

**공개 진입점**:
```python
def run_multi_agent(household_id: str) -> InsightsLLMOutput:
    """수퍼바이저 그래프 실행. insights.py 라우터에서 호출."""
```

---

### 기존 단일 에이전트(`graph.py`)와의 관계

| 항목 | 단일 에이전트 (`graph.py`) | 멀티에이전트 (`multi_agent/`) |
|------|--------------------------|-------------------------------|
| 진입점 | `run_graph()` | `run_multi_agent()` |
| 구조 | ReAct 10도구 전부 | 역할 분리 후 병렬 실행 |
| 토큰 | 단일 컨텍스트 누적 | 에이전트별 독립 컨텍스트 |
| 유지 여부 | 하위 호환용 유지 | 신규 구현 — insights.py에서 점진적 전환 |

---

## 확정 사항

- [x] 기준선: 직전 2개년 동월 평균 (전년 데이터 부족 시 군집 Proxy)
- [x] 캐시백 단가: 절감률 구간별 30~100원/kWh, 30% 상한
- [x] 정산 주기: 월별 (한전 자동 청구 차감)
- [x] 신청 URL: https://en-ter.co.kr/ec/apply/prsApply/select.do
- [x] Aggregator 없음 — KEPCO 직접
- [x] savings_krw Python 후처리 — LLM은 savings_kwh만 생성, 단가는 cashback_unit_rate()로 적용
- [x] 시간대 이동 권고 제외 — 총 kWh 절감 없음, 에너지캐시백 기준 미충족
- [x] 멀티에이전트 설계 확정 — 수퍼바이저 패턴, Module 2·3·5 역할 분리, Module 4 RAG는 보류

## 미결 사항

- [ ] 캐시백 단가 구간 KEPCO 공식 확인 (현재 추정값)
- [ ] 신규 가구 기준선 Proxy: 군집 평균 kWh 기준값 측정 필요
- [ ] monthly_baselines 사전 계산 시점 (매월 1일 배치)
- [ ] appliance_status_intervals 실데이터 연결 (현재 목업 12건 — NILM 엔진 실 추론 결과 대기)
- [ ] Module 2 구현: NILM 모니터링 에이전트 (`nilm_monitor.py`)
- [ ] Module 3 구현: 캐시백 계산 노드 (`cashback_node.py`)
- [ ] Module 5 구현: AI 진단 리포트 에이전트 (`report_agent.py`)
- [ ] Supervisor 구현: LangGraph StateGraph (`supervisor.py`)
- [ ] insights.py 라우터 전환: run_graph → run_multi_agent
- [ ] Module 4 (지식 검색 RAG): 문서 소싱 결정 후 설계 추가 예정
