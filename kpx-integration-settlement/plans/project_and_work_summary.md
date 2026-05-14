# ax_nilm 프로젝트 개요 및 내 파트 작업 정리

> 최초 작성: 2026-05-08 | 최종 갱신: 2026-05-13 | 담당: juyeon | 브랜치: Frontend

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
│   │   ├── data_tools.py          ← 10개 데이터 조회 도구 (실DB + mock fallback)
│   │   ├── schemas.py             ← InsightsLLMOutput Pydantic 스키마
│   │   ├── coach.py               ← 단일 ReAct 코치 에이전트 (legacy fallback)
│   │   ├── rag_retriever.py       ← Module 4: pgvector 유사도 검색 (DB 없으면 [] 폴백)
│   │   └── multi_agent/
│   │       ├── supervisor.py      ← LangGraph StateGraph + run_multi_agent() 진입점
│   │       ├── nilm_monitor.py    ← Module 2: 이상이벤트·가전소비 구조화 (LLM)
│   │       ├── cashback_node.py   ← Module 3: 기준선·절감률·예상캐시백 산정 (순수 계산)
│   │       ├── rag_node.py        ← Module 4: retrieve() 호출 래퍼 노드
│   │       └── report_agent.py    ← Module 5: 이상 진단 + 절감 권고 생성 (structured LLM)
│   ├── api/
│   │   └── routers/
│   │       ├── dashboard.py       ← GET /api/dashboard/summary
│   │       ├── usage.py           ← GET /api/usage/analysis
│   │       ├── auth.py            ← 인증
│   │       ├── settings.py        ← GET /api/settings/account
│   │       ├── cashback.py        ← GET /api/cashback/tracker
│   │       └── insights.py        ← GET /api/insights/summary (멀티에이전트 우선, 단일 폴백)
│   └── tasks/
│       └── celery_tasks.py        ← Celery 배치 태스크 3개
├── scripts/
│   ├── seed_anomaly.sql           ← appliance_status_intervals 목업 시드
│   ├── create_rag_table.sql       ← rag_chunks 테이블 + IVFFLAT cosine 인덱스
│   ├── embed_rag_docs.py          ← 문서 → 512토큰 청크 → OpenAI 임베딩 → UPSERT
│   └── evaluate_agent.py          ← LangSmith 평가 스크립트 (14개 평가자)
├── docs/
│   └── rag/                       ← 에너지캐시백 지식베이스 문서 7개 (RAG 소스)
├── agents/
│   └── ORCHESTRATOR.md 등 역할 문서 9개
└── tests/
    ├── run_target_households.py   ← 9가구 통합 검증
    └── test_rag_retriever.py      ← RAG 단위 테스트 11개 (mock-only)
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

### Phase 8 — 멀티에이전트 재도입 (수퍼바이저 패턴)

> 2026-05-11 ~ 2026-05-12

**`d46e937` docs(plan): PLAN.md DR·RAG 잔재 제거 + 현재 구현 기준 갱신**

**`9d845df` fix(agent): 시간대 이동 권고 제거 + 프로젝트 요약 문서 추가**
- 시간대 이동 권고(세탁기·건조기 등)를 시스템 프롬프트에서 제거
  - 이유: 시간대 이동은 총 kWh 절감 없음 → 에너지캐시백 기여 없음

**`dbac304` feat(agent): 수퍼바이저 패턴 멀티에이전트 구현**
- LangGraph `StateGraph` 기반 4-노드 파이프라인:
  - `START` → `nilm_monitor` ‖ `cashback` (병렬) → `rag_retriever` → `report` → `END`
- **Module 2** `nilm_monitor.py`: 이상 이벤트 수집 + 가전 소비 패턴 → `_NilmLLMOutput` 구조화
- **Module 3** `cashback_node.py`: 순수 계산 노드 (LLM 없음)
  - `baseline_kwh`, `savings_rate`, `cashback_rate_krw_per_kwh`, `projected_cashback_krw` 산출
  - 단가표: 3%→30원, 5%→60원, 10%→80원, 20%→100원/kWh
- **Module 5** `report_agent.py`: NILM + 캐시백 + 날씨 통합 → `InsightsLLMOutput` (structured output)
- `insights.py` 라우터: `run_multi_agent` 우선 호출, 실패 시 단일 에이전트 폴백 유지
- 이유: Module 2·3 독립 실행 가능 → 병렬화로 레이턴시 단축, LLM 호출은 Module 5만 담당

**`d551168` fix(settlement): 캐시백 단가 정정 (30/60/80/100원/kWh)**
- 기존 단가표(30·50·70·100원) → 공식 KEPCO 요율(30·60·80·100원)로 수정

