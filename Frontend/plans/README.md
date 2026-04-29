# Frontend Plans

Phase 단위 작업 PLAN 파일을 보관한다. Orchestrator agent 가 이 디렉토리의 PLAN 을 순차 실행한다.

## 파일 명명 규칙

```
PLAN_{NN}_{도메인}.md
```

- `NN`: 두 자리 Phase 번호 (00=부트스트랩, 01~07=핵심 7화면, 08~=후속 작업)
- `도메인`: kebab-case 한 단어 (`bootstrap`, `landing`, `auth`, `dashboard`, `usage`, `cashback`, `settings`, `insights`)

## 현재 상태

| Phase | 도메인 | 상태 | 비고 |
|---|---|---|---|
| 00 | bootstrap | **작성 완료** | Vite 스캐폴드 + 7 라우트 placeholder + Sidebar/Topbar + AuthGuard 골격 |
| 01 | landing | 미작성 | `/` 비로그인 진입점 (디자인 변형 B) |
| 02 | auth | 미작성 | OAuth 2.0 / JWT httpOnly 쿠키 (변형 A) |
| 03 | dashboard | 미작성 | 분석형 (변형 C: 좌 차트 + 우 KPI) |
| 04 | usage | 미작성 | 종합 분석 (변형 A: 가전별 분해 + 24h 라인) |
| 05 | cashback | 미작성 | 목표 트래커 (변형 C: 진행바 + 미션) |
| 06 | settings | 미작성 | 사이드바 6 탭 (변형 A+B+C+D+E 결합) |
| 07 | insights | 미작성 | AI 진단 요약 (변형 A) |

> 화면 변형 확정 매핑은 [`../docs/screen_variants.md`](../docs/screen_variants.md) 참조. 관리자 콘솔(08)은 Phase 0 범위에서 제외.

## 작성 순서

1. PLAN_00_BOOTSTRAP.md 부터 시작 (스캐폴드 부재 → 코드 작성 불가).
2. 인증(02) 완료 후 보호 라우트가 필요한 03~07 진행.
3. 랜딩(01)은 `/` 비로그인이라 02 와 병렬 가능 — 단 AuthGuard 가 인증 시 `/home` 으로 redirect 하는 분기는 02 종료 후 검증.
4. 새 Phase 시작 시 이 README 의 표 갱신.

## 템플릿

[PLAN_TEMPLATE.md](PLAN_TEMPLATE.md) 복사 후 작성.
