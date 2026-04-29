# Frontend Phase 06 — 설정 / 계정 본 구현

> 작성일: 2026-04-29
> 브랜치: Frontend
> 도메인: settings (5탭)
> 디자인 변형: **A+B+C+D+E 결합** — `Frontend/docs/screen_variants.md` §06 매핑
> 데드라인 컨텍스트: 2026-05-18 공모전 출품 (-19일)

---

## 1. 목표

인증 사용자가 `/settings/*` 진입 시 좌측 사이드바 5탭으로 프로필·알림·보안·이상 탐지 내역·이메일 연동을 탐색하고, **각 탭별 시각 의도와 핵심 인터랙션**을 확인한다. **모든 데이터는 mock**, 사용자 직접 변경(저장·삭제·발송)은 일관되게 visual only 처리(추후 mutation Phase 에서 활성화).

> 가장 큰 Phase. 5 sub-Phase 묶음으로 보되, **D(이상 탐지 내역)·E(이메일 연동) 는 단순화** — 이메일 SMTP/POP 사용자 직접 입력은 B2C 사용자 시나리오와 어긋나므로 큰 폭 축소.

---

## 2. 화면 / 라우트

| 라우트 | 컴포넌트 | 접근 권한 | 비고 |
|---|---|---|---|
| `/settings` | `SettingsLayout` (Outlet) | protected | 사이드바 + Outlet (이미 존재) |
| `/settings/account` | `AccountPage` | protected | 06-A 프로필 + 한전 연동 (카드 2) |
| `/settings/notifications` | `NotificationsPage` | protected | 06-B 알림×채널 매트릭스 + 방해 금지 |
| `/settings/security` | `SecurityPage` | protected | 06-C 비밀번호 / 2FA / 세션 / 위험 영역 |
| `/settings/anomaly-log` | `AnomalyLogPage` | protected | 06-D KPI 3 + 필터 + 이벤트 테이블 (내보내기 visual only) |
| `/settings/email` | `EmailPage` | protected | 06-E **단순화**: 수신 주소 + 알림 종류 토글 + 테스트 발송 (SMTP/POP visual only) |

**라우트·placeholder 모두 Phase 0 에서 이미 깔려있음** — 본 Phase 는 5 페이지 내부를 채우는 작업.

---

## 3. 컴포넌트 트리 (탭별)

### 06-A AccountPage

```
AccountPage
├── ProfileCard                                ← features/settings/components/ProfileCard.tsx
│   ├── 카드 헤더 "프로필" + "수정" pill 버튼 (visual)
│   └── readonly 표 (이름 / 이메일 / 휴대폰 / 구성원 수)
└── KepcoLinkCard                              ← features/settings/components/KepcoLinkCard.tsx
    ├── 카드 헤더 "한전 연동" + "재연동" pill 버튼 (visual)
    └── readonly 표 (고객번호 / 주소(마스킹) / 계약 종별 / 연동일)
```

### 06-B NotificationsPage

```
NotificationsPage
├── PageHeader (h2 "알림" + h-sub)
├── NotificationMatrixCard                     ← features/settings/components/NotificationMatrixCard.tsx
│   └── 표 (행 = 알림 종류 4-5종, 열 = 채널 3 [이메일/SMS/푸시], 셀 = checkbox)
└── DoNotDisturbCard                           ← features/settings/components/DoNotDisturbCard.tsx
    └── 토글 + 시간 범위 select 2 (시작/종료, 30분 단위)
```

### 06-C SecurityPage

```
SecurityPage
├── PageHeader (h2 "보안" + h-sub)
├── PasswordCard                               ← features/settings/components/PasswordCard.tsx
│   └── 비밀번호 변경 폼 (현재 / 신규 / 확인 + "변경" 버튼 visual only)
├── TwoFactorCard                              ← features/settings/components/TwoFactorCard.tsx
│   └── 2FA 토글 + 상태 pill ("미설정" / "활성")
├── SessionsCard                               ← features/settings/components/SessionsCard.tsx
│   └── 활성 세션 표 (디바이스 / 위치 / 마지막 활동 / 로그아웃 버튼 visual)
└── DangerZoneCard                             ← features/settings/components/DangerZoneCard.tsx
    └── "계정 삭제" 버튼 + 경고 텍스트 (red border, 클릭 visual only)
```

