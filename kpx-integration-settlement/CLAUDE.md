# kpx-integration-settlement

> 이 파일은 [`_claude_templates/CLAUDE_kpx-integration-settlement.md`](../_claude_templates/CLAUDE_kpx-integration-settlement.md)를 실제 작업 디렉토리에 적용한 것입니다.
> 세부 규칙은 템플릿 파일을 참조하세요. 루트 [`CLAUDE.md`](../CLAUDE.md) 보안 규칙도 함께 적용됩니다.

## 이 브랜치에서 작업 시작 체크리스트

1. `config/.env.example`을 복사해 `config/.env` 생성 후 실제 값 입력
2. `pip install openai celery redis xgboost`
3. `OPENAI_API_KEY` 환경변수 확인
4. 도구 smoke test: `python -c "from src.agent.data_tools import get_household_profile; print(get_household_profile('HH001')['summary'])"`
5. 코치 에이전트 실행: `python -c "from src.agent.coach import run_coach; print(run_coach('HH001', '이번 주 전기료 줄이려면?'))"`

## 로컬 API 서버 (Frontend 연결용, 2026-04-30~)

Frontend의 MSW mock을 실 DB 데이터로 대체하는 로컬 FastAPI 서버.

```bash
# kpx-integration-settlement/ 에서 실행
pip install fastapi uvicorn

# IAP 터널 연결 후 (localhost:5436)
DEFAULT_HH=HH001 DB_PASSWORD=<secret> uvicorn src.api.main:app --reload --port 8000
# DEFAULT_HH: HH001~HH003 (mock) 또는 H011 등 (DB 실데이터)
```

| 파일 | 엔드포인트 |
|------|------------|
| `src/api/routers/dashboard.py` | `GET /api/dashboard/summary` |
| `src/api/routers/usage.py` | `GET /api/usage/analysis` |
| `src/api/routers/settings.py` | `GET /api/settings/account` |
| `src/api/routers/cashback.py` | `GET /api/cashback/tracker` |

**Frontend 연결**: `Frontend/.env.local`에 `VITE_API_BASE_URL=http://localhost:8000` 설정 → MSW 자동 우회.

## 아키텍처 (Tool-use 패턴, 2026-04-28~)

임베딩 기반 접근 → Tool-use 패턴으로 전환 ([설계 근거](plans/agent_tool_design.md)).

| 파일 | 역할 |
|------|------|
| `src/agent/data_tools.py` | 8개 데이터 조회 도구 + mock 데이터 (3가구) + TOOL_SCHEMAS |
| `src/agent/coach.py` | 코치 Agent loop (baseline 컨텍스트 주입 + function calling) |
| `tests/test_data_tools.py` | 8개 도구 schema 검증 단위 테스트 |

**mock → 실데이터 연결 예정**: 4주차에 DB·NILM·KMA·KEPCO API 연결.

## 파일 생성 금지 위치

- `kpx-integration-settlement/*.py` (루트 직접 생성 금지)
- 프로젝트 루트 직접 생성 금지

모든 규칙은 [`_claude_templates/CLAUDE_kpx-integration-settlement.md`](../_claude_templates/CLAUDE_kpx-integration-settlement.md) 참조.