**`d15878d` feat(tasks): Celery 배치 태스크 3개 구현**
- `refresh_all_baselines`: 전 가구 2개년 동월 평균 기준선 계산 → `monthly_baselines` upsert
  - `billing_day` 기반 검침 사이클, proxy_cluster fallback 지원
- `finalize_cashback_results`: 실측 기반 KEPCO 에너지캐시백 산정 → `cashback_results` upsert
- `refresh_household_baseline`: 신규 가입/수동 트리거용 단일 가구 즉시 갱신
- 22개 단위 테스트 PASS (billing_period 경계, tier_rate 전 구간, mock DB upsert)

---

### Phase 9 — RAG 모듈 (Module 4) 구현

> 2026-05-12

**`1f31285` docs(rag): 에너지캐시백 지식베이스 문서 7개 작성**
- `docs/rag/` 에 에너지캐시백 관련 한국어 문서 7개 작성 (RAG 소스 원문)

**`2be8b54` feat(rag): Module 4 pgvector 임베딩 파이프라인 + 검색 모듈 구현**
- `scripts/create_rag_table.sql`: `rag_chunks` 테이블 + IVFFLAT cosine 인덱스 (lists=10)
- `scripts/embed_rag_docs.py`: H2 섹션 분리 → 512토큰 청크 → OpenAI `text-embedding-3-small` → UPSERT
- `src/agent/rag_retriever.py`: `retrieve()` / `retrieve_with_scores()` — DB 미연결 시 `[]` 폴백

**`0b49a4e` feat(rag): Module 4 RAG report_agent 통합 + 평가 스크립트 멀티에이전트 전환**
- `rag_node.py` 추가: `retrieve()` 호출 래퍼 → `rag_context` 상태 업데이트
- `report_agent.py`: `rag_context` 청크를 LLM 페이로드에 주입
- `run_target_households.py`: `run_graph` → `run_multi_agent` 전환
- `test_rag_retriever.py`: RAG 단위 테스트 11개 (mock-only, DB/API 키 불필요)

**`24c2575` feat(agent): RAG 검색을 별도 그래프 노드로 분리 (Module 4)**
- `supervisor.py`에서 RAG 호출을 `rag_retriever` 노드로 분리 (fan-in 전 단계)
- 이유: `nilm_monitor`·`cashback` 완료 후 RAG 쿼리를 구성해야 컨텍스트 품질이 높음

**`1e5b2b7` fix(report_agent): get_weather 호출 인자를 날짜 범위 리스트로 수정**
- `get_weather(date_range)` 인자를 `[start_date, end_date]` 리스트 형태로 수정
  - 이유: `data_tools.py` 시그니처와 불일치로 런타임 오류 발생

---

### Phase 10 — LangSmith 평가 시스템 구축

> 2026-05-12 ~ 2026-05-13

**`482f0e5` refactor(agent): settlement 모듈 제거 및 multi_agent 리팩터링**
- `settlement/calculator.py` 제거 → `cashback_node.py`로 통합

**`360f772` feat(eval): LangSmith 평가 가구 3개 → 50개로 확장**
- `evaluate_agent.py` 데이터셋을 HH001~HH003(mock) 3가구에서 50가구로 확장
- LangSmith 데이터셋 자동 생성 로직 포함

**`b57a145` fix(eval): llm_quality 0.6 원인 제거 — mock 데이터 품질 개선**
- HH001~HH003 mock 데이터의 이상 이벤트·가전 구성 보강
  - 이유: mock 데이터가 빈 이벤트/0.0 kWh 가전으로 채워져 LLM이 무의미한 출력 생성

**`70e6d5a` feat(eval): 평가자 4개 추가 — 안전성·캐시백 적합성·추천 적절성·RAG 충실도**
- `target()` 함수를 `run_multi_agent()` → `_get_graph().invoke()` 직접 호출로 변경
  - 중간 상태(`nilm_output`, `cashback_output`, `rag_context`)를 평가자에 노출
- `safety`: 사용 중단·필수 가전 중단 표현 감지 (금지어 목록 기반)
- `cashback_compliance`: 단계 요율 테이블 일치 + 정산액 계산 정합성 검증
- `rec_relevance`: NILM `top_consumers` ↔ 권고 논리 연결 LLM judge
- `rag_faithfulness`: RAG 청크 ↔ 진단·권고 일치 LLM judge (청크 없으면 중립 0.5)

**`00b2d50` feat(eval): 평가자 5개 추가 — 중복·계절·커버리지·지연·비용**
- `rec_uniqueness`: `top_consumers` 기기명 기준 권고 중복 탐지
- `seasonal_alignment`: 날씨 `tavg` 기온 기준 냉·난방 방향 일치 검증
- `anomaly_coverage`: 이상 이벤트 건수 대비 진단 커버리지 비율 (0.0~1.0)
- `latency`: graph invoke 실측 ms, SLA 30s 기준 0/1
- `cost_estimate`: `langchain_community` 콜백 실측 → 없으면 문자 기반 rough 추정

