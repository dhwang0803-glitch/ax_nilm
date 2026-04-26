# Database 추가 작업 대기 목록 (임시)

> 작성일: 2026-04-26 (최초) · 갱신: 2026-04-26 (Phase B-1 메타 적재 완료)
> 작성 맥락: main 머지 후(39 커밋 동기화) 각 feature 브랜치의 DB 의존을 수집한 결과.
> 성격: **임시 작업 노트.** 모든 항목 클로즈 후에는 본 파일을 폐기하고 `migrations/`·`schema_design.md`로 흡수한다.

---

## 현재 상태 (2026-04-26 세션 종료 시점)

**✅ 완료**:
- P0 (KPX 신규 테이블/컬럼 5건) — 마이그레이션 01~04 발행
- P1 (pgvector skeleton) — 마이그레이션 05 발행 (차원 미확정 상태로)
- P2 (label_map ↔ appliance_types, status_codes seed) — 마이그레이션 06~07 발행
- P3 Phase A (Repository / ORM 코드) — `Database/src/{models,repositories}/`
- **GCP 인프라 배포** — VM `ax-nilm-db-dev` (asia-northeast3-a, e2-standard-2, 100GB pd-ssd) + Postgres 16 + TimescaleDB + pgvector + ax_nilm_app 사용자 + Secret Manager. 시드 23행 검증 완료
- 셋업 자동화 — `Database/scripts/gcp/01~03b_*.sh`, runbook `Database/docs/gcp_setup.md`
- **Phase B-1: AI Hub 메타 적재** — `Database/scripts/load_aihub_meta.py` 작성 + 적재 완료. `households=79`, `household_channels=1045` (희소; 가구당 9~22채널), `household_daily_env=2449` (79×31일). 채널→appliance_code 매핑은 hardcode dict (한글 표기 7건 미스매치 회피). 가구ID `house_001`→`H001` 변환. ON CONFLICT DO NOTHING 으로 재실행 안전. PII 미적재 (Fernet 후속).

**⏳ Phase B 대기 (다음 세션)**:
1. **팀원 IAM 부여** — 현재 본인 계정만 접근 가능. `roles/iap.tunnelResourceAccessor` + `roles/compute.osLogin` + `roles/secretmanager.secretAccessor` (대상자 명단 회신 후 일괄 처리)
2. **`Database/docs/team_onboarding.md`** — 새 환경에서 5분 안에 connect 가능한 walkthrough
3. **Fernet 키 발급 + Secret Manager 등록** (`ax-nilm-credential-master-key`) — 미등록 시 PIIRepository 인스턴스화 실패. 등록 후 `household_pii` 79행 적재 (address/members/income_dual/utility_facilities/extra_appliances)
4. **dev10 power 적재 스크립트** — GCS `nilm/training_dev10/` parquet → `power_1min` (10가구 분량 hot tier 채움)
5. **Integration tests** — `Database/tests/`, IAP 터널 활성 상태에서 pytest

**🔧 알려진 사소한 버그 (Phase B 안에 함께)**:
- `power_1hour` cagg 의 `COMMENT ON MATERIALIZED VIEW` 한 줄만 실패 (TimescaleDB cagg 가 표준 MV 가 아님). 데이터/인덱스 영향 없음. 수정 마이그레이션: `COMMENT ON VIEW power_1hour ...`

**미결정 (외부 의존)**:
- P1 임베딩 차원 (KPX ADR 미발행) → 결정 후 `ALTER COLUMN embedding TYPE vector(N)` + IVFFlat/HNSW 인덱스 추가 마이그레이션
- P4 이상 이벤트 테이블 (anomaly-detection 브랜치 코드 0개)

---

## 0. 브랜치 스냅샷 (2026-04-26 기준)

