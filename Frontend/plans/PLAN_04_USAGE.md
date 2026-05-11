# Frontend Phase 04 — 사용량 분석 본 구현

> 작성일: 2026-04-29
> 브랜치: Frontend
> 도메인: usage
> 디자인 변형: **A (종합 분석)** — `Frontend/docs/screen_variants.md` 확정안
> 데드라인 컨텍스트: 2026-05-18 공모전 출품 (-19일)

---

## 1. 목표

인증 사용자가 `/usage` 진입 시 NILM 가전별 분해 결과를 종합 화면(주간 페어 막대 + 24h 라인 + 가전별 표 + 월별 막대)에서 한눈에 본다. **Recharts LineChart 첫 도입** + 기존 Dashboard 차트 컴포넌트 공용화.

---

## 2. 화면 / 라우트

| 라우트 | 컴포넌트 | 접근 권한 | 비고 |
|---|---|---|---|
| `/usage` | `UsagePage` | protected (AuthGuard) | NILM 가전별 분해 분석 |

라우트 자체는 Phase 0 등록 완료. 본 Phase 는 컴포넌트 본 구현.

---

## 3. 컴포넌트 트리

```
UsagePage
├── PageHeader
│   ├── h1 "사용량 분석" + h-sub "NILM 가전별 분해 결과"
│   └── Toolbar (우측)
│       ├── Segmented (일/주/월/연 — Phase 4 = visual only, "주" fixed)
│       ├── "기간 선택" ghost 버튼 (Phase 4 = placeholder, alert "준비 중")
│       └── "CSV 내보내기" 버튼 (Phase 4 = placeholder, alert "준비 중")
├── WeeklyPairCard (메인, full-width)        ← src/components/charts/WeeklyPairBarChart 재사용
│   ├── h4 "주간 전력 소모량 — 지난 주 vs 이번 주" + Legend
│   └── WeeklyPairBarChart
├── grid-2
│   ├── HourlyLineCard                       ← features/usage/components/HourlyLineCard.tsx
│   │   ├── h4 "시간대별 평균 (24h)"
│   │   └── HourlyLineChart                  ← features/usage/components/HourlyLineChart.tsx (Recharts LineChart, 평균 점선 + 오늘 실선)
│   └── ApplianceBreakdownCard               ← features/usage/components/ApplianceBreakdownCard.tsx
│       ├── h4 "가전별 분해 (이번 주)"
│       └── 5행 표 (가전 / kWh / 점유% / 전주 대비)
└── MonthlyTrendCard                         ← src/components/charts/MonthlyBarChart 재사용
    ├── h4 "월별 전력 소모량 — 추세"
    └── MonthlyBarChart
```

### 차트 컴포넌트 승격 (Phase 04 추가 작업)

| 컴포넌트 | 이전 (Phase 03) | 이후 (Phase 04) | 사유 |
|---|---|---|---|
| `WeeklyPairBarChart` | `features/dashboard/components/` | `src/components/charts/` | Phase 03 + 04 두 화면 사용 → cross-feature import 회피 |
| `MonthlyBarChart` | `features/dashboard/components/` | `src/components/charts/` | 동일 |

승격 후 features/dashboard 의 import 경로도 갱신.

### 신규 컴포넌트 (`features/usage/components/`)

| 컴포넌트 | 역할 |
|---|---|
| `HourlyLineChart` | Recharts LineChart, 24h × 2 시리즈 (평균 점선 strokeDasharray + 오늘 실선) |
| `HourlyLineCard` | LineChart wrapper + h4 + axis label |
| `ApplianceBreakdownCard` | 표 wrapper (가전명 / kWh / 점유 / 전주 대비) |
| `UsageToolbar` | Segmented + "기간 선택" + "CSV 내보내기" (모두 visual/placeholder) |

---

## 4. API 엔드포인트 의존

| 엔드포인트 | 메서드 | 용도 | 상태 |
|---|---|---|---|
| `/api/usage/analysis` | GET | 주간 페어 + 시간대 24h + 가전별 분해 + 월별 12 한 번에 | 미배포 → MSW 모킹 |

응답 스키마 (제안):
```ts
type UsageAnalysis = {
  weekly: { days: Array<{ day: string; thisWeek: number; prevWeek: number }>; thisWeekTotal: number; prevWeekTotal: number };
  hourly: {
    hours: Array<{ hour: number; average: number; today: number }>;  // 24 entries (0~23)
  };
  applianceBreakdown: Array<{
    name: string;       // "에어컨/난방"
    kwh: number;        // 16.4
    sharePercent: number; // 36
    weekOverWeekPercent: number; // +12
  }>;
  monthly: {
    year: number;
    months: Array<{ month: number; kwh: number }>;
    currentMonth: number;
  };
};
```

`weekly` 와 `monthly` 는 Dashboard 의 응답 구조와 거의 동일 — 백엔드 합류 시 통합 가능.

---

## 5. 인수 기준 (Acceptance)