**`6579d67` fix(eval): cashback_compliance — enrolled 필드 오용 제거**
- `enrolled` 필드가 `savings_rate >= 3%` 여부를 나타낸다고 잘못 해석하여 발생한 오류 수정
  - 실제 `enrolled` = DB의 **프로그램 가입 여부** (savings_rate와 독립적)
  - 수정: `enrolled` 검사 제거 → 요율 불일치·정산액 불일치만 검증

**`480bf23` fix(eval): seasonal_alignment 오탐 수정 + rec_relevance regex 강화**

*문제 1 — `seasonal_alignment` 전 가구 0.000*

- **근본 원인**: 효율 방향 권고 제목(예: `"전기장판 온도 단계 낮추기"`)이 난방 가전 키워드 `"전기장판"`을 포함 → 평가자가 여름철 난방 방향 위반으로 오탐
- **수정**: `_EFFICIENCY_KEYWORDS = ["낮추기", "줄이기", "절전", "조정", "타이머", "설정", "최적화", "점검", "단계", "예약", "모아서"]` allow-list 추가
  - 해당 키워드가 제목에 포함되면 계절 방향 검사를 건너뜀 — "에어컨 낮추기"처럼 냉방 기기를 절전하는 권고도 올바르게 통과
- **결과**: 0.000 → **0.980** (HH049 1건 실제 위반 잔존)

*문제 2 — `rec_relevance` 전 가구 0.500 (1차 원인)*

- **근본 원인**: `_call_judge` 정규식 `r"점수\s*:\s*([1-5])"` 이 gpt-4o-mini 출력(`점수：3`, `Score: 4`, `점수: 3.5` 등)을 매칭하지 못해 항상 기본값 0.5 반환
- **수정**: 정규식을 `r"(?:점수|Score)\s*[:：]\s*([1-5])(?:\.\d)?"` 로 강화 (전각 콜론·영문 라벨·소수점 처리), 매칭 실패 시 첫 30자에서 단독 숫자 fallback 추가

**`a0acf6d` fix(data_tools): mock 가구(HH001-HH050) IAP 터널 연결 시 DB 라우팅 버그 수정**

*문제 — `rec_relevance` 전 가구 0.500 (2차 · 실제 근본 원인)*

- **배경**: regex 강화 후에도 여전히 0.500 고착 → 데이터 흐름 추적
- **근본 원인**: IAP 터널 활성화 상태(localhost:5436)에서 `_get_db_conn()`이 실제 DB 커넥션 반환 → `get_hourly_appliance_breakdown` / `get_consumption_hourly` / `get_anomaly_events` 세 함수 모두 `if conn:` 분기로 DB를 조회
  - DB에 HH001~HH050 행 없음 → 세 함수 모두 `E_NO_DATA` 반환
  - `nilm_monitor` 노드가 빈 `daily_summary: []`·`anomalies: []` 수신 → LLM이 `top_consumers: []` 생성
  - `rec_relevance` 평가자는 `top_consumers`가 비어 있으면 판단 불가 → 조기 반환 0.5

- **수정**: 세 함수에서 `if conn:` → `if conn and household_id not in _KNOWN_HOUSEHOLDS:`
  ```python
  # 수정 전 (버그)
  conn = _get_db_conn()
  if conn:
      return _db_hourly_breakdown(conn, household_id, date)

  # 수정 후
  conn = _get_db_conn()
  if conn and household_id not in _KNOWN_HOUSEHOLDS:
      return _db_hourly_breakdown(conn, household_id, date)
  ```
  - `_KNOWN_HOUSEHOLDS` = `_build_synthetic_households()`가 생성하는 HH001~HH050 집합
  - mock 가구는 IAP 터널 활성 여부와 무관하게 항상 인메모리 mock 데이터를 사용, 실 가구(H011 등)는 그대로 DB 조회

- **eval-fix-v3 결과 (50가구)**:

  | 지표 | 수정 전 | 수정 후 |
  |------|---------|---------|
  | `rec_relevance` | 0.500 | **0.968** |
  | `seasonal_alignment` | 0.000 | **0.980** |
  | `llm_quality` | 0.600 | **0.792** |
  | `rag_faithfulness` | 0.500 | **0.880** |
  | `rec_uniqueness` | — | 0.740 |
  | `latency` | — | 0.980 |
  | `cost_estimate` | — | 0.280 |
  | `schema_valid` / `rec_count` / `savings_range` / `field_length` / `safety` / `cashback_compliance` / `anomaly_coverage` | 1.000 | **1.000** |

