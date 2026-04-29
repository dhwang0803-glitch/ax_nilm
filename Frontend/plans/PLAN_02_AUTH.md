# Frontend Phase 02 — 로그인 / 회원가입 본 구현

> 작성일: 2026-04-29
> 브랜치: Frontend
> 도메인: auth
> 디자인 변형: **A (좌우 분할)** — `Frontend/docs/screen_variants.md` 확정안
> 데드라인 컨텍스트: 2026-05-18 공모전 출품 (오늘 -29 기준 19일)

---

## 1. 목표

비로그인 사용자가 `/auth/login` 진입 시 좌우 분할 디자인이 렌더되어, 이메일/비밀번호 또는 카카오/네이버/Google SSO 로 로그인하면 useAuth 에 user 가 주입되어 `/home` 또는 origin `from` 으로 redirect 된다. 같은 디자인 패턴으로 `/auth/signup` 회원가입도 동작. 로그아웃 시 useAuth.logout → `/auth/login` 으로 복귀.

본 Phase 는 백엔드 미배포 단계 — **MSW handler 모킹**으로 진행. 백엔드 합류 시 endpoint 만 실 서버로 전환.

---

## 2. 화면 / 라우트

| 라우트 | 컴포넌트 | 접근 권한 | 비고 |
|---|---|---|---|
| `/auth/login` | `LoginPage` | public | 인증 시 `/home` redirect |
| `/auth/signup` | `SignupPage` | public | 인증 시 `/home` redirect |
| `/auth/forgot` | (제외) | - | Phase 후속 — Phase 02 = 링크 placeholder, 클릭 시 toast "준비 중" |
| `/auth/oauth/:provider/callback` | (서버 사이드, 미구현) | - | Phase 02 = SSO 버튼 클릭 시 MSW 모킹으로 즉시 setUser |

라우트 자체는 Phase 0 에서 등록 완료 — 본 Phase 는 LoginPage / SignupPage 컴포넌트 본 구현.

---

## 3. 컴포넌트 트리

```
LoginPage / SignupPage
└── AuthLayout                           ← features/auth/components/AuthLayout.tsx
    ├── BrandPanel (좌측 다크)            ← features/auth/components/BrandPanel.tsx
    │   ├── 브랜드 "에너지캐시백"
    │   ├── h2 카피 (로그인=절약하세요 / 회원가입=시작 안내)
    │   └── ftnote "© 2026 ax_nilm · KEPCO 협력"
    └── <Outlet/> 또는 children            ← 우측 폼

LoginPage 의 우측:
  LoginForm                              ← features/auth/components/LoginForm.tsx
  ├── EmailField, PasswordField          ← features/auth/components/Field.tsx (재사용)
  ├── 자동 로그인 체크박스 + 비밀번호 찾기 링크
  ├── "로그인" primary 버튼
  ├── "또는" 구분선
  ├── OAuthButtons (카카오/네이버/Google)  ← features/auth/components/OAuthButtons.tsx
  └── "처음이신가요? 회원가입 →" 링크

SignupPage 의 우측:
  SignupForm                             ← features/auth/components/SignupForm.tsx
  ├── EmailField, PasswordField, PasswordConfirmField, NameField
  ├── KEPCO 고객번호 필드 (선택, "나중에 하기" 체크박스 포함)
  │   └── "나중에 하기" 체크 시 안내문 표시: "설정 > 계정 > 한전 연동에서 추후 입력 가능합니다"
  ├── 약관 동의 체크박스 (Phase 02 = 단일 통합 체크박스)
  ├── "회원가입" primary 버튼
  ├── "또는" 구분선
  ├── OAuthButtons (재사용)
  └── "이미 계정이 있으신가요? 로그인 →" 링크
```

> AuthLayout/BrandPanel/Field/OAuthButtons 는 LoginPage + SignupPage 두 곳 사용 — 즉시 컴포넌트화 (3번째 등장 원칙의 예외, 명백한 1:1 재사용).

### 디자인 토큰 매핑

