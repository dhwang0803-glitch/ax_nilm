# Test Writer Agent 지시사항 (Database 브랜치)

## 역할

Database 계층 구현 전에 실패하는 테스트를 먼저 작성한다 (TDD Red 단계).
구현 후에는 테스트를 실행하고 결과를 수집한다 (검증 단계).

대상: 스키마 DDL, Repository 구현체, ETL 스크립트, 마이그레이션, 운영 정책(cagg / retention).

---

## 테스트 작성 원칙

1. 구현 코드 / DDL 이 없어도 테스트를 먼저 작성한다
2. 각 테스트는 하나의 요구사항만 검증한다 (스키마 검증 / round-trip / 경계 조건)
3. 기대값 (행수, 집계값, 제약 위반 예외) 을 명확하게 명시한다
4. 테스트 실패 시 원인을 파악할 수 있는 메시지를 포함한다
5. **실제 테스트 DB 에 연결**한다. 인메모리 SQLite 금지 (TimescaleDB 고유 기능 검증 불가)
6. PII 관련 테스트는 **합성 데이터만** 사용한다. 실제 AI Hub 샘플 복사 금지

---

## 테스트 파일 위치

```
Database/tests/
├── conftest.py                    ← test_db_url fixture, 각 테스트별 격리 스키마
├── schemas/
│   ├── test_core_tables.py        ← households, appliance_types, household_channels
│   ├── test_timeseries.py         ← power_1min hypertable, power_1hour cagg
│   └── test_activity_intervals.py ← EXCLUDE gist 제약
├── repositories/
│   ├── test_power_repository.py
│   ├── test_household_repository.py
│   ├── test_pii_repository.py
│   ├── test_activity_repository.py
│   └── test_ingestion_log_repository.py
├── scripts/
│   ├── test_ingest_aihub.py       ← 30Hz → 1분 집계 정확성
│   └── test_migrate.py            ← up/down 라운드트립
└── reports/                       ← Reporter Agent 산출물
```

---

## 테스트 DB 준비

```python
# conftest.py
import pytest
import os
from sqlalchemy.ext.asyncio import create_async_engine

@pytest.fixture(scope="session")
def test_db_url():
    return os.environ['TEST_DATABASE_URL']   # 별도 테스트 DB, 없으면 테스트 전체 skip

@pytest.fixture
async def clean_engine(test_db_url):
    engine = create_async_engine(test_db_url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb;"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist;"))
    yield engine
    await engine.dispose()
```

---

## 테스트 작성 예시

### 스키마 / hypertable 검증

```python
import pytest
from sqlalchemy import text

@pytest.mark.asyncio
async def test_power_1min_is_hypertable(clean_engine, apply_schemas):
    """power_1min 이 chunk_time_interval=7d 하이퍼테이블로 생성된다."""
    async with clean_engine.begin() as conn:
        rows = await conn.execute(text("""
            SELECT chunk_time_interval
            FROM timescaledb_information.dimensions
            WHERE hypertable_name = 'power_1min'
              AND column_name = 'bucket_ts'
        """))
        interval = rows.scalar_one()
    assert interval == "7 days"
```

### Activity interval EXCLUDE 제약

```python
@pytest.mark.asyncio
async def test_activity_intervals_exclude_overlap(repo):
    """같은 household × channel 에서 tstzrange 가 겹치는 삽입은 거부된다."""
    await repo.insert(household_id=1, channel_num=2, start_ts="2025-01-01 10:00",
                      end_ts="2025-01-01 11:00", appliance_code="TV")
    with pytest.raises(IntegrityError, match="exclude"):
        await repo.insert(household_id=1, channel_num=2, start_ts="2025-01-01 10:30",
                          end_ts="2025-01-01 11:30", appliance_code="TV")
```

### Repository round-trip

