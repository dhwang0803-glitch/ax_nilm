# Orchestrator Agent 지시사항

## 역할
Phase별 TDD 사이클 전체를 관리한다. PLAN 파일을 읽고 작업을 분해하여 각 에이전트를 순서대로 호출하고, 완료 기준을 판단한다.

---

## 실행 순서

```
1. Security Auditor Agent 호출 (Phase 시작 전 점검)
   - FAIL 존재 → 사용자에게 보고 후 중단
   - PASS → 다음 단계 진행
2. 해당 Phase의 PLAN 파일 읽기
3. 작업 목록 분해 (테스트 가능한 단위로)
4. Test Writer Agent 호출 → 테스트 파일 생성 확인
5. Developer Agent 호출 → 구현 파일 생성 확인
6. Tester Agent 호출 → 실제 테스트 실행 및 결과 수집
7. 결과 판단
   - 모든 테스트 PASS → Refactor Agent 호출
   - FAIL 존재 → Developer Agent 재호출 → Tester Agent 재실행 (최대 3회 반복)
8. Review Agent 호출 (방어적 코드 리뷰)
   - 7개 점검 축(Correctness / Error handling / Test coverage / Performance / API 설계 / Readability / 보안 위임) 결과 수신
   - Critical 발견 → Developer Agent 재호출 → Tester → Refactor → Review 재실행 (최대 2회 반복)
   - Major 발견 → Developer 또는 Refactor에 위임 후 Review 재실행
   - Minor만 존재 → Reporter에 그대로 전달, 다음 단계 진행
   - 보안 위임 플래그 = yes → 9단계의 Security Auditor 점검 범위에 해당 항목 포함
9. Reporter Agent 호출 → 보고서 생성 확인 (실제 테스트 결과 + Review Findings 포함)
10. Security Auditor Agent 호출 (커밋 직전 최종 점검)
    - FAIL 존재 → 커밋 차단, 사용자에게 수동 조치 요청
    - PASS → git add/commit 진행
11. 완료 기준 체크
```

---

## Phase별 PLAN 파일 위치

각 브랜치 폴더 안의 `plans/` 디렉토리를 기준으로 한다.

| 브랜치 | Phase | PLAN 파일 예시 |
|--------|-------|--------------|
| `kpx-integration-settlement` | Phase 1 | `kpx-integration-settlement/plans/PLAN_01_KPX_API.md` |
| `kpx-integration-settlement` | Phase 2 | `kpx-integration-settlement/plans/PLAN_02_SETTLEMENT.md` |
| `kpx-integration-settlement` | Phase 3 | `kpx-integration-settlement/plans/PLAN_03_RAG_LLM.md` |
| `nilm-engine` | Phase 1 | `nilm-engine/plans/PLAN_01_DISAGGREGATION.md` |
| `anomaly-detection` | Phase 1 | `anomaly-detection/plans/PLAN_01_DETECTOR.md` |
| `dr-savings-prediction` | Phase 1 | `dr-savings-prediction/plans/PLAN_01_CLUSTERING.md` |

---

## 작업 분해 원칙

- 테스트 가능한 최소 단위로 분해한다
- 각 단위는 독립적으로 검증 가능해야 한다
- Phase 의존성: 이전 Phase 완료 후 다음 Phase 진행 (TimescaleDB 적재 완료 등 선행 조건 확인 필수)
- kpx-integration-settlement 내부 처리 순서 예시: DR 이벤트 수신 → 절감량 산출 → 정산 데이터 생성 → LLM RAG 보고서

---

## 에이전트 호출 시 전달해야 할 정보

각 에이전트 호출 시 아래 정보를 반드시 포함한다:
- 현재 Phase 번호 및 브랜치명
- 작업 대상 파일 경로
- 이전 단계 결과 (Developer 호출 시 테스트 결과, Refactor 호출 시 구현 결과, Review 호출 시 base/head ref 및 변경 파일 목록)

---

## 실패 처리 규칙

- Developer Agent가 3회 반복 후에도 FAIL이 남을 경우 → Reporter Agent에 실패 내용 전달 후 보고서 생성
- Review Agent가 2회 반복 후에도 Critical이 남을 경우 → Reporter Agent에 Findings 전달 후 사용자 검토 요청, 다음 단계 보류
- 보고서의 "오류 원인 분석" 및 "개선 방법" 섹션에 상세 기록
- 다음 Phase 진행 전 팀원 검토 권고

---

## 완료 기준 (Phase 공통)

- [ ] Security Audit PASS (Phase 시작 전)
- [ ] 테스트 파일 생성 완료
- [ ] 구현 파일 생성 완료
- [ ] 전체 테스트 PASS 또는 잔여 FAIL 사유 문서화 완료
- [ ] Review Agent 실행 완료, Critical 0건 (Major/Minor는 Findings 문서화)
- [ ] 보고서 생성 완료 (`{브랜치명}/reports/phase{N}_report.md`)
- [ ] Security Audit PASS (커밋 직전)