- [ ] `/usage` 인증 후 진입 → 헤더 + 도구바 + 4 카드 (주간 페어 / 24h 라인 / 가전 분해 표 / 월별 막대) 모두 렌더
- [ ] 주간 페어 차트: 7일 × (지난 주 muted + 이번 주 dark) + 우측 legend
- [ ] 24h 라인 차트: 평균 점선 (strokeDasharray) + 오늘 실선 (highlight)
- [ ] 가전별 표: 5행 — 에어컨/난방 / 냉장고 / 세탁·건조 / 주방 / 조명·기타. 각 행 (가전명 / kWh / 점유% / 전주 대비)
- [ ] 월별 막대: 12개월 + current month highlight
- [ ] Segmented control "주" 만 active, 일/월/연 클릭 시 disabled or alert "준비 중"
- [ ] "기간 선택" / "CSV 내보내기" 클릭 → alert "준비 중"
- [ ] **로딩 상태**: skeleton (4 카드 영역)
- [ ] **에러 상태**: 페이지 단위 "데이터를 불러올 수 없습니다 [재시도]"
- [ ] WCAG: 표는 `<table>` semantic, 헤더 `<th>` + `<thead>`, 차트 aria-label
- [ ] `pnpm typecheck && lint && test && test:e2e --project=chromium && build` 모두 그린

---

## 6. E2E 골든 패스

```
1. 인증 사용자가 /usage 진입
2. h1 "사용량 분석" + h-sub "NILM 가전별 분해 결과" 표시
3. 도구바 (Segmented + 기간 선택 + CSV 내보내기) 표시
4. 주간 페어 차트 카드 (legend 포함) 표시
5. grid-2: 시간대별 라인 차트 + 가전별 분해 표 (5행) 표시
6. 월별 막대 차트 카드 표시
7. "CSV 내보내기" 클릭 → alert "준비 중" (e2e 에서 dialog handler 로 검증)
```

테스트 파일:
- `tests/e2e/usage.spec.ts` — 모든 영역 visible + 도구바 클릭 동작 (1-2 케이스)
- `tests/unit/usage.test.tsx` — UsagePage 의 success/error 분기 + 가전 분해 표의 행 수

---

## 7. 의존 / 선행 조건

- **선행 Phase**: PLAN_00, 02, 03 (모두 머지)
- **신규 의존성**: 없음 (Recharts/TanStack Query 이미 사용)
- **차트 승격 작업**: `src/components/charts/` 신규 디렉토리 + 2 컴포넌트 이동 + Dashboard 의 import 경로 갱신
- **MSW handler 추가**: `/api/usage/analysis` + `tests/fixtures/usageData.ts`

---

## 8. 범위 제외 (Out of Scope)

- **모바일 반응형** — 데스크탑 1440 only (PLAN_M 후속)
- **CSV 내보내기 본 구현** — Phase 04 = placeholder. 후속 Phase 에 blob 생성 + download
- **기간 선택 (date range picker)** — Phase 04 = placeholder
- **Segmented control 일/월/연 데이터 전환** — visual only. 후속 Phase 에 endpoint 분리 + 데이터 전환
- **시간대별 차트의 인터랙션 고도화** (zoom, brush) — 후속
- **가전별 표 정렬/필터** — 후속
- **빈 상태 (신규 가입자 데이터 부재)** — 후속
- **번들 크기 최적화** — 별도 PLAN_TUNING (Recharts manualChunks)

---

## 9. 위험 / 미정 사항 (사용자 검토 필요)

### 잠정 결정 (5건)

1. **차트 컴포넌트 승격**: `WeeklyPairBarChart` + `MonthlyBarChart` → **`src/components/charts/`** (cross-feature import 회피, Phase 03 → Phase 04 두 번째 등장)
2. **CSV 내보내기 / 기간 선택**: **placeholder** (alert "준비 중") — 데드라인 압박, 후속 PLAN
3. **Segmented control 동작**: **visual only** ("주" fixed). 일/월/연 클릭 시 alert. 데이터 전환은 후속
4. **24h 라인 차트**: Recharts `LineChart` + 2 시리즈 (`average` 점선 `strokeDasharray="4 4"` + `today` 실선 `var(--ink-1)`)
5. **MSW endpoint**: **단일 `GET /api/usage/analysis`** (주간 + 시간대 + 가전 분해 + 월별 한 번에)

### 잔존 불확실성

- **가전 분해 표의 전주 대비 색상**: `+12%` 같이 prefix `+`/`-` 로 의미 표현. 색상은 Phase 04 = ink-2 단색 (디자인 그레이스케일)
- **"오늘" 라인의 의미**: dev mock 은 임의 데이터. 실 데이터 합류 시 "현재 시각까지의 실측" 인지 "당일 24h 예상" 인지 백엔드 확인 필요
- **24h X축 표기**: 0~23 vs 00:00~23:00 vs 6시간 간격(00/06/12/18/24)? 디자인은 6시간 간격. Phase 04 = 6시간 tick 만 표시 (Recharts `interval` prop)

### Phase 04 작업량 추정

- 작성 일정: 2일 (차트 승격 + 신규 컴포넌트 4 + MSW + 테스트)
- 위험: Recharts LineChart 의 strokeDasharray + 2 시리즈 색상 매칭 첫 도입 디버깅 (1시간 buffer)
