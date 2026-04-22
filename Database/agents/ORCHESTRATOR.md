# Orchestrator Agent 지시사항 (Database 브랜치)

## 역할
Database 브랜치의 TDD 사이클 전체를 관리한다. 작업 단위(스키마 추가 / Repository 메서드 / ETL 규칙 / 마이그레이션)를 분해하여
각 에이전트를 순서대로 호출하고, 완료 기준을 판단한다.

---

## 실행 순서

```
1. Security Auditor Agent 호출 (작업 시작 전 점검)
   - FAIL 존재 → 사용자 보고 후 중단
   - PASS → 다음 단계
2. 작업 대상 결정
   - 스키마 변경 → `Database/schemas/` 또는 `Database/migrations/`
   - Repository 메서드 → `Database/src/repositories/`
   - ETL 규칙 변경 → `Database/scripts/`
3. 작업 목록 분해 (테스트 가능한 단위로)
4. Test Writer Agent 호출 → 테스트 파일 생성 확인
5. Developer Agent 호출 → 구현 파일 생성 확인
6. Tester Agent 호출 → pytest 실제 실행 (실제 테스트 DB 연결)
7. 결과 판단
   - 모든 테스트 PASS → Refactor Agent 호출
   - FAIL 존재 → Developer Agent 재호출 → Tester 재실행 (최대 3회)
8. Review Agent 호출 (방어적 코드 리뷰)
   - 7개 점검 축 결과 수신
   - Critical 발견 → Developer 재호출 → Tester → Refactor → Review 재실행 (최대 2회)
   - Major 발견 → Developer 또는 Refactor 에 위임 후 Review 재실행
   - Minor 만 존재 → Reporter 에 전달, 다음 단계 진행
   - 보안 위임 플래그 = yes → 10단계 Security Auditor 점검 범위에 해당 항목 포함
9. Reporter Agent 호출 → 보고서 생성 확인 (pytest 결과 + Review Findings 포함)
10. Security Auditor Agent 호출 (커밋 직전 최종 점검)
    - FAIL 존재 → 커밋 차단, 사용자 수동 조치 요청
    - PASS → git add/commit 진행 (Database/ 하위 파일만 스테이징)
11. 완료 기준 체크
```

---

## 작업 유형별 검증 포인트

| 작업 유형 | Test Writer 필수 항목 | Tester 검증 포인트 |
|----------|---------------------|-------------------|
| 신규 테이블 (`schemas/*.sql`) | DDL 적용 후 `\d` 로 컬럼·제약 확인 | `migrate-up` → `migrate-down` 라운드트립 |
| Repository 메서드 추가 | save / retrieve / filter 각각의 pytest | 실제 테스트 DB 에서 round-trip |
| TimescaleDB hypertable 추가 | `create_hypertable()` 호출 결과 확인 | chunk_time_interval, partitioning_column 검증 |
| Continuous aggregate | cagg 정의 SQL + `CALL refresh_continuous_aggregate(...)` | 원본 데이터 변경 후 재리프레시 결과 비교 |
| retention / compression 정책 | 정책 적용 스크립트 멱등성 테스트 | 정책 부재 시 FAIL 로그 발생 확인 |
| ETL 스크립트 (`ingest_aihub.py`) | `dataset_spec.md §6` 정제 규칙 6건 단위 테스트 | 샘플 CSV 1개 적재 → `power_1min` 행수·`energy_wh` 합계 검증 |
| PII 암호화 경로 | Fernet encrypt → DB 저장 → decrypt 라운드트립 | 평문이 DB 평문 컬럼에 흘러가지 않는지 grep |

---

## 작업 분해 원칙

- 테스트 가능한 최소 단위로 분해한다
- 각 단위는 독립적으로 검증 가능해야 한다
- 스키마 순서 의존: `001_core_tables.sql` → `002_timeseries_tables.sql` → `003_seed_appliance_types.sql` → `migrations/*.sql`
- ETL 순서 의존: `households` + `household_channels` 선행 → `power_1min` 적재 → `activity_intervals` 라벨 적재

---

## 에이전트 호출 시 전달해야 할 정보

각 에이전트 호출 시 아래 정보를 반드시 포함한다:
- 작업 대상 파일 경로 (상대경로, `Database/` 하위)
- 작업 유형 (표 참조)
- 이전 단계 결과 (Developer 호출 시 테스트 결과, Refactor 호출 시 구현 결과, Review 호출 시 base/head ref + 변경 파일 목록)
- 테스트 DB 접속 정보는 `.env` 를 통해서만 (에이전트에게 평문 전달 금지)

---

## 실패 처리 규칙

- Developer 3회 반복 후에도 FAIL 잔존 → Reporter 에 실패 내용 전달 후 보고서 생성, 사용자 검토 대기
- Review 2회 반복 후에도 Critical 잔존 → Reporter 에 Findings 전달 후 진행 보류
- `cagg` / `retention` 정책 실패 → 운영 헬스체크 항목 이라 사용자에게 즉시 보고 (자동 재시도 금지)
- 마이그레이션 DOWN 스크립트 없는 DDL 변경 → 🔴 HIGH 로 Reporter 에 기록하고 병합 보류

---

## 완료 기준 (공통)

- [ ] Security Audit PASS (작업 시작 전)
- [ ] 테스트 파일 생성 완료 (`Database/tests/`)
- [ ] 구현 파일 생성 완료 (`Database/schemas/` or `src/repositories/` or `scripts/`)
- [ ] 전체 테스트 PASS 또는 잔여 FAIL 사유 문서화
- [ ] Review Agent 실행 완료, Critical 0건
- [ ] 마이그레이션 DOWN 경로 또는 복구 방법 문서화 (DDL 변경 시)
- [ ] 보고서 생성 완료 (`Database/tests/reports/` 또는 PR 본문)
- [ ] Security Audit PASS (커밋 직전)
- [ ] `Database/` 하위 파일만 스테이징 (다른 브랜치 파일 혼입 0건)
