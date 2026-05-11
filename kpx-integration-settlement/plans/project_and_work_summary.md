# ax_nilm 프로젝트 개요 및 내 파트 작업 정리

> 작성일: 2026-05-08 | 담당: juyeon | 브랜치: Frontend

---

## 1. 프로젝트 주제

**NILM(Non-Intrusive Load Monitoring) 기반 에너지 효율화 플랫폼**

단일 분전반 계량기 데이터 하나만으로 세탁기·에어컨·냉장고 등 개별 가전의 전력 소비를 분해(Disaggregation)하고, 이상 탐지·DR(수요반응)·전력거래소 연계까지 통합 제공하는 에너지 관리 서비스.

### 핵심 기능 범위 (REQ-001 ~ 009)

| REQ | 기능 | 담당 모듈 |
|-----|------|-----------|
| REQ-001 | NILM 분해 엔진 (30Hz → 22종 가전 식별, CNN+TDA) | `nilm-engine` |
| REQ-002 | 이상 탐지 (성능 저하 감지, LLM 진단 리포트) | `kpx-integration-settlement` |
| REQ-003 | DR 의사결정 (절감 잠재량 예측, 경제성 분석) | `dr-savings-prediction` |
| REQ-004 | 데이터 관리 (TimescaleDB, ETL 파이프라인) | `Database` |
| REQ-005 | 전력거래소 연계 (DR 이벤트, 정산 데이터) | `kpx-integration-settlement` |
| REQ-006 | UI (대시보드, DR 분석, 이상탐지 로그) | `Frontend` (미착수) |
| REQ-007 | 인증·보안 (OAuth 2.0, AES-256) | `API_Server` (미착수) |

### 기술 스택

- **ML/DL**: Python, PyTorch, scikit-learn, XGBoost
- **신호처리**: PyWavelets, GUDHI (TDA)
- **DB**: TimescaleDB + PostgreSQL 16, asyncpg, SQLAlchemy 2.0
- **백엔드**: FastAPI, LangGraph, LangChain, OpenAI API (GPT-4o-mini)
- **MLOps**: LangSmith, Docker

---

## 2. 내 파트: kpx-integration-settlement

### 담당 범위

- **LLM 에너지 코치 에이전트** (이상 탐지 진단 + 절약 추천 생성)
- **FastAPI 로컬 서버** (Frontend MSW mock → 실 DB 데이터 연결)
- **에너지캐시백 정산 파이프라인** (KEPCO 단가 기반 savings_krw 산출)

### 모듈 구조

```
kpx-integration-settlement/
├── src/
│   ├── agent/
│   │   ├── graph.py          ← LangGraph ReAct 에이전트 + Insights 스키마
│   │   ├── data_tools.py     ← 10개 데이터 조회 도구 (실DB + mock fallback)
│   │   ├── anonymizer.py     ← PII 스크럽 (도구 출력 레벨)
│   │   ├── validator.py      ← LLM 출력 검증
│   │   └── trace_logger.py   ← 로컬 트레이스 저장
│   ├── api/
│   │   └── routers/
│   │       ├── dashboard.py  ← GET /api/dashboard/summary
│   │       ├── usage.py      ← GET /api/usage/analysis
│   │       ├── auth.py       ← 인증
│   │       ├── settings.py   ← GET /api/settings/account
│   │       ├── cashback.py   ← GET /api/cashback/tracker
│   │       └── insights.py   ← GET /api/insights/summary (에이전트 연동)
│   └── settlement/
│       └── calculator.py     ← KEPCO 에너지캐시백 단가 계산
├── scripts/
│   └── seed_anomaly.sql      ← appliance_status_intervals 목업 시드
└── tests/
    └── run_target_households.py ← 9가구 통합 검증
```

---

## 3. 작업 이력 (커밋 순)

### Phase 1 — 모듈 초기 구조 및 도메인 설정

**`97c6a12` feat(kpx): KPX 연계·정산 모듈 초기 구조 추가**
- `kpx-integration-settlement/` 디렉토리 구조 생성
- 전력거래소 DR 이벤트 수신·정산 기본 골격

**`a1402be` refactor(kpx): 국민DR → 에너지캐시백 구조 전환**  
**`906918d` refactor(kpx): DR(수요반응) → 에너지캐시백으로 도메인 전환**
- 초기 국민DR 기반 설계를 KEPCO 에너지캐시백 체계로 전환
- 절감률 기반 단가표 (3%·5%·10%·20% 구간) 도입

