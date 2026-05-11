# Frontend Phase {NN} — {간단 제목}

> 작성일: YYYY-MM-DD
> 브랜치: Frontend
> 도메인: {auth | dashboard | usage | cashback | insights | bootstrap | ...}

---

## 1. 목표

한 문장으로 이 Phase 가 끝났을 때 사용자가 할 수 있게 되는 것을 기술.

예: "사용자가 이메일/비밀번호로 로그인하고, 로그아웃할 수 있다."

---

## 2. 화면 / 라우트

| 라우트 | 컴포넌트 | 접근 권한 | 비고 |
|---|---|---|---|
| `/auth/login` | `LoginPage` | public | OAuth 버튼 + 폼 |
| `/auth/callback` | `OAuthCallbackPage` | public | OAuth provider redirect |

라우트가 없는 Phase (예: 부트스트랩)는 "해당 없음" 명시.

---

## 3. 컴포넌트 트리 / 와이어프레임

```
LoginPage
├── AuthLayout
├── OAuthButtons (Kakao, Naver, Google)
├── LoginForm
│   ├── EmailField
│   ├── PasswordField
│   └── SubmitButton
└── SignupLink
```

또는 Figma/이미지 링크 첨부.

---

## 4. API 엔드포인트 의존

| 엔드포인트 | 메서드 | 용도 | 백엔드 상태 |
|---|---|---|---|
| `/auth/login` | POST | 로그인 | 미배포 → MSW 모킹 |
| `/auth/me` | GET | 세션 확인 | 미배포 → MSW 모킹 |
| `/auth/logout` | POST | 로그아웃 | 미배포 → MSW 모킹 |

백엔드 미배포 엔드포인트는 `tests/fixtures/handlers.ts` 에 MSW handler 작성. 본 Phase 종료 후 백엔드 배포되면 통합 테스트.

---

## 5. 인수 기준 (Acceptance)

- [ ] 사용자 시나리오 1: ...
- [ ] 사용자 시나리오 2: ...
- [ ] 모바일 뷰포트(375×667)에서 가로 스크롤 없음
- [ ] 키보드 네비게이션으로 폼 제출 가능
- [ ] 로딩/에러/빈 상태 3분기 표시

---

## 6. E2E 골든 패스

```
1. 사용자가 /auth/login 진입
2. 이메일/비밀번호 입력
3. 로그인 버튼 클릭
4. /  대시보드로 이동
5. 다시 /auth/login 으로 가도 자동 redirect (이미 로그인됨)
```

`tests/e2e/{domain}.spec.ts` 에 1건 이상 작성.

---

## 7. 의존 / 선행 조건

- 선행 Phase: PLAN_00_BOOTSTRAP (Vite 스캐폴드 완료)
- 백엔드 의존: API_Server `/auth/*` 엔드포인트 (없으면 MSW 모킹)
- 디자인 시스템: 본 Phase 에서 추가될 공용 컴포넌트 — `Button`, `TextField`

---

## 8. 범위 제외

- (Phase 01 예시) 비밀번호 재설정 플로우 — Phase 별도 진행
- (공통) 다국어(i18n) 도입 — 후속

---

## 9. 위험 / 미정 사항

- OAuth 콜백 URL 등록 절차 — 백엔드 팀 확인 필요
- Refresh token 만료 시 silent refresh 정책 — API_Server 응답 형식 확정 후 결정
