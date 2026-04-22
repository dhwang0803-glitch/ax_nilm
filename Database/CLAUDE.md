# Database — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 관련 문서

- 전체 아키텍처: [`docs/context/architecture.md`](../docs/context/architecture.md)
- 스토리지 선택·해상도 정책 (ADR-001): [`docs/context/decisions.md`](../docs/context/decisions.md)
- 파일 맵: [`docs/context/MAP.md`](../docs/context/MAP.md)
- 스키마 설계 근거: [`docs/schema_design.md`](./docs/schema_design.md)
- 데이터셋 명세 (AI Hub 71685): [`docs/dataset_spec.md`](./docs/dataset_spec.md)
- 다운스트림 소비자: `CLAUDE_API_Server.md`, `CLAUDE_Execution_Engine.md` (예정)

## 모듈 역할

**Data Layer** — NILM 기반 에너지 효율화 서비스의 영속성 계층.

- TimescaleDB + PostgreSQL 스키마 설계 및 마이그레이션 관리
- Repository 구현체(비동기) 및 ORM 모델 제공
- PII(주소·구성원·맞벌이) AES-256 암호화 저장소 구현
- AI Hub 71685 데이터셋 ETL 스크립트 (CSV 30Hz → 1분 집계 → DB)

**저장 정책 (ADR-001 요약)**:
- 30Hz 원시 전력 데이터는 **DB에 저장하지 않는다**. NILM 엔진이 로컬/스트림에서 직접 읽고 폐기.
- DB 는 2단 해상도: `power_1min` (hot, 7일) + `power_1hour` (cold, continuous aggregate — 시간대별 이상탐지 패턴 보존).
- NILM 엔진 분해 결과도 DB 미적재 — AI Hub 라벨(`activity_intervals`)과 평가 비교만.

## 다운스트림 소비자

- `API_Server` — Repository 인터페이스 통해 UI·리포트용 집계 쿼리 수행
- `Execution_Engine` (NILM 엔진) — 30Hz 원시는 **DB 우회하여 직접 읽음**. 메타데이터(`household_channels`, `appliance_types`) 조회 시에만 Repository 사용

모든 소비자는 Repository 구현체를 통해서만 DB 에 접근 (직접 SQL 금지).

## 파일 위치 규칙 (MANDATORY)

```
Database/
├── schemas/      ← DDL (CREATE TABLE/INDEX) SQL — 001_core, 002_timeseries, 003_seed
├── migrations/   ← 스키마 변경 이력 (YYYYMMDD_설명.sql) + cagg/retention/compression policy
├── src/          ← Repository 구현체 (import 전용)
│   ├── repositories/
│   │   ├── power_repository.py         ← power_1min / power_1hour 조회
│   │   ├── household_repository.py     ← households + household_channels
│   │   ├── pii_repository.py           ← household_pii (AES-256, 권한 분리)
│   │   ├── activity_repository.py      ← activity_intervals 라벨
│   │   └── ingestion_log_repository.py ← ETL 이력
│   └── models/   ← SQLAlchemy ORM 모델
├── scripts/      ← ingest_aihub.py, migrate.py, validate_sample.py, extract_pdf_text.py
├── tests/        ← pytest (실제 DB 연결, 스키마·ETL 검증)
├── docs/         ← schema_design.md, dataset_spec.md, ERD
├── agents/       ← 에이전트 역할 문서 사본 (post-checkout 훅이 복사)
└── dataset_staging/  ← AI Hub 원본/샘플/설명서 — git 추적 제외 (.gitignore)
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| `CREATE TABLE`, `CREATE INDEX`, `CREATE MATERIALIZED VIEW` | `schemas/` |
| `ALTER TABLE`, cagg 리프레시 정책, retention 정책 | `migrations/YYYYMMDD_*.sql` |
| Repository 구현 (import 전용) | `src/repositories/` |
| SQLAlchemy ORM 모델 | `src/models/` |
| ETL·검증 실행 스크립트 | `scripts/` |
| pytest | `tests/` |
| AI Hub 원본/샘플/설명서 | `dataset_staging/` (git ignore) |

**`Database/` 루트 또는 프로젝트 루트에 파일 직접 생성 금지.**

## 기술 스택

```python
import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
import asyncpg
from cryptography.fernet import Fernet   # PII 암호화
```

- PostgreSQL 16+ with **TimescaleDB 2.x** extension
- `btree_gist` 확장 (activity_intervals EXCLUDE 제약용)
- 비동기 드라이버: `asyncpg` (FastAPI async 호환)
- ORM: SQLAlchemy 2.0 async

## 핵심 테이블

### 메타 (관계형)

| 테이블 | 설명 |
|--------|------|
| `appliance_types` | 22종 가전 + 메인 분전반 카테고리 (ch01~ch23) |
| `households` | 가구 마스터 — 평문 분류값 (house_type, residential_type, area) |
| `household_pii` | 🔒 **PII** — address/members/income_dual, AES-256 암호화 BYTEA |
| `household_channels` | 가구별 ch01~ch23 구성 (가전 + brand + power_category + power_consumption + energy_efficiency) |
| `household_daily_env` | 가구 × 일자별 날씨/기온/풍속/습도 |

### 시계열 (TimescaleDB)

| 테이블 | 설명 |
|--------|------|
| `power_1min` | 1분 집계 hypertable (hot, 7일 retention). ch01~ch23 공용. avg/min/max + energy_wh + sample_count |
| `power_1hour` | 1시간 다운샘플 continuous aggregate (cold). `power_1min` 에서 시간 단위 자동 리프레시. 시간대별 이상탐지 패턴 보존 (REQ-002) |

### 라벨·운영

| 테이블 | 설명 |
|--------|------|
| `activity_intervals` | 가전 ON 구간 (AI Hub 라벨). EXCLUDE gist 로 (가구·채널 내) 구간 겹침 차단 |
| `ingestion_log` | ETL 파일별 적재 이력 (source_file UNIQUE, raw/agg 행수, status) |

## 핵심 인덱스

```sql
-- 가장 빈번한 쿼리: 특정 가구 × 특정 채널 × 특정 기간
CREATE UNIQUE INDEX idx_power_1min_pk
    ON power_1min (household_id, channel_num, bucket_ts);
