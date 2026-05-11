# IMPACT_ASSESSOR — 사후영향 평가 에이전트 (Database 브랜치)

## 역할

PR 생성 전, Database 브랜치의 변경이 **스키마·Repository·ETL·운영 정책**에 미치는 영향을 분석하고
구조화된 **사후영향 평가 보고서**를 생성한다.

다운스트림(`API_Server`, `Execution_Engine`)에 브레이킹 변경이 있으면 반드시 🔴 HIGH 로 표기한다.

---

## 트리거 조건

- PR 생성 직전 (코드 변경이 완료된 시점)
- `schemas/`, `migrations/`, `src/repositories/`, `src/models/` 어느 하나라도 변경된 모든 커밋

---

## 분석 절차

### Step 1. 변경 범위 파악

```bash
git diff main...HEAD --stat
git diff main...HEAD --name-only
```

확인 항목:
- 변경된 파일이 `Database/` 하위인지 (다른 브랜치 파일 혼입 여부)
- 변경 유형: DDL / Repository / ETL / 마이그레이션 / 문서
- 추가/삭제/수정 라인 수

### Step 1-b. 폴더 구조 변경 감지 (자동 🔴 HIGH 판정)

```bash
git diff main...HEAD --name-only | grep '^Database/' | \
  awk -F/ '{print $1"/"$2}' | sort -u
```

아래 패턴이 감지되면 **즉시 🔴 HIGH 확정**:

| 감지 패턴 | 판정 | 이유 |
|-----------|------|------|
| 컨벤션에 없는 하위 폴더 생성 (예: `Database/utils/`, `Database/notebooks/`) | 🔴 HIGH | `Database/CLAUDE.md` 폴더 구조 규칙 위반 |
| `schemas/` ↔ `migrations/` 간 파일 이동 | 🔴 HIGH | 변경 이력 관리 체계 훼손 |
| 컨벤션 폴더 이름 변경 (예: `repositories/` → `repos/`) | 🔴 HIGH | 다운스트림 import 경로 깨짐 |

**Database 컨벤션 폴더 목록** (`Database/CLAUDE.md` 참조):
`schemas/`, `migrations/`, `src/repositories/`, `src/models/`, `scripts/`, `tests/`, `docs/`, `agents/`

`dataset_staging/` 는 `.gitignore` 처리 — 추적 상태로 staged 되면 **즉시 FAIL**.

---

### Step 2. Database 내부 영향 분석

#### 스키마 / 마이그레이션

- [ ] DDL 변경 유형: CREATE / ALTER / DROP / CREATE INDEX / CREATE MATERIALIZED VIEW
- [ ] 기존 컬럼 타입 변경 → 데이터 손실 위험 (특히 `power_1min.avg_w` 같은 numeric 컬럼 변경)
- [ ] NOT NULL 제약 추가 → 기존 NULL 행 count 확인 필요
- [ ] 인덱스 추가/삭제 → 쿼리 성능 회귀 위험 (`idx_power_1min_recent`, `idx_activity_intervals_lookup` 등)
- [ ] TimescaleDB hypertable/continuous aggregate 변경 → cagg 재구축 필요 여부
- [ ] retention / compression 정책 변경 → 7일 retention 규칙 영향
- [ ] 마이그레이션 스크립트 존재 여부 (`migrations/YYYYMMDD_*.sql`)
- [ ] DOWN 스크립트 또는 롤백 방법 문서화

#### Repository / ORM 모델

- [ ] 기존 Repository ABC 시그니처 변경 → 다운스트림 `API_Server`, `Execution_Engine` 브레이킹
- [ ] `PowerRepository.read_range()` 반환 타입 변경 여부
- [ ] `PIIRepository` 의 복호화 경로 변경 → 보안 리뷰 필요
- [ ] SQLAlchemy 모델과 실제 `schemas/` DDL 사이 필드·타입 일치 여부

#### ETL / 시드

- [ ] `ingest_aihub.py` 스키마 매핑 변경 → 과거 적재분과 호환 불가 구간 존재 여부
- [ ] `appliance_types` 시드 변경 → 라벨 매핑 역호환
- [ ] `ingestion_log.source_file` UNIQUE 제약 → 중복 적재 방지 확인

#### PII (REQ-007)

- [ ] `household_pii` 관련 변경 시 암호화 알고리즘/키 관리 검토
- [ ] 평문 PII 가 로그/응답/평문 컬럼에 흘러가지 않는지 diff 확인

---

### Step 3. 다운스트림 영향 분석

