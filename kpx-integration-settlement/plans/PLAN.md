# kpx-integration-settlement — 구현 계획

## 개요

KPX DR 이벤트 수신 → 가구별 감축량 계산 → 환급금 산출 → LLM 맥락 메시지 생성까지
전 과정을 담당하는 모듈.

---

## 엔티티 및 컬럼명 (DB 실물 기준)

### 수요관리사업자 (aggregators — 신규, Database 브랜치 요청)

| 한글명 | 컬럼명 | 타입 | 비고 |
|--------|--------|------|------|
| 사업자 ID | `aggregator_id` | TEXT | PK |
| 사업자명 | `name` | TEXT | 예: 파란에너지, 벽산파워, LG전자 |
| 정산 단가 | `settlement_rate` | DOUBLE PRECISION | 원/kWh (1,000~1,300 범위) |
| 갱신일 | `updated_at` | TIMESTAMPTZ | 단가 변경 시 갱신 |

> settlement_rate는 aggregator별·시기별로 다름. 하드코딩 금지, 이 테이블에서 조회.

---

### 가구 (households — 기존 DB 테이블 사용)

| 한글명 | 컬럼명 | 타입 | 비고 |
|--------|--------|------|------|
| 가구 ID | `household_id` | TEXT | PK |
| 가구 유형 | `house_type` | TEXT | 1인/2~3인/4인+ |
| 군집 레이블 | `cluster_label` | SMALLINT | 0=저소비 1=고소비 2=중소비 |
| DR 참여 여부 | `dr_enrolled` | BOOLEAN | aggregator 계약 완료 여부 |
| 사업자 ID | `aggregator_id` | TEXT | FK → aggregators |
| 생성일 | `created_at` | TIMESTAMPTZ | |

> Database 브랜치 요청 컬럼: `cluster_label`, `dr_enrolled`, `aggregator_id` (migrations/ 추가 필요)

---

### DR 이벤트 (dr_events — 신규)

| 한글명 | 컬럼명 | 타입 | 비고 |
|--------|--------|------|------|
| 이벤트 ID | `event_id` | TEXT | PK, KPX 발급 |
| 시작 시각 | `start_ts` | TIMESTAMPTZ | KPX 수신값 (고정 아님) |
| 종료 시각 | `end_ts` | TIMESTAMPTZ | KPX 수신값 |
| 목표 감축량 | `target_kw` | DOUBLE PRECISION | 전체 참여 가구 합산 목표 |
| 발령 시각 | `issued_at` | TIMESTAMPTZ | KPX 발령 시각 |
| 상태 | `status` | TEXT | pending / active / completed / cancelled |

---

### 가구별 감축 실적 (dr_results — 신규)

| 한글명 | 컬럼명 | 타입 | 비고 |
|--------|--------|------|------|
| 이벤트 ID | `event_id` | TEXT | FK → dr_events |
| 가구 ID | `household_id` | TEXT | FK → households |
| CBL | `cbl_kwh` | DOUBLE PRECISION | 직전 10 평일 중 6일 가중평균 |
| 실측 사용량 | `actual_kwh` | DOUBLE PRECISION | ch01 이벤트 구간 합산 |
| 절감량 | `savings_kwh` | DOUBLE PRECISION | cbl_kwh - actual_kwh |
| 환급금 | `refund_krw` | INTEGER | savings_kwh × 정산 단가 |
| 정산 단가 | `settlement_rate` | DOUBLE PRECISION | aggregator별 상이 (원/kWh) |
| 생성일 | `created_at` | TIMESTAMPTZ | |

---

### 가전별 감축 기여 (dr_appliance_savings — 신규)

| 한글명 | 컬럼명 | 타입 | 비고 |
|--------|--------|------|------|
| 이벤트 ID | `event_id` | TEXT | FK → dr_events |
| 가구 ID | `household_id` | TEXT | FK → households |
| 채널 번호 | `channel_num` | SMALLINT | ch02~ch23 |
| 가전 코드 | `appliance_code` | TEXT | FK → appliance_types |
| 채널 CBL | `channel_cbl_kwh` | DOUBLE PRECISION | 해당 채널 이벤트 구간 CBL |
| 채널 실측 | `channel_actual_kwh` | DOUBLE PRECISION | 해당 채널 이벤트 구간 실측 |
| 채널 절감량 | `channel_savings_kwh` | DOUBLE PRECISION | |

