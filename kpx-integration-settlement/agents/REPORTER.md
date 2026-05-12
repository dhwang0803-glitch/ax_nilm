# Reporter Agent 지시사항 (kpx-integration-settlement 브랜치)

## 역할

TDD 사이클이 완료된 후 Phase별 결과 보고서를 생성한다.
Orchestrator, Test Writer, Developer, Refactor Agent로부터 결과를 수집하여 표준 형식으로 문서화한다.

---

## 보고서 저장 위치

```
kpx-integration-settlement/reports/phase{N}_report.md
```

예: Phase 2 (FastAPI 라우터) → `kpx-integration-settlement/reports/phase2_report.md`

---

## 보고서 표준 형식

```markdown
# Phase {N} 결과 보고서

**브랜치**: kpx-integration-settlement
**Phase**: {Phase 번호 및 이름}
**작성일**: {YYYY-MM-DD}
**상태**: PASS 완료 / FAIL 잔존

---

## 1. 개발 결과

### 생성된 파일
| 파일 | 위치 | 설명 |
|------|------|------|
| data_tools.py | src/agent/ | 8개 데이터 조회 도구 + mock 데이터 + TOOL_SCHEMAS |
| dashboard.py  | src/api/routers/ | GET /api/dashboard/summary |
| ...           | ...              | ...                        |

### 주요 구현 내용
- [구현한 핵심 내용 bullet point]

---

## 2. 테스트 결과

### 요약
| 구분 | 건수 |
|------|------|
| 전체 테스트 | X건 |
| PASS | X건 |
| FAIL | X건 |
| SKIP | X건 (OpenAI/DB 미연결) |
| 오류율 | X% |

### 상세 결과
| 테스트 ID | 항목 | 결과 | 비고 |
|----------|------|------|------|
| T1-01 | get_household_profile mock 폴백 | PASS | |
| T1-02 | TOOL_SCHEMAS 8개 검증 | PASS | |
| T2-01 | GET /api/dashboard/summary | PASS | |
| ...   | ...                        | ...  | ... |

---

## 3. 에이전트 실행 통계 (Phase별)

| 항목 | 처리 건수 | 성공 건수 | 성공률 |
|------|---------|---------|--------|
| 도구 함수 호출 (mock) | X | X | X% |
| FastAPI 라우터 응답 | X | X | X% |
| OpenAI API 호출 | X | X | X% (미연결 시 N/A) |
| multi_agent 실행 | X | X | X% |

---

## 4. 오류 원인 분석

> PASS 완료 시 "해당 없음" 기재

| FAIL 항목 | 원인 |
|----------|------|
| [테스트명] | [원인 설명] |

---

## 5. 개선 내용 (실제 적용)

### 버그 수정
- [수정 사항]

### 리팩토링
| 파일 | 변경 전 | 변경 후 | 이유 |
|------|--------|--------|------|

---

## 6. 다음 Phase 권고사항

- [다음 Phase 진행 전 확인 필요한 사항]
- [의존성 또는 선행 조건]
- [OpenAI API 연결 필요 여부]
- [TimescaleDB IAP 터널 연결 필요 여부]
```

---

## 수집해야 할 정보 및 출처

| 섹션 | 출처 |
|------|------|
| 개발 결과 | Developer Agent 결과 |
| 테스트 결과 | Tester Agent pytest 실행 결과 |
| 에이전트 실행 통계 | 각 모듈 실행 로그 |
| 오류 원인 분석 | Tester Agent FAIL 로그 |
| 개선 내용 | Refactor Agent 변경 사항 |
| 다음 Phase 권고 | plans/PLAN.md "다음 단계" + 이번 Phase 이슈 |

---

## 보고서 작성 완료 후

- [ ] 보고서 파일 저장 확인 (`kpx-integration-settlement/reports/phase{N}_report.md`)
- [ ] Orchestrator에 완료 보고
