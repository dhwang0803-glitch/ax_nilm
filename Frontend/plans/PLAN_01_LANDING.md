# Frontend Phase 01 — 랜딩 / 가입 안내 본 구현

> 작성일: 2026-04-29
> 브랜치: Frontend
> 도메인: landing
> 디자인 변형: **B (미니멀 히어로)** — `Frontend/docs/screen_variants.md` 확정안

---

## 1. 목표

비로그인 사용자가 `/` 진입 시 디자인 핸드오프 v3 의 LandingB 와이어프레임이 그대로 렌더되어 보이며, **PubNav "시작하기" + Hero "시작하기 · 무료" 모두 `/auth/login` 으로 이동**한다. 인증된 사용자는 `/home` 으로 자동 redirect.

---

## 2. 화면 / 라우트

| 라우트 | 컴포넌트 | 접근 권한 | 비고 |
|---|---|---|---|
| `/` | `LandingPage` | public | 인증 시 `<Navigate to="/home" replace />` |

라우트 자체는 Phase 0 에서 등록 완료 — 본 Phase 는 LandingPage 컴포넌트 본 구현만.

---

## 3. 컴포넌트 트리

```
LandingPage
├── PubNav            ← features/landing/components/PubNav.tsx
│   ├── 로고 (ax 마크 + "에너지캐시백" 워드마크)
│   ├── 메뉴 (특징, FAQ — Phase 1 = 앵커 링크 placeholder)
│   └── "시작하기" sm 버튼 → /auth/login
├── Hero              ← features/landing/components/Hero.tsx
│   ├── "베타" pill
│   ├── h1 "매달 받는 캐시백, 이번 달은 얼마일까?"
│   ├── subtitle "한전 고객번호 한 번 등록하면..."
│   ├── CTA "시작하기 · 무료" primary 버튼 → /auth/login (ghost "샘플 보기" 제외)
│   └── DashboardMockup placeholder (height 360, max-w-[1100px])
└── WhySection        ← features/landing/components/WhySection.tsx
    ├── h2 "왜 에너지캐시백인가"
    └── grid-3 카드 (가전별 분해 / 주간·월간 추적 / AI 진단)
```

> 컴포넌트 분리는 본 Phase 한정. 다른 화면이 동일 패턴(예: PubNav)을 재사용하기 시작하면 Phase 1+ 에서 `src/components/` 또는 `src/layouts/` 로 승격 검토 (premature abstraction 금지 — 3번째 등장까지 대기).

### 디자인 토큰 매핑

| 영역 | Tailwind 유틸 |
|------|--------------|
| 페이지 배경 | `bg-bg` |
| nav / hero 섹션 배경 | `bg-canvas` |
| h1 | `text-ink-1`, `font-bold`, `text-5xl tracking-tight` |
| subtitle | `text-ink-2` |
| 카드 설명 텍스트 | `text-ink-3 text-sm` |
| 카드/섹션 구분선 | `border-line-2` |
| placeholder 이미지 | `bg-fill-1 border border-line-2` + 모노 라벨 |
| primary 버튼 | `bg-ink-1 text-canvas border border-ink-1` |
| ghost 버튼 | `border border-line-2 text-ink-1` |
| pill (베타) | `bg-fill-2 text-ink-2 font-mono text-xs uppercase tracking-wider` |

---

## 4. API 엔드포인트 의존

**해당 없음.** 랜딩은 정적 페이지. 외부 호출/상태 0.

---

## 5. 인수 기준 (Acceptance)

- [ ] 비로그인 상태에서 `/` 진입 → PubNav + Hero + WhySection 3 섹션 모두 렌더
- [ ] 인증된 상태(`useAuth.setState({user})`)로 `/` 진입 → 즉시 `/home` 으로 redirect (이미 Phase 0 구현, 본 Phase 에서 회귀 미발생 검증)
- [ ] PubNav 의 "시작하기" 클릭 → `/auth/login` 이동
- [ ] Hero 의 "시작하기 · 무료" 클릭 → `/auth/login` 이동
- [ ] PubNav 의 "특징"/"FAQ" 메뉴 — 본 Phase 는 앵커(`#features`, `#faq`) 링크 placeholder, 콘텐츠 추가는 후속
- [ ] 디자인 토큰만 사용 (그레이스케일 13색 외 색상 0 — `git grep -E "#[0-9a-f]{3,6}"` 으로 검증, tokens.css 외에는 hex 색상 없음)
- [ ] WCAG 2.1 AA — heading 계층(h1 > h2 > h4), 모든 버튼/링크 `aria-*` 검증, 색 대비 4.5:1
- [ ] `pnpm typecheck && lint && test && test:e2e --project=chromium && build` 모두 그린