### 06-D AnomalyLogPage

```
AnomalyLogPage
├── PageHeader (h2 "이상 탐지 내역" + h-sub)
├── grid-3 KPI                                 ← src/components/SummaryStat 재사용 (Phase 03)
│   ├── 이번 달 이벤트 (12건)
│   ├── 평균 응답 시간 (3시간 12분)
│   └── 미해결 (2건)
├── FilterPillsCard                            ← features/settings/components/FilterPillsCard.tsx
│   └── 기간 / 심각도(낮음·중간·높음) / 가전 / 상태 — pill 버튼 그룹 (toggle visual only)
├── AnomalyEventsTable                         ← features/settings/components/AnomalyEventsTable.tsx
│   └── 표 (날짜 / 가전 / 심각도 / 설명 / 상태 / 조치) — 8-10행 mock
└── ExportToolbar                              ← visual only (CSV/JSON/PDF 버튼 alert)
```

### 06-E EmailPage (**단순화 적용**)

```
EmailPage
├── PageHeader (h2 "이메일 연동" + h-sub "이상 탐지·캐시백 알림을 받을 이메일 설정")
├── EmailRecipientCard                         ← features/settings/components/EmailRecipientCard.tsx
│   └── 수신 이메일 입력 (현재 가입 이메일 표시) + "다른 주소 사용" 체크박스 → 추가 입력란
├── EmailNotificationToggleCard                ← features/settings/components/EmailNotificationToggleCard.tsx
│   └── 알림 종류 토글 4종 (이상 탐지 / 캐시백 정산 / 주간 리포트 / 정책 안내)
├── EmailTestCard                              ← features/settings/components/EmailTestCard.tsx
│   └── "테스트 메일 발송" 버튼 + 발송 결과 영역 (visual only — 클릭 시 mock success 메시지)
└── AdvancedSmtpDisclosure                     ← visual only collapsed (SMTP/POP 설정은 admin/B2B 전용 안내 한 줄)
```

> 06-E **단순화 근거**: B2C 거주자 시나리오에서 SMTP host/port/계정 직접 입력은 일반 사용자 인지 부담 큼.
> 핵심은 "어디로 받을지(주소) + 무엇을 받을지(종류) + 작동 확인(테스트)" 3가지로 압축.

### 디자인 토큰 매핑 (공통)

| 영역 | Tailwind 유틸 |
|---|---|
| 카드 | `border border-line-2 bg-canvas p-6` |
| 카드 헤더 h3 | `text-base font-semibold` |
| 보조 텍스트 | `text-sm text-ink-3` |
| pill 버튼 (visual) | `bg-fill-2 text-ink-2 px-3 py-1 text-xs` |
| 위험 카드 (DangerZone) | `border border-state-danger` (없으면 `border-red-400`) |
| KPI 카드 | Phase 03 의 `SummaryStat` 그대로 |
| 사이드바 active 탭 | `border-l-2 border-ink-1 bg-fill-1 font-semibold` (이미 SettingsLayout 에 적용) |

---

## 4. API 엔드포인트 의존

| 엔드포인트 | 메서드 | 용도 | 상태 |
|---|---|---|---|
| `/api/settings/account` | GET | 프로필 + 한전 연동 한 번에 | 미배포 → MSW |
| `/api/settings/notifications` | GET | 알림 매트릭스 + 방해 금지 | 미배포 → MSW |
| `/api/settings/security` | GET | 2FA 상태 + 활성 세션 | 미배포 → MSW |
| `/api/settings/anomaly-events` | GET | 이벤트 테이블 + KPI 3 (단일 페치, 필터링은 클라이언트) | 미배포 → MSW (전체 반환 — 클라이언트가 useMemo 로 필터링) |
| `/api/settings/email` | GET | 수신 이메일 + 토글 4 + 테스트 결과 | 미배포 → MSW |

