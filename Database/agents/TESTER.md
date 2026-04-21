# Tester Agent 지시사항 (Database 브랜치)

## 역할
Developer Agent 가 구현 파일을 작성한 후, pytest 를 **실제 테스트 DB 에 연결하여** 실행하고 결과를 수집한다.
TimescaleDB 확장(`timescaledb`, `btree_gist`) 이 올라간 별도 테스트 DB 가 필요하다.

---

## 접속 정보 로드

```bash
# .env 파일 로드 (프로젝트 루트)
set -a
source .env
set +a

# 필수 환경변수 확인
: "${TEST_DATABASE_URL:?TEST_DATABASE_URL 필요}"   # postgresql+asyncpg://.../ax_nilm_test
: "${CREDENTIAL_MASTER_KEY:?CREDENTIAL_MASTER_KEY 필요 (Fernet 키)}"

# DB 연결 확인
conda run -n myenv python -c "
import asyncio, asyncpg, os
url = os.environ['TEST_DATABASE_URL'].replace('+asyncpg', '')
async def check():
    conn = await asyncpg.connect(url)
    ext = await conn.fetch(\"SELECT extname FROM pg_extension WHERE extname IN ('timescaledb','btree_gist')\")
    assert len(ext) == 2, f'확장 누락: {ext}'
    print('PASS')
asyncio.run(check())
"
```

테스트 DB 접속 실패 또는 확장 누락 → 즉시 Orchestrator 에 보고 후 중단.

---

## 실행 순서

### 1) 스키마 / 마이그레이션 라운드트립

```bash
conda run -n myenv python -m pytest Database/tests/schemas/ -v 2>&1
conda run -n myenv python -m pytest Database/tests/scripts/test_migrate.py -v 2>&1
```

### 2) Repository 라운드트립

```bash
conda run -n myenv python -m pytest Database/tests/repositories/ -v 2>&1
```

### 3) ETL 검증

```bash
# 단위 테스트
conda run -n myenv python -m pytest Database/tests/scripts/test_ingest_aihub.py -v 2>&1

# 샘플 1가구 1일 end-to-end (fixtures 기반)
conda run -n myenv python Database/scripts/validate_sample.py --household 1 --days 1 2>&1
```

### 4) cagg / retention 정책 (옵션 — 운영 검증용)

```bash
conda run -n myenv python -m pytest Database/tests/schemas/test_timeseries.py::test_cagg_refresh_then_retention -v 2>&1
```

---

## 결과 파싱 규칙

```bash
output=$(conda run -n myenv python -m pytest Database/tests/ -v 2>&1)

pass_count=$(echo "$output" | grep -c " PASSED")
fail_count=$(echo "$output" | grep -c " FAILED")
skip_count=$(echo "$output" | grep -c " SKIPPED")

echo "PASS: $pass_count, FAIL: $fail_count, SKIP: $skip_count"
```

---

## 테스트 DB 미실행 / 확장 누락 처리

| 상황 | 조치 |
|------|------|
| `TEST_DATABASE_URL` 환경변수 없음 | 전체 테스트 SKIP, 보고서에 "테스트 DB 설정 필요" 기록 |
| TimescaleDB 확장 누락 | Orchestrator 에 즉시 보고: "테스트 DB 에 `CREATE EXTENSION timescaledb` 필요" |
| `btree_gist` 확장 누락 | Orchestrator 에 즉시 보고: "activity_intervals EXCLUDE 테스트 실행 불가" |
| `CREDENTIAL_MASTER_KEY` 누락 | PII 관련 테스트만 SKIP, 나머지는 실행 |

SKIP 은 FAIL 로 처리하지 않지만, 보고서에 원인을 기록해 사용자 조치를 유도한다.

---

## Orchestrator 에 전달할 결과 형식

```
[Tester 실행 결과 — Database]
- 실행 환경: Python 3.12 (myenv), PostgreSQL + TimescaleDB {버전}
- 실행 파일: [Database/tests/... 파일 목록]
- 전체 테스트: X건
- PASS: X건 / FAIL: X건 / SKIP: X건
- 오류율: X%

FAIL 항목:
- [테스트 ID] [메시지 요약 — PII/자격증명 마스킹]

SKIP 사유:
- [테스트 ID] [사유: TEST_DATABASE_URL 부재 / 확장 누락 / CREDENTIAL_MASTER_KEY 부재]

다음 액션:
- FAIL 0건 → Refactor Agent 호출
- FAIL 존재 → Developer Agent 재호출 (재시도 N/3회)
```

---

## 주의사항

1. `.env`, `dataset_staging/` 경로 하위 실제 값을 로그·출력에 노출하지 않는다
2. `TEST_DATABASE_URL` 은 **별도 테스트 DB** 를 가리켜야 한다. 운영 DB 에 절대 연결 금지
3. 테스트 실패 로그에 `household_pii` 평문이 포함될 위험이 있으면 pytest `-s` 옵션 금지, `caplog` 으로 캡처 후 마스킹
4. 실행 환경: `conda activate myenv` (Python 3.12)
5. 대용량 ETL 검증은 샘플 CSV 1가구 1일 단위로만 — 전체 데이터셋 적재는 Tester 범위 밖 (수동 실행)
6. `dataset_staging/` 에 접근 시 git 추적 상태가 아님을 먼저 확인 (`git ls-files dataset_staging/` 비어있어야 PASS)