---

### 현재 평가자 목록 (14개)

| 유형 | 평가자 | 측정 항목 |
|------|--------|-----------|
| 규칙 | `schema_valid` | anomaly_diagnoses·recommendations 키 존재 여부 |
| 규칙 | `rec_count` | 권고 3~5개 범위 |
| 규칙 | `savings_range` | savings_kwh 0.1~10.0 kWh 범위 |
| 규칙 | `field_length` | title ≤30자, action ≤15자, diagnosis ≤100자 |
| 규칙 | `safety` | 사용 중단·필수 가전 중단 표현 부재 |
| 규칙 | `cashback_compliance` | 요율 테이블 일치 + 정산액 계산 정합성 |
| 규칙 | `rec_uniqueness` | 기기명 중복 권고 없음 |
| 규칙 | `seasonal_alignment` | 기온 기준 냉·난방 방향 일치 |
| 규칙 | `anomaly_coverage` | 이상 이벤트 대비 진단 커버리지 비율 |
| LLM judge | `rec_relevance` | NILM top_consumers ↔ 권고 논리 연결 |
| LLM judge | `rag_faithfulness` | RAG 청크 ↔ 진단·권고 근거 일치 |
| LLM judge | `llm_quality` | 전반적 출력 품질 (0.0~1.0) |
| 런타임 | `latency` | graph invoke ms, SLA 30s 기준 |
| 런타임 | `cost_estimate` | LLM 호출 비용 추정 (원) |

---

## 4. 현재 DB 상태

| 테이블 | 행 수 | 상태 |
|--------|-------|------|
| `power_1hour` | 124,992 | ✅ 실데이터 (9가구) |
| `household_daily_env` | 2,449 | ✅ 실데이터 |
| `appliance_status_intervals` | 12 | ⚠️ 목업 시드 (NILM 엔진 실데이터 대기) |
| `rag_chunks` | — | ⚠️ embed_rag_docs.py 실행 필요 (pgvector 테이블, DB 연결 시) |
| `monthly_baselines` | — | ⚠️ refresh_all_baselines Celery 태스크 1회 실행 필요 |
| `cashback_results` | — | ⚠️ finalize_cashback_results Celery 태스크 실행 필요 |
| `dr_events` / `dr_results` | 0 | ❌ 미연결 |

---

## 5. 미완료 항목

| 항목 | 비고 |
|------|------|
| DR 관련 테이블 연결 | `dr_events`/`dr_results` 데이터 없음 — NILM 엔진 실적 투입 후 진행 |
| `appliance_status_intervals` 실데이터 | NILM 엔진에서 실 추론 결과 적재 필요 |
| RAG 임베딩 적재 | DB 연결 환경에서 `python scripts/embed_rag_docs.py` 1회 실행 필요 |
| LangSmith 50가구 전체 평가 실행 | `python scripts/evaluate_agent.py` — ~$1-2, LLM 150+ 호출 |
| PR 리뷰·merge | Frontend 브랜치 → main |

---

## 6. 아키텍처 선택 이유

### Tool-use vs RAG

현재 파트는 **Tool-use + RAG 혼합** 패턴을 사용한다.

- **Module 2·3**: Tool-use — 데이터 소스가 구조화된 DB 테이블(`power_1hour`, `appliance_status_intervals`)이므로 RAG 불필요
- **Module 4**: RAG — 에너지캐시백 지식베이스(한국어 문서 7개)를 `pgvector` 유사도 검색으로 참조
  - 가전 매뉴얼·KEPCO 고시문 등 비구조화 텍스트를 진단 근거로 활용
  - DB 미연결 시 `[]` 폴백 → 에이전트 동작에 영향 없음

### 단일 ReAct vs 멀티에이전트 (수퍼바이저)

| | 단일 ReAct (`coach.py`) | 멀티에이전트 (`supervisor.py`) |
|--|-------------------------|-------------------------------|
| LLM 호출 | 매 도구 호출마다 | Module 2·5만 LLM, Module 3은 순수 계산 |
| 병렬화 | 불가 | Module 2·3 병렬 실행 |
| 레이턴시 | 높음 | 낮음 |
| 현재 사용 | Fallback | 기본 경로 |

멀티에이전트를 기본 경로로 쓰고 단일 에이전트는 장애 시 폴백으로 유지.

### savings_krw Python 후처리 이유

LLM에 단가 계산을 위임하면 항목별 단가가 달라지는 일관성 문제 발생.  
`cashback_unit_rate(household_id)` 함수로 가구 이력에서 단가를 추출 → 파싱 직후 일괄 적용.
