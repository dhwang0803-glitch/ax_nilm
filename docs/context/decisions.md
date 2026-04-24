# Architecture Decision Records (ADR)

> 중요한 기술 결정의 배경, 대안, 근거를 기록한다.
> 기존 결정을 뒤집을 때는 기존 ADR에 *Superseded by ADR-NNN* 표시 후 새 ADR을 추가한다.
> 삭제하지 않는다.

ADR 형식: Status · Context · Decision · Consequences · Alternatives Considered.

---

## ADR-001 — 전력 시계열 데이터 저장소 선택 및 해상도 정책

- **Status**: Accepted — 2026-04-21
- **관련 브랜치**: `Database`
- **구현 근거**: `Database/docs/schema_design.md §0, §3`, `Database/docs/dataset_spec.md §8`
- **상위 요구사항**: 루트 `CLAUDE.md` REQ-001 (NILM, 30Hz), REQ-004 (데이터 관리), REQ-007 (보안)

### Context

AI Hub 71685 데이터셋(110가구 × 31일 × 23채널, 30Hz)을 기반으로 NILM 기반 에너지 효율화 서비스를 구축한다. 실측 샘플 검증 결과:

- 1채널/일 = 2,592,000 rows (~200 MB CSV)
- 전체 데이터셋 원시 ~8 TB, 실시간 스트리밍까지 고려하면 무한 증가
- 30Hz 원시 데이터는 **NILM 엔진(분해·이상탐지)** 의 입력 신호이며, 그 외 UI·리포트·DR 정산 등은 분/시간 해상도면 충분

선택해야 할 것:
1. 어떤 저장소를 쓸 것인가 — PostgreSQL / TimescaleDB / InfluxDB / 파일(Parquet) / 하이브리드
2. 어느 해상도로 저장할 것인가 — 30Hz 원시 / 1분 집계 / 1일 집계 / 이중 계층
3. 원시 데이터와 NILM 엔진 결과를 DB에 넣을 것인가

### Decision

**세 가지를 묶어 결정한다.**

**D1. 스토리지 엔진: TimescaleDB (PostgreSQL 16 확장)**

- 시계열 전용(InfluxDB)·관계형 전용(순수 Postgres)·파일(Parquet) 대신 **Timescale = Postgres 확장** 단일 엔진 채택.
- 하이퍼테이블·columnstore·continuous aggregate·retention policy 등 시계열 운영 기능을 갖추면서 관계형 조인(가구/가전/날씨 메타) 품질 유지.

**D2. 30Hz 원시 데이터는 DB에 저장하지 않는다**

- 30Hz 원시는 NILM 엔진이 로컬 파일(또는 Kafka 스트림)에서 직접 읽어 분해·이상탐지 수행 후 폐기.
- DB는 이 결과물의 소비자(UI·리포트)만 서빙.

**D3. Hot/Cold 이중 해상도 저장 (1분 7일 + 1일 장기)**

- Hot tier: `power_1min` hypertable — 최근 7일, 1분 해상도 (avg/min/max active_power + energy_wh + 전기 특성 avg)
- Cold tier: `power_1day` continuous aggregate — 7일 이상 과거, 1일 해상도 (avg(avg)/min(min)/max(max) + sum(energy_wh))
- 주간 적재(예: 월요일 1주치 주입) + 연속집계 자동 리프레시 + 7일 retention drop 의 조합으로 운영.
- 집계 방식은 30Hz→1분 때와 동일 규칙을 재사용 (min/max 계층 합성성 성립).

**D4. NILM 엔진의 분해 결과는 DB에 저장하지 않는다**

- 모델 출력은 평가용으로 AI Hub 기제공 라벨(`activity_intervals`)과 비교에만 사용, DB 적재 없음.
- 서비스 론칭 이후 모델 출력 서빙이 필요해지면 재검토 (별도 ADR 발행).

**D5. 개인식별정보(PII)는 분리 테이블 + AES-256 암호화**