**모든 mutation (PATCH/POST 저장·발송) 은 본 Phase 범위 외** — 클릭 시 visual feedback 만, 후속 mutation Phase 에서 활성화.

응답 스키마 (제안):
```ts
type AccountResponse = {
  profile: { name: string; email: string; phone: string; memberCount: number };
  kepco:   { customerNo: string; addressMasked: string; contractType: string; linkedAt: string };
};

type NotificationsResponse = {
  matrix: Array<{ kind: string; email: boolean; sms: boolean; push: boolean }>;
  doNotDisturb: { enabled: boolean; startMinutes: number; endMinutes: number };
};

type SecurityResponse = {
  twoFactorEnabled: boolean;
  sessions: Array<{ id: string; device: string; location: string; lastActiveAt: string; current: boolean }>;
};

type AnomalyEventsResponse = {
  kpi: { monthCount: number; avgResponseMinutes: number; unresolvedCount: number };
  events: Array<{
    id: string; occurredAt: string; appliance: string;
    severity: "low" | "medium" | "high";
    description: string; status: "open" | "resolved";
  }>;
};

type EmailResponse = {
  primaryEmail: string;
  alternateEmail: string | null;
  toggles: { anomaly: boolean; cashback: boolean; weeklyReport: boolean; policy: boolean };
  lastTestAt: string | null;
};
```

---

## 5. 인수 기준 (Acceptance)

탭별 분리. 각 탭은 독립적으로 인수 가능하지만 본 Phase 는 **5개 동시 머지** (탭 전환 일관성 보장).

### 06-A AccountPage
- [ ] `/settings/account` 진입 → ProfileCard + KepcoLinkCard 2개 카드 렌더
- [ ] 프로필 카드: 이름/이메일/휴대폰/구성원 수 4행 + "수정" pill
- [ ] 한전 카드: 고객번호/주소(마스킹)/계약 종별/연동일 4행 + "재연동" pill
- [ ] 두 pill 클릭 → visual only (alert 또는 무동작)

### 06-B NotificationsPage
- [ ] 매트릭스 표 4행 × 3채널 = 12 checkbox + 헤더
- [ ] 방해 금지 토글 + 시작/종료 select 2
- [ ] 모든 입력 — 로컬 state 만 변동, 서버 저장 visual only

### 06-C SecurityPage
- [ ] 4 카드 모두 렌더 (Password / 2FA / Sessions / DangerZone)
- [ ] 비밀번호 폼 — 빈 값 검증만 (제출 시 visual feedback "변경되었습니다" mock)
- [ ] 2FA 토글 visual
- [ ] 활성 세션 표 — 현재 세션 표시 (`current: true`) + "로그아웃" 버튼 visual
- [ ] DangerZone 클릭 → confirm 모달 또는 alert (실 삭제 금지)

### 06-D AnomalyLogPage
- [ ] grid-3 KPI 카드 (Phase 03 SummaryStat 재사용)
- [ ] 필터 pill 클릭 → active state 토글 + **클라이언트 사이드 필터링 작동** (심각도/상태 다중 선택, 가전 단일 선택, 기간 select)
- [ ] 필터 적용 시 KPI 의 "이번 달 이벤트" 도 동기 갱신 (필터 결과 행 수)
- [ ] 이벤트 테이블 8-10행, 심각도 pill 색 차등 (low=`bg-fill-2` / medium=`bg-yellow-100` / high=`bg-red-100`)
- [ ] 내보내기 버튼 3개 (CSV/JSON/PDF) — 클릭 시 alert "준비 중"

### 06-E EmailPage
- [ ] 수신 주소 (가입 이메일 prefilled) + "다른 주소 사용" 체크 시 입력란 노출
- [ ] 알림 토글 4종
- [ ] "테스트 메일 발송" 버튼 클릭 → mock success 메시지 200ms 후 표시
- [ ] AdvancedSmtpDisclosure — collapsed details 안내 한 줄 ("기업 사용자는 별도 SMTP 설정 가능 — 추후 지원")

### 공통
- [ ] 사이드바 active 탭 highlight (이미 작동)
- [ ] 모든 페이지: 로딩/에러 분기 (TanStack Query)
- [ ] WCAG: 폼 라벨 매핑, 키보드 네비, 표 semantic
- [ ] `pnpm typecheck && lint && test && test:e2e --project=chromium && build` 모두 그린

