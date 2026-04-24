# Architecture Decision Records (ADR)

> 중요한 기술 결정의 배경, 대안, 근거를 기록한다.
> 기존 결정을 뒤집을 때는 기존 ADR에 *Superseded by ADR-NNN* 표시 후 새 ADR을 추가한다.
> 삭제하지 않는다.

ADR 형식: Status · Context · Decision · Consequences · Alternatives Considered.

---

## ADR-001 — 전력 시계열 데이터 저장소 선택 및 해상도 정책

- **Status**: Accepted — 2026-04-21
- **관련 브랜치**: `Database`
- **구현 근거**: `Database/docs/schema_design.md §0, §3`, `Database/docs/dataset_spec.md §8`
- **상위 요구사항**: 루트 `CLAUDE.md` REQ-001 (NILM, 30Hz), REQ-004 (데이터 관리), REQ-007 (보안)

### Context

AI Hub 71685 데이터셋(110가구 × 31일 × 23채널, 30Hz)을 기반으로 NILM 기반 에너지 효율화 서비스를 구축한다. 실측 샘플 검증 결과:

- 1채널/일 = 2,592,000 rows (~200 MB CSV)
- 전체 데이터셋 원시 ~8 TB, 실시간 스트리밍까지 고려하면 무한 증가
- 30Hz 원시 데이터는 **NILM 엔진(분해·이상탐지)** 의 입력 신호이며, 그 외 UI·리포트·DR 정산 등은 분/시간 해상도면 충분

선택해야 할 것:
1. 어떤 저장소를 쓸 것인가 — PostgreSQL / TimescaleDB / InfluxDB / 파일(Parquet) / 하이브리드
2. 어느 해상도로 저장할 것인가 — 30Hz 원시 / 1분 집계 / 1일 집계 / 이중 계층
3. 원시 데이터와 NILM 엔진 결과를 DB에 넣을 것인가

### Decision

**세 가지를 묶어 결정한다.**

**D1. 스토리지 엔진: TimescaleDB (PostgreSQL 16 확장)**

- 시계열 전용(InfluxDB)·관계형 전용(순수 Postgres)·파일(Parquet) 대신 **Timescale = Postgres 확장** 단일 엔진 채택.
- 하이퍼테이블·columnstore·continuous aggregate·retention policy 등 시계열 운영 기능을 갖추면서 관계형 조인(가구/가전/날씨 메타) 품질 유지.

**D2. 30Hz 원시 데이터는 DB에 저장하지 않는다**

- 30Hz 원시는 NILM 엔진이 로컬 파일(또는 Kafka 스트림)에서 직접 읽어 분해·이상탐지 수행 후 폐기.
- DB는 이 결과물의 소비자(UI·리포트)만 서빙.

**D3. Hot/Cold 이중 해상도 저장 (1분 7일 + 1일 장기)**

- Hot tier: `power_1min` hypertable — 최근 7일, 1분 해상도 (avg/min/max active_power + energy_wh + 전기 특성 avg)
- Cold tier: `power_1day` continuous aggregate — 7일 이상 과거, 1일 해상도 (avg(avg)/min(min)/max(max) + sum(energy_wh))
- 주간 적재(예: 월요일 1주치 주입) + 연속집계 자동 리프레시 + 7일 retention drop 의 조합으로 운영.
- 집계 방식은 30Hz→1분 때와 동일 규칙을 재사용 (min/max 계층 합성성 성립).

**D4. NILM 엔진의 분해 결과는 DB에 저장하지 않는다**

- 모델 출력은 평가용으로 AI Hub 기제공 라벨(`activity_intervals`)과 비교에만 사용, DB 적재 없음.
- 서비스 론칭 이후 모델 출력 서빙이 필요해지면 재검토 (별도 ADR 발행).

**D5. 개인식별정보(PII)는 분리 테이블 + AES-256 암호화**

