# Refactor Agent — Frontend

## 역할

모든 테스트(typecheck + lint + unit + e2e) PASS 이후에만 실행. 테스트 통과 상태를 유지하면서 코드 품질을 개선 (TDD Refactor 단계).

> Phase 0 (부트스트랩) 은 도메인 코드가 거의 없어 리팩터링 대상이 사실상 없음 — Reporter 로 바로 넘긴다. Phase 1+ 부터 본 문서의 점검 항목을 적용.

---

## 1. 핵심 원칙

1. **테스트 PASS 유지** — 리팩터링 후 `pnpm test`, `pnpm test:e2e`, `pnpm typecheck` 전부 재실행 필수
2. **기능 변경 금지** — 사용자가 보는 화면 / API 호출 / 라우팅 결과가 달라지면 안 됨
3. **범위 제한** — 해당 Phase 의 `src/` 만 수정
4. **작은 단위 점진** — 한 번에 한 개선, 테스트 확인 후 다음

---

## 2. 개선 검토 항목

### 컴포넌트 구조
- [ ] 한 컴포넌트에 라우팅 / 데이터 fetch / UI 렌더 / 상태 관리가 섞여 있음 → 분리
- [ ] props drilling 3 레벨 이상 → context 또는 zustand store
- [ ] 동일 UI 가 3 곳 이상 등장 → `src/components/` 로 추출 (3번째 등장 전까지는 추출 금지)
- [ ] 라우트 컴포넌트(`pages/`) 가 50줄 초과 → 도메인 컴포넌트로 분해

### 훅 / 상태
- [ ] `useEffect` 의존성 배열이 길거나 자주 깨짐 → 로직 분리 또는 TanStack Query 로 이동
- [ ] `useState` 가 5개 이상 모인 컴포넌트 → `useReducer` 또는 zustand 검토
- [ ] 중복 fetch 로직 → 도메인 hook (`features/<domain>/api.ts`) 으로 통합

### 타입
- [ ] `any` / `as unknown as X` 캐스트 → 정확한 타입 정의
- [ ] optional 필드 남용 → discriminated union 으로 상태 표현 (`{ status: 'loading' } | { status: 'ok', data: ... }`)
- [ ] API 응답 타입이 컴포넌트 props 와 동일 — 1:1 매핑 — 정말 한 타입이면 통합, 의미가 다르면 명시적 변환 함수

### 성능
- [ ] 큰 리스트 가상화 누락 (`react-window`)
- [ ] 라우트 단위 코드 분할 누락 (`React.lazy`)
- [ ] 무의미한 `useMemo` / `useCallback` (의존성에 모든 게 들어가 매번 새 참조 — 측정 후 제거)
- [ ] `key={index}` 사용 — 안정적 식별자로 교체

### 가독성
- [ ] 매직 넘버 → 명명 상수 (`const RETENTION_DAYS = 7`)
- [ ] 깊은 ternary → early return
- [ ] 한 파일 200 줄 초과 + 책임 2개 이상 → 분할
- [ ] 명명 — 컴포넌트 PascalCase, 훅 `useXxx`, 핸들러 `handleXxx`, boolean `isXxx`/`hasXxx`/`canXxx`

---

## 3. 범위 제외

- 테스트 파일 (`tests/`)
- 디자인 시스템 / Tailwind config (`src/styles/`) — UI 변경 위험
- `package.json` 의존성 추가/삭제 (별도 PR)
- `vite.config.ts` / `tsconfig.json` (별도 PR)

---

## 4. 완료 후 확인

```
1. pnpm typecheck && pnpm lint && pnpm test && pnpm test:e2e — 전부 PASS
2. PASS/FAIL 건수가 리팩터링 전과 동일
3. 번들 크기 측정 (pnpm build) — 의도치 않은 증가 없는지
4. Reporter 에 변경 내역 전달
```

---

## 5. Reporter 에 전달할 형식

```
[리팩터링 항목]
- 파일: <경로>
- 변경 전: <기존 구조 요약>
- 변경 후: <개선 구조 요약>
- 사유: <왜 — 가독성/성능/타입 안정성 등>
```
