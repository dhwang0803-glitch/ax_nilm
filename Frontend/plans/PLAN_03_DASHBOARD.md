# Frontend Phase 03 — 대시보드 (홈) 본 구현

> 작성일: 2026-04-29
> 브랜치: Frontend
> 도메인: dashboard
> 디자인 변형: **C (분석형)** — `Frontend/docs/screen_variants.md` 확정안
> 데드라인 컨텍스트: 2026-05-18 공모전 출품 (-19일)

---

## 1. 목표

인증 사용자가 `/home` 진입 시 좌(2/3) 차트 영역 + 우(1/3) KPI 영역의 분석형 대시보드를 본다. 주간/월별 전력 사용 추이, 이번 달 사용량/예상 캐시백/예상 요금 KPI, 가전별 점유율을 한눈에 파악. **Recharts 첫 도입** + **TanStack Query 첫 사용** + 로딩/에러 상태 분기.

---

## 2. 화면 / 라우트

| 라우트 | 컴포넌트 | 접근 권한 | 비고 |
|---|---|---|---|
| `/home` | `DashboardPage` | protected (AuthGuard) | 로그인 후 첫 화면 |

라우트 자체는 Phase 0 등록 완료. 본 Phase 는 컴포넌트 본 구현.

---

## 3. 컴포넌트 트리

```
DashboardPage
├── PageHeader (h1 "홈" + h-sub "분석형 — 데이터 우선 레이아웃")
├── 좌측 (flex-2)
│   ├── WeeklyUsageCard           ← features/dashboard/components/WeeklyUsageCard.tsx
│   │   ├── h4 + Segmented (주/월/연 — Phase 3 = visual, "주" only)
│   │   ├── WeeklyPairBarChart    ← features/dashboard/components/WeeklyPairBarChart.tsx (Recharts)
│   │   └── 하단 4 stat row (이번 주 합계 / 지난 주 / 차이 / 평균/일)
│   └── MonthlyUsageCard          ← features/dashboard/components/MonthlyUsageCard.tsx
│       ├── h4 + pill "2026"
│       └── MonthlyBarChart        ← features/dashboard/components/MonthlyBarChart.tsx (Recharts, current month highlight)
└── 우측 (flex-1)
    ├── KpiCard (이번 달 사용량 — kWh + 전월 대비 delta)
    ├── KpiCard (예상 캐시백 — 원 + 단가)
    ├── KpiCard (예상 요금 — 원)
    └── ApplianceShareCard         ← features/dashboard/components/ApplianceShareCard.tsx
        └── 5 항목 horizontal bar (냉난방/냉장고/세탁·건조/주방/기타)
```

### 공용 컴포넌트 신규 (`src/components/`)

| 컴포넌트 | 위치 | 사유 (3번째 등장 원칙 예외) |
|---|---|---|
| `KpiCard` | `src/components/KpiCard.tsx` | Phase 03 대시보드 3개 + Phase 04 사용량(잠재) + Phase 05 캐시백 KPI + Phase 07 진단 KPI = **다수 화면에서 동일 패턴 즉시 등장**. 공용화 합리적. |

차트 컴포넌트들(WeeklyPairBarChart, MonthlyBarChart)은 Phase 03 한정 features 폴더 유지. Phase 04 사용량 분석에서 동일 차트 재사용 시점에 `src/components/` 로 승격.

### 디자인 토큰 매핑 (Recharts 색상)

