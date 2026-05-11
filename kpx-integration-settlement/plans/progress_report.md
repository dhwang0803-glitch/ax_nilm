# kpx-integration-settlement 진행 현황 (2026-05-05)

> 담당자: juyeon | 브랜치: Frontend → PR → main

---

## 담당 범위

`kpx-integration-settlement/` — LLM Agent + FastAPI 서버 + 이상탐지 파이프라인

---

## 완료 항목

### 1. Agent 아키텍처 전환 (Tool-use ReAct)
- **파일**: `src/agent/graph.py`
- 임베딩 기반 → LangGraph `create_react_agent` 패턴으로 전환
- GPT-4o-mini + 10개 도구 + MemorySaver 체크포인터
- LangSmith 트레이싱 (`ax_nilm-kpx` 프로젝트, `LANGCHAIN_TRACING_V2=true`)
- 토큰 사용량 집계 추가 (`compare_tokens.py` 연동용)
- **커밋 대기 중** (미커밋)

### 2. 데이터 도구 실DB 연결 (10개)
- **파일**: `src/agent/data_tools.py`

| 함수 | 연결 상태 | 소스 테이블 |
|------|-----------|-------------|
| `get_consumption_summary` | ✅ 실DB | `power_1hour` |
| `get_hourly_appliance_breakdown` | ✅ 실DB | `power_1hour` |
| `get_consumption_hourly` | ✅ 실DB | `power_1hour` |
| `get_consumption_breakdown` | ✅ 실DB | `power_1hour` |
| `get_cashback_history` | ✅ 실DB | `power_1hour` 기반 산출 |
| `get_tariff_info` | ✅ 실DB | `power_1hour` 기반 산출 |
| `get_anomaly_events` | ✅ 실DB | `appliance_status_intervals` |
| `get_anomaly_log` | ✅ 실DB | `appliance_status_intervals` |
| `get_weather` | ✅ 실DB | `household_daily_env` |
| `get_household_profile` | ✅ 실DB | `power_1hour` 기반 |
| `get_forecast` | ✅ 실DB | `household_daily_env` CURRENT_DATE 이후 조회 |

- HH001~HH003 가구는 mock fallback 유지 (하위 호환)
- DB 미연결 환경에서도 mock으로 동작

### 3. 이상탐지 시드 데이터
- **파일**: `scripts/seed_anomaly.sql`
- `appliance_status_intervals` 12행 목업 삽입 완료
- FK 안전: `appliance_status_codes` 기존 코드(0~32)만 사용
- NILM 엔진 실데이터 투입 전 임시 목업

### 4. FastAPI 서버 (6개 라우터)
| 라우터 | 엔드포인트 |
|--------|------------|
| `dashboard.py` | `GET /api/dashboard/summary` |
| `usage.py` | `GET /api/usage/analysis` |
| `auth.py` | 인증 관련 |
| `settings.py` | `GET /api/settings/account` |
| `cashback.py` | `GET /api/cashback/tracker` |
| `insights.py` | `GET /api/insights/summary` |

### 5. Insights 에이전트 + API
- **파일**: `src/api/routers/insights.py`
- `InsightsLLMOutput` Pydantic 파싱 + 폴백 `run_insights()` 경로
- 인메모리 캐시 (TTL 1시간)
- 파싱 실패 시 `logger.warning()` 진단 로그 추가
- `household_id` 쿼리 파라미터 지원
- **커밋 대기 중** (미커밋)

### 6. 9가구 통합 검증
- **파일**: `tests/run_target_households.py`
- H011, H015, H016, H017, H039, H049, H054, H063, H067 — 9/9 성공
- LangSmith 트레이스 생성 확인 (`ax_nilm-kpx`)
- **커밋 대기 중** (미커밋)

---

## DB 현황 (2026-05-05 기준)

| 테이블 | 행 수 | 상태 |
|--------|-------|------|
| `power_1hour` | 124,992 | ✅ 실데이터 |
| `household_daily_env` | 2,449 | ✅ 실데이터 |
| `appliance_status_intervals` | 12 | ⚠️ 목업 시드 |
| `dr_events` | 0 | ❌ 미연결 |
| `dr_results` | 0 | ❌ 미연결 |
| `dr_appliance_savings` | 0 | ❌ 미연결 |

---

## 진행 중 / 미완료

| 항목 | 상태 | 비고 |
|------|------|------|
| `mermaid.md` "인사이트 생성" 표현 수정 | ⏳ 미완 | "AI 진단 리포트" 등 대체어 협의 중 |
| 3개 파일 커밋 & push | ⏳ 미완 | `graph.py`, `insights.py`, `run_target_households.py` |
| `get_forecast` DB 연결 | ✅ 완료 | `household_daily_env` CURRENT_DATE 이후 7일 조회, mock fallback 유지 |
| DR 관련 테이블 연결 | ❌ 미착수 | `dr_events`/`dr_results` 데이터 없음 |

---

## main 대비 커밋 이력 (HEAD 기준)

```
a75ebb0 Merge branch 'main' into Frontend
bd182b3 feat(agent): appliance_status_intervals 목업 시드 + 이상탐지 안정화
2ab4f91 feat(api): insights/summary household_id 쿼리 파라미터 추가
6daa8b6 feat(agent): 단일 ReAct 에이전트 리팩토링 + LLM 프롬프트 스타일 개선
```

---

## 미커밋 파일 3개 (PR 전 필요)

```
M  src/agent/graph.py          ← 토큰 추적 수정
M  src/api/routers/insights.py ← 로깅 추가
M  tests/run_target_households.py ← H067 공백 버그 수정
```
