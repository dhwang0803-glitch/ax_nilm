# Frontend Phase Reports

Phase TDD 사이클 완료 후 Reporter agent 가 생성하는 결과 리포트를 보관한다.

## 파일 명명 규칙

```
phase{NN}_report.md
```

- `NN`: 두 자리 Phase 번호 (PLAN 파일과 동일)
- 한 Phase 당 한 파일. 재실행 시 덮어쓰기 (히스토리는 git log).

## 작성자

[Reporter Agent](../agents/REPORTER.md) — Orchestrator 가 호출.

## 보고서 구조

[REPORT_TEMPLATE.md](REPORT_TEMPLATE.md) 참조.
