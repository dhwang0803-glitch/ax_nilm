# Visual-Only / Placeholder 백로그

> Phase 별 본 구현에서 **visual only** 또는 **placeholder** 로 처리한 UI 컨트롤·기능 목록.
> 데드라인 압박(2026-05-18 공모전) 으로 본 구현 미루고 시각 의도만 보존한 항목들.
> 출품 후 또는 데드라인 여유 시 본 구현 진행.

## 작성 규칙

- 항목 추가 시 **Phase 본 구현 PR 과 같은 묶음**으로 본 백로그도 갱신
- 본 구현 완료 시 해당 항목 삭제 + 커밋 메시지에 명시
- 우선순위 표기 (HIGH / MED / LOW) — 사용자 임팩트 기준

## 우선순위 기준

- **HIGH**: 핵심 기능 — 데이터 기반 동작이 사용자 가치에 직결 (예: CSV 내보내기, 기간 선택)
- **MED**: 보조 기능 — 동작하지 않아도 화면 의도 전달 가능 (예: 자동 로그인, 미션 토글)
- **LOW**: 관리·설정 — 사용 빈도 낮고 후속 기능 (예: 비밀번호 찾기, 약관 페이지)

---

## Phase 01 — 랜딩 (`/`)

| 항목 | 위치 | 현재 동작 | 본 구현 필요 | 우선순위 |
|------|------|-----------|---------------|----------|
| "특징"/"FAQ" nav 메뉴 | `features/landing/components/PubNav.tsx` | `<a href="#features"/>` 앵커 placeholder | 마케팅 콘텐츠 섹션 추가 + 부드러운 스크롤 | LOW |
| DashboardMockup placeholder | `features/landing/components/Hero.tsx` | 줄무늬 패턴 + "FULL DASHBOARD MOCK" 라벨 | 실제 대시보드 스크린샷/이미지 (Phase 03 완성 후 캡처) | MED |

---

## Phase 02 — 인증 (`/auth/*`)

| 항목 | 위치 | 현재 동작 | 본 구현 필요 | 우선순위 |
|------|------|-----------|---------------|----------|
| 자동 로그인 체크박스 | `features/auth/components/LoginForm.tsx` | form state 만 보유, 서버 미전달 | refresh token 만료 시간 분기 또는 백엔드 정책 | MED |
| 비밀번호 찾기 버튼 | `features/auth/components/LoginForm.tsx` | `alert("준비 중입니다")` | `/auth/forgot` 라우트 + 이메일 발송 흐름 | LOW |
| OAuth 콜백 흐름 | `features/auth/api.ts` `oauthLogin` | MSW 즉시 200 모킹 | 실 OAuth provider redirect → callback URL → 백엔드 토큰 교환 | HIGH (백엔드 의존) |
| 약관 동의 텍스트 | `features/auth/components/SignupForm.tsx` | "서비스 이용약관 및 개인정보..." 텍스트 only | 약관 전문 페이지 또는 모달 + 외부 링크 | LOW |

---

## Phase 03 — 대시보드 (`/home`)

| 항목 | 위치 | 현재 동작 | 본 구현 필요 | 우선순위 |
|------|------|-----------|---------------|----------|
| Segmented control (주/월/연) | `features/dashboard/components/WeeklyUsageCard.tsx` | "주" fixed, 다른 옵션 클릭 무동작 | 데이터 endpoint 분리 + 단위별 응답 + 상태 관리 | MED |

---

## Phase 04 — 사용량 분석 (`/usage`)

| 항목 | 위치 | 현재 동작 | 본 구현 필요 | 우선순위 |
|------|------|-----------|---------------|----------|
| Toolbar segmented (일/주/월/연) | `features/usage/components/UsageToolbar.tsx` | "주" 외 클릭 시 alert "준비 중" | endpoint 분리 + 데이터 전환 + URL query param 동기화 | HIGH |
| "기간 선택" 버튼 | `features/usage/components/UsageToolbar.tsx` | alert "준비 중" | date range picker 모달 + custom 기간 fetch | HIGH |
| "CSV 내보내기" 버튼 | `features/usage/components/UsageToolbar.tsx` | alert "준비 중" | client-side blob 생성 (Papa Parse 등) 또는 백엔드 export endpoint | HIGH |

---

## Phase 05 — 캐시백 (`/cashback`)

| 항목 | 위치 | 현재 동작 | 본 구현 필요 | 우선순위 |
|------|------|-----------|---------------|----------|
| 미션 상태 토글 | `features/cashback/components/TodayMissionsCard.tsx` | 클릭 무동작 (대기/완료 표시만) | PATCH `/api/missions/:id` mutation + 낙관적 업데이트 | MED |

---

## Phase 0 / 공통 레이아웃

| 항목 | 위치 | 현재 동작 | 본 구현 필요 | 우선순위 |
|------|------|-----------|---------------|----------|
| Topbar 검색 input | `layouts/Topbar.tsx` | `<input type="search">` UI 만 | 전역 검색 기능 (가전/이상이벤트/캐시백 등 통합) | LOW |
| Topbar 알림 아이콘 | `layouts/Topbar.tsx` | 회색 박스 visual only | 알림 dropdown + 카운트 + 읽음 처리 | MED |

---

## Phase 06 — 설정 / 계정 (`/settings/*`)

> PLAN_06_SETTINGS.md §8 Out of Scope 와 동기화. 본 구현 PR 머지 시 항목 검증.

### 06-A 프로필 / 한전 연동 (`/settings/account`)

| 항목 | 위치 | 현재 동작 | 본 구현 필요 | 우선순위 |
|------|------|-----------|---------------|----------|
| 프로필 "수정" pill | `features/settings/components/ProfileCard.tsx` | 클릭 visual only | 프로필 편집 모달 + PATCH `/api/settings/account/profile` | MED |
| 한전 "재연동" pill | `features/settings/components/KepcoLinkCard.tsx` | 클릭 visual only | 한전 OAuth/고객번호 재인증 흐름 | MED |

