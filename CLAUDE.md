# ax_nilm — Claude Code 프로젝트 지침

> NILM(Non-Intrusive Load Monitoring) 기반 에너지 효율화 서비스

## 프로젝트 개요

단일 분전반 계량기 데이터만으로 개별 가전의 전력 소비를 분해(Disaggregation)하고,
이상 탐지, DR(수요반응) 참여 분석, 전력거래소 연계까지 제공하는 에너지 효율화 플랫폼.

## 요구사항 범위 (REQ-001 ~ REQ-009)

| REQ | 영역 | 핵심 기능 |
|-----|------|-----------|
| REQ-001 | NILM 분해 엔진 | 30Hz 전력 데이터 수집, 특징 추출, 하이브리드 가전 식별(CNN+TDA), 22종 분류 |
| REQ-002 | 이상 탐지 | 성능 저하/비정상 작동 감지, LLM 진단 리포트, 심각도별 알림 |
| REQ-003 | DR 의사결정 | 절감 잠재량 예측(XGBoost), 경제성 분석, 시나리오 비교, 맞춤형 권고 |
| REQ-004 | 데이터 관리 | TimescaleDB+PostgreSQL, ETL/EtLT 파이프라인, 리포트 생성 |
| REQ-005 | 전력거래소 연계 | DR 이벤트 수신, 감축 실적 산출, 정산 데이터 전송 |
| REQ-006 | UI (웹/모바일) | 대시보드, 기기 상세, DR 분석, 이상탐지 로그 |
| REQ-007 | 인증 및 보안 | OAuth 2.0/SSO, AES-256 암호화, TLS 1.3 |
| REQ-008 | 비기능 요구사항 | 성능(<2s), 가용성(99.5%), 확장성(10K), MLOps |
| REQ-009 | B2B 집단 분석 | 지역별 수요 예측, DR 정책 효과 검증 |

## 기술 스택 (요구사항 정의서 기준)

- **ML/DL**: Python, PyTorch, TensorFlow, scikit-learn, XGBoost
- **신호처리**: PyWavelets, GUDHI, scikit-tda, SciPy
- **데이터**: Pandas, NumPy, TimescaleDB, PostgreSQL, InfluxDB
- **파이프라인**: Apache Airflow, Kafka, Redis, Celery
- **백엔드**: FastAPI, JWT, OAuth2
- **프론트엔드**: React, TypeScript, Recharts, Tailwind CSS, React Native
- **MLOps**: MLflow, DVC, Docker, Kubernetes, GitHub Actions
- **LLM**: OpenAI API, LangChain

## 보안 규칙 (MANDATORY)

1. 하드코딩 자격증명 금지 — `os.getenv()` 사용, 기본값에 실제 인프라 정보 금지
2. `.env` 파일 커밋 금지
3. 전력 데이터 및 개인정보는 AES-256 암호화 저장
4. DB 접속 정보는 환경변수로만 참조
5. 커밋 전 `_agent_templates/SECURITY_AUDITOR.md` 기준 보안 점검 필수

## 브랜치 전략

- `main` — 통합 브랜치 (직접 push 금지, PR only)
- `docs` — 위키 편집 전용 (`docs/context/` 관리)
- 모듈 브랜치 — 브랜치명이 곧 작업 디렉토리 (예: `Database/`, `API_Server/`)

## 파일 구조 컨벤션

- 브랜치별 폴더 구조는 `_claude_templates/CLAUDE_{브랜치명}.md` 참조
- 에이전트 역할 문서: `_agent_templates/` (post-checkout 훅이 자동 복사)
- 공유 지식 베이스: `docs/context/` (docs 브랜치에서만 편집)

## 토큰 절감 규칙 (MANDATORY)

### 파일 읽기 전략
- 작업 시작 시 대상 파일의 전체 크기를 먼저 확인한다 (wc -l 또는 limit=1)
- 500줄 이하 파일은 전체 읽기 허용
- 500줄 초과 파일은 목차/헤더를 먼저 읽고(limit=30), 작업에 필요한 구간을 특정한 뒤 해당 구간만 읽는다
- 판단이 불확실하면 "이 구간만 읽어도 되는지" 사용자에게 확인 후 진행한다

### 출력 간결화
- 파일 Write 후 변경 내용을 반복 설명하지 않는다 (diff를 보면 알 수 있는 내용은 생략)
- 단, 설계 판단이 들어간 경우(왜 이 구조를 선택했는지)는 한 줄로 근거를 남긴다
- 탐색 중간 결과를 전부 나열하지 않고, 최종 결론만 보고한다

### 세션 관리
- 단일 세션에서 서로 독립적인 작업을 연속 수행하지 않는다 — 작업 단위별로 세션을 분리한다
- 컨텍스트가 커졌다고 느끼면 /compact 실행을 사용자에게 권고한다

## 관련 문서

- 아키텍처: [`docs/context/architecture.md`](docs/context/architecture.md) _(설계 후 작성 예정)_
- 설계 결정: [`docs/context/decisions.md`](docs/context/decisions.md)
- 파일 맵: [`docs/context/MAP.md`](docs/context/MAP.md)
- 요구사항 정의서: 별도 관리 (xlsx)
