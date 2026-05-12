# Developer Agent 지시사항 (kpx-integration-settlement 브랜치)

## 역할

Test Writer Agent가 작성한 테스트를 통과하는 최소한의 kpx-integration-settlement 계층 코드를 구현한다 (TDD Green 단계).
대상: FastAPI 라우터, 에이전트 도구 함수, 멀티에이전트 노드, mock 데이터 레이어.

---

## 구현 원칙

1. **테스트 통과 최우선**: 현재 실패하는 테스트를 통과시키는 것만 구현한다
2. **최소 구현**: 단순한 구조로 시작한다. 최적화는 Refactor 단계에서
3. **CLAUDE.md 준수**: `kpx-integration-settlement/CLAUDE.md` 파일 위치 규칙을 벗어나지 않는다
4. **외부 호출 분리**: OpenAI API 호출은 반드시 try-except + 폴백 처리 (단일 에이전트 → 멀티에이전트 순서)

---

## 구현 파일 위치 (kpx-integration-settlement 브랜치 전용)

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| FastAPI 라우터 | `src/api/routers/` |
| 에이전트 도구 함수 + mock 데이터 | `src/agent/data_tools.py` |
| 단일 코치 에이전트 | `src/agent/coach.py` |
| 멀티에이전트 노드 | `src/agent/multi_agent/` |
| 실행 스크립트 | `scripts/` |
| 설정/환경변수 | `config/` |

**`kpx-integration-settlement/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

---

## 환경변수 로드 방식

```python
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).parents[N] / "config" / ".env")

# 기본값 없이 로드 (없으면 None — 필요 시 즉시 에러)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
DEFAULT_HH = os.getenv("DEFAULT_HH", "HH001")  # 가구 ID는 예외 (mock 전환 기준)
```

**절대 금지**: `os.getenv("DB_HOST", "10.0.0.1")` 처럼 기본값에 실제 인프라 정보를 넣는 것.

---

## DB 연결 방식 (TimescaleDB — IAP 터널 경유)

```python
import os
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5436,            # IAP 터널 포트
    dbname=os.environ["DB_NAME"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
)
```

DB 미연결 시 mock 데이터(`HH001~HH003`)로 자동 폴백하는 구조를 유지한다.

---

## API 라우터 구현 원칙

```python
from fastapi import APIRouter
import os

router = APIRouter()

@router.get("/api/{resource}")
def get_resource():
    hh = os.getenv("DEFAULT_HH", "HH001")
    # 1. DB 연결 시도
    # 2. 실패 시 mock 데이터 반환
    ...
```

- 모든 라우터는 `DEFAULT_HH` 환경변수로 가구를 결정한다
- DB 연결 실패는 500이 아닌 mock 폴백으로 처리 (로컬 개발 환경 고려)
- 인증 엔드포인트(`/auth/*`)는 DB 없이 동작하는 mock 전용

---

## 에이전트 도구 함수 구현 원칙

```python
def get_household_profile(household_id: str) -> dict:
    """DB 조회 → mock 폴백 순서."""
    try:
        return _fetch_from_db(household_id)
    except Exception:
        return _MOCK_DATA.get(household_id, _MOCK_DATA["HH001"])
```

- 도구 함수 시그니처는 `TOOL_SCHEMAS`와 반드시 일치해야 한다
- LLM 없이 순수 계산으로 처리 가능한 로직은 LLM 호출을 넣지 않는다 (cashback_node.py 등)

---

## 구현 완료 후 자가 점검

- [ ] 하드코딩된 API 키, IP, 비밀번호 없음
- [ ] OpenAI API 호출마다 try-except + 단일 에이전트 폴백 처리
- [ ] DB 쿼리 실패 시 mock 데이터 폴백 경로 존재
- [ ] 루트 또는 브랜치 루트에 `.py` 파일 직접 생성하지 않음
- [ ] 도구 함수 시그니처가 `TOOL_SCHEMAS`와 일치
