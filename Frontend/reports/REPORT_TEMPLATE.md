# Frontend Phase {NN} — {간단 제목}

> 생성: YYYY-MM-DD HH:MM
> 브랜치: Frontend
> PLAN: [Frontend/plans/PLAN_{NN}_{도메인}.md](../plans/PLAN_{NN}_{도메인}.md)

---

## 1. 작업 요약

- 목표: <PLAN 의 한 줄 요약>
- 주요 변경: <3~5개 bullet>

## 2. 구현 파일

| 파일 | 종류 | LoC |
|---|---|---|
| src/features/{domain}/components/{Component}.tsx | 컴포넌트 | 0 |
| src/features/{domain}/api.ts | API hook | 0 |
| ... | | |

> Phase 00 (부트스트랩) 의 경우: package.json, vite.config.ts, tsconfig.json, tailwind.config.ts 등 설정 파일 위주.

## 3. 테스트 결과

- typecheck: PASS / FAIL (에러 N)
- lint: PASS / FAIL (경고 N)
- unit: PASS N / FAIL M / SKIP K (소요 Xs)
- e2e: PASS N / FAIL M (소요 Ys)
- 커버리지 요약: lines X% / functions Y%

실패 케이스 (있을 때):
- <파일:테스트명> — <원인>

## 4. Review Findings

- Critical: <개수> — <요약>
- Major: <개수>
- Minor: <개수>
- 보안 위임: yes/no

세부 (Critical/Major):
- [Critical] <파일:라인> — <설명>
- [Major]    ...

## 5. Refactor 변경

- <파일>: <변경 전> → <변경 후> (사유)

## 6. Security Audit

- pre-phase: PASS / FAIL
- pre-commit: PASS / FAIL
- 위반 사항: <있다면 리스트>

## 7. Impact Assessment

- 위험도: High / Medium / Low
- 백엔드 동시 PR 필요: yes/no
- 영향 받는 화면: <리스트>

## 8. 미해결 / 다음 Phase 로 이월

- [ ] <항목 1>
- [ ] <항목 2>

## 9. 회고 (선택)

- 잘된 점 / 개선할 점 — 1~2 줄
