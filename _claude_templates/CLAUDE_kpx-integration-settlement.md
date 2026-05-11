# kpx-integration-settlement — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 관련 문서

- 전체 아키텍처: [`docs/context/architecture.md`](../docs/context/architecture.md)
- 설계 결정 (ADR-002~005): [`docs/context/decisions.md`](../docs/context/decisions.md)
- 파일 맵: [`docs/context/MAP.md`](../docs/context/MAP.md)
- 구현 계획: [`kpx-integration-settlement/plans/PLAN.md`](../kpx-integration-settlement/plans/PLAN.md)
- 요구사항: REQ-003 (DR 의사결정), REQ-005 (전력거래소 연계)

## 모듈 역할

**KPX 연계·정산 레이어** — DR 이벤트 수신 → 가구별 감축량 계산 → 환급금 산출 → LLM 맥락 메시지 생성.

**3단 계산 공식**

```
공식식:  가구 전체 절감량     = 가구 단위 CBL - 이벤트 구간 실측 총 사용량
내부식:  가전별 절감량(추정)  = 가전별 기준 사용량 - 가전별 NILM 추정 사용량
보정식:  기타/미분류 절감량   = 가구 전체 절감량 - Σ(가전별 절감량)
         (음수 = NILM 과대추정 -> UI "추정 오차 포함" 표시)
```

**CBL 산정**: 직전 10 평일 중 상위2·하위2 제외 6일 평균 (Mid 6/10, KPX 표준)
**신규 가구 fallback**: 10일 미만 시 `ch01 CBL x 군집 평균 비율` Proxy 적용 후 전환

## 파일 위치 규칙 (MANDATORY)

```
kpx-integration-settlement/
├── plans/           <- 구현 계획 (PLAN.md)
├── src/
│   ├── settlement/  <- CBL 계산, 절감량·환급금 산출, 가전 DR 분류
│   │   ├── cbl.py           <- Mid(6/10) + Proxy CBL
│   │   ├── calculator.py    <- 공식식·내부식·보정식
│   │   └── appliance.py     <- 온도제어형/부하이동형/상시부하 분류
│   ├── rag/         <- 전력 패턴 임베딩, pgvector 유사 날 검색
│   │   ├── embedder.py      <- 1440분 프로파일 -> 384차원 임베딩
│   │   └── retriever.py     <- pgvector 유사 날 검색 + LLM 맥락 생성
│   ├── agent/       <- LLM Agent (Claude Haiku)
│   │   ├── tools.py         <- 도구 4종 정의 + schema
│   │   └── recommender.py   <- agent loop (익명화 적용)
│   ├── kpx/         <- KPX Open API 게이트웨이
│   │   └── client.py        <- Mock + HttpKPXGateway (스펙 확보 후 구현)
│   └── tasks/       <- Celery 배치
│       └── batch_compute.py <- 1시간 주기 + DR 이벤트 트리거
├── benchmark/       <- 임베딩·CBL·아키텍처 비교 실험
│   ├── data_loader.py
│   ├── embeddings.py
│   ├── cbl_methods.py
│   ├── architectures.py
│   └── run_benchmark.py
├── scripts/         <- DB seed SQL
├── tests/           <- pytest
├── config/          <- .env.example
└── CLAUDE.md
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| CBL·절감량 계산 로직 | `src/settlement/` |
| 임베딩·RAG 검색 | `src/rag/` |
| LLM Agent | `src/agent/` |
| KPX API 연동 | `src/kpx/` |
| Celery 배치 | `src/tasks/` |
| 비교 실험 | `benchmark/` |
| DB seed SQL | `scripts/` |
| pytest | `tests/` |

**`kpx-integration-settlement/` 루트 또는 프로젝트 루트에 파일 직접 생성 금지.**

## 기술 스택

```python
import anthropic                          # Claude Haiku Agent (tool_use)
from sentence_transformers import SentenceTransformer  # 전력 패턴 임베딩
import celery                             # 배치 작업
import httpx                              # KPX API 연동 (예정)
import xgboost                            # benchmark CBL 비교용
```

- LLM: `claude-haiku-4-5-20251001` (tool_use 기반 agent loop)
- 임베딩: `sentence-transformers/all-MiniLM-L6-v2` (384차원)
- 벡터 DB: pgvector (`household_embeddings` 테이블, Database 브랜치)
- 배치: Celery + Redis

## 익명화 규칙 (MANDATORY)

LLM 입력 **금지**: `household_id`, 주소, 가구원 수, 소득 정보
LLM 입력 **허용**: `temperature`, `cluster_label`, `savings_kwh`, `appliance_code` 목록, 유사 날 맥락 텍스트

## 인터페이스

- **업스트림**: `Execution_Engine` — 가전별 NILM 추정 사용량
- **업스트림**: `Database` — `power_efficiency_30min`, `household_embeddings` 조회
- **다운스트림**: `API_Server` — `/dr/events`, `/dr/results/{household_id}` 엔드포인트
- **외부**: KPX Open API — DR 이벤트 수신, 감축 실적 전송

## 미완성 항목

- `src/kpx/client.py` `HttpKPXGateway` — KPX API 스펙 확보 후 구현
- `src/tasks/batch_compute.py` — Database 브랜치 Repository 연동 후 구현
- Repository 구현체 — Database 브랜치 완성 후 연동

## 토큰 절감 규칙 (MANDATORY)

### 파일 읽기 전략
- 500줄 이하 파일은 전체 읽기 허용
- 500줄 초과 파일은 목차/헤더 먼저 읽고(limit=30), 필요 구간만 읽는다

### 출력 간결화
- 파일 Write 후 변경 내용 반복 설명 금지 (diff로 확인 가능)
- 설계 판단이 들어간 경우만 한 줄로 근거 남김
