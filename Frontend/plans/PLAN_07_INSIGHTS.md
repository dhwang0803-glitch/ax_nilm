# Frontend Phase 07 — AI 진단 (`/insights`) 본 구현

> 작성일: 2026-04-30
> 브랜치: Frontend
> 도메인: insights (단일 화면, sub-Phase 분리 없음)
> 디자인 변형: **A 진단 요약** — `Frontend/docs/screen_variants.md` §07
> 데드라인 컨텍스트: 2026-05-18 공모전 출품 (-18일)

---

## 1. 목표

인증 사용자가 `/insights` 진입 시 **NILM 모델의 실시간 진단 결과**를 한 화면에서 확인한다 — 이번 주/달 진단 KPI 3개 + 최근 이상 사용 highlight + LLM 추천 표 + 주간 진단 추이 차트. **모든 데이터는 mock**, 추천 클릭·재진단 등 mutation 은 visual only.

> Phase 06 묶음 종료 직후의 **단일 도메인 Phase**. 5탭 sub-Phase 묶음이었던 06 과 달리 본 Phase 는 한 페이지 1 PR.

### REQ-002 분산 재확인 (06-D 와의 명확한 차이)

| 영역 | 07 `/insights` (본 Phase) | 06-D `/settings/anomaly-log` (이미 머지) |
|---|---|---|
| 시점 | **현재·미래 지향** (지금 이상 / 추천 / 신뢰도) | **과거 지향** (전체 이벤트 로그 / 감사) |
| 데이터 형식 | KPI + highlight 카드 1-3건 + 추천 표 + 추이 차트 | 전체 이벤트 표 8-10행 + 다축 필터 |
| 사용자 행동 | "지금 무엇을 해야 하나" | "언제 무슨 일이 있었나" |
| LLM 의존 | 추천 텍스트 = LLM 생성 (익명화 후) | 없음 (이벤트 기록만) |

→ 동일 이벤트가 **양쪽에 동시 등장 가능** (06-D = 한 행, 07 = highlight 카드). 의도된 분산.

---

## 2. 화면 / 라우트

| 라우트 | 컴포넌트 | 접근 권한 | 비고 |
|---|---|---|---|
| `/insights` | `InsightsPage` | protected | 단일 페이지 (이미 placeholder 존재 — `src/features/insights/InsightsPage.tsx`) |

라우트 등록·사이드바 메뉴(`AI 진단`)는 Phase 0 부트스트랩 시점에 이미 적용되어 있음 — 본 Phase 는 placeholder 를 본 구현으로 교체.

---

## 3. 컴포넌트 트리

```
InsightsPage
├── PageHeader (h2 "AI 진단" + 우측 메타 "마지막 분석: 2026-04-30 09:12 · 모델 v2.4")
├── InsightsKpiSection                   ← features/insights/components/InsightsKpiSection.tsx
│   ├── KpiCard "이번 주 진단" (12건 / delta "전주 대비 +3건")
│   ├── KpiCard "이번 달 예상 절약" (9,840원 / delta "+1,230원")
│   └── KpiCard "모델 신뢰도" (92% / foot "표본 79세대")
├── AnomalyHighlightCard                 ← features/insights/components/AnomalyHighlightCard.tsx
│   └── 최근 이상 사용 1-3건 카드 리스트 (가전 + severity pill + 헤드라인 + LLM 권고 한 줄 + "자세히" 링크 visual)
├── RecommendationsTable                 ← features/insights/components/RecommendationsTable.tsx
│   └── 표 (가전 / 추천 조치 / 예상 절약 / 신뢰도 bar) — 5-8행 mock
└── WeeklyTrendCard                      ← features/insights/components/WeeklyTrendCard.tsx
    └── Recharts ComposedChart — 막대(진단 건수) + 라인(예상 절약) — 4-8주
```

### 디자인 토큰 매핑 (06 일관 적용)

| 영역 | Tailwind 유틸 |
|---|---|
| 카드 | `border border-line-2 bg-canvas p-6` |
| 카드 헤더 h3 | `text-base font-semibold` |
| 보조 텍스트 | `text-sm text-ink-3` |
| severity pill (06-D 인라인 패턴 재사용) | low=`bg-fill-2` / medium=`bg-yellow-100` / high=`bg-red-100` |
| 신뢰도 bar | `bg-fill-2` 트랙 + `bg-ink-1` fill (퍼센트 폭) |
| pill 버튼 (visual) | `bg-fill-2 text-ink-2 px-3 py-1 text-xs` |

### 재사용 컴포넌트

- `src/components/KpiCard.tsx` — 03 / 06-D 패턴 그대로 (delta + foot 활용)
- `src/components/charts/*` — 04 의 `WeeklyPairBarChart`/`MonthlyBarChart` 는 막대 only 라 본 Phase 의 ComposedChart 와 형태가 다름 → 새 컴포넌트 (`WeeklyTrendCard` 안에 인라인 Recharts)