> KPX 정산은 ch01(전체 미터) 기준. 채널별 분해는 UI 표시 전용.

---

### 전력 소비 패턴 임베딩 (household_embeddings — 신규)

| 한글명 | 컬럼명 | 타입 | 비고 |
|--------|--------|------|------|
| 가구 ID | `household_id` | TEXT | FK → households |
| 기준일 | `ref_date` | DATE | 임베딩 생성 기준일 |
| 임베딩 벡터 | `embedding` | vector(384) | pgvector, 1440분→24시간 평균→임베딩 |
| 임베딩 모델 | `embed_model` | TEXT | 예: chronos-t5-small |
| 생성일 | `created_at` | TIMESTAMPTZ | |

> TimescaleDB + pgvector 확장 사용. 유사 날 CBL 보정 및 LLM RAG 맥락 검색에 활용.

---

### 30분 단위 DR 사전 계산 (power_efficiency_30min — 신규, Database 브랜치 요청)

| 한글명 | 컬럼명 | 타입 | 비고 |
|--------|--------|------|------|
| 가구 ID | `household_id` | TEXT | FK → households |
| 버킷 시작 시각 | `bucket_ts` | TIMESTAMPTZ | 30분 단위 |
| 채널 번호 | `channel_num` | SMALLINT | ch01~ch23 |
| 30분 누적 소비량 | `energy_wh` | DOUBLE PRECISION | |
| 사전 계산 CBL | `cbl_wh` | DOUBLE PRECISION | 직전 10 평일 6일 가중평균 |
| 절감량 | `savings_wh` | DOUBLE PRECISION | cbl_wh - energy_wh |
| DR 구간 여부 | `is_dr_window` | BOOLEAN | DR 이벤트 구간에 해당하면 true |
| DR 이벤트 ID | `event_id` | TEXT | NULL 허용, DR 구간일 때만 값 있음 |
| 계산 시각 | `computed_at` | TIMESTAMPTZ | |

> 이 테이블은 Database 브랜치에서 생성 요청. kpx-integration-settlement는 이 테이블을 읽기만 함.
> Celery 배치(1시간 주기) + DR 이벤트 트리거로 채워지며, LLM 호출 시 직접 참조.

---

## 유스케이스 구현 스펙

### UC-1. DR 이벤트 수신

```
KPX Open API → Kafka topic: dr.events.inbound
→ consumer: event_id, start_ts, end_ts, target_kw 파싱
→ dr_events 테이블 저장
→ 참여 가구 대상 사전 알림 트리거 (UC-3)
```

---

### UC-2. 가구별 감축량 계산

> TimescaleDB 직접 조회 금지. power_efficiency_30min 사전 계산 테이블에서 읽음.

```python
def calc_savings(household_id: str, event_id: str) -> dict:
    event = get_dr_event(event_id)           # dr_events 조회
    rows  = get_precomputed(                 # power_efficiency_30min 조회
                household_id,
                event_id,
                channel_num=1               # ch01 전체 미터만
            )
    cbl_wh     = sum(r.cbl_wh for r in rows)
    actual_wh  = sum(r.energy_wh for r in rows)
    savings_kwh = (cbl_wh - actual_wh) / 1000
    refund_krw  = max(0, savings_kwh) * get_settlement_rate(household_id)
    return {"cbl_kwh": cbl_wh / 1000, "actual_kwh": actual_wh / 1000,
            "savings_kwh": savings_kwh, "refund_krw": int(refund_krw)}
```

트리거 방식 (power_efficiency_30min 채우는 주체):
```
① Celery beat (1시간 주기)   → 전 가구 30분 집계 사전 계산
② DR 이벤트 수신 시          → 해당 이벤트 구간 즉시 계산
```

---

### UC-3. 가전별 감축 가능량 예측

```
ch02~ch23 parquet ON/OFF 구간과 이벤트 구간 겹침 계산

channel_savings_kwh =
    power_w / 1000 * overlap_hours  (온도 제어형)

channel_savings_kwh =
    channel_cbl_kwh - channel_actual_kwh  (부하 이동형: 이동 성공 시 ≒ CBL)
```

DR 가전 분류:
- 온도 제어형: `appliance_code` IN (에어컨, 제습기, 전기장판, 온수매트)
- 부하 이동형: (세탁기, 의류건조기, 전기밥솥, 인덕션, 식기세척기, 에어프라이어)
- 제외: (냉장고, 김치냉장고, 무선공유기)

