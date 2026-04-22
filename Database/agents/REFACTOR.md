# Refactor Agent 지시사항 (Database 브랜치)

## 역할
모든 테스트가 PASS 된 이후에만 실행된다. 테스트 통과 상태를 유지하면서 Database 계층 코드 품질을 개선한다 (TDD Refactor 단계).

---

## 핵심 원칙

1. **테스트 통과 상태 유지**: 리팩토링 후 반드시 전체 테스트 재실행하여 PASS 확인
2. **기능·쿼리 결과 변경 금지**: 동일 입력에 대해 동일 행/집계값을 반환해야 함
3. **범위 제한**: `Database/src/` 및 `Database/scripts/` 만 수정. `schemas/` · `migrations/` 는 이미 배포된 이력이므로 수정 금지
4. **작은 단위로 개선**: 한 번에 하나씩 개선하고 테스트 확인 후 다음으로 넘어간다

---

## 개선 검토 항목

### Repository 코드 품질

- [ ] 중복된 WHERE 절 / ORDER BY 패턴 → 공통 헬퍼로 통합
- [ ] 반복되는 `AsyncSession` 개방·닫기 → 컨텍스트 매니저로 통합
- [ ] 에러 처리 누락 (ETL 실패 시 `ingestion_log.status = 'failed'` 기록 경로)
- [ ] 하드코딩된 배치 크기 / 청크 시간 → 상수 또는 설정값
- [ ] 로깅 메시지 명확성 (household_id·channel_num·bucket_ts 맥락 포함 여부, 단 PII·평문 값은 로그 금지)

### 시계열 쿼리 성능

- [ ] 루프 안 쿼리 제거 (N+1 → 배치 `IN (...)` 조회)
- [ ] `time_bucket()` 호출이 WHERE 절 파티셔닝 키 앞에 오지 않는지 — chunk pruning 저해
- [ ] `power_1min` vs `power_1hour` 라우팅 경계 (7일 기준)가 한 곳에서만 정의되는지
- [ ] 대용량 INSERT 가 `INSERT ... VALUES` 대신 `copy_records_to_table()` / `executemany` 를 사용하는지
- [ ] 불필요한 `SELECT *` 제거 — 필요한 컬럼만 지정

### ETL 정제 규칙

- [ ] `dataset_spec.md §6` 6건 규칙이 헬퍼 함수 한 곳에 모여 있는지 (산발적 `if` 분기 통합)
- [ ] `power_consumption = "unknown"` → `None` 변환 로직이 여러 곳에 중복되어 있지 않은지
- [ ] 30Hz → 1분 집계 함수가 `avg/min/max/energy_wh/sample_count` 5개를 한 번의 스캔으로 산출하는지

### 인덱스 / 제약 힌트 (제안만, 실제 변경은 migrations/ 에서)

- [ ] 자주 쓰는 쿼리가 `idx_power_1min_recent` 를 타는지 EXPLAIN 으로 확인
- [ ] `activity_intervals` 조회가 GiST 인덱스를 타는 tstzrange 오버랩 연산자인지
- [ ] 인덱스 변경 제안은 코드가 아닌 `migrations/YYYYMMDD_*.sql` 신규 파일로 기록 (Refactor 범위 밖)

---

## 리팩토링 범위 제한

아래 항목은 Refactor Agent 의 수정 대상에서 제외한다:

- 테스트 파일 (`Database/tests/`)
- DDL·시드 SQL (`Database/schemas/`, `Database/migrations/`) — 이미 적용된 이력
- 설계 문서 (`Database/docs/schema_design.md`, `dataset_spec.md`, `ERD/`)
- 환경 설정 (`.env`, `dataset_staging/`)
- 공용 컨텍스트 문서 (`docs/context/*`)

위 항목 변경이 필요하면 Developer 재호출 또는 별도 PR 로 분리.

---

## 리팩토링 완료 후 확인

```
1. 전체 테스트 재실행 (`pytest Database/tests/ -v`)
2. 이전 테스트 결과와 PASS/FAIL 건수 동일한지 확인
3. 샘플 ETL 재실행하여 `power_1min` 행수·합계 변동 없는지 검증 (기능 동일성 검사)
4. 변경된 내용 목록 작성 → Reporter Agent 에 전달
```

## Reporter Agent 에 전달할 개선 내용 형식

```
[리팩토링 항목]
- 파일: [파일명]
- 변경 전: [기존 코드/구조 요약]
- 변경 후: [개선된 코드/구조 요약]
- 개선 이유: [왜 개선했는지 — 중복 제거 / N+1 해소 / 파티셔닝 키 정렬 / ETL 규칙 통합 등]
- 테스트 영향: [PASS 유지 / 샘플 검증 결과]
```
