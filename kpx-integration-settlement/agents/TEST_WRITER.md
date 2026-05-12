# Test Writer Agent 지시사항 (kpx-integration-settlement 브랜치)

## 역할

구현 전에 실패하는 테스트를 먼저 작성한다 (TDD Red 단계).
대상: FastAPI 라우터, 에이전트 도구 함수(data_tools.py), 멀티에이전트 노드.

---

## 테스트 파일 위치

```
kpx-integration-settlement/tests/
```

| 테스트 파일 | 대상 |
|------------|------|
| `tests/test_data_tools.py` | 8개 도구 함수 schema + mock 폴백 |
| `tests/test_routers.py` | FastAPI 라우터 4종 (dashboard/usage/settings/cashback) |
| `tests/test_coach.py` | 단일 코치 에이전트 run_coach() |
| `tests/test_multi_agent.py` | 멀티에이전트 run_multi_agent() + 노드별 단위 |
| `tests/test_insights.py` | /api/insights/summary 폴백 로직 |

---

## 테스트 작성 원칙

1. 구현 코드가 없어도 테스트를 먼저 작성한다
2. 각 테스트는 하나의 요구사항만 검증한다
3. 외부 호출(OpenAI API, TimescaleDB)은 반드시 Mock/patch로 격리한다
4. DB 미연결 상태에서도 mock 폴백 경로를 테스트할 수 있어야 한다

---

## 테스트 작성 예시

### 도구 함수 schema 검증 (test_data_tools.py)

```python
import pytest
from src.agent.data_tools import TOOL_SCHEMAS, get_household_profile

def test_tool_schemas_count():
    """TOOL_SCHEMAS에 8개 도구가 정의되어 있어야 한다"""
    assert len(TOOL_SCHEMAS) == 8

def test_get_household_profile_mock_fallback():
    """DB 미연결 시 HH001 mock 데이터를 반환해야 한다"""
    result = get_household_profile("HH001")
    assert "summary" in result
    assert result["household_id"] == "HH001"

def test_get_household_profile_unknown_id():
    """알 수 없는 ID는 HH001 기본값으로 폴백해야 한다"""
    result = get_household_profile("UNKNOWN_99")
    assert result["household_id"] == "HH001"
```

### FastAPI 라우터 테스트 (test_routers.py)

```python
import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_dashboard_summary_returns_200():
    """GET /api/dashboard/summary는 200과 JSON을 반환해야 한다"""
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    data = response.json()
    assert "household_id" in data

def test_cashback_tracker_mock():
    """DB 미연결 시에도 /api/cashback/tracker는 mock 데이터를 반환해야 한다"""
    response = client.get("/api/cashback/tracker")
    assert response.status_code == 200
    assert "cashback" in response.json() or "status" in response.json()

def test_auth_login_wrong_credentials():
    """잘못된 자격증명은 401을 반환해야 한다"""
    response = client.post("/auth/login", json={"email": "x@x.com", "password": "wrong"})
    assert response.status_code == 401
```

### 멀티에이전트 노드 단위 테스트 (test_multi_agent.py)

```python
import pytest
from unittest.mock import patch

def test_cashback_node_pure_calculation():
    """cashback_node는 LLM 없이 순수 계산으로 캐시백을 산정해야 한다"""
    from src.agent.multi_agent.cashback_node import run_cashback_node
    state = {
        "household_id": "HH001",
        "baseline_kwh": 300.0,
        "current_kwh": 270.0,
    }
    result = run_cashback_node(state)
    assert "savings_rate" in result
    assert result["savings_rate"] == pytest.approx(0.1, rel=1e-3)

def test_run_multi_agent_llm_error_fallback():
    """OpenAI API 오류 시 단일 에이전트(run_insights)로 폴백해야 한다"""
    with patch("src.agent.multi_agent.supervisor.run_multi_agent_internal",
               side_effect=Exception("OpenAI unavailable")):
        from src.api.routers.insights import get_insights_summary
        result = get_insights_summary("HH001")
        assert result is not None
```

---

## 필수 테스트 카테고리

### 도구 함수 (data_tools.py)
- 8개 도구 TOOL_SCHEMAS 구조 검증 (name, description, parameters 키 존재)
- 각 도구 함수의 mock 폴백 동작 (HH001~HH003 데이터 반환)
- 알 수 없는 household_id 전달 시 HH001 기본값 반환

### FastAPI 라우터
- GET /api/dashboard/summary — 200 + household_id 포함 JSON
- GET /api/usage/analysis — 200
- GET /api/settings/account — 200
- GET /api/cashback/tracker — 200 (DB 미연결 시 mock)
- POST /auth/login — 401 (잘못된 자격증명), 200 (정상)
- POST /auth/signup — 422 (이미 존재하는 이메일), 201 (정상)

### 멀티에이전트 (multi_agent/)
- cashback_node: 순수 계산 검증 (LLM 없음)
- nilm_monitor: 5개 도구 호출 구조화 검증
- report_agent: LLM 오류 시 예외 처리 확인
- run_multi_agent: OpenAI 오류 시 run_insights 폴백

### 코치 에이전트 (coach.py)
- run_coach()가 문자열 응답을 반환해야 한다
- OpenAI API 오류 시 폴백 메시지 반환 확인

---

## 테스트 결과 수집 형식

```
전체 테스트: X건
PASS: X건
FAIL: X건
SKIP: X건

FAIL 목록:
- [테스트 ID]: [실패 메시지]
```