| 영역 | Tailwind 유틸 |
|------|--------------|
| 좌측 BrandPanel 배경 | `bg-ink-1 text-canvas` (다크) |
| 우측 폼 영역 | `bg-canvas` |
| 폼 필드 input | `border border-line-2 bg-canvas px-3 py-2 text-sm` |
| 폼 필드 label | `text-xs text-ink-3 font-mono uppercase tracking-wider` |
| primary 버튼 | `bg-ink-1 text-canvas border border-ink-1 px-4 py-2.5 text-sm w-full justify-center` |
| ghost 버튼 (SSO) | `border border-line-2 bg-canvas text-ink-1 px-4 py-2.5 text-sm w-full justify-center` |
| 구분선 "또는" | `flex-1 h-px bg-line-3` + `text-[11px] text-ink-3` |
| 회원가입 / 로그인 링크 | `text-xs text-ink-3` + 강조 부분 `font-semibold text-ink-1` |
| 에러 메시지 | `text-xs text-red-600` (그레이스케일 외 첫 강조 — 위험 색상은 시스템 기본 적색 허용 §9) |

---

## 4. API 엔드포인트 의존

| 엔드포인트 | 메서드 | 용도 | 상태 |
|---|---|---|---|
| `/auth/login` | POST | `{email, password}` → `{user, expiresAt}` (Set-Cookie httpOnly JWT) | 미배포 → MSW 모킹 |
| `/auth/signup` | POST | `{email, password, name, agreeTerms}` → `{user}` (자동 로그인) | 미배포 → MSW 모킹 |
| `/auth/me` | GET | 세션 확인 → `{user}` 또는 401 | 미배포 → MSW 모킹 |
| `/auth/logout` | POST | 쿠키 무효화 → 204 | 미배포 → MSW 모킹 |
| `/auth/oauth/:provider` | POST | provider in (kakao, naver) → `{user}` (Phase 02 = 즉시 성공 모킹) | 미배포 → MSW 모킹 |

본 Phase 의 `tests/fixtures/handlers.ts` 갱신:
- 5개 handler 추가 (200 응답, 메모리 내 user 저장소)
- 401 케이스 (잘못된 credentials) — 이메일이 `wrong@test.com` 일 때 401 반환
- 422 케이스 (signup 시 이메일 중복) — 이메일이 `taken@test.com` 일 때 422 반환

---

## 5. 인수 기준 (Acceptance)

### 로그인
- [ ] 비로그인에서 `/auth/login` 진입 → 좌우 분할 + 좌측 다크 BrandPanel + 우측 LoginForm 렌더
- [ ] 이메일 정규식 미통과 (`a@b` 등) → submit 차단 + inline 에러 "올바른 이메일 형식이 아닙니다"
- [ ] 비밀번호 8자 미만 → submit 차단 + "비밀번호는 8자 이상" 에러
- [ ] 정상 자격증명 (`test@example.com` / `password123`) → MSW 200 + useAuth.setUser → `/home` redirect
- [ ] 잘못된 자격증명 (`wrong@test.com`) → MSW 401 + "이메일 또는 비밀번호가 일치하지 않습니다" inline 에러
- [ ] "카카오로 시작하기" 클릭 → MSW `/auth/oauth/kakao` 200 + setUser + redirect
- [ ] "네이버로 시작하기" 클릭 → MSW `/auth/oauth/naver` 200 + setUser + redirect
- [ ] "Google로 시작하기" 클릭 → MSW `/auth/oauth/google` 200 + setUser + redirect
- [ ] "회원가입 →" 클릭 → `/auth/signup`
- [ ] "비밀번호 찾기" 클릭 → toast "준비 중" (`alert()` 또는 `console.warn` 임시)