| 브랜치 | 상태 | DB 접점 요약 |
|--------|------|--------------|
| `nilm-engine` | main 머지 완료 (PR #21까지) | GCS parquet 직접 학습. 추론 결과는 향후 `appliance_status_intervals`에 적재 (스키마 004 이미 존재) |
| `dr-savings-prediction` | 미머지. KMeans n=9 군집화 + 시간대 분석 스크립트 | parquet 기반 분석. 결과 `cluster_label`을 `households`에 영속화 필요 |
| `kpx-integration-settlement` | 미머지. CBL/정산/가전기여/RAG 모듈 초안 + `seed_aggregators.sql` 작성 | **PLAN.md에서 DB 신규 테이블·컬럼 다수 명시 요청** |
| `anomaly-detection` | 미머지, 빈 브랜치 | 코드 없음. REQ-002 정의상 `appliance_status_intervals` confidence ≥ 0.6 입력 + 이상 이벤트 테이블 필요(이미 마이그레이션 예정 항목) |

---

## 1. P0 — KPX `kpx-integration-settlement/plans/PLAN.md`에서 명시 요청

### 1.1 `aggregators` 테이블 신규
- 출처: `kpx-integration-settlement/scripts/seed_aggregators.sql`
- 컬럼: `aggregator_id PK`, `name`, `settlement_rate DOUBLE PRECISION (원/kWh, CHECK >0)`, `updated_at`
- 시드 3건: AGG_PARAN(1000) / AGG_BYUKSAN(1200) / AGG_LG(1300)
- 작업: KPX의 SQL을 `Database/migrations/`로 회수, KPX 브랜치는 후속 PR에서 제거

### 1.2 `households` 컬럼 추가 (3개)
- `cluster_label SMALLINT` — DR 브랜치 KMeans 결과 적재
- `dr_enrolled BOOLEAN`
- `aggregator_id TEXT FK → aggregators(aggregator_id)`

### 1.3 `dr_events` 신규
- `event_id PK (KPX 발급)`, `start_ts`, `end_ts`, `target_kw`, `issued_at`, `status TEXT CHECK IN (pending|active|completed|cancelled)`

### 1.4 `dr_results` 신규
- PK 후보: `(event_id, household_id)`
- 컬럼: `cbl_kwh`, `actual_kwh`, `savings_kwh`, `refund_krw INTEGER`, `settlement_rate`, `cbl_method TEXT (mid_6_10|proxy_cluster)`, `created_at`
- FK: `event_id → dr_events`, `household_id → households`

### 1.5 `dr_appliance_savings` 신규
- 컬럼: `event_id`, `household_id`, `channel_num SMALLINT`, `appliance_code TEXT`, `channel_cbl_kwh`, `channel_actual_kwh`, `channel_savings_kwh`
- FK: `event_id → dr_events`, `(household_id, channel_num) → household_channels`, `appliance_code → appliance_types`
- 용도: KPX 정산은 ch01 기준이고 채널별 분해는 UI 표시 전용

### 1.6 `power_efficiency_30min` 신규 ⭐ "Database 브랜치 요청" 명시
- PK: `(household_id, channel_num, bucket_ts)`
- 컬럼: `energy_wh`, `cbl_wh`, `savings_wh`, `is_dr_window BOOLEAN`, `event_id TEXT NULL` (DR 구간일 때만), `computed_at`
- 쓰기: Celery 배치(1시간 주기) + DR 이벤트 트리거에서 채움
- 읽기: KPX UC-2 `calc_savings`가 TimescaleDB 직접 조회 대신 이 테이블만 사용
- 검토 필요: TimescaleDB hypertable로 만들지(시간축 큼) 여부 — 30분 × 365일 × 23ch × N가구 규모 추산 후 결정

---

## 2. P1 — pgvector 도입 결정 필요

### 2.1 `pgvector` 확장 + `household_embeddings` 신규
- 컬럼: `household_id`, `ref_date DATE`, `embedding vector(384 또는 768)`, `embed_model TEXT`, `created_at`
- 미결: 차원수(384 vs 768), 임베딩 모델(Chronos vs TimesFM vs 자체) — KPX 측 ADR 미발행
- **권장 분리**: 우리 쪽은 확장 enable + 빈 스켈레톤 테이블만 발행, 차원 확정 후 KPX 또는 우리 쪽에서 후속 마이그레이션으로 차원 확정·인덱스(IVFFlat/HNSW) 추가
- **상태 (2026-04-26)**: `migrations/20260426_05_enable_pgvector_skeleton.sql` 발행 완료
  - `CREATE EXTENSION IF NOT EXISTS vector` + 차원 미지정(`vector`) 컬럼 + B-tree 인덱스 2종(가구·모델 축)
  - PK = `(household_id, ref_date, embed_model)` — 모델별 임베딩 병존 가능
  - **후속 작업 필요**: KPX ADR 발행 후 (a) `ALTER COLUMN embedding TYPE vector(N)` 차원 확정, (b) IVFFlat 또는 HNSW 인덱스 추가

---

## 3. P2 — 정합성·네이밍 갭

### 3.1 `label_map.py` ↔ `appliance_types` 매핑
- nilm-engine `src/classifier/label_map.py`: 한글 라벨 인덱스 0~21 (배열 순서가 곧 모델 출력 인덱스)
- DB `appliance_types`: 영문 코드(`TV`, `KETTLE`, ...) + `default_channel`(AI Hub 채널 1~23)
- **핵심**: 모델 출력 인덱스 순서 ≠ AI Hub 채널 순서 ≠ DB `default_channel`
  - 예: 모델 idx 1=`전기포트` ↔ DB `KETTLE` ch04, 모델 idx 2=`선풍기` ↔ DB `FAN` ch03
- 이름 표기 차이 다수:
  - NILM `식기세척기/건조기` vs DB `DISHWASHER` (`식기세척기`)
  - NILM `전기장판/담요` vs KPX `전기장판, 담요` vs DB `ELEC_BLANKET` (`전기장판/담요`)
  - NILM `진공청소기(유선)` vs DB `VACUUM` (`진공청소기`)
- 작업: DB를 단일 진실 소스로 두고 `appliance_types`에 `nilm_label_index SMALLINT UNIQUE NULL`(0~21) 컬럼 추가하여 모델 인덱스 → appliance_code 양방향 결정. seed에 채워 넣음.
- **상태 (2026-04-26)**: `migrations/20260426_06_add_nilm_label_index.sql` 발행 완료
  - ALTER TABLE + UPDATE 백필 + 22행 검증 DO 블록 (매핑 누락 시 즉시 RAISE EXCEPTION)
  - 한글 라벨 표기 차이는 무시하고 `appliance_code` 로 매칭 — DB 가 단일 소스
  - **하류 영향**: nilm-engine 추론 결과를 `appliance_status_intervals` 에 적재할 때
    `appliance_types.nilm_label_index = <model output idx>` 로 join 하여 `appliance_code` 획득

### 3.2 `appliance_status_codes` seed
- 004 스키마는 빈 테이블로만 생성됨
- nilm-engine 첫 추론 결과 분포 확인 후 모델 팀과 합의된 코드 세트로 seed
- Database/CLAUDE.md 마이그레이션 예정 항목으로 이미 표기됨
- **상태 (2026-04-26)**: `migrations/20260426_07_seed_appliance_status_codes.sql` 발행 완료
  - 모델 팀 회신본 (`model_interface.md §5.1` 확정안) 기준 12개 코드 시드
  - 코드 범위: 0-9 범용+Type1 / 10-19 Type2 복합사이클 / 20-29 Type3 양자화 bucket(Low/Mid/High) / 30-39 Type4 주기성 / 40-99 예약
  - `appliance_code` 모두 NULL — 31/32 "냉장고 전용" 은 FRIDGE+KIMCHI_FRIDGE 둘 다 해당해 단일 FK 표현 불가, 호환성 판정은 application 레이어에서 `nilm_type` 으로 처리
  - schemas/004 테이블 COMMENT 의 임시 가이드("20-29 Type4")를 모델 팀 확정 범위로 덮어씀

---

## 4. P3 — Repository / ORM 공백 (스키마는 있으나 코드 없음)

### 4.1 `Database/src/models/` 비어있음
- SQLAlchemy 2.0 async ORM 모델 부재
- Repository 구현 전제
- **상태 (2026-04-26)**: 완료
  - `models/base.py` (DeclarativeBase) + `meta.py` / `household.py` / `power.py` / `nilm.py` / `dr.py` 5개 도메인 모듈
  - 11개 테이블 전수 매핑 (appliance_types, aggregators, appliance_status_codes, households, household_pii, household_channels, household_daily_env, household_embeddings, power_1min, power_1hour, power_efficiency_30min, activity_intervals, appliance_status_intervals, ingestion_log, dr_events, dr_results, dr_appliance_savings)
  - pgvector 컬럼은 차원 미지정(`Vector()`) — migration 05 와 일치
  - EXCLUDE gist 제약은 ORM 표현 불가 → schemas SQL 이 단일 소스, ORM 측은 IntegrityError 로 받음

### 4.2 `Database/src/repositories/` 비어있음
- Database/CLAUDE.md에 6개 명시: `power_repository, household_repository, pii_repository, activity_repository, nilm_inference_repository, ingestion_log_repository`
- KPX 신규 요구로 추가 필요: `dr_repository`(events/results/appliance_savings), `aggregator_repository`, `embedding_repository`(P1 후)
- 인터페이스 호환성: KPX `src/settlement/cbl.py`의 `UsageRepository` Protocol(`get_weekday_usage`, `get_cluster_avg_ratio`), `src/settlement/calculator.py`의 `AggregatorRepository`(`get_settlement_rate`)을 충족할 것
- **상태 (2026-04-26)**: 베이스 6 + DR/Aggregator 2 완료. embedding_repository 는 P1 후속 (차원 확정 후).
  - `repositories/protocols.py` — Protocol 통합 정의 (KPX UsageRepository / AggregatorRepository 동일 시그니처)
  - 베이스 6: `power_repository.py` (UsageRepository 충족), `household_repository.py`, `pii_repository.py` (Fernet AES-256 + `CREDENTIAL_MASTER_KEY` env 강제), `activity_repository.py`, `nilm_inference_repository.py` (`record_transition` 단일 트랜잭션), `ingestion_log_repository.py`
  - KPX 추가 2: `aggregator_repository.py` (캐시 없음 — 단가 변경 즉시 반영), `dr_repository.py` (event 헤더 + result + appliance_savings 분해)
  - 부트스트랩: `Database/src/db.py` (asyncpg DSN 강제 + pool_pre_ping), `Database/requirements.txt` (SQLAlchemy 2.0 + asyncpg + pgvector + cryptography + pytest)
  - **다음 세션**: integration tests (실제 PostgreSQL 컨테이너), `embedding_repository`, KPX 측에 “Database 측 Protocol 사용 가능” 공지

---

## 5. P4 — 향후 (미머지 브랜치 첫 코드 후)

### 5.1 이상 이벤트 테이블 (REQ-002)
- Database/CLAUDE.md에 `20260501_add_anomaly_events.sql` 예정으로만 표기
- anomaly-detection 브랜치가 비어있어 컬럼/세부 스펙 미확정
- 입력원은 `appliance_status_intervals` (confidence ≥ 0.6) — 004 스키마 이미 준비됨

---

## 6. 작업 순서 — 완료분 + Phase B 계획

### 6.1 완료분 (참고용 이력)
- 2026-04-26 오전: 마이그레이션 01~07 발행 (P0/P1/P2)
- 2026-04-26 오후: P3 Phase A 코드 (`Database/src/{models,repositories}/`)
- 2026-04-26 오후: GCP 인프라 배포 + 스키마 적용 + 시드 검증

### 6.2 Phase B 권장 순서 (다음 세션 시작 시 위에서부터)

1. ~~**AI Hub 메타 적재**~~ — **완료 (2026-04-26)**
   - 스크립트: `Database/scripts/load_aihub_meta.py` (TL.zip 직접 단일 패스, asyncpg + ORM, ON CONFLICT DO NOTHING)
   - 소스: SSD `D:\nilm_raw\downloads\...TL.zip` 32,395 JSON (GCS `nilm/labels/training.parquet` 는 ON 구간만 보존, 메타 풀필드 없음)
   - 적재 결과: `households=79`, `household_channels=1045` (가구당 9~22채널 희소), `household_daily_env=2449` (79가구×31일)
   - **검증 사실** (전수조사):
     - 같은 채널 번호 = 같은 가전 (79가구 충돌 0) → 채널→appliance_code hardcode dict 안전
     - 한글 표기 7건 미스매치 (예: AI Hub `일반 냉장고` vs DB `냉장고`) — 한글 매칭 시도 시 깨짐
     - 가구ID 포맷 변환 `house_001`→`H001` (DB CHECK `^H[0-9]{3}$`)
     - `unknown` / `""` → NULL, `energy_efficiency` 1~5 외 → NULL (CHECK 위반 차단)
   - PII 부분(`address`, `members`, `income_dual`, `utility_facilities`, `extra_appliances`)은 3번 Fernet 키 등록 후 별도 PII 적재로 보완

2. **팀원 IAM 부여** (사용자 명단 회신 후 일괄)
   ```bash
   for ROLE in iap.tunnelResourceAccessor compute.osLogin secretmanager.secretAccessor; do
       gcloud projects add-iam-policy-binding $PROJECT_ID \
           --member="user:peer@example.com" --role="roles/$ROLE"
   done
   ```

3. **`Database/docs/team_onboarding.md`**
   - 새 머신/계정에서 5분 안에 connect 가능한 walkthrough
   - 본인의 `.env` 작성 → gcloud 인증 → IAP 터널(LOCAL_PG_PORT=5436) → DATABASE_URL → Python 검증

4. **Fernet 키 발급 + Secret Manager 등록 + PII 적재**
   ```bash
   FERNET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
   printf '%s' "$FERNET_KEY" | gcloud secrets create ax-nilm-credential-master-key --data-file=-
   ```
   - PII 적재: 1번에서 이미 79가구 households 가 있으므로 `household_pii` 만 INSERT. address/members 는 Fernet 암호화 BYTEA, 나머지(income_dual/utility_facilities/extra_appliances) 는 평문. extra_appliances 원소 `strip()` 처리.

5. **dev10 power 적재**
   - 스크립트: `Database/scripts/load_dev10_power.py`
   - 입력: GCS `gs://ax-nilm-data-dhwang0803/nilm/training_dev10/` (10가구 raw parquet, hive partition)
   - 변환: 30Hz raw → 1분 버킷 집계 (avg/min/max + energy_wh 적분) → `power_1min` INSERT
   - 의존: 1번 메타 적재 완료 ✓ (FK)

6. **Integration tests** (`Database/tests/`)
   - IAP 터널 활성 상태에서 pytest
   - Repository 단위: `record_transition` 트랜잭션, EXCLUDE gist 위반, FK CASCADE
   - 시작점: `tests/conftest.py` (`session_scope` 픽스처) + `test_smoke.py` (extension/seed 검증)

7. **`power_1hour` COMMENT 수정 마이그레이션** (사소)
   - `migrations/20260427_XX_fix_power_1hour_comment.sql`
   - `COMMENT ON VIEW power_1hour IS '...'` (현재는 MATERIALIZED VIEW 키워드로 시도 → cagg 가 catalog 상 view 라 실패)

### 6.3 후속 (외부 의존 해소 후)
- **P1 임베딩 차원 확정** — KPX ADR 발행 후 `ALTER COLUMN embedding TYPE vector(N)` + ANN 인덱스
- **P4 이상 이벤트 테이블** — anomaly-detection 브랜치 첫 코드 / REQ-002 스펙 확정 후
- **embedding_repository** — P1 차원 확정 후

---

## 부록 — 본 분석에서 참조한 핵심 파일

- `kpx-integration-settlement/plans/PLAN.md` (DB 요청 마스터 소스)
- `kpx-integration-settlement/scripts/seed_aggregators.sql`
- `kpx-integration-settlement/src/settlement/{cbl,calculator,appliance}.py`
- `dr-savings-prediction/src/features/{cluster_features,extractor,time_features}.py`
- `dr-savings-prediction/scripts/check_target_clusters.py`
- `nilm-engine/src/classifier/label_map.py`
- `nilm-engine/src/disaggregator.py`
- 기존 스키마: `Database/schemas/001~004*.sql`