---

## 4. API 엔드포인트 의존

| 엔드포인트 | 메서드 | 용도 | 상태 |
|---|---|---|---|
| `/api/insights/summary` | GET | KPI + highlight + 추천 + 주간 추이 한 번에 | 미배포 → MSW (delay 300ms — 06 일관) |

**단일 페치** 채택 — `/insights` 는 한 화면 한 데이터셋이므로 페이지 = 한 useQuery 가 06 EmailPage 와 같은 패턴. 추후 LLM 응답이 오래 걸리면 KPI + 추천만 분리하는 방향 검토 (현재 mock 단계는 단일).

본 Phase 에 **mutation 없음** (재진단·추천 dismiss·즐겨찾기 등은 후속 mutation Phase).

### 응답 스키마

```ts
type InsightsResponse = {
  generatedAt: string;       // ISO — 마지막 분석 시각
  modelVersion: string;      // "v2.4" 형태
  sampleHouseholds: number;  // 모델 학습 샘플 (KPI foot 표시)
  kpi: {
    weeklyDiagnosisCount: number;       // 12
    weeklyDiagnosisDelta: number;       // +3 (전주 대비)
    monthlyEstimatedSavingKrw: number;  // 9840
    monthlySavingDelta: number;         // +1230
    modelConfidence: number;            // 0.92
  };
  anomalyHighlights: Array<{
    id: string;
    appliance: string;          // "에어컨"
    severity: "low" | "medium" | "high";
    headline: string;           // "정상 대비 25% 과소비"
    recommendation: string;     // LLM 권고 1-2줄
    detectedAt: string;
  }>;
  recommendations: Array<{
    id: string;
    appliance: string;
    action: string;             // "필터 청소 · 설정 온도 +1℃"
    estimatedSavingKrw: number;
    confidence: number;         // 0~1
  }>;
  weeklyTrend: Array<{
    weekLabel: string;          // "W14" / "4월 1주" — UI 단순 표시용
    diagnosisCount: number;
    estimatedSavingKrw: number;
  }>;
};
```

LLM 텍스트는 **API_Server 가 가구 식별정보 제외 익명화 후 가공해 전달** (루트 `CLAUDE.md` 규칙) — Frontend 는 표시만.

---

## 5. 인수 기준 (Acceptance)

- [ ] `/insights` 진입 → PageHeader + 4 섹션 (KPI 3 / Highlight / 추천 / 추이) 모두 렌더
- [ ] KPI 3 카드 — delta 양수 `+`, foot "표본 N세대"/"전월 대비" 표시
- [ ] AnomalyHighlightCard — 1-3건 카드 (severity pill 색 06-D 패턴) + 빈 응답 시 "최근 이상 사용 없음" 빈 상태
- [ ] RecommendationsTable — 5-8행, 신뢰도 컬럼은 시각 바(`bg-fill-2` 트랙)
- [ ] WeeklyTrendCard — Recharts ComposedChart, 4-8 데이터 포인트, hover tooltip
- [ ] 로딩: skeleton 4 섹션 (06 EmailSkeleton 패턴)
- [ ] 에러: 카드 1개 + 재시도 버튼 (06 EmailPage 패턴)
- [ ] 빈 응답 (`anomalyHighlights = []` / `recommendations = []`): 섹션별 빈 상태 메시지
- [ ] WCAG: 표 semantic, 헤드라인 헤딩 레벨 일관, 키보드 포커스
- [ ] `pnpm typecheck && lint && test && test:e2e --project=chromium && build` 모두 그린

---

## 6. E2E 골든 패스

```
1. 로그인 (test@example.com / nilm-mock-2026!) → /home
2. 사이드바 "AI 진단" 클릭 → /insights 진입
3. h2 "AI 진단" visible
4. KPI 3 카드 visible (이번 주 진단 / 이번 달 예상 절약 / 모델 신뢰도)
5. "최근 이상 사용" 헤딩 + 1-3 카드 visible
6. "추천 조치" 헤딩 + 표 visible (행 5+)
7. "주간 추이" 헤딩 + 차트 svg visible
```

테스트 분배:
- `tests/unit/insights.test.tsx` — 4 섹션 렌더 + KPI 텍스트 + 표 행 수 + 에러 분기 + 빈 응답 분기
- `tests/e2e/insights.spec.ts` — 위 골든 패스 1건

---

## 7. 의존 / 선행 조건

- **선행 Phase**: PLAN_00 ~ 06 (모두 머지) — 사이드바 / AppShell / KpiCard / TanStack Query 모두 가용
- **신규 의존성**: 없음 (Recharts 는 04 에서 도입 완료)
- **MSW handler 추가**: `/api/insights/summary` 1 endpoint + `tests/fixtures/insightsData.ts`
- **재사용 컴포넌트**:
  - `src/components/KpiCard.tsx` (03 / 06-D 패턴)
  - `src/layouts/AppShell` (이미 라우트에 적용됨)