---

## 6. E2E 골든 패스

```
1. 인증 사용자가 사이드바 "설정" 클릭 → /settings/account 진입
2. 5개 탭 순차 클릭 → 각각 페이지 변경 + h2/h3 표시 확인
3. /settings/anomaly-log: KPI 3 + 필터 pill + 표 8행 visible
4. /settings/email: "테스트 메일 발송" 클릭 → 성공 메시지 visible
5. /settings/security: DangerZone 클릭 → 모달/alert 표시
```

테스트 분배:
- `tests/unit/settings.account.test.tsx` — 카드 2개 렌더 + pill
- `tests/unit/settings.notifications.test.tsx` — 매트릭스 12 checkbox
- `tests/unit/settings.security.test.tsx` — 4 카드 + 폼 validation
- `tests/unit/settings.anomalyLog.test.tsx` — KPI / 필터 토글 / 테이블 행 수
- `tests/unit/settings.email.test.tsx` — 토글 + 테스트 발송 mock
- `tests/e2e/settings.spec.ts` — 5탭 순차 진입 + 핵심 영역 visible

---

## 7. 의존 / 선행 조건

- **선행 Phase**: PLAN_00, 02, 03 (모두 머지 — Phase 04/05 도 머지됨)
- **신규 의존성**: 없음 (date format 은 `Intl.DateTimeFormat` 표준)
- **MSW handler 추가**: 5 endpoint × `handlers.ts` + `tests/fixtures/settingsData.ts`
- **재사용 컴포넌트**:
  - `src/components/SummaryStat` (KPI — Phase 03)
  - `src/layouts/Sidebar`/`Topbar` (이미 존재)
  - `SettingsLayout` (이미 존재)

---

## 8. 범위 제외 (Out of Scope)

### 명시 visual only 처리 (= 본 Phase 미구현, 백로그 등록)

| 영역 | visual only 사유 | 우선순위 |
|---|---|---|
| 프로필 / 한전 정보 수정 mutation | 사용자 PII 변경 — 백엔드 정책 필요 | MED |
| 알림·방해 금지 저장 mutation | PATCH `/api/settings/notifications` | MED |
| 비밀번호 변경 / 2FA 활성화 / 세션 로그아웃 / 계정 삭제 | 보안 mutation — 백엔드 정책 + 추가 인증 단계 | HIGH |
| 이상 탐지 이벤트 **서버 사이드** 필터·페이징 | 본 Phase 는 클라이언트 필터로 본 구현. 백엔드 합류 시 query param 전환 | MED |
| CSV / JSON / PDF 내보내기 | Phase 04 의 CSV 와 묶어 통합 PR | HIGH |
| 이메일 테스트 발송 실 SMTP | 백엔드 SMTP 합류 시 | MED |
| **SMTP/POP 사용자 직접 설정** (디자인 핸드오프 변형 E 원본) | **B2C 시나리오와 mismatch — admin/B2B 전용 또는 영구 제외 검토** | LOW |
| 이메일 템플릿 편집기 (디자인 변형 E 원본) | 사용자가 템플릿을 편집하는 시나리오 부재 — admin 전용 | LOW |

### 후속 Phase

- 모바일 반응형 — 데스크탑 1440 only (출품 후 PLAN_M)
- 시각 회귀 (Playwright 스크린샷)
- 약관 / 개인정보 처리방침 페이지

---

## 9. 위험 / 미정 사항 (사용자 검토 필요)

### D / E 단순화 결정 — **E 만 단순화 채택** (사용자 확정 2026-04-29)

#### D: AnomalyLog 필터 → **본 구현** (단순화 미채택)