### 회원가입
- [ ] 비로그인에서 `/auth/signup` 진입 → 좌우 분할 + 우측 SignupForm 렌더
- [ ] 이메일/비밀번호/비밀번호 확인/이름 4 필드 모두 채워야 submit 활성
- [ ] 비밀번호 ≠ 비밀번호 확인 → "비밀번호가 일치하지 않습니다" inline
- [ ] 약관 동의 미체크 → submit 차단
- [ ] 정상 → MSW 200 + setUser + `/home` redirect
- [ ] 이메일 중복 (`taken@test.com`) → MSW 422 + "이미 가입된 이메일입니다" inline
- [ ] "로그인 →" 링크 → `/auth/login`
- [ ] **KEPCO 고객번호**: 입력 시 검증 (10자리 숫자) → 정상 회원가입에 포함되어 전송
- [ ] **"나중에 하기" 체크 시**: KEPCO 필드 비활성화 + 안내문 "설정 > 계정 > 한전 연동에서 추후 입력 가능합니다" 표시 → 회원가입 시 KEPCO null 로 전송

### AuthGuard 동선 갱신
- [ ] 미인증 사용자가 `/usage` 진입 → `/auth/login` redirect (location state 에 `from = /usage`)
- [ ] 로그인 성공 → `from.pathname` 으로 redirect (없으면 `/home`)

### 로그아웃
- [ ] AppShell Topbar 의 아바타 클릭 → dropdown "로그아웃" 노출
- [ ] "로그아웃" 클릭 → MSW `/auth/logout` 204 + useAuth.logout + `/auth/login` redirect

### 공통
- [ ] `pnpm typecheck && lint && test && test:e2e --project=chromium && build` 모두 그린
- [ ] 비밀번호 input 은 `type="password"`, autocomplete `current-password` (login) / `new-password` (signup)
- [ ] 폼 필드 모두 `aria-label` 또는 `<label>` 명시 (WCAG 2.1 AA)
- [ ] 비밀번호 평문 console/Sentry 에 출력 0 (`feedback_design_ux_before_frontend_code.md` 의 보안 규칙)

---

## 6. E2E 골든 패스

```
[로그인 시나리오]
1. 비로그인 사용자가 /usage 진입 → /auth/login 으로 redirect (location.state.from = /usage)
2. 잘못된 자격증명 입력 → 401 에러 메시지 표시
3. 정상 자격증명 입력 → /usage (원래 가려던 곳) 로 자동 이동
4. AppShell + Topbar + 사용량 분석 placeholder 표시
5. Topbar 아바타 클릭 → "로그아웃" dropdown
6. 로그아웃 클릭 → /auth/login 으로 복귀

[회원가입 시나리오]
1. /auth/login 의 "회원가입 →" 클릭 → /auth/signup
2. 4 필드 + 약관 동의 → 회원가입 → /home 자동 이동
3. 이미 가입된 이메일 케이스 → 422 inline 에러
```

테스트 파일:
- `tests/e2e/auth.spec.ts` — 로그인/회원가입 E2E 3 케이스
- `tests/unit/loginForm.test.tsx` — Form validation 단위 테스트 (이메일 정규식, 비밀번호 길이, 401 처리)
- `tests/unit/signupForm.test.tsx` — Signup validation (비밀번호 일치, 약관 동의, 422)

---

## 7. 의존 / 선행 조건

