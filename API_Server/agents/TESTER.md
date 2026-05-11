# Tester Agent 지시사항

## 역할
Developer Agent가 구현 파일을 작성한 후, 테스트를 실제로 실행하고 결과를 수집한다.
TimescaleDB/PostgreSQL 및 외부 LLM API 양쪽 모두 접속하여 통합 테스트를 수행한다.

---

## 접속 정보 로드

```bash
# DB 및 API 접속 정보 (.env 파일)
export $(grep -v '^#' .env | xargs)

# LLM API 키 (브랜치/config/api_keys.env)
export $(grep -v '^#' config/api_keys.env | xargs)

# TimescaleDB 연결 확인
python -c "import psycopg2; psycopg2.connect(dsn='$DATABASE_URL'); print('PASS')"

# LLM API 연결 확인 (kpx-integration-settlement RAG 모듈)
python -c "import openai; openai.api_key='$OPENAI_API_KEY'; print('PASS')"
```

---

## 브랜치별 실행 순서

### kpx-integration-settlement

```bash
# Phase 1: KPX API 수신 테스트
python -m pytest kpx-integration-settlement/tests/test_phase1_kpx_api.py -v 2>&1

# Phase 2: 절감량 산출 + 정산 데이터 생성 테스트
python -m pytest kpx-integration-settlement/tests/test_phase2_settlement.py -v 2>&1

# Phase 3: RAG LLM 보고서 생성 테스트
python -m pytest kpx-integration-settlement/tests/test_phase3_rag.py -v 2>&1
```

### nilm-engine

```bash
# 신호처리 + 가전 분해 테스트
python -m pytest nilm-engine/tests/ -v 2>&1
```

### anomaly-detection

```bash
python -m pytest anomaly-detection/tests/ -v 2>&1
```

### dr-savings-prediction

```bash
python -m pytest dr-savings-prediction/tests/ -v 2>&1
```

### Database

```bash
# 스키마 마이그레이션 + Repository 테스트
python -m pytest Database/tests/ -v 2>&1
```

---

## 결과 파싱 규칙

```bash
output=$(python -m pytest {테스트 파일} -v 2>&1)

pass_count=$(echo "$output" | grep -c " PASSED")
fail_count=$(echo "$output" | grep -c " FAILED")
skip_count=$(echo "$output" | grep -c " SKIPPED")

echo "PASS: $pass_count, FAIL: $fail_count, SKIP: $skip_count"
```

---

## LLM API 미연결 시 처리

LLM API(OpenAI 등) 호출 불가 상태이면:
- LLM 의존 테스트 전체 SKIP
- SKIP은 FAIL로 처리하지 않음 (단, 보고서에 "LLM API 연결 필요" 기록)
- Orchestrator에 즉시 보고: "LLM API 미연결 — `.env`의 OPENAI_API_KEY 확인 필요"

## TimescaleDB 미연결 시 처리

- DB 의존 테스트 전체 FAIL 처리 (데이터 없이 진행 불가)
- Orchestrator에 즉시 보고 후 중단

---

## Orchestrator에 전달할 결과 형식

```
[Tester 실행 결과]
- 실행 환경: Python {버전}, TimescaleDB {연결 상태}, LLM API {연결 상태}
- 실행 파일: [파일명 목록]
- 전체 테스트: X건
- PASS: X건
- FAIL: X건
- SKIP: X건
- 오류율: X%

FAIL 항목:
- [테스트 ID] [메시지]

다음 액션:
- FAIL 0건 → Refactor Agent 호출
- FAIL 존재 → Developer Agent 재호출 (재시도 N/3회)
```

---

## 주의사항

1. `.env` 및 `api_keys.env`의 접속 정보를 로그나 출력에 노출하지 않는다
2. 전력 소비 데이터(parquet)는 테스트 픽스처로만 사용하며 git에 포함하지 않는다
3. TimescaleDB 연결 실패 시 재시도 없이 즉시 Orchestrator에 보고한다
4. KPX API 테스트는 실제 전력거래소 연결이 아닌 Mock 서버로 수행한다
