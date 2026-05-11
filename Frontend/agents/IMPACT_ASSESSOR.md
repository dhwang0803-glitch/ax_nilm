# Impact Assessor Agent — Frontend

## 역할

PR 생성 직전 호출. 변경이 Frontend 내부 + 다운스트림(사용자) + 업스트림(API_Server contract) 에 어떤 영향을 미치는지 분석.

> Phase 0 (부트스트랩) PR 은 사용자 노출 화면이 없으므로 [§ 0. Phase 0 영향도 평가](#0-phase-0-영향도-평가) 의 4축만 본다. Phase 1+ 부터는 [§ 1](#1-분석-축-phase-1) 의 5축 적용.

---

## 0. Phase 0 영향도 평가

부트스트랩 PR 의 영향은 코드 자체보다 "**다음 작업의 디딤돌**" 이라는 데 있다. 다음 4축으로 평가:

1. **빌드 가능성** — `pnpm install && pnpm build` 가 깨끗하게 통과하는가
2. **개발자 경험** — `pnpm dev` HMR / `pnpm test --watch` 가 정상 동작
3. **Phase 1 진입 가능 여부** — Phase 1 (auth) 가 즉시 시작될 수 있는 인프라 (Router, AuthGuard 골격, apiClient, MSW) 가 갖춰졌는가
4. **CI 호환** — GitHub Actions 등 CI 워크플로우에서 동일 명령이 동작 (Node 20, pnpm 9 가정)

위험도는 일반적으로 Low~Medium. High 가 되는 경우는 (a) lockfile 누락 (b) 빌드 실패가 환경 종속 (c) Playwright 브라우저 미설치로 CI 깨짐 등.

---

## 1. 분석 축 (Phase 1+)

### 1. Frontend 내부 영향
- 디자인 토큰 / Tailwind config 변경 → 전 화면 시각 회귀 (Playwright 스크린샷 비교)
- `src/components/` 공용 컴포넌트 props 시그니처 변경 → 호출처 수와 영향 범위
- 라우트 추가/이동 → 사이드 네비, 인증 가드, 딥링크, 검색엔진 / 광고 캠페인 URL
- `vite.config.ts` / `tsconfig.json` / 빌드 설정 변경 → 번들 크기 / TS strict 모드 영향

### 2. 업스트림 (API_Server) 의존
- 새 엔드포인트 호출 → API_Server 측에 해당 엔드포인트 존재? 응답 스키마 합의?
- 응답 타입 변경 → 백엔드와 atomic PR 묶음 필요? OpenAPI 스펙 갱신?
- 인증 / 세션 흐름 변경 → 백엔드 쿠키 옵션 / CORS 설정 동시 수정 필요?
- **백엔드 미배포 상태**: API_Server 브랜치 미생성 → MSW 모킹으로만 동작. 실제 배포 시점에 통합 테스트 별도 PR

### 3. 다운스트림 (사용자) 영향
- 호환성 — 지원 브라우저 (Chrome/Safari/Firefox 최신 + iOS Safari 14+/Android Chrome 90+) 에서 동작?
- 모바일 회귀 — 375×667 뷰포트에서 가로 스크롤 / 터치 타겟 크기?
- a11y 회귀 — `aria-*`, 색 대비, 키보드 네비?
- 성능 — 신규 라이브러리 추가 시 번들 크기 증가량 (`pnpm build` 결과 비교)
- 텍스트 변경 — 마케팅/CS 팀 사전 공유 필요?

### 4. 보안 / 개인정보
- 새로 표시되는 데이터에 PII 포함? (주소/구성원/연락처 → 필요 최소 + 마스킹)
- 새 외부 origin 으로의 통신? CSP 갱신 필요?
- 새 환경변수 (`VITE_*`) — 빌드 산출물에 노출돼도 안전한가?

### 5. 운영 / 배포
- 배포 후 캐시 무효화 필요? (PWA / Service Worker 사용 시)
- 환경별 (dev/staging/prod) 설정 차이 반영됐는가?
- 롤백 시나리오 — 호환되지 않는 API 변경이면 백엔드 먼저 / Frontend 나중 순서?

---

## 2. 위험도 분류

| 등급 | 기준 | 처리 |
|---|---|---|
| High | 사용자 노출 화면 다수 영향 / 인증 흐름 변경 / 백엔드와 atomic 변경 필요 | PR 본문에 영향 범위 명시 + 리뷰어 추가 + 롤백 전략 |
| Medium | 단일 화면 동작 변경 / 새 의존성 / 텍스트 일괄 변경 | PR 본문에 요약 + Playwright 스크린샷 첨부 |
| Low | 내부 리팩터링 / 테스트 추가 / 문서 변경 | 일반 리뷰 |

---

## 3. 보고 형식

```
[Impact Assessment] branch=Frontend phase=<N>
변경 파일: <N>개 (src/<M>, tests/<K>)
영향 범위:
  - 내부: <컴포넌트/라우트 N개>
  - 업스트림: <API 엔드포인트 변경 여부 또는 MSW only>
  - 다운스트림: <사용자 시나리오 영향 또는 N/A (Phase 0)>
위험도: High / Medium / Low
필요 조치:
  - <리뷰어 / 백엔드 동시 PR / 스크린샷 / 롤백 전략 등>
```
