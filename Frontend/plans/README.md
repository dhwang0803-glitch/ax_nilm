# Frontend Plans

Phase 단위 작업 PLAN 파일을 보관한다. Orchestrator agent 가 이 디렉토리의 PLAN 을 순차 실행한다.

## 파일 명명 규칙

```
PLAN_{NN}_{도메인}.md
```

- `NN`: 두 자리 Phase 번호 (00=부트스트랩, 01~05=핵심 5화면, 06~=후속 작업)
- `도메인`: kebab-case 한 단어 (`bootstrap`, `auth`, `dashboard`, `usage`, `cashback`, `insights`)

## 현재 상태

| Phase | 도메인 | 상태 | 비고 |
|---|---|---|---|
| 00 | bootstrap | 미작성 | Vite 스캐폴드 + 기본 인프라 |
| 01 | auth | 미작성 | OAuth 2.0 / JWT httpOnly 쿠키 |
| 02 | dashboard | 미작성 | 월간 요약 / 알림 카운트 |
| 03 | usage | 미작성 | 가전별 분해 차트 |
| 04 | cashback | 미작성 | KEPCO 에너지캐시백 |
| 05 | insights | 미작성 | 이상탐지 + LLM 추천 |

## 작성 순서

1. PLAN_00_BOOTSTRAP.md 부터 시작 (스캐폴드 부재 → 코드 작성 불가).
2. 인증(01) 완료 후 보호 라우트가 필요한 02~05 진행.
3. 새 Phase 시작 시 이 README 의 표 갱신.

## 템플릿

[PLAN_TEMPLATE.md](PLAN_TEMPLATE.md) 복사 후 작성.