---

### Phase 2 — LLM 코치 에이전트 구현 (Tool-use 패턴)

**`8ddfcc2` feat(kpx): Tool-use 패턴 전환 — 1·2주차 LLM 코치 에이전트 구현**
- 임베딩 기반 접근 → Function Calling 패턴으로 전환
- 8개 데이터 조회 도구 + TOOL_SCHEMAS 정의
- `coach.py`: baseline 컨텍스트 주입 + function calling 에이전트 루프

**`58bac3d` feat(kpx): 유사 가구 Proxy 기준선 + LLM 맥락 인식 프롬프트 강화**
- 동일 주거 유형·면적 가구를 baseline 비교 기준으로 활용

---

### Phase 3 — 멀티에이전트 → 단일 ReAct 에이전트 전환

**`51ad39e` feat(kpx): LangGraph 멀티에이전트 + FastAPI 로컬 서버 구축**
- LangGraph supervisor + 하위 에이전트(consumption / anomaly / cashback) 구조
- FastAPI 서버 6개 라우터 초기 구현
- Frontend `.env.local` 연결 (MSW mock 우회)

**`6daa8b6` feat(agent): 단일 ReAct 에이전트 리팩토링 + LLM 프롬프트 스타일 개선**
- 멀티에이전트(supervisor 3-layer) → `create_react_agent` 단일 구조로 단순화
- GPT-4o-mini + 10개 도구 + MemorySaver 체크포인터
- 이유: 멀티에이전트 라우팅 오버헤드 > 단일 에이전트 효율

**`e0aeed8` feat(kpx): LangSmith 트레이싱 도입 + API 호환성 수정**
- `LANGCHAIN_TRACING_V2=true`, 프로젝트명 `ax_nilm-kpx`
- 토큰 사용량 집계 (`usage_metadata` + `response_metadata.token_usage`)

---

### Phase 4 — 실DB 연결 (3주차)

**`91cdd9b` feat(kpx): data_tools 실데이터 연결 — power_1hour + appliance_status_intervals**

10개 도구 전체 실DB 연결 완료:

| 함수 | 소스 테이블 |
|------|-------------|
| `get_consumption_summary` | `power_1hour` |
| `get_hourly_appliance_breakdown` | `power_1hour` (22ch × 24h) |
| `get_consumption_hourly` | `power_1hour` |
| `get_consumption_breakdown` | `power_1hour` |
| `get_cashback_history` | `power_1hour` 기반 산출 |
| `get_tariff_info` | `power_1hour` 기반 산출 |
| `get_anomaly_events` | `appliance_status_intervals` |
| `get_anomaly_log` | `appliance_status_intervals` |
| `get_weather` | `household_daily_env` |
| `get_household_profile` | `power_1hour` 기반 |

- HH001~HH003: mock fallback 유지 (하위 호환)
- IAP 터널(localhost:5436) 없는 환경에서도 mock으로 동작

**`b372e9a` fix(kpx): data_tools SQL 컬럼명 수정 — asc_.label → asc_.label_ko**
- 실DB 스키마와 컬럼명 불일치 수정

---

### Phase 5 — Insights API + 캐시백 미션

**`cc41e61` feat(kpx): cashback 미션 하드코딩 → 가구 프로필 기반 동적 생성**
- 가구 유형(apartment/house)·면적·가전 구성에 따라 미션 동적 생성

**`ab7b4f1` feat(kpx): 캐시백 미션 소스를 AI 진단 LLM 추천으로 통합**
- `get_or_run_insights()` → LLM recommendations를 캐시백 미션 소스로 사용

**`9842f85` refactor(kpx): LLM 항상 켜기 — INSIGHTS_LLM 플래그 + 규칙 기반 폴백 제거**
- `INSIGHTS_LLM` 환경변수 플래그 제거, LLM 항상 활성화
- 규칙 기반 fallback 삭제

**`339e669` fix(kpx): run_insights Pydantic 제약조건 강화 — LLM 출력 품질 보정**
- `InsightsLLMOutput` 스키마: `diagnosis` max_length=100, `action` max_length=15
- `savings_kwh` ge=0.1·le=10.0 범위 제약

**`2ab4f91` feat(api): insights/summary household_id 쿼리 파라미터 추가**
- 엔드포인트 `GET /api/insights/summary?household_id=H011` 형태로 확장

---

### Phase 6 — 이상탐지 안정화 + 예보 연결

