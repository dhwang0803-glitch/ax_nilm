# Test Writer Agent — Frontend

## 역할

Developer 가 구현하기 **전에** 실패하는 테스트를 먼저 작성한다 (TDD Red).
대상은 컴포넌트·훅·순수 유틸·E2E 골든 패스.

> 본 브랜치 시작 시점에는 `package.json`·테스트 도구가 없을 수 있다. [§ 0. 부트스트랩 모드](#0-부트스트랩-모드-phase-0) 참조.

---

## 0. 부트스트랩 모드 (Phase 0)

Phase 0 에서는 도메인 컴포넌트가 없으므로 테스트 작성도 다음 한 건만 수행한다:

```ts
// tests/e2e/smoke.spec.ts
test('루트 진입 시 placeholder 가 보인다', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText(/에너지캐시백/i)).toBeVisible();
});
```

```ts
// tests/unit/lib/format.test.ts (예: lib 가 비어있으면 생략 가능)
import { describe, it, expect } from 'vitest';

describe('placeholder', () => {
  it('빌드/테스트 파이프라인이 동작한다', () => {
    expect(1 + 1).toBe(2);
  });
});
```

이 단계의 목표는 도메인 검증이 아니라 **Vitest + Playwright 가 정상 실행되는 것** 의 증명이다. Phase 1 부터는 [§ 1 ~ 6](#1-테스트-도구-frontend-한정) 의 표준 작성 규칙을 적용.

---

## 1. 테스트 도구 (Frontend 한정)

| 종류 | 도구 | 위치 |
|---|---|---|
| 순수 함수 / 훅 단위 | Vitest | `tests/unit/` |
| 컴포넌트 | Vitest + `@testing-library/react` | `tests/unit/` |
| API mocking | MSW (`tests/fixtures/handlers.ts`) | `tests/unit/` |
| E2E (브라우저) | Playwright | `tests/e2e/` |
| 접근성 (옵션) | `@axe-core/react` 또는 RTL `getByRole` 강제 | `tests/unit/` |

---

## 2. 작성 원칙

1. **테스트는 하나의 사용자 의도** — "월간 캐시백 카드가 단가 구간을 표시한다" 처럼 한 줄로 설명 가능.
2. **구현 디테일이 아닌 행동을 검증** — `getByRole('button', { name: /로그인/ })` 처럼 사용자가 보는 것 기준. 클래스명 / 내부 state 선택 금지.
3. **MSW 로 API 격리** — 실제 네트워크 호출 금지. `tests/fixtures/handlers.ts` 에 응답 시나리오 정의.
4. **한 테스트 = 한 assertion 묶음** — 무관한 검증 합치기 금지.
5. **빈/로딩/에러 3가지 상태 모두 테스트** — 차트 / 리스트는 데이터 부재 케이스가 누락되기 쉬움.

---

## 3. 컴포넌트 테스트 템플릿

> 아래 컴포넌트 경로(`@/features/<domain>/components/...`)는 스캐폴드 + 해당 Phase 진입 후 등장. 부트스트랩 단계에서는 import 가 깨질 수 있으므로 사용 금지.

```tsx
// tests/unit/features/<domain>/<Component>.test.tsx
import { render, screen } from '@testing-library/react';
import { ComponentName } from '@/features/<domain>/components/ComponentName';

describe('ComponentName', () => {
  it('정상 props 일 때 핵심 텍스트가 보인다', () => {
    render(<ComponentName prop1={...} prop2={...} />);
    expect(screen.getByText(/.../)).toBeInTheDocument();
  });

  it('빈 데이터 상태 안내 문구를 보여준다', () => {
    render(<ComponentName prop1={null} prop2={null} />);
    expect(screen.getByText(/측정 데이터가 없습니다/)).toBeInTheDocument();
  });
});
```

---

## 4. 훅 테스트 템플릿 (TanStack Query)

```tsx
// tests/unit/features/<domain>/<useHook>.test.tsx
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useDomainResource } from '@/features/<domain>/api';

const wrapper = ({ children }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

it('도메인 리소스를 가져온다', async () => {
  const { result } = renderHook(() => useDomainResource('id'), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data).toBeDefined();
});
```

---

## 5. E2E (Playwright) — 핵심 5 화면 골든 패스

```ts
// tests/e2e/<flow>.spec.ts
test('로그인 → 대시보드 → 도메인 화면 진입', async ({ page }) => {
  await page.goto('/auth/login');
  // 시나리오에 맞춰 작성
});
```

- 모바일 뷰포트(`devices['iPhone 13']`) + 데스크탑 두 컨텍스트 병렬 실행
- 시각 회귀(`expect(page).toHaveScreenshot()`) 는 디자인 토큰 변경 PR 에서만 자동 갱신

---

## 6. a11y 검증 패턴

```tsx
import { axe, toHaveNoViolations } from 'jest-axe';
expect.extend(toHaveNoViolations);

it('컴포넌트가 a11y 위반이 없다', async () => {
  const { container } = render(<DomainCard ... />);
  expect(await axe(container)).toHaveNoViolations();
});
```

또는 RTL 의 `getByRole` 만으로도 의미상 마크업 검증 가능 (역할이 없으면 쿼리 실패).

---

## 7. 작성 완료 기준

- [ ] 새 컴포넌트 / 훅 / 페이지마다 테스트 1개 이상 (Phase 0 은 smoke 만 허용)
- [ ] 컴포넌트 테스트는 빈/로딩/에러 3분기 포함
- [ ] API 호출은 MSW 로 모킹 (실 네트워크 0)
- [ ] E2E 는 핵심 5화면 골든 패스 + 모바일 뷰포트 1개 (Phase 1 부터)
- [ ] 모든 테스트는 단독 실행 가능 (테스트 간 상태 공유 금지)
- [ ] `pnpm test` 빨강 → Developer 호출