- `household_pii` 테이블에 `address`/`members`/`income(실제=맞벌이여부)` 격리.
- Fernet(AES-256) 대칭키 암호화, 키는 환경변수 `CREDENTIAL_MASTER_KEY`.
- 분석 역할은 `household_pii` 직접 조회 권한 없음.

### Consequences

**Positive**

- 운영 점유량: 7일 hot ~1.1 GB + 24일 cold ~50 MB ≈ **1.2 GB 수준**으로 상시 유지. 원시 8TB 대비 6,600× 축소.
- 단일 엔진(Postgres) 운영 → 백업·HA·모니터링 도구 단일화.
- 관계형 조인(가구 메타 × 측정값) 자연스러움 → NILM 분석 쿼리 단순.
- `power_1min` → `power_1day` 연속집계로 주간 다운샘플 로직을 DB가 자동 수행 → 애플리케이션 배치 코드 불필요.
- PII 분리로 개인정보 보호법·루트 보안 규칙 실행 경계 확립.

**Negative / Trade-offs**

- 30Hz 원시를 DB에서 사후 조회할 수 없음 → 이상 이벤트 사후 분석에 원시가 필요하면 별도 스냅샷 테이블 도입 필요 (연기됨).
- `avg(avg)` 1일 집계는 1분 버킷의 `sample_count` 가 균일할 때만 정확 → 결측 발생 시 가중평균(`sum(avg × count)/sum(count)`)으로 리팩터링 필요.
- Retention 과 cagg refresh 의 순서 의존성 → cagg 가 멈추면 7일 drop 도 멈춰야 데이터 손실 없음, 운영 모니터링 필수.
- NILM 모델 출력 미저장 → 장기 성능 추적·재학습 피드백 루프에 외부 스토리지(로그/S3) 별도 설계 필요.
- TimescaleDB 하이퍼테이블은 chunk 간 FK 제약이 제한적 → `(household_id, channel_num)` 참조 무결성을 ETL 단계에서 프로그램적으로 보장.

### Alternatives Considered

| 대안 | 기각 사유 |
|------|-----------|
| **InfluxDB** 단독 | 시계열 성능은 유사하나, 110가구 × 23채널 × 가전/날씨 메타 조인 쿼리에 플럭스 스크립트가 장황. 관계형 무결성(EXCLUDE gist)·PII 테이블 분리 불가 |
| **순수 PostgreSQL** (확장 없음) | 수억 행 시계열의 파티셔닝·압축·연속집계를 애플리케이션이 구현해야 함. 운영 부담 과다 |
| **Parquet 파일 레이크 + Trino** | 대화형 대시보드 쿼리 지연 과다. 가구 단위 갱신 작업에 부적합 |
| **30Hz 원시를 DB에 하이퍼테이블로 저장** | 8TB+ 규모. 관리 부담 대비 실효성 낮음 (분해·이상탐지 외 수요 없음). Columnstore 압축 후에도 1~2TB |
| **단일 1분 테이블, retention 없음** | 1~2년 후 100~200 GB 로 증가. 분석 수요상 1년 이상 과거는 1일 해상도로도 충분 → 비효율 |
| **1분→1시간→1일 3단 계층** | 쿼리 라우팅 복잡도 증가. 현재 요구사항(대시보드·월간 리포트)에 과대 설계 — 필요 시 `power_1hour` cagg 추가 여지로 남김 |
| **NILM 결과를 DB에 적재하고 실시간 서빙** | 모델 품질 미검증 상태에서 운영 부담 선행. 먼저 AI Hub 라벨과의 오프라인 평가로 신뢰도 확보 후 재결정 |

### Follow-ups

- [ ] 압축/보존 policy migration SQL 분리 (`Database/migrations/20260421_compression_retention.sql`)
- [ ] ETL 스크립트(`Database/scripts/ingest_aihub.py`) — CSV/JSON → 1분 집계 → DB
- [ ] cagg refresh + retention 운영 헬스체크 지표 정의 (후속 ADR 가능)
- [ ] 이상 이벤트 고해상도 윈도우 테이블 필요성 재평가