| 데이터 시리즈 | 토큰 |
|---|---|
| 메인 막대 (이번 주, 현재 월) | `var(--ink-2)` (#3f3f46) |
| 서브 막대 (지난 주) | `var(--fill-3)` (#d4d4d8) |
| 강조 막대 (current month) | `var(--ink-1)` (#18181b) |
| Axis tick | `var(--ink-3)` |
| Grid line | `var(--line-3)` |

Recharts 의 `fill`, `stroke` props 에 CSS variable 직접 전달 불가 — `getComputedStyle(document.documentElement).getPropertyValue('--ink-1')` 또는 hex 직접 사용. 잠정: **hex 직접 사용** (tokens.css 와 동일 값 hardcode, 토큰 변경 시 `src/lib/chart-colors.ts` 한 곳만 갱신).

---

## 4. API 엔드포인트 의존

| 엔드포인트 | 메서드 | 용도 | 상태 |
|---|---|---|---|
| `/api/dashboard/summary` | GET | KPI 3개 + weekly 7 + monthly 12 + appliance breakdown 한 번에 | 미배포 → MSW 모킹 |

응답 스키마 (제안):
```ts
type DashboardSummary = {
  kpis: {
    monthlyUsageKwh: number;        // 218
    monthlyDeltaPercent: number;    // -8.4
    estimatedCashbackKrw: number;   // 4820
    cashbackRateKrwPerKwh: number;  // 30
    estimatedBillKrw: number;       // 31200
  };
  weekly: {
    days: Array<{ day: string; thisWeek: number; prevWeek: number }>;  // 7 entries (월~일)
    thisWeekTotal: number;
    prevWeekTotal: number;
    avgPerDay: number;
  };
  monthly: {
    year: number;                                                       // 2026
    months: Array<{ month: number; kwh: number }>;                       // 12 entries
    currentMonth: number;                                                // 11
  };
  applianceBreakdown: Array<{ name: string; sharePercent: number }>;     // 5 entries 합 100
};
```

단일 호출 결정 사유: TanStack Query 첫 도입 시점이라 단순화 + 대시보드는 통합 화면. Phase 04 사용량 분석에서 endpoint 분리 가능 (필터별 다른 응답).

---

## 5. 인수 기준 (Acceptance)

- [ ] `/home` 인증 후 진입 → 좌 차트 2개 + 우 KPI 3개 + 가전별 점유율 카드 모두 렌더
- [ ] 주간 차트: 7일 페어 막대 (지난 주 muted + 이번 주 dark)
- [ ] 월별 차트: 12개월 단일 막대, current month (응답의 `currentMonth` 인덱스) highlight `var(--ink-1)`
- [ ] KPI 3개 각각 값 + 단위 + delta(있는 경우) 표시
- [ ] 가전별 점유율: 5 항목 horizontal bar + 퍼센트 mono font
- [ ] **로딩 상태**: skeleton (placeholder gray box, Recharts 영역 + KPI 영역 모두)
- [ ] **에러 상태**: 카드별 "데이터를 불러올 수 없습니다 [재시도]" 표시
- [ ] **빈 상태**: 신규 가입 직후 0 데이터 — Phase 03 = MSW 가 항상 mock 데이터 반환하므로 미구현. 빈 상태는 후속 Phase
- [ ] 차트 hover tooltip (Recharts 기본) — kWh 단위 + 날짜
- [ ] WCAG: 차트는 `<title>` 또는 aria-label, KPI 는 heading + value 의미 구조
- [ ] `pnpm typecheck && lint && test && test:e2e --project=chromium && build` 모두 그린

---

## 6. E2E 골든 패스

```
1. 인증 사용자가 /home 진입
2. h1 "홈" + h-sub "분석형 — 데이터 우선 레이아웃" 표시
3. 좌측 주간 차트 영역 (7개 막대 페어) + 하단 4 stat 표시
4. 좌측 월별 차트 영역 (12개 막대 + current month highlight) 표시
5. 우측 KPI 3개 + 가전별 점유율 5 항목 표시
6. (옵션) MSW handler 가 500 반환 시 에러 상태 카드 표시 — 단위 테스트로 검증
```

테스트 파일:
- `tests/e2e/dashboard.spec.ts` — 로그인 후 /home 의 주요 영역 visible 검증
- `tests/unit/dashboard.test.tsx` — DashboardPage 의 loading/success/error 3분기 렌더 검증 (MSW handler override)
- `tests/unit/applianceShare.test.tsx` — 가전별 점유율 합 100% 검증

---

## 7. 의존 / 선행 조건

- **선행 Phase**: PLAN_00 + 02 (인증 — 이미 머지됨)
- **신규 의존성**: 없음 — Recharts 는 Phase 0 부트스트랩에서 이미 설치됨
- **MSW handler 추가**: `/api/dashboard/summary` 1개 + `tests/fixtures/dashboardData.ts` (mock 응답 분리)
- **TanStack Query 첫 사용**: `src/features/dashboard/api.ts` 에 `useDashboardSummary()` hook
- **공용 컴포넌트 신규**: `src/components/KpiCard.tsx`

---

## 8. 범위 제외 (Out of Scope)

- **모바일 반응형** — 데스크탑 1440 only (PLAN_M 후속)
- **Segmented control "월/연" 전환** — Phase 03 = "주" only visual. 월/연 데이터는 Phase 04 사용량 분석에서
- **차트 인터랙션 고도화** — Recharts 기본 tooltip만. 클릭 → 상세 modal 등은 후속
- **데이터 새로고침 버튼** — TanStack Query 의 `refetch` 는 도입하되 명시적 UI 버튼은 후속
- **차트 export (CSV/PNG)** — 후속
- **실시간 업데이트 (WebSocket/SSE)** — 후속
- **빈 상태 화면 (신규 가입자)** — 후속, MSW 가 항상 mock 반환
- **시각 회귀 (Playwright screenshot diff)** — 후속

---

## 9. 위험 / 미정 사항 (사용자 검토 필요)

### 잠정 결정 (5건)

1. **KpiCard 위치**: **공용 `src/components/KpiCard.tsx`** (3번째 등장 원칙 예외 — 즉시 다중 화면 사용 예정).
2. **MSW endpoint**: **단일 `GET /api/dashboard/summary`** (KPI + weekly + monthly + breakdown 한 번에). Phase 04 에서 분리 가능.
3. **차트 라이브러리**: **Recharts** (Phase 0 에서 이미 설치).
4. **Segmented control 동작**: **visual only** ("주" fixed). 월/연 데이터 전환은 Phase 04.
5. **차트 색상**: **hex 직접 사용** (CSS var 우회 불가). `src/lib/chart-colors.ts` 한 곳에 정의 — 토큰 변경 시 한 곳만 갱신.

### 잔존 불확실성

- **Recharts 번들 크기**: 도입 시 +50~80 KB 추정. dynamic import 또는 chunking 검토는 데드라인 압박 고려해 후속 (현재는 main bundle 포함).
- **TanStack Query 의 staleTime/gcTime**: Phase 03 = 기본값 (staleTime=0, gcTime=5분). 후속에서 도메인별 조정.
- **차트 hover tooltip 다국어**: Phase 03 한국어 hardcode. i18n 도입 후 갱신.
- **로딩 skeleton 의 정확한 디자인**: 디자인 핸드오프에 명시 없음. 잠정: `bg-fill-1` placeholder + 차트 영역 height 동일 유지. 디자이너 합의 후 정밀화.
- **응답 스키마 백엔드 합류 시 정렬**: 본 PLAN 의 type 은 frontend 시점 가정. 백엔드 OpenAPI 확정 시 갱신.

### Phase 03 작업량 추정

- 작성 일정: 2-3일 (Recharts 첫 도입 디버깅 + 4 차트/KPI 컴포넌트 + 테스트)
- 위험: Recharts 의 SSR-unfriendly 경고/에러, ResponsiveContainer 의 레이아웃 quirk. 발생 시 1 차트 단순화 (fixed width).