### 06-B 알림 (`/settings/notifications`)

| 항목 | 위치 | 현재 동작 | 본 구현 필요 | 우선순위 |
|------|------|-----------|---------------|----------|
| 매트릭스 checkbox 저장 | `features/settings/components/NotificationMatrixCard.tsx` | 로컬 state 만, 서버 미전달 | PATCH `/api/settings/notifications` + debounce | MED |
| 방해 금지 시간 저장 | `features/settings/components/DoNotDisturbCard.tsx` | 로컬 state 만 | 같은 endpoint 에 묶어 저장 | MED |

### 06-C 보안 (`/settings/security`)

| 항목 | 위치 | 현재 동작 | 본 구현 필요 | 우선순위 |
|------|------|-----------|---------------|----------|
| 비밀번호 변경 | `features/settings/components/PasswordCard.tsx` | mock success 메시지 | POST `/api/auth/password` + 현재 비밀번호 검증 | HIGH |
| 2FA 활성화 | `features/settings/components/TwoFactorCard.tsx` | 토글 visual | TOTP QR + 백업 코드 + 검증 흐름 | HIGH |
| 세션 강제 로그아웃 | `features/settings/components/SessionsCard.tsx` | 버튼 visual | DELETE `/api/auth/sessions/:id` | HIGH |
| 계정 삭제 | `features/settings/components/DangerZoneCard.tsx` | alert visual | confirm 모달 + 추가 인증 + DELETE 흐름 + 데이터 보존 정책 | HIGH |

### 06-D 이상 탐지 내역 (`/settings/anomaly-log`)

| 항목 | 위치 | 현재 동작 | 본 구현 필요 | 우선순위 |
|------|------|-----------|---------------|----------|
| 필터 서버 사이드 전환 | `features/settings/components/FilterPillsCard.tsx` | 클라이언트 사이드 필터링(useMemo) 작동 | 백엔드 합류 시 query param 송신 + 페이징 | MED |
| 이벤트 행 "상세" 버튼 | `features/settings/components/AnomalyEventsTable.tsx` | alert "준비 중" | 이벤트 상세 모달 또는 `/anomaly/:id` 라우트 (07 highlight "자세히" 와 deep link 통합 검토) | MED |
| CSV 내보내기 | `features/settings/components/ExportToolbar.tsx` | alert "준비 중" | client blob 또는 백엔드 export endpoint (Phase 04 와 통합) | HIGH |
| JSON 내보내기 | 같음 | alert "준비 중" | 같음 | HIGH |
| PDF 내보내기 | 같음 | alert "준비 중" | 백엔드 PDF 생성 (jsPDF 또는 server-side) | MED |

### 06-E 이메일 연동 (`/settings/email`)

| 항목 | 위치 | 현재 동작 | 본 구현 필요 | 우선순위 |
|------|------|-----------|---------------|----------|
| 수신 주소 저장 | `features/settings/components/EmailRecipientCard.tsx` | 로컬 state 만 | PATCH `/api/settings/email` | MED |
| 알림 토글 4종 저장 | `features/settings/components/EmailNotificationToggleCard.tsx` | 로컬 state 만 | 같은 endpoint 에 묶어 저장 | MED |
| 테스트 메일 발송 | `features/settings/components/EmailTestCard.tsx` | mock success 200ms 후 표시 | POST `/api/settings/email/test` + 실 SMTP 발송 결과 | MED |
| **SMTP/POP 사용자 직접 설정** | (미구현 — `AdvancedSmtpDisclosure` 한 줄 안내) | collapsed details | **검토 필요**: B2C UI 노출 여부 — admin/B2B 전용 분리 또는 영구 제외 | LOW |
| 이메일 템플릿 편집 | (미구현) | 없음 | 사용자가 직접 편집하는 시나리오 부재 — admin 전용 분리 권고 | LOW |

---

## Phase 07 — AI 진단 (`/insights`)

> PLAN_07_INSIGHTS.md §8 Out of Scope 와 동기화. mutation 일괄 후속 (06 와 같은 정책).

| 항목 | 위치 | 현재 동작 | 본 구현 필요 | 우선순위 |
|------|------|-----------|---------------|----------|
| highlight 카드 "자세히" 버튼 | `features/insights/components/AnomalyHighlightCard.tsx` | alert "준비 중" | 이벤트 상세 모달 또는 06-D 행으로 deep link (06-D "상세" 와 통합) | LOW |
| "재진단 / 다시 분석" 버튼 | (미구현 — PLAN_07 §8) | 없음 (현재 미배치) | 재진단 버튼 + POST `/api/insights/regenerate` + LLM 재호출 | MED |
| 추천 dismiss / 완료 체크 | (미구현 — PLAN_07 §8) | 없음 | PATCH `/api/insights/recommendations/:id` + 낙관적 업데이트 | MED |
| 주간 추이 차트 기간 segment (4주/12주/52주) | (미구현 — PLAN_07 §8) | 4주 fixed | endpoint 분리 + 단위별 응답 (Phase 04 segment 와 통합) | LOW |
| 추천 표 신뢰도 정렬·필터 | (미구현 — PLAN_07 §8) | 없음 (서버 응답 순서 그대로) | 정렬 헤더 + 신뢰도 임계 필터 | LOW |

---

## 출품 후 우선순위 정리

본 백로그를 출품 직후 한 번 정리 (HIGH 항목 묶음 → PLAN_M_VISUAL_BACKLOG 같은 통합 PLAN). 우선순위 재배치 + 백엔드 의존 항목 분리.