---

## 6. E2E 골든 패스

```
1. 비로그인 사용자가 / 진입
2. h1 "매달 받는 캐시백" 텍스트 보임
3. PubNav "시작하기" 버튼 클릭 → URL = /auth/login
4. 뒤로가기 → /
5. Hero "시작하기 · 무료" 버튼 클릭 → URL = /auth/login
```

> "이미 계정이 있다면 로그인 / 신규 회원가입" 토글은 Phase 02 (auth) 에서 본 구현. Phase 01 단계는 두 CTA 모두 `/auth/login` 으로 일관되게 보냄.

`tests/e2e/landing.spec.ts` 신규 작성. 기존 `smoke.spec.ts` 의 "전기요금, 줄인 만큼 돌려받으세요" 검증은 Phase 1 카피로 갱신 (`매달 받는 캐시백`).

추가로 `tests/unit/landing.test.tsx` 1건 — `<LandingPage />` 렌더 시 인증 상태 분기(authenticated → Navigate, unauthenticated → 3 섹션 렌더) 검증.

---

## 7. 의존 / 선행 조건

- **선행 Phase**: PLAN_00_BOOTSTRAP (스캐폴드 + AuthGuard + useAuth + 라우트 등록 — 완료)
- **백엔드 의존**: 없음
- **디자인 레퍼런스**:
  - `Frontend/docs/screen_variants.md` (확정 매핑)
  - 외부: `C:\Users\user\Downloads\ax_nilm (2)\design_handoff_web_wireframes\screens.jsx` (LandingB 정의, line 588~618)
- **공용 컴포넌트 추가 없음** — `src/components/` 비움 유지 (3번째 등장 대기)

---

## 8. 범위 제외 (Out of Scope)

- **모바일 반응형** — Phase 1 은 데스크탑 1440 기준만. 1024px 이하 대응은 별도 PLAN_M (responsive) 에서 일괄 처리
- **브랜드 컬러** — 그레이스케일 그대로
- **i18n** — 한국어 전용
- **"특징"/"FAQ" 메뉴 콘텐츠** — 앵커 링크 placeholder 만, 본 콘텐츠는 마케팅 측 카피 확정 후 후속
- **DashboardMockup 실 이미지** — Phase 1 = `bg-fill-1` placeholder 박스 + 라벨. 실 스크린샷은 Phase 02(대시보드) 본 구현 후 캡처 → Phase 후속
- **시각 회귀 (Playwright screenshot diff)** — 현 단계는 텍스트/링크 검증만
- **a11y 자동 검증 도구 통합** (`@axe-core/react`) — 의존성은 설치되어 있지만 실 통합 테스트는 Phase 1+

---

## 9. 위험 / 미정 사항

- **DashboardMockup placeholder 의 height 360px** — 데스크탑 1440 에서 어울리는 비율이지만, `max-w-[1100px]` 컨테이너 + 360px 고정 높이는 narrow 뷰포트(1280)에선 약간 어색할 수 있음. Phase 1 = 1440 기준 그대로, 회귀 시 `aspect-video` 또는 `aspect-[16/9]` 로 전환 검토.

## 결정 이력 (2026-04-29)

§1, §3, §5, §6 본문에 통합된 사용자 결정:
1. 두 "시작하기" CTA 모두 `/auth/login` 이동. 회원가입은 login 페이지 안에서 토글 (Phase 02)
2. "샘플 보기" 버튼 제거 — DashboardMockup placeholder 자체로 시각 의도 충족
3. 모바일 반응형 미개발 — 2026-05-18 공모전 데드라인 압박. `Frontend/CLAUDE.md` §디자인/UX 원칙 단계화 갱신 (본 PR 포함)