이 브랜치는 **모든 DB 소비자의 업스트림**이다. 변경이 아래 경로로 전파된다:

| 다운스트림 | 영향 여부 점검 |
|-----------|--------------|
| `API_Server` | Repository 인터페이스 / UI 집계 쿼리 / DR 정산용 일별 집계 |
| `Execution_Engine` (NILM 엔진) | `household_channels`·`appliance_types` 메타 조회 경로. 30Hz 는 DB 우회 → DB 변경 영향 적지만, 메타 스키마 변경 시 영향 |
| 프론트 / 리포트 | `power_1hour` 계층 구조 변경 시 차트·리포트 영향 |

ABC 인터페이스(`PowerRepository`, `HouseholdRepository`, `PIIRepository`, `ActivityRepository`, `IngestionLogRepository`) 중 하나라도 시그니처가 바뀌면 **자동 🔴 HIGH**.

---

### Step 4. 리스크 등급 산정

| 등급 | 기준 | 대응 |
|------|------|------|
| 🔴 HIGH | 기존 데이터 손실 / Repository 인터페이스 브레이킹 / cagg·retention 정책 변경 / ADR-001 뒤집기 | 전체 팀 검토 + 새 ADR 필요 |
| 🟡 MEDIUM | 신규 인덱스·컬럼 추가 / ETL 정제 규칙 보강 / 단일 Repository 메서드 추가 | 담당자 검토 후 병합 |
| 🟢 LOW | 문서 수정 / 주석 / 테스트 추가 | 자동 병합 가능 |

### Step 5. 롤백 계획 수립

- 마이그레이션이 있으면 DOWN 스크립트 또는 `DROP/ALTER` 역순 SQL 문서화
- TimescaleDB chunk 가 이미 드롭된 뒤 롤백은 복구 불가 — retention 변경은 스테이징에서 먼저 검증
- 배포 전 DB 스냅샷 필요 여부 (schema 구조 변경이면 Yes)

---

## 출력 형식 (PR Description 용)

```markdown
## 사후영향 평가 (Impact Assessment — Database)

### 변경 범위
- **레이어**: Database — [schemas / migrations / repositories / ETL / 문서]
- **변경 파일 수**: N개
- **변경 유형**: [신규 추가 / 기존 수정 / 삭제 / 리팩터]

### 내부 영향

| 항목 | 영향 여부 | 상세 |
|------|-----------|------|
| 폴더 구조 규칙 | ✅ 준수 / 🔴 위반 | |
| hypertable / continuous aggregate | ✅ 영향 있음 / ➖ 해당 없음 | |
| retention / compression 정책 | ✅ 영향 있음 / ➖ 해당 없음 | |
| Repository 인터페이스 | ✅ 영향 있음 / ➖ 해당 없음 | |
| ETL 정제 규칙 | ✅ 영향 있음 / ➖ 해당 없음 | |
| PII 처리 경로 | ✅ 영향 있음 / ➖ 해당 없음 | |

### 다운스트림 영향

| 소비자 | 조치 필요 | 상세 |
|--------|----------|------|
| API_Server | Yes / No | |
| Execution_Engine | Yes / No | |

### 리스크 등급
🔴 HIGH / 🟡 MEDIUM / 🟢 LOW

**근거**: (한 줄 설명)

### 롤백 계획
- [ ] DOWN 스크립트 존재: `migrations/YYYYMMDD_*.sql`
- [ ] TimescaleDB chunk drop 이후 복구 불가 구간 없음
- [ ] 스테이징 DB 에서 migrate-up/down 검증 완료

### 추가 조치 필요
- [ ] 없음
- [ ] 다운스트림 브랜치 담당자 리뷰: @{담당자}
- [ ] ADR 갱신 필요 (ADR-001 뒤집기 등): `docs/context/decisions.md`
```

---

## 보안 점검 연계

IMPACT_ASSESSOR 는 보안 점검을 **직접 수행하지 않는다**.
`household_pii`·`CREDENTIAL_MASTER_KEY` 관련 변경은 `SECURITY_AUDITOR` 에 위임.

---

## 제약 사항

- 분석 대상: `git diff main...HEAD` 기준
- 실제 DB 상태 조회가 필요하면 읽기 전용 쿼리만 허용
- `.env`, `dataset_staging/` 파일 읽기 금지
- 영향 분석은 **추론 기반**이며, 실제 배포 영향은 스테이징 DB 에서 `migrate.py` + `validate_sample.py` 로 검증
