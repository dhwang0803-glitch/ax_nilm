# Frontend Phase 05 — 캐시백 본 구현

> 작성일: 2026-04-29
> 브랜치: Frontend
> 도메인: cashback
> 디자인 변형: **C (목표 트래커)** — `Frontend/docs/screen_variants.md` 확정안
> 데드라인 컨텍스트: 2026-05-18 공모전 출품 (-19일)

---

## 1. 목표

인증 사용자가 `/cashback` 진입 시 월간 절감 목표 진행 상황(현재 / 예상 / 목표 마커)을 진행바로 보고, 주간/월별 사용 추이 차트와 오늘의 미션 표를 통해 절감 액션을 확인한다. **차트는 Phase 03/04 의 공용 컴포넌트 그대로 재사용**.

---

## 2. 화면 / 라우트

| 라우트 | 컴포넌트 | 접근 권한 | 비고 |
|---|---|---|---|
| `/cashback` | `CashbackPage` | protected (AuthGuard) | KEPCO 캐시백 트래커 |

---

## 3. 컴포넌트 트리

```
CashbackPage
├── PageHeader (h1 "목표 트래커" + h-sub "월간 절감 목표 + 진행 상황")
├── GoalProgressCard                      ← features/cashback/components/GoalProgressCard.tsx
│   ├── h4 "11월 목표 — 10% 절감 / ₩11,900" + D-Day pill
│   ├── 진행바 (현재 ink-2 + 예상 줄무늬 gradient)
│   └── 3 마커 (현재 / 예상 / 목표)
├── grid-2
│   ├── 주간 차트 카드                     ← src/components/charts/WeeklyPairBarChart 재사용
│   └── 월별 차트 카드                     ← src/components/charts/MonthlyBarChart 재사용
└── TodayMissionsCard                     ← features/cashback/components/TodayMissionsCard.tsx
    └── 표 (미션 / 예상 절감 kWh / 상태 pill)
```

### 신규 컴포넌트 (`features/cashback/components/`)

| 컴포넌트 | 역할 |
|---|---|
| `GoalProgressCard` | 목표 진행바 + 마커 + D-Day pill. CSS 줄무늬 패턴(예상 부분)은 inline style 또는 `@layer components` 의 새 클래스 |
| `TodayMissionsCard` | 표 (미션 / 예상 절감 / 상태) — 상태는 `대기`/`완료` pill |

차트는 신규 컴포넌트 없음 — Phase 04 의 src/components/charts/ 직접 import.

### 디자인 토큰 매핑 (진행바)

| 영역 | Tailwind 유틸 |
|---|---|
| 진행바 트랙 | `bg-fill-2 border border-line-2 h-6` |
| 현재 부분 (62%) | `bg-ink-2 text-canvas` + 인라인 width % |
| 예상 부분 (8%, 줄무늬) | inline style `repeating-linear-gradient(45deg, var(--ink-3) 0 4px, var(--fill-2) 4px 8px)` (Tailwind 유틸 불가) |
| D-Day pill | `bg-fill-2 text-ink-2` |
| 상태 pill (대기) | `bg-fill-2 text-ink-2` |
| 상태 pill (완료) | `bg-ink-1 text-canvas` |

---

## 4. API 엔드포인트 의존

| 엔드포인트 | 메서드 | 용도 | 상태 |
|---|---|---|---|
| `/api/cashback/tracker` | GET | 목표 + 진행 + weekly 7 + monthly 12 + missions 한 번에 | 미배포 → MSW 모킹 |

응답 스키마 (제안):
```ts
type CashbackTracker = {
  goal: {
    month: number;                  // 11
    targetSavingsPercent: number;   // 10
    targetCashbackKrw: number;      // 11900
    daysRemaining: number;          // 15
    currentSavingsPercent: number;  // 8.4
    expectedSavingsPercent: number; // 9.5
    progressPercent: number;        // 62 (현재 / 목표 비율)
    expectedProgressPercent: number; // 8 (예상 추가 부분의 % point — 진행바 styling)
  };
  weekly: { days: WeeklyPairDatum[] };
  monthly: { year: number; months: MonthlyDatum[]; currentMonth: number };
  missions: Array<{
    id: string;
    title: string;
    expectedSavingsKwh: number;
    status: "pending" | "done";
  }>;
};
```

`progressPercent` + `expectedProgressPercent` 는 진행바 시각용 (디자인의 62% / 8% 매칭).

