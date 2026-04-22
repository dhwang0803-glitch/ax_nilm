# Reporter Agent 지시사항 (Database 브랜치)

## 역할
TDD 사이클 완료 후 Database 작업 단위(스키마 변경 / Repository 추가 / ETL 규칙 보강 등)의 결과 보고서를 생성한다.
Orchestrator, Test Writer, Developer, Refactor, Review Agent 로부터 결과를 수집하여 표준 형식으로 문서화한다.

---

## 보고서 저장 위치

```
Database/tests/reports/{YYYYMMDD}_{작업요약}.md
```

예:
- `Database/tests/reports/20260421_power_1min_hypertable.md`
- `Database/tests/reports/20260425_pii_repository_roundtrip.md`

PR 본문에 붙여넣는 요약 보고는 같은 양식으로 작성하되 파일은 별도 저장.

---

## 보고서 표준 형식

```markdown
# Database 작업 결과 보고서 — {작업 요약}

**작업 대상**: {schemas / migrations / repositories / scripts / 문서}
**작성일**: {YYYY-MM-DD}
**상태**: PASS 완료 / FAIL 잔존

---

## 1. 개발 결과

### 생성·수정된 파일
| 파일 | 위치 | 설명 |
|------|------|------|
| 002_timeseries_tables.sql | Database/schemas/ | power_1min hypertable + power_1hour cagg |
| power_repository.py | Database/src/repositories/ | read_range() 7일 경계 자동 라우팅 |
| ingest_aihub.py | Database/scripts/ | 30Hz → 1분 집계 ETL |

### 주요 구현 내용
- [구현한 핵심 내용 bullet — 테이블 구조, Repository 메서드 시그니처, ETL 규칙 등]

---

## 2. 테스트 결과

### 요약
| 구분 | 건수 |
|------|------|
| 전체 테스트 | X건 |
| PASS | X건 |
| FAIL | X건 |
| SKIP | X건 |
| 오류율 | X% |

### 상세 결과
| 테스트 ID | 항목 | 결과 | 비고 |
|----------|------|------|------|
| T01 | `power_1min` hypertable 생성 + chunk_time_interval 검증 | PASS | |
| T02 | PowerRepository.read_range() 7일 경계 라우팅 | PASS | |
| T03 | PIIRepository encrypt/decrypt 라운드트립 | PASS | |
| T04 | ingest_aihub.py 샘플 1가구 1일 적재 → 행수 1440·energy_wh 합계 | PASS | |
| T05 | activity_intervals EXCLUDE gist 겹침 차단 | PASS | |

---

## 3. ETL / 적재 통계 (해당 시)

| 테이블 | 적재 행수 | 예상 행수 | 일치 | 비고 |
|--------|---------|---------|------|------|
| power_1min | X | 1440 × 23 × N일 | ✅ | |
| activity_intervals | X | AI Hub 라벨 수 | ✅ | |
| ingestion_log | X | 입력 파일 수 | ✅ | |

---

## 4. 오류 원인 분석

> PASS 완료 시 "해당 없음" 기재

| FAIL 항목 | 원인 | 재현 조건 |
|----------|------|----------|
| [테스트명] | [원인 설명] | [재현 커맨드] |

---

## 5. 개선 내용 (실제 적용)

### 버그 수정
- [수정 사항]

### 리팩토링 (Refactor Agent 산출)
| 파일 | 변경 전 | 변경 후 | 이유 |
|------|--------|--------|------|

### Review Findings (Review Agent 산출)
- [Critical] 수: N건 / 해결: N건
- [Major] 수: N건 / 해결: N건
- [Minor] 수: N건 / 문서화만: N건

---

## 6. 사후영향 (IMPACT_ASSESSOR 요약)

- **리스크 등급**: 🔴 HIGH / 🟡 MEDIUM / 🟢 LOW
- **다운스트림 영향**: `API_Server` / `Execution_Engine` 각각 Yes/No
- **마이그레이션 DOWN 경로**: 존재 / 부재

---

## 7. 다음 작업 권고사항

- [후속 작업: retention 정책 적용, cagg 초기 리프레시, 다운스트림 브랜치 공지 등]
- [의존성 또는 선행 조건]
- [주의사항: 헬스체크·스테이징 검증 필요 여부]
```

---

## 수집해야 할 정보 및 출처

| 섹션 | 출처 |
|------|------|
| 개발 결과 | Developer Agent 결과 |
| 테스트 결과 | Tester Agent 실행 결과 (pytest 출력) |
| ETL/적재 통계 | `ingest_aihub.py` 또는 `validate_sample.py` 출력 |
| 오류 원인 분석 | Tester Agent FAIL 로그 |
| 개선 내용 | Refactor Agent + Review Agent 결과 |
| 사후영향 | IMPACT_ASSESSOR 보고서 |
| 다음 작업 권고 | 작업 맥락 + IMPACT_ASSESSOR "추가 조치 필요" |

---

## 보고서 작성 시 주의

1. `household_pii` 관련 테스트 결과에 **실제 평문 값**을 포함하지 않는다 (마스킹, 예: `address = "서*** 강**"`)
2. `.env` / `dataset_staging/` 경로 하위 실제 파일명을 그대로 노출하지 않는다 (데이터셋 라이선스 준수)
3. 실패 로그에 DB 접속 정보가 포함되어 있으면 커밋 전 제거
4. 보고서는 **공개 가능한 수준**으로만 작성 (PR 리뷰어 이외 팀원도 볼 수 있음을 전제)

---

## 보고서 작성 완료 후

- [ ] 보고서 파일 저장 확인 (`Database/tests/reports/`)
- [ ] PR 본문에 요약 섹션 붙여넣기
- [ ] `MEMORY.md` 갱신 불필요 (작업별 보고서는 반복 참조 대상 아님)
- [ ] Orchestrator 에 완료 보고