---

## ADR-002 — DR 절감량 계산 기준 및 CBL 산정 방식

- **Status**: Accepted — 2026-04-23
- **관련 브랜치**: `kpx-integration-settlement`
- **구현 근거**: `kpx-integration-settlement/plans/PLAN.md §UC-2`
- **상위 요구사항**: REQ-005 (전력거래소 연계, 감축 실적 산출)

### Context

DR 이벤트 종료 후 가구별 절감량을 계산해야 한다. 계산 기준으로 두 가지 방식이 존재한다.

1. **채널별 합산**: NILM으로 분리된 가전 채널(ch02~ch23) 절감량 합산
2. **전체 미터 기준**: ch01(분전반 전체 미터) CBL - 실측

### Decision

**전체 미터(ch01) 기준 CBL 방식 채택.**

- 절감량 = `cbl_kwh - actual_kwh` (ch01 이벤트 구간)
- CBL = 이벤트 직전 10 평일 중 상위 2일·하위 2일 제외한 6일 가중평균 (KPX 표준)
- NILM 채널(ch02~ch23)별 절감량은 KPX 정산 기준이 아닌 **UI 가전별 기여 표시 전용**

### Consequences

**Positive**
- ch01은 실측값으로 NILM 분해 오차 없음 → KPX 검증 통과 신뢰도 높음
- 채널 합산 시 발생하는 분해 오차 누적 방지

**Negative**
- 가전별 정확한 기여도는 NILM 정확도에 의존 → UI 참고용으로만 제공

### Alternatives Considered

| 대안 | 기각 사유 |
|------|-----------|
| 에어컨 채널[고정시간대] 직접 합산 | 이벤트 구간이 고정이 아니며, 에어컨 외 가전 기여 누락 |
| 모든 NILM 채널 합산 | 분해 오차 누적, KPX 미터값과 불일치 가능 |

---

## ADR-003 — DR 이벤트 구간 처리 방식

- **Status**: Accepted — 2026-04-23
- **관련 브랜치**: `kpx-integration-settlement`
- **상위 요구사항**: REQ-005 (DR 이벤트 수신)

### Context

DR 이벤트 발령 시각과 종료 시각을 어떻게 처리할지 결정해야 한다.
초기 설계에서 17~20시 고정 구간으로 가정했으나 KPX 운영 규칙 확인 결과 이와 다름이 확인됨.

### Decision

**DR 이벤트 구간은 KPX 수신값(start_ts, end_ts)을 그대로 사용한다.**

- 발령 가능 시간: 평일 06:00~21:00 (KPX 국민DR 기준)
- 사전 통보: 이벤트 시작 최소 30분 전
- 코드 내 시간대 하드코딩 금지 — 모든 계산은 수신된 start_ts, end_ts 기준

### Consequences

**Positive**: 실제 KPX 운영 방식과 정합. 이벤트 구간 변경 시 코드 수정 불필요

**Negative**: 시뮬레이션 시 임의 이벤트 구간 주입 필요 (현재 18:00~19:00 사용)

---

## ADR-004 — LLM 입력 데이터 익명화 정책

- **Status**: Accepted — 2026-04-23
- **관련 브랜치**: `kpx-integration-settlement`
- **상위 요구사항**: REQ-007 (보안), 개인정보보호법

### Context

가구 전력 소비 패턴은 개인식별 가능 정보(PII)이다. LLM 맥락 메시지 생성을 위해 OpenAI API(GPT-4o-mini)를 사용하며, 데이터가 외부 서버로 전송된다.

### Decision

**LLM API 호출 시 household_id·주소·가구원 정보를 제외한 익명화 데이터만 전송한다.**

전송 허용 필드:
- `temperature`, `humidity`, `windchill` (공개 기상 데이터)
- `cluster_label` (0/1/2, 군집 번호)
- `savings_kwh`, `refund_krw` (집계값)
- `appliance_code` 목록 (가전 종류, 식별 불가)
- `event_start`, `event_end` (이벤트 구간)