---

## 5. 인수 기준 (Acceptance)

- [ ] `/cashback` 인증 후 진입 → 헤더 + 진행바 카드 + grid-2 차트 + 미션 표 모두 렌더
- [ ] 진행바: 현재 부분 dark + 예상 부분 줄무늬 gradient + 3 마커 (현재/예상/목표)
- [ ] 진행바 위 D-Day pill (`D-15` 형태)
- [ ] 주간 페어 차트 + 월별 차트 (Phase 03/04 와 동일)
- [ ] 미션 표: 3행 (대기 2 + 완료 1) 표시. 상태 pill 색상 다름 (완료 = dark, 대기 = muted)
- [ ] 로딩/에러/재시도 분기
- [ ] WCAG: 진행바 `role="progressbar"` + `aria-valuenow` (현재 절감률), 표 semantic
- [ ] `pnpm typecheck && lint && test && test:e2e --project=chromium && build` 모두 그린

---

## 6. E2E 골든 패스

```
1. 인증 사용자가 /cashback 진입 (sidebar 클릭)
2. h1 "목표 트래커" + h-sub 표시
3. "11월 목표 — 10% 절감 / ₩11,900" + D-Day pill 표시
4. 진행바 + 3 마커(현재 8.4% / 예상 9.5% / 목표 10%)
5. grid-2: 주간 + 월별 차트
6. 오늘의 미션 표 (3행)
```

테스트:
- `tests/unit/cashback.test.tsx` — success / error / 진행바 aria 속성 / 미션 행 수
- `tests/e2e/cashback.spec.ts` — sidebar 진입 + 모든 영역 visible

---

## 7. 의존 / 선행 조건

- **선행 Phase**: PLAN_00, 02, 03, 04 (모두 머지)
- **신규 의존성**: 없음
- **차트**: src/components/charts/ 그대로 재사용 (Phase 04 에서 승격됨)
- **MSW handler 추가**: `/api/cashback/tracker` + `tests/fixtures/cashbackData.ts`

---

## 8. 범위 제외 (Out of Scope)

- **모바일 반응형** — 데스크탑 1440 only
- **미션 상태 토글** (대기 → 완료 클릭 동작) — Phase 5 = visual only. 후속 Phase 에 mutation API 추가
- **목표 변경 UI** (사용자가 절감 목표 % 직접 설정) — 후속
- **캐시백 지급 내역 표** (변형 A 패턴) — 변형 C 에 없음, 후속 또는 별도 화면
- **단가 구간 표** (3% 이상 30원 등) — 변형 A 만 보유, 변형 C 미포함
- **PDF 영수증 내려받기** (변형 B 패턴) — 변형 C 미포함
- **시각 회귀** — 후속

---

## 9. 위험 / 미정 사항 (사용자 검토 필요)

### 잠정 결정 (4건)

1. **진행바 줄무늬**: Tailwind 유틸 불가 → **inline style** `repeating-linear-gradient` (Hero 의 `placeholder-img` 패턴과 동일 — 1회성이라 `@layer components` 클래스화 안 함)
2. **D-Day pill**: 정적 mock 값(`D-15`). 백엔드 응답에 `daysRemaining` 포함 → 동적 표시
3. **미션 상태 토글**: **visual only** (Phase 5 미션 클릭 무동작). 후속 Phase 에 PATCH `/api/missions/:id` mutation 추가
4. **MSW endpoint**: **단일 `GET /api/cashback/tracker`** (목표 + 차트 데이터 + 미션 한 번에)

### 잔존 불확실성

- **D-Day 계산 기준**: dev mock 정적. 실 백엔드 합류 시 "현재 시각 → 월말" 계산 (`new Date()` 또는 백엔드 응답)
- **목표 절감률 시드**: 디자인 = 10%, ₩11,900. 실 사용자별 다를 것 — 백엔드 정책에 따라
- **진행바 의 `progressPercent` vs `expectedProgressPercent` 합산 규칙**: 디자인 = 62% + 8% = 70% (현재 + 예상 추가) ≠ 목표 도달률. 두 값 모두 응답으로 받음 (계산 백엔드)

### Phase 05 작업량 추정

- 작성 일정: **1-2일** (차트 재사용 + 신규 2 컴포넌트 + MSW + 테스트)
- 가장 단순한 Phase. Phase 06 settings(5탭) 진입 전 가벼운 워밍업.
