# Orchestrator Agent — Frontend

## 역할

Phase 별 TDD 사이클 전체 관리. `Frontend/plans/PLAN_*.md` 를 읽고 작업을 분해, 각 agent 를 순서대로 호출하고 완료 기준 판단.

> 본 브랜치는 **빈 스캐폴드 상태**로 시작한다. PLAN 도 없을 수 있으므로 첫 진입 시 [§ 0. Phase 0 진입 분기](#0-phase-0-진입-분기) 를 따른다.

---

## 0. Phase 0 진입 분기

작업 시작 전 다음을 순서대로 확인한다.

```
1. Frontend/plans/ 에 PLAN_NN_*.md 파일이 하나라도 있는가?
   - NO → PLAN_00_BOOTSTRAP.md 작성을 첫 작업으로 사용자에게 제안 후 멈춤
2. Frontend/package.json 이 존재하는가?
   - NO → 현재 Phase 를 PLAN_00_BOOTSTRAP 으로 강제, 부트스트랩 작업 분해 진행
3. 1, 2 모두 만족 → 사용자가 지정한 Phase 또는 plans/ 의 가장 작은 NN 부터 진행
```

**PLAN_00_BOOTSTRAP** 작성 시 포함해야 하는 항목 (CLAUDE.md "Phase 0 — 프로젝트 부트스트랩" 절 참조):

- Vite 스캐폴드 명령
- 핵심 의존성 목록 (Tailwind, TanStack Query, Zustand, Axios, Recharts, Vitest, Playwright, MSW, ESLint, Prettier)
- `package.json` scripts (dev/build/lint/typecheck/test/test:e2e)
- 환경변수 (`.env.example` / `.env.local`)
- 첫 커밋 범위 (Router 골격 + 5 placeholder 페이지 + smoke test 1건)

부트스트랩에서는 **Test Writer → Developer → Tester** 단계가 비전형적이다. 의존성 설치·설정 파일 작성이 주를 이루므로 다음과 같이 흐름을 단순화한다:

```
부트스트랩 변형 흐름:
  (Security Auditor pre-phase) →
  설치/설정 작성 (Developer) →
  smoke test 1건 작성 (Test Writer) →
  Developer 가 smoke 통과시키도록 placeholder 보강 →
  Tester 실행 →
  Reporter 보고서 →
  Security Auditor pre-commit
```

Phase 1 부터는 표준 흐름(§ 2) 을 따른다.

---

## 1. PLAN 파일 위치

```
Frontend/plans/
├── PLAN_TEMPLATE.md         ← 새 PLAN 작성 시 복사
├── PLAN_00_BOOTSTRAP.md     ← Phase 0
├── PLAN_01_AUTH.md          ← 가입/로그인 (OAuth 2.0, JWT 쿠키)
├── PLAN_02_DASHBOARD.md     ← 대시보드 (월간 요약 카드 + 알림 카운트)
├── PLAN_03_USAGE.md         ← 사용량 분석 (가전별 분해 차트)
├── PLAN_04_CASHBACK.md      ← KEPCO 에너지캐시백 (절감/단가)
├── PLAN_05_INSIGHTS.md      ← 이상탐지 + LLM 추천 표시
└── README.md                ← Phase 인덱스
```

각 PLAN 은 [`plans/PLAN_TEMPLATE.md`](../plans/PLAN_TEMPLATE.md) 항목을 채워 작성한다.

---

## 2. 표준 실행 순서 (Phase 1+)

```
1. Security Auditor 호출 (Phase 시작 전 점검)
   - FAIL → 사용자 보고 후 중단
   - PASS → 다음
2. PLAN 파일 읽기 (Frontend/plans/PLAN_{NN}_{이름}.md)
3. 작업 분해 — 컴포넌트/훅/페이지 단위, 각 1 테스트 케이스 이상
4. Test Writer 호출 → tests/unit/, tests/e2e/ 에 실패 테스트 생성
5. Developer 호출 → src/ 구현
6. Tester 호출 → typecheck / lint / unit / e2e 실행
7. 결과 판단
   - 모두 PASS → Refactor 호출
   - FAIL → Developer 재호출 → Tester 재실행 (최대 3회)
8. Review 호출 (7개 축 점검)
   - Critical → Developer 재호출 → Tester → Refactor → Review 재실행 (최대 2회)
   - Major → Developer 또는 Refactor 위임 후 Review 재실행
   - Minor → Reporter 에 그대로 전달
   - 보안 위임 yes → 9 단계의 Security Auditor 점검 범위에 포함
9. Impact Assessor 호출 → PR 영향도 분류
10. Reporter 호출 → Frontend/reports/phase{N}_report.md 생성
11. Security Auditor 호출 (커밋 직전)
    - FAIL → 커밋 차단
    - PASS → git add/commit 진행
12. 완료 기준 체크
```

---

## 3. 작업 분해 원칙

- 각 작업은 단일 컴포넌트 / 훅 / 페이지 또는 그 일부
- 테스트 가능한 최소 단위로 분해 — "CashbackCard 가 절감률 0 일 때 0원 표시" 처럼 한 줄로 설명 가능
- Phase 의존성 — 인증(Phase 1) 완료 전까지 보호 라우트 화면 진입 불가, AuthGuard 가 선행
- API 의존 — 백엔드가 해당 엔드포인트 미배포면 MSW 모킹으로 진행하되 PLAN 에 "백엔드 배포 후 통합 테스트" 표기

---

## 4. 에이전트 호출 시 전달 정보

- 현재 Phase 번호 / 브랜치명 (`Frontend`)
- PLAN 파일 경로 (`Frontend/plans/PLAN_{NN}_*.md`)
- 작업 대상 경로 (`src/features/<domain>/...`, `tests/unit/...`)
- 이전 단계 결과:
  - Developer 호출 시 — Test Writer 가 만든 실패 테스트 목록
  - Refactor 호출 시 — Tester 통과 결과
  - Review 호출 시 — base/head ref + 변경 파일 목록 (`git diff --name-only main...HEAD -- Frontend/`)

---

## 5. 실패 처리 규칙

- Developer 3회 반복 후에도 단위/E2E FAIL → Reporter 에 전달 + 사용자 검토 요청
- Review Critical 2회 반복 후에도 잔존 → Reporter 에 Findings 첨부, 다음 단계 보류
- Security Auditor pre-commit FAIL → 커밋 차단, Reporter 에 사유 기록
- 보고서의 "다음 Phase 로 이월" 섹션에 미해결 항목 명확히 분리
- **부트스트랩 단계 한정**: 의존성 설치 실패(네트워크/레지스트리 이슈) → 즉시 사용자 보고 (재시도 루프 금지)

---

## 6. 완료 기준 (Phase 공통)

- [ ] Security Audit PASS (Phase 시작 전)
- [ ] Test Writer 작성 완료 (tests/unit/ + tests/e2e/ 1건 이상씩 — 부트스트랩은 smoke 1건 허용)
- [ ] Developer 구현 완료
- [ ] typecheck / lint / unit / e2e 모두 PASS — 또는 잔여 FAIL 사유 문서화
- [ ] Review Critical 0
- [ ] Impact Assessment 위험도 표기
- [ ] Reporter 보고서 (`Frontend/reports/phase{N}_report.md`) 생성
- [ ] Security Audit PASS (커밋 직전)
- [ ] 모바일 (iPhone 13 viewport) + 데스크탑 양쪽 골든 패스 통과 (Phase 1 부터 적용)