전송 금지 필드:
- `household_id`, `address`, `members`, `income`

### Consequences

**Positive**: 외부 API 전송 시 PII 유출 방지, 개인정보보호법 준수

**Negative**: 가구 맥락 일부 손실 → 개인화 정확도 일부 저하 허용

### Alternatives Considered

| 대안 | 기각 사유 |
|------|-----------|
| 로컬 Gemma 26B | 품질 검증 필요, 초기 단계에서 운영 부담 높음 — 추후 검토 |
| 전체 데이터 전송 | 개인정보보호법 위반 위험 |

---

## ADR-005 — 30분 단위 DR 사전 계산 테이블 도입

- **Status**: Accepted — 2026-04-23
- **관련 브랜치**: `kpx-integration-settlement` (읽기), `Database` (생성 담당)
- **구현 근거**: `kpx-integration-settlement/plans/PLAN.md §power_efficiency_30min`
- **상위 요구사항**: REQ-008 (성능 <2s)

### Context

DR 절감량 계산 시 TimescaleDB `power_1min`을 매 요청마다 직접 조회하면 DB 병목이 발생한다.
프론트엔드 효율화 방안 표시·정산 계산 등 여러 유스케이스가 동일 데이터를 반복 조회하는 구조.

### Decision

**30분 단위 DR 사전 계산 테이블(`power_efficiency_30min`)을 별도 생성하고, 모든 절감량 조회는 이 테이블에서만 읽는다.**

- `power_1min` 직접 조회 금지 (kpx-integration-settlement 내에서)
- 채우는 주체: Celery beat (1시간 주기 전 가구 집계) + DR 이벤트 수신 시 즉시 계산
- LLM 호출 시점: 프론트엔드 효율화 방안 요청 시에만

### Consequences

**Positive**
- 반복 TimescaleDB 조회 제거 → 응답 지연 감소
- LLM 호출 빈도 제어 가능 (요청 시에만)

**Negative**
- Celery 배치 지연 시 최신 데이터 반영 늦어질 수 있음 (최대 1시간 지연)
- 테이블 관리 추가 (Database 브랜치 협업 필요)

### Alternatives Considered

| 대안 | 기각 사유 |
|------|-----------|
| 실시간 TimescaleDB 조회 | 분당 1분 행 풀스캔 → 병목 확인됨 |
| Redis 캐싱 | 사전 계산 결과를 DB에 영속화하는 것이 감사·정산 추적에 유리 |

---

## ADR-006 — NILM 학습 데이터 GCS 버킷 dual-region 전환

- **Status**: **Superseded by ADR-007 — 2026-04-24** (전제 오류: `asia-northeast3` + `us-central1` custom dual-region 조합은 GCS에서 허용되지 않음, 실제 적용 전 기각)
- **원래 Status**: Accepted — 2026-04-24
- **관련 브랜치**: `Database`
- **구현 근거**: `Database/docs/nilm_gcs_access_guide.md`, `Database/docs/gcs_dualregion_migration.md`
- **상위 요구사항**: 루트 `CLAUDE.md` REQ-001 (NILM 학습 데이터 접근), REQ-008 (성능/비용)

### Context

현재 NILM 학습용 parquet 버킷 `ax-nilm-data-dhwang0803` 은 single-region (`asia-northeast3`, Seoul) 로 생성되어 있다. 팀 구성원 일부가 **Colab 무료/기본 티어**에서 실험을 진행 중인데, Colab 런타임 리전은 `us-central1` 로 고정되며 사용자가 선택할 수 없다. 결과:

- 버킷(asia-northeast3) → Colab(us-central1) 접근 시 **대륙 간 인터넷 egress** 단가($0.12/GB) 적용
- 태평양 왕복 네트워크 지연으로 반복 학습(여러 에폭) 시 속도 저하
- 기존 가이드(§5)가 권고한 "로컬 캐시 후 반복 학습" 전략이 Colab 에서는 매 세션 재다운로드로 귀결 → 비용 상쇄 불가