- **선행 Phase**: PLAN_00 부트스트랩 (완료) + PLAN_01 랜딩 (PR #38 머지)
- **백엔드 의존**: 없음 (MSW 모킹). 백엔드 합류 시 `apiClient` baseURL 만 실 서버로 변경
- **신규 의존성**: `react-hook-form` + `@hookform/resolvers` + `zod` (사용자 결정 — 경험 보유). schema 중심 폼 검증 + 타입 추론 + Phase 06 settings 의 더 복잡한 폼 대비 인프라 미리 도입.
- **MSW 통합**: `tests/fixtures/handlers.ts` 갱신 + `src/main.tsx` 에 dev 모드 service worker 등록 추가
  - `pnpm exec msw init public/` 한 번 실행 → `public/mockServiceWorker.js` 생성 (커밋)
  - `src/main.tsx` 에 `if (import.meta.env.DEV) { import('./mocks/browser').then(({worker}) => worker.start()) }`
  - `src/mocks/browser.ts` 신규: `setupWorker(...handlers)` (handlers.ts 재사용)
  - 결과: `pnpm dev` 환경에서 실 fetch 가 자동으로 MSW handler 로 라우트됨

---

## 8. 범위 제외 (Out of Scope)

- **비밀번호 찾기 (`/auth/forgot`)** — 링크 placeholder + toast "준비 중", 본 구현 후속
- **자동 로그인 (Remember me)** — visual only, 실 동작 후속 (refresh token 정책 확정 필요)
- **OAuth provider 추가** — Kakao + 네이버 2개. Google 등 추가는 후속
- **이메일 인증 (verification)** — 가입 즉시 활성. 인증 메일 발송은 후속
- **2FA (TOTP)** — Phase 06-C 보안 탭에서 본 구현
- **세션 만료 UI** — 401 인터셉터 → `/auth/login` redirect 만 (Phase 0 구현). 토큰 만료 임박 알림은 후속
- **비밀번호 강도 미터** — Phase 06-C 비밀번호 변경 시 도입
- **CAPTCHA** — 공모전 단계 무시
- **모바일 반응형** — 데드라인 후 별도 PLAN_M

---

## 9. 결정 이력 (2026-04-29 사용자 확정)

§3~§8 본문에 모두 통합됨. 8건 결정 요약:

1. **OAuth 프로바이더**: **Kakao + 네이버 + Google** (3개)
2. **회원가입 디자인**: LoginA 좌우 분할 패턴 재사용 (좌측 BrandPanel 공유 + 우측 폼만 변경)
3. **회원가입 필드**: 이메일 / 비밀번호 / 비밀번호 확인 / 이름 / 약관 동의 + **KEPCO 고객번호 (선택, "나중에 하기" 옵션)**. 나중에 하기 선택 시 "설정 > 계정 > 한전 연동에서 추후 입력 가능" 안내문.
4. **MSW endpoint 5개**: `/auth/{login,signup,me,logout,oauth/:provider}` (provider in {kakao, naver, google})
5. **세션 방식**:
   - **dev**: MSW + useAuth.setUser 직접 주입. cookie 미사용. 새로고침 시 다시 로그인 (zustand 메모리)
   - **prod (백엔드 합류 후)**: 옵션 B 전환 — httpOnly cookie + `/auth/me` 자동 복원 + apiClient `withCredentials: true` (이미 설정됨)
6. **Form validation**: **react-hook-form + zod 도입** (사용자 경험 보유). schema 중심 + 타입 추론 + 06 settings 의 복잡한 폼 대비.
7. **로그아웃 UI**: Topbar 아바타 클릭 → `<details>` 기반 간단 dropdown ("로그아웃" 1개 항목). 본격 dropdown menu 라이브러리는 후속.
8. **에러 색상**: 시스템 기본 적색 (`text-red-600`) 허용 — 폼 inline 에러 한정. 디자이너 브랜드 적색 확정 시 후속 PR 에서 교체.

## 잔존 불확실성 (Phase 02 진행 가능, 후속 정밀화 필요)

- **MSW init** — `pnpm exec msw init public/` 실행 시 user prompt 발생할 수 있음. 자동화 가능한지 확인 필요. 실패 시 수동 가이드 추가.
- **dev 모드에서 MSW 와 React Router 의 동시 동작** — service worker 의 첫 등록은 비동기. App 마운트 전 worker.start() await 해야 일부 케이스 안전. 잠정: `worker.start({ onUnhandledRequest: 'bypass' })` + App 즉시 렌더 (handler 매칭 안 되는 요청은 그대로 전송).
- **로그아웃 dropdown 의 keyboard a11y** — Phase 02 에선 `<details>` + `<summary>` 또는 click outside 처리. 정밀 dropdown 은 후속.
- **OAuth 콜백 시뮬레이션** — Phase 02 = SSO 버튼 클릭 = 즉시 MSW 200 (실제 OAuth flow 없음). 백엔드 합류 시 redirect → callback 흐름으로 전환.

### Phase 02 작업량 추정 (데드라인 5/18 영향)

- 작성 일정: 3-4일 (`project_kepco_competition_deadline_2026_05_18.md` 추정과 일치)
- 위험: MSW 통합 디버깅이 예상보다 길어질 가능성 → 1일 buffer 확보. 초과 시 회원가입 페이지 placeholder 유지하고 로그인만 본 구현하는 옵션 (PLAN 단축)
