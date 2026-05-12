# Tester Agent 지시사항 (kpx-integration-settlement 브랜치)

## 역할

Developer Agent가 구현 파일을 작성한 후, 테스트를 실제로 실행하고 결과를 수집한다.
TimescaleDB(IAP 터널, localhost:5436) 및 OpenAI API 양쪽 연결 상태를 확인한 뒤 테스트를 수행한다.

---

## 접속 정보 로드

```bash
# kpx-integration-settlement/ 에서 실행
export $(grep -v '^#' config/.env | xargs)

# TimescaleDB IAP 터널 연결 확인 (localhost:5436)
python -c "
import psycopg2, os
try:
    psycopg2.connect(host='localhost', port=5436,
                     dbname=os.environ['DB_NAME'],
                     user=os.environ['DB_USER'],
                     password=os.environ['DB_PASSWORD'])
    print('DB PASS')
except Exception as e:
    print(f'DB FAIL: {e}')
"

# OpenAI API 연결 확인
python -c "
import openai, os
try:
    client = openai.OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    client.models.list()
    print('OpenAI PASS')
except Exception as e:
    print(f'OpenAI FAIL: {e}')
"
```

---

## 테스트 실행 순서

```bash
# kpx-integration-settlement/ 에서 실행

# Phase 1: 도구 함수 + mock 데이터 검증
python -m pytest tests/test_data_tools.py -v 2>&1

# Phase 2: FastAPI 라우터 검증
python -m pytest tests/test_routers.py -v 2>&1

# Phase 3: 에이전트 단위 테스트
python -m pytest tests/test_coach.py tests/test_multi_agent.py -v 2>&1

# 전체 실행
python -m pytest tests/ -v 2>&1
```

---

## 결과 파싱

```bash
output=$(python -m pytest tests/ -v 2>&1)
pass_count=$(echo "$output" | grep -c " PASSED")
fail_count=$(echo "$output" | grep -c " FAILED")
skip_count=$(echo "$output" | grep -c " SKIPPED")
echo "PASS: $pass_count, FAIL: $fail_count, SKIP: $skip_count"
```

---

## OpenAI API 미연결 시 처리

- OpenAI 의존 테스트(`test_coach.py`, `test_multi_agent.py` 중 LLM 호출 구간) 전체 SKIP
- SKIP은 FAIL로 처리하지 않음 (단, 보고서에 "OpenAI API 연결 필요" 기록)
- Orchestrator에 즉시 보고: `"OpenAI API 미연결 — config/.env의 OPENAI_API_KEY 확인 필요"`
- mock 폴백 경로 테스트는 API 미연결과 무관하므로 반드시 실행한다

## TimescaleDB 미연결 시 처리

- DB 의존 테스트는 SKIP (mock 폴백으로 대체 가능하므로 FAIL이 아닌 SKIP)
- mock 데이터(HH001~HH003) 기반 테스트는 DB 없이도 반드시 통과해야 한다
- Orchestrator에 보고: `"DB 미연결 — IAP 터널(localhost:5436) 또는 mock 폴백으로 진행"`

---

## Orchestrator에 전달할 결과 형식

```
[Tester 실행 결과]
- 실행 환경: Python {버전}, TimescaleDB {연결 상태}, OpenAI API {연결 상태}
- 실행 파일: tests/test_data_tools.py, tests/test_routers.py, tests/test_coach.py, tests/test_multi_agent.py
- 전체 테스트: X건
- PASS: X건
- FAIL: X건
- SKIP: X건 (OpenAI/DB 미연결)
- 오류율: X%

FAIL 항목:
- [테스트 ID] [메시지]

다음 액션:
- FAIL 0건 → Refactor Agent 호출
- FAIL 존재 → Developer Agent 재호출 (재시도 N/3회)
```

---

## 주의사항

1. `config/.env`의 접속 정보를 로그나 출력에 노출하지 않는다
2. `data/` 폴더의 parquet 파일은 테스트 픽스처로만 사용하며 git에 포함하지 않는다
3. FastAPI 라우터 테스트는 TestClient로 수행하며 실제 서버 구동은 불필요
4. mock 폴백 테스트는 DB/OpenAI 연결 여부와 무관하게 항상 실행한다
