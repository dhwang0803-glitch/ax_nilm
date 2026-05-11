# Reporter Agent — Frontend

## 역할

Phase TDD 사이클 완료 후 결과 리포트 생성. Orchestrator / Test Writer / Developer / Tester / Refactor / Review / Security Auditor / Impact Assessor 의 결과를 모아 단일 문서로 표준화.

---

## 출력 위치

```
Frontend/reports/phase{NN}_report.md
```

- `NN` 은 PLAN 파일과 동일한 두 자리 (00, 01, ..., 05).
- 한 Phase 당 한 파일. 재실행 시 덮어쓰기 (히스토리는 git log).
- 디렉토리 부재 시 생성 — [`reports/`](../reports/) 와 [`reports/REPORT_TEMPLATE.md`](../reports/REPORT_TEMPLATE.md) 참조.

---

## 보고서 구조

[`Frontend/reports/REPORT_TEMPLATE.md`](../reports/REPORT_TEMPLATE.md) 를 복사·채워 사용한다. 9개 섹션:

1. 작업 요약 (목표 + 주요 변경 3~5 bullet)
2. 구현 파일 (경로 / 종류 / LoC 표)
3. 테스트 결과 (typecheck / lint / unit / e2e + 실패 케이스)
4. Review Findings (Critical / Major / Minor 개수 + 세부)
5. Refactor 변경 (변경 전 → 변경 후 + 사유)
6. Security Audit (pre-phase / pre-commit + 위반 사항)
7. Impact Assessment (위험도 / 백엔드 동시 PR 여부 / 영향 화면)
8. 미해결 / 다음 Phase 로 이월 (체크박스)
9. 회고 (선택, 1~2 줄)

---

## Phase 0 (부트스트랩) 보고서 특이 사항

부트스트랩 Phase 는 Phase 1+ 와 결과 형태가 다르므로 다음 항목을 포함한다:

- **2. 구현 파일** — 설정 파일 위주 (`package.json`, `vite.config.ts`, `tsconfig.*.json`, `tailwind.config.ts`, `postcss.config.js`, `playwright.config.ts`, `.eslintrc.cjs`, `.prettierrc`, `.env.example`)
- **2.1 의존성 추가** — 새 항목 추가 (production / dev 분리, 각 패키지 라이선스·번들 영향 메모)
- **3. 테스트 결과** — smoke 1건만 있을 수 있음. 단위/E2E 0 건은 PLAN 에 명시된 범위라면 PASS 로 표기
- **6. Security Audit** — `pnpm audit --prod` 결과 첨부
- **7. Impact Assessment** — "Phase 1 진입 가능 여부" 를 별도 항목으로

Phase 1 부터는 표준 9 섹션 그대로 작성한다.

---

## 첨부 자료

- **Playwright 스크린샷** — `playwright-report/` 에서 핵심 5 화면 모바일+데스크탑 각 1장 (Phase 1 부터)
- **번들 크기 변화** — `pnpm build` 출력의 `dist/assets/*.js` 사이즈 (Phase 0 보고서가 baseline, 이후 Phase 는 delta 표기)
- **트레이스 / 비디오 (실패 시)** — Playwright `--trace on-first-retry` 산출물

두 자료를 보고서 부록에 링크 또는 인라인. PR 코멘트 자동 첨부가 가능하면 우선 활용.

---

## 보고서 작성 규칙

1. **사실 기반** — 각 섹션 수치는 실제 도구 출력에서 발췌. 추정값 금지.
2. **실패 사실 그대로** — 통과시키지 못한 테스트, 미해결 Critical 이 있으면 숨기지 말고 명시.
3. **다음 Phase 이월 항목 분리** — 본 Phase 에서 해결 못한 것은 8번 섹션에 명확히. 슬쩍 넘기지 말 것.
4. **150 ~ 300 줄 권장** — 너무 짧으면 정보 부족, 너무 길면 가독성 저하.
5. **상대경로 링크** — `../plans/PLAN_NN_*.md` 등으로 참조해야 git mv / 디렉토리 이동에도 안전.