### Decision

**D1. Configurable dual-region (`asia-northeast3` + `us-central1`) 채택**

- 한국 운영 인프라와 Colab 양쪽 모두에서 **in-region read ($0 egress)** 성립.
- Multi-region (ASIA/US/EU) 대비 리전 고정으로 단가·토폴로지 예측 가능.

**D2. 신규 버킷명 `ax-nilm-data-dhwang0803-dual` 로 생성 (기존명 재사용 포기)**

- GCS 버킷 location 은 생성 후 변경 불가 → 기존명 유지하려면 삭제 후 재생성이 필요.
- 삭제된 버킷명은 **soft-delete 유예(기본 7일)** 로 즉시 재사용 보장되지 않음.
- 이름 변경 시 **1회 복사** + 원본을 롤백 보험으로 병렬 보존 가능.

**D3. Standard async replication 사용 (Turbo replication 미채택)**

- 학습 데이터는 실시간성 요구 없음.

**D4. 원본 버킷 폐기 시점 — 팀원 전원 접근 검증 완료 후**

### Consequences (가상)

**Positive**
- Colab 과 한국 인프라 양쪽 in-region ($0 egress)
- 대륙 간 왕복 지연 제거

**Negative**
- Storage 단가 ~2배 (~$2.7/월)
- 버킷 경로 변경 → 팀원 스크립트 일괄 갱신

### Alternatives Considered

| 대안 | 기각 사유 |
|------|-----------|
| **이름 유지 + temp 2회 복사** | soft-delete 유예 해제 대기 변수, 복사량 2배, 다운타임 장기화 |
| **Multi-region `ASIA`** | `us-central1` 불포함 → egress 미해결 |
| **Colab Pro/Enterprise 개별 업그레이드** | 팀원 개인 비용 부담, 팀 전원 전환 강제 비현실 |

### 기각 사유 (실제 적용 실패)

2026-04-24 실제 버킷 생성 시도에서 `gcloud storage buckets create --placement=asia-northeast3,us-central1` 이 `HTTPError 400: Invalid custom placement config` 로 거부됨. cross-continent custom dual-region 쌍은 현재 GCS 허용 목록에 없음 (configurable dual-region 은 같은 area 내 리전 쌍만 지원). 실제 적용 전 기각 → ADR-007 로 재결정.

---

## ADR-007 — NILM 학습 데이터 cross-region 접근: 두 single-region 버킷 병렬 운영

- **Status**: Accepted — 2026-04-24 (Supersedes ADR-006)
- **관련 브랜치**: `Database`
- **구현 근거**: `Database/docs/nilm_gcs_access_guide.md`, `Database/docs/gcs_dualregion_migration.md`
- **상위 요구사항**: 루트 `CLAUDE.md` REQ-001, REQ-008

### Context

ADR-006 이 제안한 configurable dual-region (`asia-northeast3` + `us-central1`) 은 실제 생성 시도에서 GCS API 가 `Invalid custom placement config` 로 거부 — cross-continent custom dual-region 쌍은 현재 GCS 허용 목록에 없다.

원래 문제는 그대로 남아있다: 팀원 Colab 런타임이 `us-central1` 고정이라 `asia-northeast3` 버킷 접근 시 대륙 간 egress + 지연 발생.

### Decision

**D1. 같은 데이터를 두 single-region 버킷에 병렬 보존**

- `ax-nilm-data-dhwang0803` (기존, `asia-northeast3`) — **유지**
- `ax-nilm-data-dhwang0803-us` (신규, `us-central1`) — 생성 완료
- 팀원은 자기 런타임 리전에 맞는 버킷 사용 → 양쪽 모두 **in-region read ($0 egress)**

**D2. 동기화는 원본 → 복사본 방향 `gcloud storage rsync`**

