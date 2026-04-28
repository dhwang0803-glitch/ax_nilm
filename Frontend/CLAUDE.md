# Frontend — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙 + 토큰 절감 규칙과 함께 적용된다.

## 모듈 역할

**B2C 주택 거주자용 KEPCO 에너지캐시백 웹 서비스 UI**.

- 일반 가구 대상 단일 페이지 웹 앱 (SPA). 별도 네이티브 모바일 앱 없음.
- 모바일 브라우저 우선 반응형 — 1차 사용 디바이스가 스마트폰이라는 가정.
- API_Server (FastAPI) 와 REST + (선택) SSE 로만 통신. DB 직접 접근 금지.
- LLM 추천 응답은 API_Server 가 익명화·응답 가공 후 전달 → Frontend 는 표시만.

> **요구사항 변경 맥락**: 초기 기획(KPX 사업자 대상 DR 운영 콘솔) → 일반 거주자 대상 KEPCO 에너지캐시백 (`a1402be refactor(kpx): 국민DR → 에너지캐시백`). 운영자 대시보드성 화면(이벤트 발급/실시간 감축률 등)은 본 브랜치에서 구현하지 않는다.

## 현재 상태 — 빈 스캐폴드

본 브랜치는 **모든 `src/*`, `tests/*` 디렉토리에 `.gitkeep` 만 있는 상태**다. `package.json` / `vite.config.ts` / 소스 코드 어느 것도 아직 존재하지 않는다. 첫 작업은 [Phase 0 — 프로젝트 부트스트랩](#phase-0--프로젝트-부트스트랩-mandatory) 이다.

## 관련 문서 / 레퍼런스

- 핵심 화면 PLAN: [`plans/`](plans/) — Orchestrator 가 순차 실행
- Phase 보고서: [`reports/`](reports/) — Reporter 가 생성
- agent 역할: [`agents/`](agents/) — DEVELOPER, TEST_WRITER, TESTER, ORCHESTRATOR, REPORTER, REVIEW, REFACTOR, IMPACT_ASSESSOR, SECURITY_AUDITOR
- 루트 CLAUDE: [`../CLAUDE.md`](../CLAUDE.md)
- API 계약 (소비자 입장): API_Server 모듈은 아직 별도 브랜치 미생성. 백엔드 미배포 엔드포인트는 MSW 모킹으로 진행하고, 백엔드 합류 시 `OpenAPI` 스펙으로 타입 동기화

## 핵심 화면 (5)

| 화면 | 라우트 | 주 데이터 소스 | 비고 |
|---|---|---|---|
| 가입/로그인 | `/auth/*` | `POST /auth/login` (JWT httpOnly 쿠키) | OAuth 2.0 / SSO (REQ-007) |
| 대시보드 | `/` | 월간 사용량 / 캐시백 추정 / 알림 카운트 | 첫 진입, 요약 위주 |
| 사용량 분석 | `/usage` | `power_1hour` 가전별 분해 + 시간대 패턴 | Recharts 라인/스택 차트 |
| 캐시백 | `/cashback` | 직전 2개년 동월 평균 대비 절감 + 단가 구간 산출 | 매월 1일/5일 배치 결과 |
| 이상탐지 / 추천 | `/insights` | `appliance_status_intervals` 이상 이벤트 + LLM 추천 텍스트 | 진단 리포트 (REQ-002) |

> 화면을 더 추가할 때는 `src/features/` 하위 새 폴더 + 라우트 등록. 기존 화면을 일반화하기 전에 **3번째 유사 화면이 등장할 때까지 기다린다**(premature abstraction 금지 — 루트 `CLAUDE.md`).

## 기술 스택 (확정)

```
Vite 5 + React 18 + TypeScript 5
Tailwind CSS 3 + Recharts (차트)
React Router v6 (라우팅)
TanStack Query v5 (서버 상태)
Zustand (전역 클라이언트 상태 — 인증/테마)
Axios (HTTP — 인터셉터로 JWT 첨부)
Vitest + React Testing Library + MSW (단위/컴포넌트/모킹)
Playwright (E2E)
```

**패키지 매니저**: `pnpm` 9 (lockfile = `pnpm-lock.yaml`). npm/yarn 도 빌드는 가능하나 본 브랜치 스크립트·문서는 pnpm 기준.

**Next.js / React Native 채택 안 함**:
- SEO 불필요 (인증 보호 대시보드)
- API 라우트 불필요 (FastAPI 별도)
- 네이티브 앱 미배포 (반응형 웹만)
- → Vite SPA 가 빌드/HMR/번들 크기 모두 유리

---

## Phase 0 — 프로젝트 부트스트랩 (MANDATORY)

> 이 단계가 완료되기 전까지 핵심 5화면(Phase 1~5) 진입 금지.
> [`plans/PLAN_00_BOOTSTRAP.md`](plans/PLAN_00_BOOTSTRAP.md) 작성 후 Orchestrator 호출.

### 1) Vite 스캐폴드

```bash
cd Frontend
pnpm create vite . --template react-ts
# 기존 .gitkeep 들은 유지, src/ 하위 디렉토리는 본 CLAUDE.md 의 파일 위치 규칙대로 정리
```

### 2) 핵심 의존성

```bash
pnpm add react-router-dom @tanstack/react-query zustand axios recharts
pnpm add -D tailwindcss postcss autoprefixer
pnpm add -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event
pnpm add -D msw @playwright/test @axe-core/react
pnpm add -D eslint @typescript-eslint/eslint-plugin @typescript-eslint/parser \
              eslint-plugin-react-hooks eslint-plugin-react-refresh \
              prettier eslint-config-prettier
pnpm exec tailwindcss init -p
pnpm exec playwright install --with-deps chromium webkit
```

### 3) `package.json` scripts

```json
{
  "scripts": {
    "dev":        "vite",
    "build":      "tsc -b && vite build",
    "preview":    "vite preview",
    "lint":       "eslint . --max-warnings 0",
    "typecheck":  "tsc -b --noEmit",
    "test":       "vitest run",
    "test:watch": "vitest",
    "test:e2e":   "playwright test"
  }
}
```

### 4) 환경변수

```bash
# Frontend/.env.example  (커밋함)
VITE_API_BASE_URL=

# Frontend/.env.local    (커밋 금지)
VITE_API_BASE_URL=http://localhost:8000
```

`VITE_*` 만 빌드 산출물에 노출. 비밀 키는 절대 `VITE_` prefix 로 두지 않는다.

### 5) 초기 디렉토리 정리

`.gitkeep` 들은 `src/components/`, `src/features/`, `src/pages/`, `src/services/`, `src/hooks/`, `src/lib/`, `src/types/`, `src/styles/`, `tests/unit/`, `tests/e2e/`, `tests/fixtures/` 위치를 미리 잡아둔 마커 — 첫 실파일이 들어가면 같이 제거한다.

### 6) 첫 커밋 범위

- 부트스트랩 설정 파일 (`package.json`, `pnpm-lock.yaml`, `vite.config.ts`, `tsconfig.*.json`, `tailwind.config.ts`, `postcss.config.js`, `playwright.config.ts`, `.eslintrc.*`, `.prettierrc`)
- `src/main.tsx`, `src/App.tsx` — Router + AuthGuard 골격 + 5개 페이지 placeholder
- `src/services/apiClient.ts` — axios 인스턴스 + 401 인터셉터 (실제 토큰 첨부는 Phase 1)
- `tests/fixtures/handlers.ts` — MSW handler 파일 (빈 export)
- `.env.example`
- 한 번의 단위 테스트 + 한 번의 E2E (smoke test 수준 — `/` 진입 시 placeholder 텍스트 보임)

Phase 0 종료 시 `pnpm typecheck && pnpm lint && pnpm test && pnpm test:e2e` 모두 PASS.

---

## 파일 위치 규칙 (MANDATORY)

```
Frontend/
├── src/
│   ├── components/        ← 도메인 무관 재사용 UI (Button, Card, Modal, Chart wrapper)
│   ├── features/          ← 도메인별 묶음 (auth, dashboard, usage, cashback, insights)
│   │   └── <domain>/
│   │       ├── components/   ← 그 도메인에서만 쓰이는 UI
│   │       ├── api.ts        ← 그 도메인의 API 호출 (TanStack Query hooks)
│   │       └── types.ts      ← 그 도메인 응답 타입
│   ├── pages/             ← 라우트 단위 컴포넌트 (얇게 — features 컴포넌트 조립만)
│   ├── services/          ← 공통 API 클라이언트 (axios 인스턴스, auth 인터셉터)
│   ├── hooks/             ← 공용 훅 (useAuth, useMediaQuery 등)
│   ├── lib/               ← 순수 유틸 (formatKwh, dateRange 등 — DOM/React 없음)
│   ├── types/             ← 전역/공유 타입 (User, ApiError 등)
│   ├── styles/            ← Tailwind config 보강, 글로벌 css
│   ├── App.tsx
│   └── main.tsx
├── public/                ← 정적 에셋 (favicon, manifest, OG 이미지)
├── tests/
│   ├── unit/              ← Vitest + RTL (컴포넌트/훅 단위)
│   ├── e2e/               ← Playwright
│   └── fixtures/          ← MSW handler / 목 응답
├── plans/                 ← Phase PLAN (Orchestrator 가 순차 실행)
├── reports/               ← Phase 보고서 (Reporter 가 생성)
├── docs/                  ← 화면 명세, UX 결정 노트, 디자인 시스템 메모
├── agents/                ← Frontend 특화 agent 역할 문서
└── CLAUDE.md
```

| 파일 종류 | 위치 |
|---|---|
| 도메인 무관 재사용 UI 컴포넌트 | `src/components/` |
| 한 도메인 안에서만 쓰는 UI / API hook / 타입 | `src/features/<domain>/` |
| 라우트 컴포넌트 (조립만) | `src/pages/` |
| Axios 인스턴스, 인증 인터셉터, 공통 에러 핸들러 | `src/services/` |
| `useAuth`, `useMediaQuery` 등 도메인 무관 훅 | `src/hooks/` |
| 순수 함수 유틸 (포맷, 계산) | `src/lib/` |
| 단위/컴포넌트 테스트 | `tests/unit/` |
| E2E | `tests/e2e/` |

**`Frontend/` 루트 또는 프로젝트 루트에 소스 파일 직접 생성 금지.**

## 디자인 / UX 원칙

- **모바일 우선** (`<sm:` Tailwind breakpoint 부터 작성, 데스크탑은 `md:` 이상에서 보강)
- **터치 타겟 ≥ 44×44px** (애플 HIG / WCAG 2.5.5)
- **WCAG 2.1 AA 준수** — `aria-*`, 색 대비 4.5:1, 키보드 포커스 명시
- **i18n 준비** — 한국어 1차, 다국어 키 분리 (`react-i18next` 도입은 후속)
- **차트는 항상 데이터 부재 상태 / 로딩 / 에러 3가지 분기 표시**

## 보안 규칙 (REQ-007 — 루트 CLAUDE.md 보강)

- **JWT 보관**: `httpOnly`/`Secure`/`SameSite=Strict` 쿠키만. `localStorage` / `sessionStorage` 사용 **금지**.
- **PII 노출 금지**: 주소/구성원/연락처는 API_Server 가 마스킹한 형태로만 받음. 디버그 로그·콘솔 출력 금지.
- **자격증명 폼**: 입력값 React state 에 장기 보관 금지. 전송 직후 setState('') 로 초기화.
- **외부 스크립트 / iframe 금지** (분석 도구는 별도 검토 후 OAuth 분리 도메인).
- **CSP**: `default-src 'self'`, API_Server origin 만 connect 허용. 인라인 스크립트 차단.
- **빌드 타임 환경변수**: `VITE_*` prefix 만 노출 — API URL, 공개 키 외 어떤 비밀도 빌드에 포함 금지.

## API 호출 규칙

- 모든 API 호출은 `src/services/apiClient.ts` 한 곳에서 만든 axios 인스턴스 경유. 인터셉터로 `withCredentials: true` 적용 + 401 시 로그인 라우트 리다이렉트.
- 서버 데이터는 **반드시 TanStack Query** (직접 `useEffect + fetch` 금지). 캐싱·재시도·낙관적 업데이트를 표준화.
- 응답 타입은 `src/features/<domain>/types.ts` 또는 `src/types/api.ts` 에 정의. `any` 금지, OpenAPI 스펙이 확정되면 `openapi-typescript` 로 자동 생성 검토.
- 백엔드 미배포 엔드포인트는 `tests/fixtures/handlers.ts` 의 MSW handler 로 모킹하고, 통합 테스트는 PLAN 의 "백엔드 합류 후" 항목으로 표기.

## 라우팅 / 인증 가드

```tsx
<Route element={<AuthGuard />}>
  <Route path="/" element={<DashboardPage />} />
  <Route path="/usage" element={<UsagePage />} />
  ...
</Route>
<Route path="/auth/*" element={<AuthRoutes />} />
```

`AuthGuard` 는 `useAuth()` 의 user 가 null 이면 `/auth/login` 으로 redirect. JWT 만료(401) 는 axios 인터셉터가 흡수.

## 테스트 정책

| 종류 | 도구 | 대상 | 위치 |
|---|---|---|---|
| 단위 | Vitest | 순수 함수 (`src/lib/`), 훅 | `tests/unit/` |
| 컴포넌트 | Vitest + RTL | 단일 컴포넌트 렌더 + 사용자 상호작용 | `tests/unit/` |
| 통합 | Vitest + MSW | features 단위 (API mocking) | `tests/unit/` |
| E2E | Playwright | 핵심 5개 화면 골든 패스 | `tests/e2e/` |

`a11y` 검증은 컴포넌트 테스트에서 `@axe-core/react` 또는 RTL `getByRole` 강제 사용으로 누적.

## 다운스트림 / 업스트림

- **업스트림**: `API_Server` (REST + 선택 SSE) — 모든 데이터·LLM 응답·인증의 단일 진입점. 별도 브랜치 미생성 상태 → 백엔드 합류 시까지 MSW 모킹.
- **다운스트림**: 사용자 브라우저 (반응형 — Chrome/Safari/Firefox 최신 + iOS Safari/Android Chrome)

## 변경 시 영향 점검

- 디자인 토큰(Tailwind config) 수정 → 전 화면 시각 회귀 검토 (Playwright 스크린샷)
- 라우트 추가/이동 → `AuthGuard` 적용 여부, 사이드 네비 메뉴 갱신
- API 응답 스키마 변경 → `src/features/*/types.ts` + 관련 컴포넌트 동시 수정 (atomic PR)

## 토큰 절감 규칙 (루트 CLAUDE.md 동일)

- 500줄 초과 파일은 목차 먼저 → 작업 구간만 읽기
- Write 후 변경 내용 반복 설명 금지 (diff 로 충분), 설계 판단만 한 줄
- 탐색 중간 결과 나열 금지, 결론만 보고
- 작업 단위별 세션 분리, 컨텍스트 비대 시 `/compact` 권고
