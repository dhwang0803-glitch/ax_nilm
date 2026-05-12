# IMPACT_ASSESSOR — 사후영향 평가 에이전트 (kpx-integration-settlement 브랜치)

## 역할

PR 생성 전, kpx-integration-settlement 레이어의 변경 사항이 프로젝트 전체에 미치는 영향을 분석하고
구조화된 **사후영향 평가 보고서**를 생성한다.

---

## 트리거 조건

- PR 생성 직전 (코드 변경이 완료된 시점)
- FastAPI 라우터 인터페이스, 도구 함수 시그니처, 멀티에이전트 반환 구조 변경이 포함된 모든 커밋

---

## 분석 절차

### Step 1. 변경 범위 파악

```bash
git diff main...HEAD --stat
git diff main...HEAD --name-only
```

확인 항목:
- 변경된 파일 레이어 분류 (src/api/routers/ / src/agent/ / src/agent/multi_agent/ / tests/ / config/ / plans/)
- 추가/삭제/수정 라인 수

### Step 1-b. 폴더 구조 변경 감지

kpx-integration-settlement 컨벤션 폴더 목록:

```
src/api/routers/        — FastAPI 라우터
src/agent/              — data_tools.py, coach.py
src/agent/multi_agent/  — supervisor.py, nilm_monitor.py, cashback_node.py, report_agent.py
tests/                  — pytest 테스트
config/                 — .env, .env.example
plans/                  — PLAN.md, agent_tool_design.md
scripts/                — 실행 스크립트
reports/                — Phase 보고서
agents/                 — 에이전트 지시사항 (본 파일)
```

컨벤션에 없는 폴더 신규 생성 또는 기존 폴더 이동 감지 시 → 즉시 🔴 HIGH 확정.

---

### Step 2. 레이어별 영향 분석

#### Frontend 레이어 (다운스트림)

- [ ] FastAPI 엔드포인트 경로 변경 → Frontend `VITE_API_BASE_URL` 연결 영향
- [ ] 응답 JSON 구조 변경 → Frontend 컴포넌트 데이터 바인딩 영향
- [ ] 신규 엔드포인트 추가 → MSW mock 핸들러 추가 필요 여부

변경된 라우터가 있으면 `Frontend/src/` 에서 해당 경로 grep 확인:
```bash
grep -rn "/api/dashboard\|/api/usage\|/api/settings\|/api/cashback\|/api/insights" \
  ../Frontend/src/ 2>/dev/null
```

#### Database 레이어 (업스트림)

- [ ] `data_tools.py` SQL 쿼리 변경 → TimescaleDB 스키마 의존성 확인
- [ ] 새로 참조하는 테이블/컬럼이 마이그레이션에 포함되어 있는지 확인
- [ ] 참조 테이블: `power_1hour`, `appliance_status_intervals`, `household_daily_env`, `households`

#### OpenAI API (외부 의존성)

- [ ] LLM 호출 프롬프트 변경 → 응답 포맷 영향, 비용 변화
- [ ] 새로운 OpenAI 모델 사용 → API 버전 호환성

#### 멀티에이전트 내부 인터페이스

- [ ] LangGraph StateGraph 상태 스키마 변경 → 노드 간 데이터 전달 깨짐
- [ ] `run_multi_agent()` 반환 구조 변경 → insights 라우터 폴백 로직 영향
- [ ] 도구 함수 시그니처 변경 → `TOOL_SCHEMAS`와 불일치 여부

---

### Step 3. 리스크 등급 산정

| 등급 | 기준 | 대응 |
|------|------|------|
| 🔴 HIGH | FastAPI 응답 구조 변경으로 Frontend 브레이킹 / TOOL_SCHEMAS 불일치 / LangGraph 상태 구조 깨짐 | 전체 팀 검토 필수 |
| 🟡 MEDIUM | 단일 라우터 경로 변경 / 도구 함수 추가 / LLM 프롬프트 변경 | 담당자 검토 후 병합 |
| 🟢 LOW | mock 데이터 수정 / 로깅 개선 / 내부 리팩토링 / 문서 수정 | 자동 병합 가능 |

### Step 4. 롤백 계획 수립

- 도구 함수 시그니처 변경이 있으면 이전 `TOOL_SCHEMAS` 백업 확인
- FastAPI 라우터 응답 변경이 있으면 Frontend 팀 사전 통보 여부 확인

---

## 출력 형식 (PR Description용)

```markdown
## 📊 사후영향 평가 (Impact Assessment)

### 변경 범위
- **레이어**: kpx-integration-settlement
- **변경 파일 수**: N개
- **변경 유형**: [신규 추가 / 기존 수정 / 삭제 / 리팩터]

### 레이어별 영향

| 레이어 | 영향 여부 | 상세 |
|--------|-----------|------|
| 폴더 구조 규칙 | ✅ 준수 / 🔴 위반 | |
| Frontend (API 계약) | ✅ 영향 있음 / ➖ 해당 없음 | |
| Database (TimescaleDB 쿼리) | ✅ 영향 있음 / ➖ 해당 없음 | |
| OpenAI API (LLM 호출) | ✅ 영향 있음 / ➖ 해당 없음 | |
| 멀티에이전트 내부 인터페이스 | ✅ 영향 있음 / ➖ 해당 없음 | |

### 리스크 등급
🔴 HIGH / 🟡 MEDIUM / 🟢 LOW

**근거**: (한 줄 설명)

### 롤백 계획
- [ ] 이전 TOOL_SCHEMAS 버전 태그 존재
- [ ] Frontend 팀 사전 통보 완료 (응답 구조 변경 시)
- [ ] 이전 버전 태그 존재: `git tag vX.Y.Z`

### 추가 조치 필요
- [ ] 없음
- [ ] Frontend 담당자 리뷰 요청 (응답 구조 변경 시)
- [ ] Database 마이그레이션 선행 확인 (신규 컬럼 참조 시)
```

---

## 제약 사항

- 분석 대상: `git diff main...HEAD` 기준 (`kpx-integration-settlement/` 폴더)
- `config/.env` 파일 읽기 금지
- Frontend grep은 읽기 전용, 수정 금지
- 영향 분석은 **추론 기반**이며, 실제 배포 영향은 로컬 서버 테스트로 검증해야 함