- 초기 일괄 복사 1회 완료 (2026-04-24, 5,209 객체 / 64.8 GB, 534.9 MiB/s).
- 학습 데이터는 append-only 성격 강함 → 신규 데이터 업로드 시 두 버킷 동시 반영 (ETL 에 한 줄 추가).
- `cp -r "gs://src/**" "gs://dst/"` 는 `/**` 글롭이 디렉토리 평탄화 버그 유발 → **반드시 `rsync` 사용** (`--delete-unmatched-destination-objects` 로 dst 잔여물 자동 정리).

**D3. IAM 은 두 버킷에 동일 멤버·역할 부여**

- `roles/storage.objectViewer` 를 동일 팀원 리스트로 적용.

**D4. 버킷명은 리전 suffix (`-us`) 로 구분**

- `-dual` 은 오해의 소지 (dual-region 아님). 단일 리전 식별자 접미사가 명확.

**D5. 버킷 레이아웃 규칙 — dataset root 는 parquet 전용**

- `nilm/<subset>/` 아래는 parquet 만. 비-parquet 파일은 pyarrow `ds.dataset()` 을 깨뜨림 (실사례: `manifest.json` 때문에 `ArrowInvalid`).
- ETL sidecar (manifest 등) 는 `nilm/_manifests/<subset>.json` 에 격리. 기존 `manifest.json` 은 양 버킷에서 이동 완료.

### Consequences

**Positive**

- Colab(`us-central1`) · 한국 인프라 양쪽 모두 in-region → egress $0
- Storage 단가는 dual-region 대비 거의 동일 (single × 2 ≈ dual × 1)
- 운영 복잡도 낮음 (GCS 특수 기능 미사용, 표준 버킷 두 개)
- 기존 버킷 무변경 → 한국 팀의 기존 스크립트·경로 영향 없음

**Negative / Trade-offs**

- Storage 2벌 보유: 61 GB 기준 월 ~$2.8 (single 각 ~$1.4). 실질 비용은 ADR-006 추정과 동등.
- 초기 복사 1회성 cross-continent egress (~61 GB, 대략 $5-7)
- 신규 데이터 업로드 시 양쪽 반영 책임은 애플리케이션·ETL 쪽 → 헬퍼 스크립트 필요
- 양쪽 일관성 모니터링(파일 수·체크섬)은 주기적으로 수행 필요

### Alternatives Considered

| 대안 | 기각 사유 |
|------|-----------|
| **Configurable dual-region asia+us (ADR-006)** | GCS 미지원 — 실행 시점에 API 거부로 기각 |
| **Storage Transfer Service 정기 sync** | 현재 데이터 갱신 빈도 낮아 과대설계. 실시간성 요구 시 재평가 |
| **us-central1 단일 버킷 이전** | 한국 팀이 out-of-region 으로 역전, 문제 이동일 뿐 |
| **ASIA 내 dual-region (`asia-northeast1` + `asia-northeast3`)** | Colab `us-central1` 문제 미해결 |
| **Colab Pro/Enterprise 개별 업그레이드** | 팀원 개인 비용 부담 ($10/월/인), 팀 전원 전환 강제 비현실 |

### Follow-ups

- [x] 초기 복사 완료 후 정합성 검증 (5209=5209 객체, 64,842,116,835 byte 일치, MD5 샘플 3/3 OK)
- [x] 팀원 전원 신규 `-us` 버킷 접근 검증
- [x] `Database/docs/gcs_dualregion_migration.md` 작성 (파일명은 기존 유지)
- [x] `nilm/_manifests/training_dev10.json` 레이아웃 적용 (양 버킷)
- [ ] 신규 데이터 업로드 시 양쪽 버킷 반영 헬퍼 스크립트 작성 (`Database/scripts/sync_buckets.sh` 가칭)
- [ ] `convert_nilm.py` (레포 밖) 의 manifest 경로를 `nilm/_manifests/<subset>.json` 으로 업데이트
