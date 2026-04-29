# Frontend Phase 00 — 프로젝트 부트스트랩

> 작성일: 2026-04-29
> 브랜치: Frontend
> 도메인: bootstrap

---

## 1. 목표

빈 스캐폴드(.gitkeep만 존재) 상태인 Frontend 브랜치에 **Vite + React + TS + Tailwind + Recharts** 기반 SPA 골격을 세우고, **7개 라우트 placeholder + 공통 레이아웃(Sidebar/Topbar) + AuthGuard + MSW 빈 골격**까지 구성해 `pnpm typecheck && lint && test && test:e2e` 4종 그린에 도달한다.

Phase 0 종료 시점 사용자 가치: **개발자가 `pnpm dev` 실행 시 7개 라우트가 placeholder 텍스트와 함께 정상 라우팅되는 것을 확인** 가능 (실 데이터·실 화면은 Phase 01+ 에서).

---

## 2. 화면 / 라우트

| 라우트 | 컴포넌트 | 접근 권한 | 비고 |
|---|---|---|---|
| `/` | `LandingPage` (placeholder) | public | 비로그인 진입점, 인증 시 `/home` 으로 redirect |
| `/auth/login` | `LoginPage` (placeholder) | public | Phase 01 에서 본 구현 |
| `/auth/signup` | `SignupPage` (placeholder) | public | Phase 01 에서 본 구현 |
| `/home` | `DashboardPage` (placeholder) | protected | 로그인 후 첫 화면 |
| `/usage` | `UsagePage` (placeholder) | protected | |
| `/cashback` | `CashbackPage` (placeholder) | protected | |
| `/settings/account` | `SettingsAccountPage` (placeholder) | protected | 06-A (프로필 + 한전) |
| `/settings/notifications` | `SettingsNotificationsPage` (placeholder) | protected | 06-B |
| `/settings/security` | `SettingsSecurityPage` (placeholder) | protected | 06-C |
| `/settings/anomaly-log` | `SettingsAnomalyLogPage` (placeholder) | protected | 06-D |
| `/settings/email` | `SettingsEmailPage` (placeholder) | protected | 06-E |
| `/insights` | `InsightsPage` (placeholder) | protected | 07 |

> 라우트 분기 결정: `/` 는 `LandingPage` 가 처리하고 그 안에서 `useAuth()` 결과로 `<Navigate to="/home" />` 를 호출. 별도 redirect 컴포넌트 도입 안 함 (premature abstraction 회피).

---

## 3. 컴포넌트 트리 / 디렉토리 구조

```
src/
├── App.tsx                    ← Router + Provider 조립
├── main.tsx                   ← ReactDOM root
├── components/                ← 공통 재사용 (Phase 0 에선 비움)
├── features/
│   ├── auth/
│   │   ├── AuthGuard.tsx      ← <Outlet /> 보호 래퍼
│   │   └── useAuth.ts         ← Zustand store (Phase 0 = 항상 false)
│   ├── landing/LandingPage.tsx
│   ├── dashboard/DashboardPage.tsx
│   ├── usage/UsagePage.tsx
│   ├── cashback/CashbackPage.tsx
│   ├── settings/
│   │   ├── SettingsLayout.tsx ← 좌측 200px 사이드바 6 탭 (6-A 디자인 기준)
│   │   ├── AccountPage.tsx
│   │   ├── NotificationsPage.tsx
│   │   ├── SecurityPage.tsx
│   │   ├── AnomalyLogPage.tsx
│   │   └── EmailPage.tsx
│   └── insights/InsightsPage.tsx
├── pages/                     ← Phase 0 에선 비움 (features 가 자체 페이지 보유)
├── layouts/
│   ├── AppShell.tsx           ← Sidebar + Topbar + <Outlet />
│   ├── Sidebar.tsx            ← 메인 6 항목 + 계정 2 항목 (parts.jsx 기반)
│   └── Topbar.tsx             ← Breadcrumbs + 검색 + 알림 + 아바타
├── services/
│   └── apiClient.ts           ← axios 인스턴스 + 401 인터셉터 골격
├── hooks/                     ← 공용 훅 (Phase 0 비움)
├── lib/                       ← 순수 유틸 (Phase 0 비움)
├── types/                     ← 전역 타입 (Phase 0 비움)
└── styles/
    ├── tokens.css             ← 디자인 핸드오프 토큰 12개 (--bg, --canvas, --ink-*, ...)
    └── index.css              ← @tailwind base/components/utilities + tokens import
```

```
tests/
├── unit/
│   └── routing.test.tsx       ← 7 라우트 진입 + AuthGuard 동작 (1건)
├── e2e/
│   └── smoke.spec.ts          ← /  → /home(인증 후) → /usage → /insights placeholder 확인
└── fixtures/
    └── handlers.ts            ← MSW 빈 export (Phase 01 에서 채움)
```

---

## 4. API 엔드포인트 의존

**해당 없음.** Phase 0 은 스캐폴드 단계라 실제 API 호출 없음.

`apiClient.ts` 는 axios 인스턴스 + `withCredentials: true` + 401 인터셉터(로그인 라우트 redirect 골격)만. 실제 호출은 Phase 01+.

`tests/fixtures/handlers.ts` 는 빈 `export const handlers = []` — Phase 01 에서 `/auth/*` mock 추가.