```python
@pytest.mark.asyncio
async def test_power_repository_read_range_7d_boundary(repo):
    """7일 경계에서 power_1min 과 power_1hour 가 연속으로 읽힌다."""
    # 1) 10일치 샘플 데이터 준비 (1분 해상도)
    await _seed_minute_data(repo, days=10)
    await repo.refresh_cagg()

    # 2) 7일 전 00:00 ~ 현재 조회
    rows = await repo.read_range(household_id=1, channel_num=2,
                                 start="now() - interval '10 days'", end="now()")
    # 3) 7일 경계 기준 두 해상도가 혼합되어 반환
    assert any(r.resolution == "1min" for r in rows)
    assert any(r.resolution == "1day" for r in rows)
```

### PII 암호화 라운드트립

```python
@pytest.mark.asyncio
async def test_pii_encrypt_decrypt_roundtrip(pii_repo, monkeypatch):
    """Fernet 암호화된 주소가 복호화 후 원문과 일치한다."""
    monkeypatch.setenv("CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode())
    original = "테스트_주소_더미"              # 합성 데이터
    await pii_repo.save(household_id=1, address=original, members=3, income_dual=True)
    loaded = await pii_repo.get_decrypted(household_id=1)
    assert loaded.address == original
    assert loaded.income_dual is True
```

### ETL 검증 (30Hz → 1분 집계)

```python
@pytest.mark.asyncio
async def test_ingest_aihub_sample_minute_aggregation(clean_engine, apply_schemas):
    """샘플 CSV 1시간(108000 샘플) → power_1min 60행, avg/min/max/energy_wh 검증."""
    sample_csv = Path("Database/tests/fixtures/sample_1h_30hz.csv")
    await ingest_aihub(csv_path=sample_csv, household_id=1, channel_num=2)
    async with clean_engine.begin() as conn:
        rows = await conn.execute(text(
            "SELECT COUNT(*), SUM(energy_wh) FROM power_1min "
            "WHERE household_id=1 AND channel_num=2"
        ))
        count, energy_total = rows.one()
    assert count == 60
    assert energy_total == pytest.approx(expected_total_wh, rel=0.01)
```

### ETL 정제 규칙 단위 테스트

```python
@pytest.mark.parametrize("raw,expected", [
    ("unknown", None),
    ("", None),
    ("3.14", 3.14),
    ("  IND001  ", "IND001"),      # extra_appliances strip()
])
def test_clean_field(raw, expected):
    assert _clean_optional(raw) == expected
```

---

## 필수 테스트 카테고리

### 스키마 (`schemas/`)
- hypertable 생성 + chunk_time_interval / partitioning_column 설정
- continuous aggregate 정의 확인
- NOT NULL / CHECK / UNIQUE / EXCLUDE gist 제약 위반 시 예외
- 인덱스 존재 여부 (`idx_power_1min_recent`, `idx_activity_intervals_lookup` 등)

### Repository
- 각 Repository 의 save / retrieve / filter 라운드트립
- `PowerRepository.read_range()` 7일 경계에서 1min ↔ 1day 라우팅
- `PIIRepository` encrypt/decrypt 대칭성, 키 누락 시 에러
- `IngestionLogRepository` source_file UNIQUE 멱등 재시도
- `ActivityRepository` 겹침 차단 예외 발생

### ETL
- 샘플 CSV 1가구 1시간 → 행수(60) / energy_wh 합계 검증
- 정제 규칙 6건 (dataset_spec.md §6) 각각 parametrize 단위 테스트
- `meta.windchill` → `wind_speed_ms`, `meta.income` → `income_dual` 매핑 검증
- 재실행 시 `ingestion_log.source_file` UNIQUE 로 중복 적재 방지

### 마이그레이션 / 운영 정책
- `migrate-up` → `migrate-down` 라운드트립으로 스키마 원복
- cagg refresh policy 적용 후 과거 구간 요약 확인
- retention policy 적용 후 7일 초과 chunk 드롭 확인 (단, cagg 리프레시 이후 순서 유지)

---

## 테스트 결과 수집 형식

```
전체 테스트: X건
PASS: X건
FAIL: X건
SKIP: X건  (TEST_DATABASE_URL 부재 시 skip 정상)

FAIL 목록:
- [테스트 ID]: [실패 메시지 요약 — 실제 PII 값·자격증명은 포함 금지]
```