CREATE INDEX idx_power_1min_recent
    ON power_1min (household_id, channel_num, bucket_ts DESC);
CREATE INDEX idx_power_1hour_lookup
    ON power_1hour (household_id, channel_num, hour_bucket DESC);

-- 라벨 조회 / 겹침 차단
CREATE INDEX idx_activity_intervals_lookup
    ON activity_intervals (household_id, channel_num, start_ts);
-- + EXCLUDE USING gist 제약 (002_timeseries_tables.sql)

-- 메타
CREATE INDEX idx_households_house_type ON households(house_type);
CREATE INDEX idx_household_channels_appliance ON household_channels(appliance_code);
```

## 운영 정책 (cagg + retention)

**순서 민감**: `power_1hour` cagg 가 시간 단위로 리프레시되어 과거 구간을 요약한 후, `power_1min` retention 이 7일 초과 chunk 를 드롭한다.

```sql
-- 1) 1시간 다운샘플 자동 리프레시 (시간 단위)
SELECT add_continuous_aggregate_policy('power_1hour',
    start_offset       => INTERVAL '30 days',
    end_offset         => INTERVAL '2 hours',
    schedule_interval  => INTERVAL '1 hour');

-- 2) hot tier 7일 retention
SELECT add_retention_policy('power_1min', INTERVAL '7 days');
```

cagg 가 멈추면 retention 도 멈춰야 한다 → 운영 헬스체크 필수.

## Repository 패턴

`API_Server` 는 ABC 인터페이스(`PowerRepository`, `HouseholdRepository`, `PIIRepository`, `ActivityRepository`, `IngestionLogRepository`) 에만 의존. 이 브랜치는 구현체를 제공한다.

테스트 시 `InMemoryPowerRepository` 등으로 대체 가능한 구조 유지.

## PII 암호화 규칙 (REQ-007)

- 대상: `household_pii.address_enc`, `household_pii.members_enc`
- 방식: Fernet(AES-256) 대칭키, 키는 환경변수 `CREDENTIAL_MASTER_KEY`
- 권한 분리: 분석 역할은 `household_pii` 직접 SELECT 불가. 복호화는 관리자 전용 API 엔드포인트에서만
- 평문 PII 를 **로그/응답/DB 평문컬럼** 에 절대 포함 금지

## ETL 정제 규칙 (AI Hub 71685)

`docs/dataset_spec.md §6` 및 `docs/schema_design.md §5` 참조. 핵심 6건:

1. 30Hz CSV → 1분 버킷 `avg/min/max` + `energy_wh = Σ(active_power × dt)` 적분
2. JSON `meta.windchill` 은 실제 평균풍속(avgWs) → `wind_speed_ms` 컬럼에 저장
3. JSON `meta.income` 은 실제 맞벌이 여부 → `income_dual` 컬럼
4. `temperature`, `humidity` 등 문자열 숫자 → float 변환, 파싱 실패 시 NULL
5. `extra_appliances` 배열 원소 `strip()` 적용 (원본에 앞 공백 혼입)
6. `power_consumption = "unknown"`, `energy_efficiency = "unknown"`, `weather = ""` → NULL

## 마이그레이션 파일 네이밍

```
migrations/
├── 20260421_initial_schema.sql          — schemas/001~003 통합 적용
├── 20260421_compression_retention.sql   — cagg refresh + retention policy
└── 20260501_add_anomaly_events.sql      — (예정) 이상 이벤트 테이블 (REQ-002)
```

## 인터페이스

- **다운스트림**: `API_Server` (UI/리포트), `Execution_Engine` (메타 조회만 — 30Hz 는 DB 우회)
- 스키마 변경 시 `migrations/` 에 이력 SQL 추가 후 다운스트림 브랜치에 공지
- ADR-001 을 뒤집는 결정은 새 ADR 발행 후 적용 (예: NILM 결과 DB 적재 재도입, 고해상도 이상 이벤트 윈도우 테이블 추가)