---

### UC-4. 환급금 계산

```python
refund_krw = int(max(0, savings_kwh) * settlement_rate)
# settlement_rate: aggregator별 DB 관리 (1,000~1,300원/kWh)
# 하드코딩 금지
```

---

### UC-5. 참여 옵션 추천 (LLM Agent)

```
입력 (익명화된 맥락 데이터):
  - temperature, humidity, windchill     # 기상청 데이터
  - cluster_label                        # 0/1/2
  - dr_enrolled                          # 가입 여부
  - event_start, event_end               # 이벤트 구간
  - predicted_savings_kwh                # UC-3 결과
  - top_appliances: [appliance_code, ...]  # DR 가능 가전 목록
  - embedding_context                    # 유사 날 패턴 (RAG 검색 결과)

LLM 도구 목록:
  - send_pre_event_notification(message)   # 사전 행동 권고 알림
  - show_savings_result(savings, refund)   # 이벤트 후 결과 표시
  - show_enrollment_modal()                # DR 미가입자 가입 유도 팝업
  - recommend_appliance_action(actions)    # 가전별 행동 제안
```

---

## 전력 소비 패턴 임베딩 + LLM RAG 구조

```
[오프라인 배치]
power_1min (1440분) → 24시간 평균 → Chronos 임베딩
→ household_embeddings 테이블 (pgvector)

[실시간 RAG]
오늘 가구 패턴 임베딩
→ pgvector 유사도 검색 → 과거 유사 날 k개 조회
→ "작년 10월 15일(기온 12도): 인덕션 17시 사용, 절감 0.9kWh"
→ LLM 프롬프트에 맥락으로 주입
→ 계절·기온 인식 맞춤 권고 생성

활용처:
1. CBL 보정: 단순 10일 평균 대신 기온·패턴 유사 날 선별
2. LLM 맥락: "이 가구는 비슷한 날 인덕션을 18시에 씀" 정보 제공
3. 신규 가구 Proxy CBL: 유사 기존 가구 찾아 대체 기준선 사용
```

---

## 인터페이스 어댑터

| 어댑터 | 역할 | 구현 |
|--------|------|------|
| KPX API Gateway | DR 이벤트 수신, 감축 실적 전송 | httpx + Kafka producer |
| Repository Gateway | dr_events, dr_results, household_embeddings CRUD | SQLAlchemy async |
| API Controller | FastAPI 엔드포인트 | /dr/events, /dr/results/{household_id} |
| Response Presenter | 환급금·절감량 응답 포맷 | Pydantic schema |

---

## 폴더 구조 (예정)

```
kpx-integration-settlement/
├── plans/
│   └── PLAN.md              ← 이 파일
├── src/
│   ├── kpx/
│   │   └── client.py        # KPX API Gateway
│   ├── settlement/
│   │   ├── cbl.py           # CBL 계산
│   │   ├── calculator.py    # 절감량·환급금 산출
│   │   └── appliance.py     # 가전별 기여 계산
│   ├── rag/
│   │   ├── embedder.py      # 전력 패턴 임베딩
│   │   └── retriever.py     # pgvector 유사 날 검색
│   ├── agent/
│   │   ├── tools.py         # LLM 도구 정의
│   │   └── recommender.py   # LLM Agent 실행
│   └── tasks/
│       └── batch_compute.py # Celery 배치(1시간) + DR 이벤트 트리거 계산
├── tests/
├── config/
│   └── .env.example
└── CLAUDE.md
```

---

## 확정 사항

- [x] **CBL 계산 시점**: Celery 배치(1시간 주기) + DR 이벤트 트리거 방식으로 사전 계산
      → `power_efficiency_30min` 테이블에 저장, 요청 시 TimescaleDB 직접 조회 금지
- [x] **LLM 호출 시점**: 프론트엔드 효율화 방안 요청 시에만 사전 계산 테이블 조회 후 연결

---

## 미결 사항 (ADR 필요)

- [ ] pgvector 임베딩 차원수 확정 (384 vs 768)
- [ ] 임베딩 모델 선택 (Chronos vs TimesFM vs 자체 학습)
- [ ] CBL 계산 방법: 단순 10일 평균 vs 임베딩 유사 날 선별 (시점은 확정, 방법은 미결)
- [ ] settlement_rate 관리 방식 (DB vs 환경변수)
- [ ] KPX API 연동 실제 스펙 확보 (현재 Mock 구현)
