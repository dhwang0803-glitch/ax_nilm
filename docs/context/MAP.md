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
└── {브랜치명}/                 — 브랜치별 작업 디렉토리 (post-checkout 자동 생성)
```
