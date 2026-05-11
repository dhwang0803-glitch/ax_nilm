# energy-cashback — 구현 계획

## 개요

한전(KEPCO) 주택용 에너지캐시백 프로그램 연계 모듈.
NILM으로 분해한 가전별 소비 패턴을 활용해 월별 절감량을 분석하고,
캐시백 예측·가전별 절감 기여 분석·LLM 맥락 권고까지 제공한다.

> 에너지캐시백: 직전 2개년 동월 평균 대비 3% 이상 절감 시 30~100원/kWh 지급
> 신청: https://en-ter.co.kr/ec/apply/prsApply/select.do

---

## 엔티티 및 컬럼명 (DB 실물 기준)

### 가구 (households — 기존 DB 테이블, 컬럼 추가 요청)

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

### 전력 소비 패턴 임베딩 (household_embeddings — 유지)

| 한글명 | 컬럼명 | 타입 | 비고 |
|--------|--------|------|------|
| 가구 ID | `household_id` | TEXT | FK → households |
| 기준일 | `ref_date` | DATE | 임베딩 생성 기준일 |
| 임베딩 벡터 | `embedding` | vector(384) | pgvector |
| 임베딩 모델 | `embed_model` | TEXT | sentence-transformers/all-MiniLM-L6-v2 |
| 생성일 | `created_at` | TIMESTAMPTZ | |

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

DR 가전 분류 (에너지캐시백 맥락):
- 절감 용이형: 에어컨, 전기장판, 온수매트, 제습기 (사용 빈도·시간 조절 가능)
- 이동 가능형: 세탁기, 건조기, 식기세척기, 인덕션 (심야 이동 권고)
- 상시 부하: 냉장고, 김치냉장고 (절감 대상 외)

---

### UC-4. LLM Agent 월별 절감 권고

```
입력 (익명화):
  - cluster_label, cashback_enrolled
  - baseline_kwh, actual_kwh, savings_rate
  - top_saving_appliances (이번 달 절감 기여 상위 가전)
  - top_usage_appliances  (이번 달 사용량 상위 가전)
  - similar_months_text   (RAG: 작년 유사 달 패턴)
  - temperature           (월평균 기온)

LLM 도구:
  - show_cashback_result(savings_kwh, cashback_krw)   # 이번 달 결과 표시
  - show_enrollment_cta(enrollment_url)               # 미신청자 가입 유도
  - recommend_appliance_action(actions)               # 가전별 절감 행동 제안
  - show_monthly_trend(months, savings_rates)         # 월별 절감 추이 표시
```

---

## RAG 구조 (유지)

```
[오프라인 배치]
월별 1440분 프로파일 → 24시간 평균 → sentence-transformers 임베딩
→ household_embeddings 테이블 (pgvector)

[월별 권고 시]
이번 달 패턴 임베딩
→ pgvector 유사 달 검색 (동월 필터 권장)
→ "작년 7월(기온 32도): 에어컨 절감 1.2kWh, 캐시백 84원"
→ LLM 프롬프트 맥락 주입
```

---

## 폴더 구조

```
kpx-integration-settlement/
├── plans/
│   └── PLAN.md
├── src/
│   └── settlement/
│       ├── cbl.py          # 기준선 계산 (2개년 동월 평균)
│       ├── calculator.py   # 캐시백 산정 (절감률 → 단가 → 금액)
│       └── appliance.py    # 가전별 절감 기여 분석
├── benchmark/
│   └── colab_embedding_compare2.ipynb  # RAG 파이프라인 + LLM Agent (GPU 환경, Colab)
├── tests/
├── config/
│   └── .env.example
└── CLAUDE.md
```

> ~~src/kpx/~~ — KPX 연동 제거 (에너지캐시백은 KEPCO 직접, API 없음)
> ~~src/rag/, src/agent/~~ — Colab 노트북으로 이전 (GPU 환경에서 임베딩·LLM 실행)
> ~~src/tasks/~~ — Celery 배치 미구현 상태, 노트북 평가 우선

---

## 확정 사항

- [x] 기준선: 직전 2개년 동월 평균 (전년 데이터 부족 시 군집 Proxy)
- [x] 캐시백 단가: 절감률 구간별 30~100원/kWh, 30% 상한
- [x] 정산 주기: 월별 (한전 자동 청구 차감)
- [x] 신청 URL: https://en-ter.co.kr/ec/apply/prsApply/select.do
- [x] Aggregator 없음 — KEPCO 직접

## 미결 사항

- [ ] 캐시백 단가 구간 KEPCO 공식 확인 (현재 추정값)
- [ ] 신규 가구 기준선 Proxy: 군집 평균 kWh 기준값 측정 필요
- [ ] monthly_baselines 사전 계산 시점 (매월 1일 배치)
- [ ] household_embeddings 동월 필터 pgvector 쿼리 최적화
