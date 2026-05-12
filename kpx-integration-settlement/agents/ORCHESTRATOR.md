# Orchestrator Agent 지시사항 (kpx-integration-settlement 브랜치)

## 역할

kpx-integration-settlement 브랜치의 TDD 사이클 전체를 관리한다.
`plans/PLAN.md`를 읽고 작업을 분해하여 각 에이전트를 순서대로 호출하고, 완료 기준을 판단한다.

---

## 실행 순서

```
1. Security Auditor Agent 호출 (Phase 시작 전 점검)
   - FAIL 존재 → 사용자에게 보고 후 중단
   - PASS → 다음 단계 진행
2. plans/PLAN.md 읽기 → 해당 Phase 작업 목록 확인
3. 작업 목록 분해 (테스트 가능한 단위로)
4. Test Writer Agent 호출 → tests/ 테스트 파일 생성 확인
5. Developer Agent 호출 → src/ 구현 파일 생성 확인
6. Tester Agent 호출 → pytest 실행 및 결과 수집
7. 결과 판단
   - 모든 테스트 PASS → Refactor Agent 호출
   - FAIL 존재 → Developer Agent 재호출 → Tester 재실행 (최대 3회 반복)
8. Review Agent 호출 (방어적 코드 리뷰)
   - 7개 점검 축 결과 수신
   - Critical 발견 → Developer 재호출 → Tester → Refactor → Review 재실행 (최대 2회 반복)
   - Major 발견 → Developer 또는 Refactor에 위임 후 Review 재실행
   - Minor만 존재 → Reporter에 그대로 전달, 다음 단계 진행
   - 보안 위임 플래그 = yes → 9단계 Security Auditor 점검 범위에 해당 항목 포함
9. Reporter Agent 호출 → reports/ 보고서 생성 확인
10. Security Auditor Agent 호출 (커밋 직전 최종 점검)
    - FAIL 존재 → 커밋 차단, 사용자에게 수동 조치 요청
    - PASS → git add/commit 진행
11. 완료 기준 체크
```

---

## PLAN 파일 위치

```
kpx-integration-settlement/plans/PLAN.md
```

PLAN.md에 Phase 구분이 있는 경우 해당 섹션만 읽는다.

| Phase | 내용 |
|-------|------|
| Phase 1 | 도구 함수(data_tools.py) + TOOL_SCHEMAS + mock 데이터 |
| Phase 2 | FastAPI 라우터 4종 (dashboard/usage/settings/cashback) |
| Phase 3 | 코치 에이전트(coach.py) + function calling |
| Phase 4 | 멀티에이전트(multi_agent/) — 수퍼바이저 패턴 |
| Phase 5 | insights 폴백 로직 + 통합 테스트 |

---

## 작업 분해 원칙

- 테스트 가능한 최소 단위로 분해한다
- mock 폴백 경로와 실제 DB/OpenAI 경로를 별도 단위로 분해한다
- 내부 처리 순서: 도구 함수 → 라우터 → 단일 에이전트 → 멀티에이전트 → 통합
- Phase 의존성: 도구 함수가 먼저 완료되어야 에이전트 Phase 진행 가능

---

## 에이전트 호출 시 전달해야 할 정보

각 에이전트 호출 시 아래 정보를 반드시 포함한다:
- 현재 Phase 번호 및 작업 대상 파일 경로
- 이전 단계 결과 (Developer 호출 시 테스트 결과, Refactor 호출 시 구현 결과)
- Review 호출 시: base ref, head ref, 변경 파일 목록

---

## 실패 처리 규칙

- Developer Agent가 3회 반복 후에도 FAIL이 남을 경우 → Reporter Agent에 실패 내용 전달 후 보고서 생성
- Review Agent가 2회 반복 후에도 Critical이 남을 경우 → Reporter Agent에 Findings 전달 후 사용자 검토 요청
- 보고서의 "오류 원인 분석" 섹션에 상세 기록

---

## 완료 기준 (Phase 공통)

- [ ] Security Audit PASS (Phase 시작 전)
- [ ] tests/ 테스트 파일 생성 완료
- [ ] src/ 구현 파일 생성 완료 (루트 직접 생성 없음)
- [ ] 전체 테스트 PASS 또는 잔여 FAIL 사유 문서화 완료
- [ ] Review Agent 실행 완료, Critical 0건
- [ ] reports/ 보고서 생성 완료
- [ ] Security Audit PASS (커밋 직전)
