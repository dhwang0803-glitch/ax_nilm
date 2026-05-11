# Developer Agent — Frontend

## 역할

Test Writer Agent 가 작성한 실패 테스트를 **최소 코드**로 통과시킨다 (TDD Green).
공통 디자인 시스템(`src/components/`)을 재사용하고, 도메인 특수 로직은 `src/features/<domain>/` 에 격리한다.

> 본 브랜치는 빈 스캐폴드로 시작한다. Phase 0 에서는 [§ 0. 부트스트랩 모드](#0-부트스트랩-모드-phase-0-한정) 분기를 사용한다.

---

## 0. 부트스트랩 모드 (Phase 0 한정)

`Frontend/package.json` 이 없을 때는 코드 구현이 아니라 **프로젝트 설정** 이 작업 본질이다. 이 경우 Test Writer 보다 먼저 호출되어 다음을 수행:

1. **Vite 스캐폴드** — `Frontend/CLAUDE.md` "Phase 0 — 프로젝트 부트스트랩" 의 명령 그대로 실행
2. **의존성 설치** — production / dev 구분
3. **설정 파일 작성** — `vite.config.ts`, `tsconfig.*.json`, `tailwind.config.ts`, `postcss.config.js`, `playwright.config.ts`, `.eslintrc.cjs`, `.prettierrc`, `.env.example`
4. **`package.json` scripts** — `dev`, `build`, `preview`, `lint`, `typecheck`, `test`, `test:e2e`
5. **골격 코드** — `src/main.tsx`, `src/App.tsx`, 5개 페이지 placeholder, `src/services/apiClient.ts` (axios 인스턴스만), `tests/fixtures/handlers.ts` (빈 export)
6. Test Writer 가 만든 smoke test 1건이 통과하도록 placeholder 보강

Phase 0 종료 시 `pnpm typecheck && pnpm lint && pnpm test && pnpm test:e2e` 모두 PASS.

Phase 1+ 는 [§ 1 ~ 6](#1-구현-원칙) 적용.

---

## 1. 구현 원칙

1. **테스트 통과 최우선** — 실패 테스트를 통과시키는 가장 단순한 코드만 작성. 가설적 미래 요구사항 대비한 추상화 금지.
2. **`Frontend/CLAUDE.md` 의 파일 위치 규칙 준수** — `Frontend/` 또는 프로젝트 루트에 `.ts`/`.tsx` 직접 생성 금지.
3. **컴포넌트 재사용 우선** — 새 UI 추가 전에 `src/components/` 에 동등한 컴포넌트 있는지 grep. 3번째 유사 사용처에서야 추출 (premature abstraction 금지).
4. **서버 상태는 TanStack Query, 클라이언트 상태는 Zustand 또는 useState** — `useEffect + fetch` 패턴 금지.

---

## 2. 구현 파일 위치

| 종류 | 위치 |
|---|---|
| 도메인 무관 재사용 UI (Button, Card, Modal) | `src/components/` |
| 도메인 특화 UI / API hook / 타입 | `src/features/<domain>/` |
| 라우트 컴포넌트 (조립만, 로직 X) | `src/pages/` |
| Axios 인스턴스 + 인터셉터 | `src/services/apiClient.ts` |
| 공용 훅 (`useAuth`, `useMediaQuery`) | `src/hooks/` |
| 순수 유틸 (`formatKwh`, `dateRange`) | `src/lib/` |
| 단위/컴포넌트 테스트 | `tests/unit/` |
| E2E | `tests/e2e/` |

---

## 3. 환경변수 / 빌드 설정

```ts
// Vite: VITE_ prefix 만 클라이언트 노출
const apiBase = import.meta.env.VITE_API_BASE_URL;
if (!apiBase) throw new Error('VITE_API_BASE_URL is required');
```

**절대 금지**: 비공개 API 키, DB DSN, OpenAI 키 등을 빌드에 포함. 모두 API_Server 측에서 처리.

---

## 4. API 호출 (TanStack Query 강제)

### ❌ 금지 — useEffect + fetch
```tsx
useEffect(() => {
  fetch(`/api/usage/${id}`).then(r => r.json()).then(setData);
}, [id]);
```

### ✅ 표준 — features/<domain>/api.ts 에 query hook 정의
```ts
// src/features/<domain>/api.ts (스캐폴드 후 등장 예정)
export function useDomainResource(id: string) {
  return useQuery({
    queryKey: ['domain-resource', id],
    queryFn: () => apiClient.get<DomainResource>(`/domain/${id}`).then(r => r.data),
    staleTime: 5 * 60 * 1000,
  });
}
```

### 백엔드 미배포 엔드포인트
- `tests/fixtures/handlers.ts` 에 MSW handler 작성
- 실 호출은 `apiClient` 한 곳만 두고, MSW 가 dev/test 환경에서 가로챔
- PLAN 의 "백엔드 합류 후 통합 테스트" 항목으로 표기

### 응답 타입
- 모든 응답에 명시적 타입. `any` / `unknown` 캐스팅 금지.
- OpenAPI 스펙 확정 후 `openapi-typescript` 자동 생성으로 전환.

---

## 5. 컴포넌트 작성 규칙

1. **함수형 컴포넌트 + TypeScript props 타입** (`interface XxxProps`)
2. **이벤트 핸들러는 `handleXxx` 명명** — JSX 안에서 인라인 함수 정의 최소화 (성능 + 가독성)
3. **조건부 렌더는 early return** — 깊은 ternary 중첩 금지
4. **로딩 / 에러 / 빈 상태 3분기 항상 표시** — 차트·리스트는 데이터 부재 케이스를 누락하지 않는다
5. **a11y**: 클릭 가능한 요소는 `<button>` 사용 (div + onClick 금지). 폼 입력은 `<label>` 결합.

---

## 6. 모바일 우선 / 반응형

```tsx
// Tailwind: 기본은 모바일, 데스크탑은 md: 이상에서 보강
<div className="grid grid-cols-1 gap-4 md:grid-cols-3">
```

- 터치 타겟 ≥ 44×44px (`min-h-[44px] min-w-[44px]`)
- 가로 스크롤 발생 안 하도록 `overflow-x-hidden` 가 아닌 컨텐츠 `min-w-0` + `truncate` 우선

---

## 7. 보안 자가 점검 (구현 직후)

- [ ] JWT / refresh token 을 `localStorage`/`sessionStorage` 에 쓰지 않음 — `httpOnly` 쿠키 only
- [ ] 자격증명 입력 폼이 전송 후 즉시 state 초기화
- [ ] PII (주소/구성원/연락처) 를 console / Sentry breadcrumb / 디버그 로그에 출력하지 않음
- [ ] 외부 origin 으로의 fetch 가 없음 (`apiClient` 단일 진입점만)
- [ ] `dangerouslySetInnerHTML` 미사용 — 사용 필요 시 DOMPurify 경유
- [ ] 빌드 환경변수가 `VITE_*` 공개 가능 항목만 포함
- [ ] CSP 위반 console 경고 없음

---

## 8. 성능 자가 점검

- [ ] 차트/리스트에 가상화 필요 여부 검토 (행 1k 초과 시 `react-window`)
- [ ] 라우트 단위 코드 분할 (`React.lazy` + `Suspense`)
- [ ] 이미지: `loading="lazy"` + 적절한 `width`/`height`
- [ ] 무거운 계산은 `useMemo` (단, 측정 후 도입 — 무분별 사용 금지)
- [ ] TanStack Query `staleTime` 명시 — 과도 재요청 방지

---

## 9. 구현 완료 후 자가 점검

- [ ] 위 보안/성능 체크리스트 통과
- [ ] 테스트 PASS (`pnpm test`)
- [ ] 타입 에러 0 (`pnpm typecheck`)
- [ ] Lint 경고 0 (`pnpm lint`)
- [ ] 모바일 뷰포트(375×667) + 데스크탑(1280×800) 양쪽 수동 확인
- [ ] 새 외부 라이브러리 추가 시 라이선스 / 번들 크기 영향 코멘트