**`bd182b3` feat(agent): appliance_status_intervals 목업 시드 + 이상탐지 안정화**
- `scripts/seed_anomaly.sql`: `appliance_status_intervals` 12행 목업 삽입
  (NILM 엔진 실데이터 투입 전 임시 — FK는 기존 status_code 0~32 사용)
- 이상탐지 도구 `get_anomaly_events` / `get_anomaly_log` 안정화

**`d5903ef` feat(kpx): get_forecast DB 연결 + 에이전트 안정화 + 진행 현황 문서**
- `get_forecast`: `household_daily_env` CURRENT_DATE 이후 7일 조회 + mock fallback
- 9가구(`tests/run_target_households.py`) H011·H015·H016·H017·H039·H049·H054·H063·H067 통합 검증 9/9 성공
- LangSmith 트레이스 생성 확인

---

### Phase 7 — 시스템 프롬프트 품질 개선

**`11d1f77` fix(agent): 이상 진단 action 규칙 개선 + savings_krw 에너지캐시백 단가 적용**
- `action` 작성 규칙 추가:
  - 피크(순간 급상승): 설정·타이머·대기전력 차단 중심
  - 과소비(지속 증가): 부품 점검·청소·필터 교체 중심
  - "사용 줄이기", "끄세요" 표현 금지
- `savings_krw` 계산을 KEPCO 캐시백 단가표로 변경 (기존 × 100 고정 → 절감률 구간별 30·50·70·100원/kWh)

**`63f1045` fix(agent): 가전별 맥락 기반 추천 방향 규칙 추가**
- 22종 NILM 가전을 6유형으로 분류하여 권고 방향 명시:
  - 시간대 이동 가능: 세탁기·건조기·식기세척기
  - 설정 조정: 에어컨·전기장판·인덕션
  - 효율 사용: 전기포트·전기밥솥·전기다리미
  - 절전 설정만 (미사용·줄이기 금지): TV·컴퓨터·선풍기·공기청정기
  - 상시 가동 (점검·설정만): 냉장고·김치냉장고
  - 전원 차단 가능: 무선공유기·셋톱박스

**`a96650d` refactor(agent): 시스템 프롬프트 구조화 + savings_krw Python 후처리 이동**
- `_AGENT_SYSTEM` / `_INSIGHTS_SYSTEM`을 `## 역할 / ## 출력 형식 / ## 진단 규칙 / ## 권고 규칙` 4섹션으로 재구성
- `savings_krw` 계산을 LLM 프롬프트에서 제거 → Python 후처리로 이동
  - `cashback_unit_rate(household_id)`: 가구 이력에서 `cashback_rate_krw_per_kwh` 추출 (없으면 50원/kWh)
  - `insights.py`의 `get_or_run_insights()`에서 파싱 직후 적용 → 모든 추천 항목에 동일 단가 보장
- 이유: LLM에 단가 계산을 맡기면 항목별 단가가 달라지는 일관성 문제가 발생

---

## 4. 현재 DB 상태

| 테이블 | 행 수 | 상태 |
|--------|-------|------|
| `power_1hour` | 124,992 | ✅ 실데이터 (9가구) |
| `household_daily_env` | 2,449 | ✅ 실데이터 |
| `appliance_status_intervals` | 12 | ⚠️ 목업 시드 (NILM 엔진 실데이터 대기) |
| `dr_events` / `dr_results` | 0 | ❌ 미연결 |

---

## 5. 미완료 항목

| 항목 | 비고 |
|------|------|
| DR 관련 테이블 연결 | `dr_events`/`dr_results` 데이터 없음 — NILM 엔진 실적 투입 후 진행 |
| `appliance_status_intervals` 실데이터 | NILM 엔진에서 실 추론 결과 적재 필요 |
| PR #72 리뷰·merge | Frontend 브랜치 → main |

---

## 6. 아키텍처 선택 이유 (RAG vs Tool-use)

현재 파트는 **Tool-use Agent** 패턴만 사용하며 RAG를 사용하지 않는다.

- **데이터 소스가 구조화된 DB 테이블** (`power_1hour`, `appliance_status_intervals` 등) — "어느 문서에 답이 있는지 검색"하는 RAG가 필요 없음
- Tool-use = "어느 함수를 어떤 파라미터로 호출할지" LLM이 결정 → DB 쿼리 결과를 직접 LLM에 전달
- RAG가 의미 있어질 시점: 가전 매뉴얼·KEPCO 고시문 등 비구조화 텍스트를 진단 근거로 쓰고 싶을 때