---

## 5. 인수 기준 (Acceptance)

- [ ] `pnpm install` 으로 의존성 설치 PASS (lockfile 생성)
- [ ] `pnpm dev` 로 Vite 서버 기동 → `http://localhost:5173/` 에서 LandingPage placeholder 표시
- [ ] `/usage` 직접 진입 시 미인증 상태 → `/auth/login` 으로 redirect
- [ ] `pnpm typecheck` PASS (0 error)
- [ ] `pnpm lint` PASS (0 warning, `--max-warnings 0`)
- [ ] `pnpm test` PASS (Vitest, routing.test.tsx 통과)
- [ ] `pnpm test:e2e` PASS (Playwright smoke.spec.ts 통과)
- [ ] `pnpm build` PASS, `dist/` 산출물 생성
- [ ] `.env.example` 커밋, `.env.local` `.gitignore` 등록
- [ ] 디자인 토큰 12개(`--bg`, `--canvas`, `--ink-1~4`, `--line-1~3`, `--fill-1~3`)가 Tailwind config 의 `theme.extend.colors` 로 매핑되어 `text-ink-1`, `bg-canvas` 같은 유틸 사용 가능

---

## 6. E2E 골든 패스

```
[비로그인 시나리오]
1. 사용자가 / 진입 → LandingPage placeholder("ax 에너지캐시백" + "로그인" CTA) 보임
2. /home 직접 진입 → AuthGuard 가 /auth/login 으로 redirect
3. /auth/login 에서 LoginPage placeholder("로그인 — Phase 01 구현 예정") 보임

[가짜 인증 시나리오 — Phase 0 한정]
4. 테스트에서 useAuth store 의 user 를 강제 주입 → /home 진입 시 DashboardPage placeholder 보임
5. /usage, /cashback, /settings/account, /insights 모두 placeholder 표시
```

`tests/e2e/smoke.spec.ts` 1건. 가짜 인증은 Playwright `addInitScript` 로 Zustand state 주입.

---

## 7. 의존 / 선행 조건

- **선행 Phase**: 없음 (첫 PLAN)
- **외부 의존**: 없음. 백엔드 미배포 — Phase 0 에선 API 호출 없으므로 무관
- **로컬 도구**: Node.js 20 LTS + pnpm 9 (`corepack enable && corepack prepare pnpm@9 --activate` 권장)
- **디자인 레퍼런스**: `Frontend/docs/screen_variants.md` — 7화면 변형 매핑
- **외부 디자인 핸드오프**: `C:\Users\user\Downloads\ax_nilm (2)\design_handoff_web_wireframes\` (lo-fi 와이어프레임, 디자인 토큰 출처)

---

## 8. 범위 제외 (Out of Scope)

- **실 데이터 fetch / TanStack Query 사용** — Phase 01+ 에서 도입
- **Zustand store 본 구현** — Phase 0 은 `useAuth` 만 placeholder (항상 unauthenticated)
- **MSW handler 본 구현** — 빈 export만, Phase 01 에서 `/auth/*` mock 추가
- **각 화면의 실제 UI 구현** (대시보드 차트, 사용량 분해 표 등) — Phase 02~07
- **OAuth 2.0 / SSO 통합** — Phase 01
- **모바일 반응형** — Phase 0 = 데스크탑 1440 only. 1024px 이하 대응은 Phase 1+ 이연
- **i18n** — Phase 0 = 한국어 전용. `react-i18next` 도입은 후속
- **브랜드 컬러** — Phase 0 = 그레이스케일만. 강조색은 디자이너 추가 합의 후 Phase 1+
- **디자인 시스템 컴포넌트** (`Button`, `Card`, `Modal` 등) — 첫 사용 시점에 추가 (premature abstraction 회피)
- **Storybook / Playroom** — 도입 안 함

---

## 9. 위험 / 미정 사항

- **pnpm 9 미설치 환경** — `corepack` 로 자동 활성화. 실패 시 npm/yarn 폴백 가이드 README 에 추가
- **Playwright 브라우저 다운로드 (~300MB)** — `playwright install --with-deps chromium webkit` 첫 실행 시 시간 소요. CI 캐시 전략은 Phase 1+ 검토
- **Vite + React 19 호환성** — Phase 0 시점 React 18 명시. 19 전환 시 별도 PLAN
- **AuthGuard redirect 루프** — 미인증 시 `/auth/login`, 인증 시 `/home` redirect. `/` 가 양쪽 분기를 가지므로 무한 redirect 회피용 테스트 1건 필수 (인수 기준 §5 항목 #3 으로 검증)
- **잔존 오픈 퀘스천**: 브랜드 컬러 / 모바일 반응형 / i18n — Phase 0 에서는 명시적으로 제외 (§8). Phase 1+ 시작 전에 디자이너·PM 합의 필요
- **사이드바 IA 변경 가능성** — `parts.jsx` 의 사이드바는 메인 4 + 계정 2 항목. 추후 항목 추가 시 디자인 측 합의 필수 (디자인 변경 이력은 `docs/screen_variants.md` 에 기록)
- **외부 디자인 핸드오프 위치** — 사용자 로컬(`Downloads/`) 만. repo 동기화는 디자인 라이선스/저작권 고려 후 별도 결정. PLAN_00 단계에서는 디자인 토큰 값만 코드로 추출
