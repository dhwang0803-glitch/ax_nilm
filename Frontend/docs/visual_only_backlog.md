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

## 후속 Phase 추가 예정 (Phase 06 settings + 07 insights)

Phase 06/07 본 구현 시 본 백로그도 갱신 — 5탭 settings 와 AI 진단의 placeholder 항목 추가.

## 출품 후 우선순위 정리

본 백로그를 출품 직후 한 번 정리 (HIGH 항목 묶음 → PLAN_M_VISUAL_BACKLOG 같은 통합 PLAN). 우선순위 재배치 + 백엔드 의존 항목 분리.