- **결정**: 필터 pill 클릭 시 **클라이언트 사이드 필터링** 작동. mock 이벤트 배열을 심각도/상태/가전/기간 필터로 거른 결과만 표 + KPI "이번 달 이벤트" 행 수에 반영.
- **Why**: 사용자 확정. Phase 04 segmented(visual only)와 다른 결정 — anomaly 로그는 사용자가 자기 데이터를 실제로 탐색하는 시나리오가 핵심이고, mock 8-10행 규모에서도 필터링 인터랙션은 가치 있음.
- **백엔드 합류 시 전환**: 클라이언트 필터 → query param 송신. 이 시점에서 handler 가 query 무시하고 전체 반환하던 코드 제거. 백엔드 페이징·정렬 도입 시 자연스럽게 서버 사이드로.

#### E-단순화: SMTP/POP 직접 입력 → AdvancedSmtpDisclosure 한 줄 안내

- **결정**: 06-E 본 구현은 **수신 주소 + 알림 토글 + 테스트** 3가지로 축소. SMTP host/port/계정/암호화/POP 인입 등 디자인 핸드오프 변형 E 의 깊은 폼은 collapsed disclosure 한 줄로 압축 ("기업 사용자는 별도 SMTP 설정 가능 — 추후 지원").
- **Why**: B2C 거주자 사용자가 SMTP 설정을 직접 다루는 시나리오 없음 (KEPCO 캐시백 피벗 후 사용자상). 디자인 핸드오프 변형 E 는 운영자/B2B 콘솔용 조각으로 추정.
- **대안(미채택)**:
  - (a) 변형 E 원본 그대로 구현 — 폼 필드 10+개, 테스트 부담 큼, 데드라인 -19일에 비효율
  - (b) E 탭 자체 제거 — 사이드바 5→4탭 변경 → screen_variants v3 와 어긋남
- **사용자 확인 필요**: 변형 E 의 SMTP/POP 가 B2C UI 에 그대로 노출되어야 한다면 본 PLAN §3-E 를 확장. 그렇지 않다면 본 단순화 채택.

### 잠정 결정 (4건)

1. **mutation 일괄 visual only**: 5탭 모든 저장/발송/삭제 버튼은 visual only. 후속 mutation Phase 에 통합 (PATCH/POST 한 번에).
2. **이상 탐지 mock 8-10행**: KPI(미해결 2건) 와 일관되도록 unresolved 2건 + resolved 6-8건.
3. **2FA 카드**: 토글 visual + 상태 pill ("미설정" 기본). 실제 2FA QR/TOTP 등록 흐름은 후속.
4. **활성 세션 mock**: 2-3건 (현재 데스크톱 + 모바일 + 다른 위치). 서버에서 실 세션 정보 받기 전까지 hard-coded.

### 잔존 불확실성

- **계정 삭제 흐름**: confirm 모달 vs 별도 `/settings/account/delete` 라우트 — 본 Phase 는 alert 만, 후속에 결정.
- **이메일 토글 4종 정책**: anomaly / cashback / weeklyReport / policy — 백엔드 정책 합류 시 종류·디폴트 재조정.
- **이상 탐지 심각도 색**: low/medium/high — Tailwind 토큰 부재. inline `bg-yellow-100`/`bg-red-100` 인라인 vs 새 토큰 추가 — 인라인 채택 (1회성).

---

## 10. Phase 06 작업량 추정

| sub-Phase | 추정 | 비고 |
|---|---|---|
| 06-A AccountPage | 0.3일 | 카드 2 readonly, 단순 |
| 06-B NotificationsPage | 0.5일 | 매트릭스 표 + 방해 금지 |
| 06-C SecurityPage | 0.7일 | 4 카드 + 폼 validation |
| 06-D AnomalyLogPage | 1.0일 | KPI + 필터(클라이언트 사이드 필터링) + 테이블 |
| 06-E EmailPage (단순화) | 0.4일 | 단순화 후 카드 4 |
| 공통 (MSW + 테스트 + e2e) | 0.4일 | 5 endpoint + 5 unit + 1 e2e |
| **총** | **~3.3일** | 가장 큰 Phase. 데드라인 5/18 까지 -19일 → Phase 07 (insights) 여유 충분 |

> **단순화 효과**: E 만 단순화. 변형 E 원본(SMTP/POP 폼) 포함 시 +1.0일 추가. D 는 본 구현(클라이언트 필터링)으로 사용자 가치 보존.