- **placeholder 교체 대상**: `src/features/insights/InsightsPage.tsx` (현재 2줄 placeholder)

---

## 8. 범위 제외 (Out of Scope)

### 명시 visual only 처리 (= 본 Phase 미구현, 백로그 등록)

| 영역 | visual only 사유 | 우선순위 |
|---|---|---|
| "재진단" / "다시 분석" 버튼 mutation | 백엔드 LLM 호출 트리거 — 백엔드 합류 시 | MED |
| 추천 dismiss / 완료 체크 mutation | PATCH `/api/insights/recommendations/:id` | MED |
| highlight 카드 "자세히" 링크 → 상세 페이지 | 상세 페이지 부재 (06-D 행으로 deep link 검토 필요) | LOW |
| 차트 기간 segment (4주/12주/52주) | 04 segment 와 같이 visual only 또는 본 Phase 제외 | LOW |
| 추천 신뢰도 정렬·필터 | 5-8행 규모에 정렬 UI 과잉 | LOW |

### 후속 Phase

- **데모 인박스 sprint** (출품 직전) — `project_demo_inbox_strategy.md` 참조
- 모바일 반응형 — 데스크탑 1440 only (출품 후 PLAN_M)
- LLM 응답 스트리밍 (SSE) — 백엔드 합류 후 검토

---

## 9. 위험 / 미정 사항

### 잠정 결정 (사용자 확인 시 본 PLAN 그대로 진행)

1. **단일 페치 vs 분리 페치**: 본 Phase 는 단일 (`/api/insights/summary`). LLM 응답이 실측에서 KPI 보다 느릴 경우 후속에서 KPI 만 따로 (`/api/insights/kpi`) 분리 검토.
2. **Highlight 카드 개수**: 1-3건 권장 (mock 은 2건). 전체 이상 이벤트는 06-D 에서 보는 의도 유지 — 07 은 "지금 봐야 하는 것" 만.
3. **신뢰도 표기**: 0~1 → 정수 % (예: 0.92 → "92%"). 시각 바 폭도 % 동일.
4. **주간 추이 차트 종류**: ComposedChart (막대 = 진단 건수 / 라인 = 예상 절약). LineChart 단일도 검토했으나 두 축 단위가 다르므로 ComposedChart + 우측 보조축.
5. **mock TODAY**: 06-D 와 동일하게 `new Date("2026-04-30")` 하드코딩 (백엔드 합류 시 제거).
6. **modelVersion 표시 위치**: PageHeader 우측 메타 한 줄. KPI 카드 foot 에 sampleHouseholds 별도 표시.

### 잔존 불확실성

- **재진단 트리거 UX**: "다시 분석" 버튼 위치(헤더 vs 푸터) — 본 Phase 에서는 버튼 자체 미배치 (visual only 도 미생성). 후속 mutation Phase 에서 버튼 + 백엔드 LLM 호출 동시 도입.
- **추천 표의 "조치" 텍스트 길이**: LLM 출력 변동 — mock 은 1-2줄, 셀 width `max-w-[280px]` + line-clamp-2 적용 검토.
- **신뢰도 bar 색**: `bg-ink-1` 단색 vs 신뢰도 구간별 색 차등 — 본 Phase 는 단색(`bg-ink-1`) 채택, 사용자 검토 시 차등 도입 가능.

---

## 10. 작업량 추정

| 항목 | 추정 | 비고 |
|---|---|---|
| types + api hook + fixtures + handler | 0.2일 | 단일 endpoint |
| InsightsKpiSection | 0.1일 | KpiCard 3 조립 |
| AnomalyHighlightCard | 0.2일 | severity pill + 카드 1-3건 + 빈 상태 |
| RecommendationsTable | 0.2일 | 5-8행 표 + 신뢰도 bar |
| WeeklyTrendCard | 0.3일 | Recharts ComposedChart 처음 사용 |
| InsightsPage 조립 (skeleton/error/empty) | 0.1일 | 06 EmailPage 패턴 그대로 |
| 단위 테스트 + e2e | 0.3일 | 5-7 케이스 + 1 e2e |
| 검증 5종 + PR | 0.1일 | typecheck/lint/test/test:e2e/build |
| **총** | **~1.5일** | 단일 화면 / sub-Phase 분리 없음 |

> 데드라인 5/18 까지 **-18일** → Phase 07 종료 후 출품 직전 sprint (~5/15-17) 에서 **데모 인박스 + 통합 e2e + 출품 자료 + visual-only HIGH 백로그** 모두 처리 가능.
