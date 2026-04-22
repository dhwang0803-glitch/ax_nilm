# 파일/디렉토리 맵

> 상위 구조 지도. 파일이 추가될 때마다 갱신하지 않는다.
> 갱신 트리거: 새 최상위 폴더/브랜치가 생길 때만.

## 최상위 구조

```
ax_nilm/
├── CLAUDE.md                  — 프로젝트 전역 Claude Code 지침
├── _claude_templates/         — 브랜치별 CLAUDE.md 템플릿
├── _agent_templates/          — 에이전트 역할 문서 (9종)
├── .claude/commands/          — 커스텀 슬래시 커맨드 (PR-report)
├── .githooks/                 — Git 훅 (post-checkout)
├── .github/                   — PR 템플릿
├── docs/
│   ├── context/               — 공유 지식 베이스 (architecture, ADR, MAP)
│   └── class-diagrams/        — 요구사항별 클래스 다이어그램 (.drawio)
├── Database/                  — 데이터 레이어 브랜치 작업 폴더
│   ├── schemas/               — DDL (001_core, 002_timeseries, 003_seed)
│   ├── migrations/            — 스키마 변경 이력 (YYYYMMDD_*.sql)
│   ├── src/                   — Repository · ORM 모델 (import 전용)
│   ├── scripts/               — ETL · 검증 실행 스크립트
│   ├── tests/                 — pytest
│   ├── docs/                  — 스키마 설계 근거 · 데이터셋 명세
│   └── agents/                — 에이전트 역할 문서 사본
└── {다른 모듈 브랜치}/          — API_Server / Execution_Engine / Frontend 등
                                 (post-checkout 훅이 각 브랜치 진입 시 자동 생성)
```

## 브랜치 ↔ 폴더 대응

| 브랜치 | 최상위 폴더 | 상태 |
|--------|-------------|------|
| `main` | (통합 브랜치, 전체 루트) | — |
| `docs` | `docs/context/` 만 편집 | 활성 |
| `Database` | `Database/` | 활성 |
| `API_Server` | `API_Server/` | 미착수 |
| `Execution_Engine` | `Execution_Engine/` | 미착수 |
| `Frontend` | `Frontend/` | 미착수 |

각 모듈 브랜치의 내부 규칙은 `_claude_templates/CLAUDE_{브랜치명}.md` 참조.
