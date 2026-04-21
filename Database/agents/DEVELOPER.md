# Developer Agent 지시사항 (Database 브랜치)

## 역할

Test Writer Agent가 작성한 테스트를 통과하는 최소한의 Database 계층 코드를 구현한다 (TDD Green 단계).
대상: SQLAlchemy ORM 모델, Repository 구현체, ETL 스크립트, 마이그레이션 SQL.

---

## 구현 원칙

1. **테스트 통과 최우선**: 현재 실패하는 테스트를 통과시키는 것만 구현한다
2. **최소 구현**: 단순한 SQL/쿼리로 시작한다. 최적화는 Refactor 단계에서
3. **CLAUDE.md 준수**: `Database/CLAUDE.md` 파일 위치 규칙·저장 정책(ADR-001)을 벗어나지 않는다
4. **Repository 인터페이스 보존**: `API_Server`, `Execution_Engine` 가 의존하는 ABC 시그니처는 변경 금지 (필요 시 새 메서드 추가)

---

## 구현 파일 위치 (Database 브랜치 전용)

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| `CREATE TABLE`, `CREATE INDEX`, `CREATE MATERIALIZED VIEW` | `schemas/` |
| `ALTER TABLE`, cagg 리프레시 정책, retention 정책 | `migrations/YYYYMMDD_*.sql` |
| Repository 구현 (import 전용) | `src/repositories/` |
| SQLAlchemy ORM 모델 | `src/models/` |
| ETL·검증 실행 스크립트 (ingest_aihub, migrate, validate_sample) | `scripts/` |
| pytest | `tests/` |

**`Database/` 루트 또는 프로젝트 루트에 `.py`/`.sql` 파일 직접 생성 금지.**

---

## 환경변수 로드 방식

```python
from dotenv import load_dotenv
import os

load_dotenv('.env')  # 프로젝트 루트의 .env

DATABASE_URL = os.environ['DATABASE_URL']        # asyncpg 드라이버 URL
CREDENTIAL_MASTER_KEY = os.environ['CREDENTIAL_MASTER_KEY']  # Fernet AES-256 키
```

**절대 금지**: `os.getenv("DB_HOST", "10.0.0.1")` 처럼 기본값에 실제 IP/DB명/사용자명을 넣는 것.
허용 기본값: `"localhost"`, `"5432"`, `"postgres"`, `""`

---

## DB 연결 방식 (비동기)

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
import os

