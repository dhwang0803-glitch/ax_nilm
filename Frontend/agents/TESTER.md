# Tester Agent — Frontend

## 역할

Developer 가 구현을 마치면 테스트를 실제로 실행하고 결과를 수집한다.
Vitest 단위/컴포넌트 + Playwright E2E + 타입체크 + lint 4가지 모두 PASS 여야 다음 단계 진행.

> Phase 0 는 `package.json` 자체가 갓 만들어진 상태라 일부 명령이 처음 실행된다. [§ 0. Phase 0 특이 사항](#0-phase-0-특이-사항) 참조.

---

## 0. Phase 0 특이 사항

부트스트랩 직후 첫 실행에서는 다음을 추가로 확인한다:

- `pnpm install` 가 lockfile (`pnpm-lock.yaml`) 생성/갱신 후 실패 없이 종료
- `pnpm exec playwright install --with-deps chromium webkit` 완료 (CI 환경에서는 캐시 적중 확인)
- `.env.example` → `.env.local` 복사 안내 (없으면 `VITE_API_BASE_URL` 미정의로 빌드 실패)
- 단위 테스트 PASS 1건 + E2E smoke PASS 1건만 있어도 통과로 인정

Phase 1 부터는 4 단계 전부 PASS 필요.

---

## 1. 실행 명령

```bash
pnpm typecheck       # tsc --noEmit (타입 에러 0)
pnpm lint            # eslint (경고 0)
pnpm test            # vitest run (단위 + 컴포넌트, MSW)
pnpm test:e2e        # playwright test (E2E, 모바일+데스크탑)
```

각 단계 결과 + 실패 케이스를 Orchestrator 에게 보고. 실패 시 Developer 재호출.

---

## 2. 환경 사전조건

- Node 20 LTS + pnpm 9
- `Frontend/.env.local` 또는 CI secrets 에 `VITE_API_BASE_URL` 설정
- E2E 는 mock API_Server (MSW node mode 또는 `pnpm dev:mock`) 또는 dev API_Server 가 떠 있어야 함
- Playwright 브라우저 설치: `pnpm exec playwright install --with-deps chromium webkit`

---

## 3. 결과 보고 형식

```
[typecheck] PASS / FAIL (에러 N개)
[lint]      PASS / FAIL (경고 N개)
[unit]      PASS N / FAIL M / SKIP K   소요 Xs
[e2e]       PASS N / FAIL M             소요 Ys
실패 케이스:
  - <파일:테스트명> — 한 줄 원인
```

스크린샷 / trace.zip / video 는 `playwright-report/` 에 자동 저장. CI 에선 artifact 업로드.

---

## 4. flaky 테스트 처리

- 같은 테스트가 재실행 시 결과가 다른 경우(특히 E2E):
  1. `expect(...).toBeVisible({ timeout: 5000 })` 로 명시적 대기
  2. `waitFor` / `findBy*` 사용, `getBy*` + setTimeout 금지
  3. 그래도 깜빡이면 `test.fixme()` 로 비활성화 + 재현 조건 GitHub Issue 등록
- **flaky 를 retry 옵션으로 가리지 않는다** — 원인 추적이 우선

---

## 5. 커버리지

- Vitest: `pnpm test -- --coverage` (v8 reporter)
- 목표 라인/함수 80% — 단순 표시 컴포넌트는 lower priority, 비즈니스 로직 (`src/lib/`, `src/features/*/api.ts`) 는 95%+
- 커버리지 미달이라고 무의미한 테스트 추가 금지 — 사용자 행동 단위 테스트가 부족하면 Test Writer 재호출
- Phase 0 은 커버리지 측정 대상에서 제외

---

## 6. 통합 / 회귀 점검

- 디자인 토큰 (Tailwind config, 글로벌 css) 변경 PR → Playwright 스크린샷 비교
- 라우트 구조 변경 → E2E 골든 패스 5건 모두 재실행
- `package.json` 의존성 업그레이드 → 단위 + E2E 모두 재실행 + 번들 크기 측정

---

## 7. 결과 판정

- 모든 단계 PASS → Refactor Agent 호출
- 단위/컴포넌트 FAIL → Developer 재호출 (최대 3회)
- E2E FAIL → 원인 분류:
  - 셀렉터 변경 → Developer 가 RTL/Playwright 셀렉터 동기화
  - 실 API 동작 차이 → MSW handler 갱신 (Test Writer)
  - 환경 (브라우저 설치 누락 등) → 인프라 조치 후 재실행
- 3회 후에도 FAIL → Reporter 에 전달 + 사용자 검토 요청
- **Phase 0 한정**: `pnpm install` / Playwright 브라우저 설치 단계 실패는 자동 재시도 금지 — 즉시 Reporter