- `household_pii` 테이블에 `address`/`members`/`income(실제=맞벌이여부)` 격리.
- Fernet(AES-256) 대칭키 암호화, 키는 환경변수 `CREDENTIAL_MASTER_KEY`.
- 분석 역할은 `household_pii` 직접 조회 권한 없음.

### Consequences

**Positive**

- 운영 점유량: 7일 hot ~1.1 GB + 24일 cold ~50 MB ≈ **1.2 GB 수준**으로 상시 유지. 원시 8TB 대비 6,600× 축소.
- 단일 엔진(Postgres) 운영 → 백업·HA·모니터링 도구 단일화.
- 관계형 조인(가구 메타 × 측정값) 자연스러움 → NILM 분석 쿼리 단순.
- `power_1min` → `power_1day` 연속집계로 주간 다운샘플 로직을 DB가 자동 수행 → 애플리케이션 배치 코드 불필요.
- PII 분리로 개인정보 보호법·루트 보안 규칙 실행 경계 확립.

**Negative / Trade-offs**

- 30Hz 원시를 DB에서 사후 조회할 수 없음 → 이상 이벤트 사후 분석에 원시가 필요하면 별도 스냅샷 테이블 도입 필요 (연기됨).
- `avg(avg)` 1일 집계는 1분 버킷의 `sample_count` 가 균일할 때만 정확 → 결측 발생 시 가중평균(`sum(avg × count)/sum(count)`)으로 리팩터링 필요.
- Retention 과 cagg refresh 의 순서 의존성 → cagg 가 멈추면 7일 drop 도 멈춰야 데이터 손실 없음, 운영 모니터링 필수.
- NILM 모델 출력 미저장 → 장기 성능 추적·재학습 피드백 루프에 외부 스토리지(로그/S3) 별도 설계 필요.
- TimescaleDB 하이퍼테이블은 chunk 간 FK 제약이 제한적 → `(household_id, channel_num)` 참조 무결성을 ETL 단계에서 프로그램적으로 보장.

### Alternatives Considered

| 대안 | 기각 사유 |
|------|-----------|
| **InfluxDB** 단독 | 시계열 성능은 유사하나, 110가구 × 23채널 × 가전/날씨 메타 조인 쿼리에 플럭스 스크립트가 장황. 관계형 무결성(EXCLUDE gist)·PII 테이블 분리 불가 |
| **순수 PostgreSQL** (확장 없음) | 수억 행 시계열의 파티셔닝·압축·연속집계를 애플리케이션이 구현해야 함. 운영 부담 과다 |
| **Parquet 파일 레이크 + Trino** | 대화형 대시보드 쿼리 지연 과다. 가구 단위 갱신 작업에 부적합 |
| **30Hz 원시를 DB에 하이퍼테이블로 저장** | 8TB+ 규모. 관리 부담 대비 실효성 낮음 (분해·이상탐지 외 수요 없음). Columnstore 압축 후에도 1~2TB |
| **단일 1분 테이블, retention 없음** | 1~2년 후 100~200 GB 로 증가. 분석 수요상 1년 이상 과거는 1일 해상도로도 충분 → 비효율 |
| **1분→1시간→1일 3단 계층** | 쿼리 라우팅 복잡도 증가. 현재 요구사항(대시보드·월간 리포트)에 과대 설계 — 필요 시 `power_1hour` cagg 추가 여지로 남김 |
| **NILM 결과를 DB에 적재하고 실시간 서빙** | 모델 품질 미검증 상태에서 운영 부담 선행. 먼저 AI Hub 라벨과의 오프라인 평가로 신뢰도 확보 후 재결정 |

### Follow-ups

- [ ] 압축/보존 policy migration SQL 분리 (`Database/migrations/20260421_compression_retention.sql`)
- [ ] ETL 스크립트(`Database/scripts/ingest_aihub.py`) — CSV/JSON → 1분 집계 → DB
- [ ] cagg refresh + retention 운영 헬스체크 지표 정의 (후속 ADR 가능)
- [ ] 이상 이벤트 고해상도 윈도우 테이블 필요성 재평가