engine = create_async_engine(
    os.environ['DATABASE_URL'],         # postgresql+asyncpg://...
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

TimescaleDB 확장은 마이그레이션에서만 로드 (`CREATE EXTENSION IF NOT EXISTS timescaledb;`).

---

## DB 접근 코드 작성 원칙 (MANDATORY — 네트워크 I/O 최소화)

> 1분 집계 적재는 가구 × 채널 × 분 단위로 수십만 행/일 규모.
> 루프 안에 DB 왕복을 두면 ETL 이 파이프라인 밖에서 초과 시간을 잡아먹는다.
> **코드 작성 전 반드시 DB 왕복 수를 계획하고 주석으로 명시한다.**

### 금지 패턴 — N+1 / 행별 INSERT

```python
# 절대 금지: 가구별 루프로 개별 INSERT
for (household_id, channel_num, bucket_ts, values) in minute_rows:
    await session.execute(
        insert(PowerOneMin).values(household_id=household_id, ...)
    )
```

### 올바른 패턴 — 배치 조회 + 배치 INSERT (COPY 또는 executemany)

```python
# DB 왕복 계획:
#   SELECT households  1회
#   SELECT channels    1회
#   INSERT power_1min  N회 (N = ceil(행수 / batch_size))

# 1) 메타 조회는 한 번에
channels = await session.execute(
    select(HouseholdChannel).where(
        HouseholdChannel.household_id.in_(household_ids)
    )
)

# 2) 순수 Python 집계 (DB 왕복 없음)
rows = aggregate_to_minute_buckets(csv_stream, channel_map)

# 3) 배치 INSERT (5000~10000 행 단위)
for chunk in chunked(rows, size=5000):
    await session.execute(insert(PowerOneMin), chunk)
await session.commit()
```

대용량 적재는 `asyncpg.copy_records_to_table()` 이 `INSERT ... VALUES` 보다 10배 이상 빠르다.
Continuous aggregate 리프레시 직후의 retention 순서는 운영 정책이므로 코드가 아닌 `migrations/` 에서 처리한다.

### 설계 판단 기준

| 총 DB 왕복 수 | 판단 | 조치 |
|--------------|------|------|
| ~50회 이하 | ✅ 양호 | 그대로 구현 |
| 50~500회 | ⚠️ 주의 | 배치 통합 검토 |
| 500회 초과 | ❌ 재설계 | 루프 안 쿼리 제거 필수 / COPY 전환 |

---

## 시계열 쿼리 작성 원칙

1. `power_1min` / `power_1day` 조회 시 항상 `(household_id, channel_num, bucket_ts)` 파티셔닝 키를 WHERE 절 앞쪽에 둔다 — TimescaleDB chunk pruning 활성화 조건
2. 최근 7일 이내는 `power_1min`, 그 이전은 `power_1day` 에서 읽도록 Repository 내부에서 분기 — `PowerRepository.read_range(start, end)` 가 자동 라우팅
3. 전 기간 UNION 뷰가 필요하면 `schemas/` 에 `power_combined` 뷰로 별도 정의 (라우팅은 애플리케이션이 아닌 DB 에 위임 가능)
4. `activity_intervals` 조회는 `tstzrange && tstzrange('[start,end)')` GiST 인덱스를 타도록 작성

---

## PII 취급 규칙 (MANDATORY — REQ-007)

- `household_pii` 테이블 직접 SELECT 금지 — 반드시 `PIIRepository` 경유
- 복호화는 `Fernet(CREDENTIAL_MASTER_KEY).decrypt(address_enc)` 에서만 수행, 결과는 **절대 로그/응답/평문 컬럼**에 남기지 않음
- Repository 반환 타입은 복호화 여부를 타입에 명시 (`HouseholdPIIEncrypted` vs `HouseholdPIIDecrypted`)

---

## ETL 구현 시 주의 (AI Hub 71685)

`Database/docs/dataset_spec.md §6` 의 정제 규칙 6건을 반드시 먼저 읽고 구현한다. 대표 함정:

- JSON `meta.windchill` 은 실제 평균풍속(avgWs) → `wind_speed_ms` 컬럼
- JSON `meta.income` 은 실제 맞벌이 여부 → `income_dual` 컬럼 (PII)
- `extra_appliances` 배열은 각 원소 `strip()` 필요 (앞 공백 혼입)
- `power_consumption = "unknown"`, `energy_efficiency = "unknown"`, `weather = ""` → NULL
- `energy_wh = Σ(active_power × dt)` 적분은 30Hz 샘플 간격 이 불균등할 수 있으므로 시간차를 실제로 측정

---

## 구현 완료 후 자가 점검

- [ ] 하드코딩된 API 키, IP, 비밀번호 없음 (`CREDENTIAL_MASTER_KEY` 기본값 없음)
- [ ] 외부 API 호출 없음 (Database 브랜치는 HTTP 호출 부재 확인)
- [ ] 루프 안에 DB 쿼리 없음 (N+1 없음)
- [ ] `household_pii` 직접 접근 코드 없음 (Repository 경유)
- [ ] 30Hz raw 데이터를 DB 에 적재하지 않음 (ADR-001 준수)
- [ ] NILM 엔진 분해 결과를 DB 에 적재하지 않음 (ADR-001 준수)
- [ ] 마이그레이션 SQL 은 `schemas/` 가 아닌 `migrations/YYYYMMDD_*.sql` 에 기록
- [ ] `ingestion_log.source_file` UNIQUE 제약 위반 시 멱등 재시도 경로 확보
