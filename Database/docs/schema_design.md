# 데이터베이스 스키마 설계 근거

> 대상 DDL: `Database/schemas/001_core_tables.sql`, `002_timeseries_tables.sql`, `003_seed_appliance_types.sql`, `004_nilm_inference_tables.sql`
> 상위 요구사항: 루트 `CLAUDE.md` REQ-001 (NILM 엔진, 30Hz), REQ-002 (이상 탐지), REQ-004 (데이터 관리), REQ-007 (보안)
> 데이터 명세: `Database/docs/dataset_spec.md`
> 모델 인터페이스: `Database/docs/model_interface.md`

## 0. 핵심 정책 결정

**30Hz 원시 전력 데이터는 DB에 저장하지 않는다.**

- NILM 엔진이 로컬 파일(또는 스트림)에서 30Hz 데이터를 직접 읽어
  분해(Disaggregation)·이상탐지 수행 후 결과만 반환, 원시는 폐기.
- 이상 이벤트 고해상도 윈도우 테이블은 **후속 작업으로 연기**.

**NILM 모델 출력은 구간 기반으로 DB에 적재한다.** _(정책 개정 — 초기 설계에서 뒤집음)_

- CNN+TDA 하이브리드 모델의 가전 상태 분류 결과를 `appliance_status_intervals` 에 구간 단위로 저장.
- 이유: 실서비스 단계에서는 AI Hub 같은 ground truth 라벨이 존재하지 않으므로 시간대별 이상 탐지 (REQ-002) 및 실시간 알림(프론트 태그 + SMTP)의 입력원이 모델 출력 자체. 어딘가에 영속화해야 함.
- AI Hub 라벨(`activity_intervals`)은 학습/평가 ground truth, 모델 출력(`appliance_status_intervals`)은 실서비스/이상탐지 입력 — **두 테이블은 병행**하며 IoU/F1 평가에서 JOIN.
- 상세 스펙: `Database/docs/model_interface.md`.

**DB 저장은 2단 해상도 구조(hot/cold)로 운영한다.**

| 계층 | 해상도 | 범위 | 테이블 |
|------|--------|------|--------|
| Hot  | 1분    | 최근 7일 | `power_1min` (hypertable) |
| Cold | 1시간  | 7일 이상 과거 | `power_1hour` (continuous aggregate on `power_1min`) |

- 신규 데이터는 매주(예: 월요일) 1주치를 1분 해상도로 `power_1min` 에 적재.
- 7일이 지난 chunk 는 **retention 정책으로 자동 삭제**, 그 전에 연속집계가
  `power_1hour` 로 시간 단위 요약 저장 → 장기 보관.
- 집계 규칙(1분 → 1시간)은 30Hz → 1분 때와 동일: `avg/min/max` + 누적 `energy_wh`.

**cold 해상도를 1일이 아닌 1시간으로 택한 이유**: REQ-002 이상탐지는 "가구 A가 평소
08~10시에 가전 B 사용" 같은 **시간대별 패턴**을 학습·검증해야 한다. 1일 해상도로
다운샘플하면 시간대 정보가 전부 소실돼 시간대별 이상탐지가 불가능. 1시간 해상도는
24× 더 무겁지만 전구간 보관해도 ~120 MB 수준으로 저장 부담이 작고, 시간대 특성을
cold tier 에서도 그대로 유지할 수 있다.

### 0.1 이 결정의 이유

| 항목 | 30Hz 원시 | 1분 집계 (hot) | 1시간 집계 (cold) |
|------|-----------|----------------|-------------------|
| 1채널/일 행 수 | 2,592,000 | 1,440 | 24 |
| 1채널/일 용량 | ~200 MB | ~115 KB | ~2 KB |
| 전체 데이터셋 (110가구·31일·23채널) 기준 | ~8 TB | ~5~6 GB (전구간 1분 보관 시) | **~120 MB** (전구간 1시간 보관 시) |
| 실제 DB 동시 점유 (7일 hot + 24일 cold) | — | ~1.1 GB (7일분) | ~95 MB (24일분) |
| NILM 엔진 접근 경로 | 파일/스트림 직접 (DB 우회) | — | — |

- 30Hz 원시는 NILM 엔진 내부 연산 중간 산출물 성격.
- 최근 7일은 대시보드·이상탐지 사후 조회용으로 1분 해상도 유지.
- 7일 이상 과거는 리포트·월간 추세 + **시간대별 이상탐지**용이므로 1시간 해상도가
  최소 요구선. 1분 대비 60× 축소, 1일 대비 24× 확대.
- 고해상도가 필요한 이상 이벤트 스냅샷은 추후 필요성 검증 뒤 별도 테이블 도입.

## 1. 스토리지 선택

| 데이터 성격 | 선택 | 이유 |
|------------|------|------|
| 1분 집계 전력 시계열 (hot) | **TimescaleDB** hypertable | 7일 retention, 분/시간 해상도 조회 |
| 1시간 다운샘플 집계 (cold) | **TimescaleDB** continuous aggregate | `power_1min` 에서 자동 리프레시, 장기 보관 + 시간대 패턴 보존 |
| 가구/가전/라벨 메타 | **PostgreSQL** | 관계형 무결성·EXCLUDE 제약 필요 |
| 30Hz 원시 (NILM 엔진 입력) | **DB 저장 안 함** | §0 정책 |

단일 엔진(Timescale=Postgres)으로 운영 복잡도 최소화. InfluxDB는 운영 모니터링 등 부가 용도로 한정.

## 2. 테이블 분할 전략

```
appliance_types                — 22+1종 가전 마스터 (정적)
households                     — 가구 마스터 (준식별 분류값; 분석 가능)
household_pii                  — 주소/구성원/맞벌이 (🔒 암호화·접근통제)
household_channels             — 가구별 ch01~ch23 구성 (가전 메타 포함)
household_daily_env            — 가구별 일별 날씨/기온/풍속/습도
power_1min                     — 1분 집계 시계열 (hypertable, hot 7일, ch01~ch23 공용)
power_1hour                    — 1시간 다운샘플 (continuous aggregate, cold 장기, 시간대 패턴 보존)
activity_intervals             — 가전 ON 구간 라벨 (AI Hub ground truth, 초 단위 정밀도)
appliance_status_intervals     — CNN+TDA 모델 상태 출력 (구간 기반, 실서비스/이상탐지 입력)
appliance_status_codes         — status_code 의미 정의 마스터
ingestion_log                  — 파일 적재 이력
```

### 2.1 PII 분리 (보안)

루트 `CLAUDE.md` 보안 규칙의 "개인정보 AES-256 암호화"를 구현 가능한 경계로 만들기 위해 가구 테이블을 **평문 분류값**과 **암호화 PII** 둘로 분리:

- `households` — `house_type`, `residential_type`, `residential_area`: 집계 분석에 필요, 저민감 준식별자
- `household_pii` — `address_enc`, `members_enc`, `income_dual`: 직접 식별 가능, 분석에 불필요

`household_pii` 직접 조회 권한은 최소 역할(감사/민원 대응)에만 부여. 분석 역할은 `households`만 접근.

### 2.2 메타데이터 정규화 (중복 저장 금지)

AI Hub JSON `meta` 24 필드는 **모두 보존**하되, 1분 행마다 복사하지 않고 정규화 테이블에 분산 저장 후 조회 시 조인:

| meta 필드 | 저장 위치 |
|----------|-----------|
| `filename`, `id`, `date` | 유도 가능 — 저장 안 함 (ETL 흔적은 `ingestion_log`) |
| `sampling_frequency`, `unit` | 시스템 상수(30Hz, W) — 저장 안 함 |
| `house_type`, `residential_type`, `residential_area`, `co-lighting` | `households` |
| `type`, `name`, `brand`, `power_category`, `power_consumption`, `energy_efficiency` | `household_channels` |
| `address`, `members`, `utility_facilities`, `extra_appliances`, `income` | `household_pii` |
| `weather`, `temperature`, `windchill`(→풍속), `humidity` | `household_daily_env` |

1분 측정 행에 메타를 복제하면 같은 값이 1,440×23=33,120회/가구/일 중복 → 정규화 유지.

### 2.3 날씨/환경 분리 근거

JSON meta 중 `weather, temperature, windchill(실제는 풍속), humidity` 는 **가구 × 날짜** 단위로 변동하므로 `household_daily_env` 로 분리.

### 2.4 이름 오용 수정

원본 JSON 필드 중 2개가 이름과 실제 의미가 다름 — 스키마에서 **실의미대로 개명**해 실수 유발 제거:

| 원본 | 실제 의미 | DB 컬럼 |
|------|----------|---------|
| `meta.windchill` | 평균풍속 (avgWs) | `household_daily_env.wind_speed_ms` |
| `meta.income` | 맞벌이 여부 | `household_pii.income_dual` |

## 3. 시계열 설계 — `power_1min`

### 3.1 단일 하이퍼테이블 (분전반 + 가전 공용)

분전반(ch01)과 AI Hub가 분리 제공하는 가전 채널(ch02~23)은 측정 스키마가 동일하므로 **한 테이블**(`power_1min`)에 channel_num 으로 구분해 적재.

- Pro: 스키마 중복 제거, 가구-전체 조회 시 UNION 불필요
- Pro: `household_channels` 조인 하나로 모든 채널 해석 가능
- 채널 범위 `CHECK(channel_num BETWEEN 1 AND 23)` 으로 규범화

### 3.2 집계 컬럼 설계 (avg/min/max + Wh)

| 컬럼 | 목적 |
|------|------|
| `active_power_avg/min/max` | 유효전력 — NILM·이상탐지 주 신호. 변동성 보존용 min/max 포함 |
| `energy_wh` | 1분간 누적 소비전력량 (Wh) — 리포트·과금·DR 실적 계산의 1차 지표 |
| `voltage_avg`, `current_avg`, `frequency_avg` | 전기 품질 지표 (변동폭 작음 → avg만) |
| `apparent_power_avg`, `reactive_power_avg`, `power_factor_avg` | 무효/역률 분석 |
| `phase_difference_avg` | 위상 관련 분석 (voltage_phase=0 상수, current_phase==phase_difference 이므로 하나만) |
| `sample_count` | 집계 품질 지표 — 정상 1,800, 미달 시 결측 경고 |

`energy_wh` 는 ETL 단계에서 `Σ(active_power × dt)` 로 적분 계산. 1분 평균×(1/60h) 근사와는 작은 오차가 있으므로 **적분 방식 확정**.

### 3.3 하이퍼테이블 파티셔닝

- **시간 축**: 7일 단위 chunk (`chunk_time_interval = INTERVAL '7 days'`)
  - 1분 집계로 행이 1,800× 줄어든 만큼 30Hz 시절의 1일 chunk 는 과분할 → 7일로 병합
- **공간 축**: `household_id` 해시 분할, 4 partitions
  - 110가구를 4 bucket 에 분산, 가구 단위 병렬 쿼리 유리

### 3.4 인덱스

```sql
-- 고유성 + 역방향 시간 조회
CREATE UNIQUE INDEX idx_power_1min_pk
    ON power_1min (household_id, channel_num, bucket_ts);
CREATE INDEX idx_power_1min_recent
    ON power_1min (household_id, channel_num, bucket_ts DESC);
```

- 기본 쿼리 패턴: **특정 가구 × 특정 채널 × 특정 기간**
- DESC 인덱스로 대시보드 최근 데이터 조회 최적화

### 3.5 Retention + Continuous Aggregate (이중 보존)

1분 해상도 데이터는 압축이 아니라 **7일 retention + 1시간 다운샘플**로 관리.

```sql
-- 1) 1시간 다운샘플 연속집계 자동 리프레시 (시간 단위)
SELECT add_continuous_aggregate_policy('power_1hour',
    start_offset       => INTERVAL '30 days',
    end_offset         => INTERVAL '2 hours',
    schedule_interval  => INTERVAL '1 hour');

-- 2) 1분 테이블: 7일 이상 지난 chunk 자동 삭제
SELECT add_retention_policy('power_1min', INTERVAL '7 days');
```

**순서 안전성**: cagg 리프레시가 한 시간에 한 번 돌아 직전 완성된 버킷까지 요약해 둔 상태에서 retention drop 이 7일 경계에서 수행됨. cagg 가 멈추면 retention 도 멈춰야 데이터 손실 없음 → 운영 모니터링 필수.

### 3.6 FK 제약 한계

TimescaleDB 하이퍼테이블은 chunk 간 FK 제약이 제한적. `power_1min(household_id, channel_num)` 의 `household_channels` 참조는 **ETL 단계에서 조회·검증**으로 대체. 스키마상 명시적 FK 미설정.

### 3.7 1시간 다운샘플 계층 (`power_1hour`)

```sql
CREATE MATERIALIZED VIEW power_1hour
WITH (timescaledb.continuous) AS
SELECT
    time_bucket(INTERVAL '1 hour', bucket_ts) AS hour_bucket,
    household_id, channel_num,
    avg(active_power_avg) AS active_power_avg,
    min(active_power_min) AS active_power_min,
    max(active_power_max) AS active_power_max,
    sum(energy_wh)        AS energy_wh,
    -- ... 나머지 전기 특성 avg(avg)
    sum(sample_count)     AS sample_count,
    count(*)              AS minute_bucket_count
FROM power_1min
GROUP BY hour_bucket, household_id, channel_num
WITH NO DATA;
```

**집계 규칙** (30Hz → 1분 때와 동일 방식):

| 컬럼군 | 1분→1시간 집계 함수 |
|--------|--------------------|
| `active_power_avg/min/max` | `avg / min / max` (min/max는 계층 합성 속성) |
| `energy_wh` | `sum` — 1시간 누적 소비전력량 (Wh) |
| `voltage_avg`, `current_avg`, `frequency_avg` 등 | `avg` (sample_count 균일 가정 시 근사) |
| `sample_count` | `sum` — 1시간 원시 샘플 총수 (정상 108,000 = 30Hz × 3,600s) |
| `minute_bucket_count` | `count(*)` — 집계 품질 지표 (정상 60) |

**주의**: `avg(avg)` 는 각 1분 버킷 `sample_count` 가 균일할 때만 가중평균과 동일. AI Hub 데이터는 1분당 1,800 포인트로 거의 균일하지만, 결측이 섞이면 오차 가능. 필요 시 `sum(avg * sample_count) / sum(sample_count)` 로 가중평균 리팩터링.

**쿼리 패턴**: 대시보드는 `UNION ALL` 또는 뷰로 hot+cold 투명 조회:

```sql
CREATE VIEW power_combined AS
SELECT bucket_ts AS ts, household_id, channel_num,
       active_power_avg, energy_wh, '1min' AS resolution
FROM power_1min
UNION ALL
SELECT hour_bucket AS ts, household_id, channel_num,
       active_power_avg, energy_wh, '1hour' AS resolution
FROM power_1hour
WHERE hour_bucket < NOW() - INTERVAL '7 days';  -- 중복 방지
```

## 4. 라벨 및 모델 출력 — 이중 구조

역할이 다른 두 구간 테이블을 병행 운영한다.

| 테이블 | 출처 | 정밀도 | 상태 표현 | 용도 |
|--------|------|--------|----------|------|
| `activity_intervals` | AI Hub 71685 제공 라벨 | 초 단위 | ON 구간만 (OFF 는 여집합) | 학습/평가 ground truth |
| `appliance_status_intervals` | CNN+TDA 모델 출력 | 모델 추론 주기 | status_code (off/active/wash/spin ...) | 실서비스, 이상탐지 입력, 실시간 알림 |

### 4.1 `activity_intervals` — ground truth (AI Hub 라벨)

`active_inactive` 배열은 "기기 ON 구간"만 나열 — 비활성 구간은 암묵적 여집합. 테이블은 **활성(ON) 구간**만 저장하고 OFF 는 도출.

**1분 집계와 독립된 초 단위 정밀도**: 라벨은 1분 버킷과 별개로 **초 단위 원래 정밀도**를 유지.

- NILM 모델 학습·평가 시 1분 해상도로 다운샘플하면 짧은 ON 이벤트(예: 전자레인지 30초) 손실
- 1분 집계와의 정합성은 쿼리 시점에 범위 연산(`tstzrange && tstzrange`)으로 해결 가능

**구간 겹침 방지**:

```sql
EXCLUDE USING gist (
    household_id WITH =,
    channel_num  WITH =,
    tstzrange(start_ts, end_ts, '[]') WITH &&
)
```

동일 (가구, 채널) 내에서 시간 구간이 겹치는 행을 DB 레벨에서 차단 — 라벨링 품질 보증.

`source` 컬럼 유일 값: `'aihub_71685'`. 과거엔 다른 라벨 출처 병존을 고려했으나, 모델 출력은 아래 `appliance_status_intervals` 로 분리했으므로 이 테이블은 외부 라벨 전용.

### 4.2 `appliance_status_intervals` — CNN+TDA 모델 출력

구간 기반(`start_ts`, `end_ts`) 으로 `status_code` + `confidence` + `model_version` 저장. 핵심 설계 포인트:

- **INSERT = 상태 전환 이벤트 발행**: 상태가 유지되는 동안은 새 행 발행 금지, 전환 시에만 이전 구간 UPDATE(`end_ts`) + 신규 INSERT 를 단일 트랜잭션으로 수행.
- **`end_ts IS NULL` = 현재 진행 중**: partial index 로 "지금 상태" O(log N) 조회.
- **`model_version` 축**: 동일 구간에 여러 버전 병존 허용 → A/B 평가, ground truth(`activity_intervals`) 와 비교 시 IoU/F1 계산.
- **`confidence < 0.6` 은 이상탐지 집계에서 제외** (REQ-001). 임계값은 초기 모델 분포 확인 후 재조정.
- **`appliance_status_codes` 마스터**: status 의미를 마스터로 분리해 가전별 상세 상태(세탁기 wash/rinse/spin, 냉장고 compressor_on/defrost 등) 확장 가능.

**구간 겹침 차단** (`model_version` 축 포함):

```sql
EXCLUDE USING gist (
    household_id  WITH =,
    channel_num   WITH =,
    model_version WITH =,
    tstzrange(start_ts, COALESCE(end_ts, 'infinity'), '[)') WITH &&
)
```

모델 팀이 확정해야 할 항목(상태 코드 세트, confidence 정의, 추론 주기 등)과 적재 트랜잭션 템플릿은 `Database/docs/model_interface.md` 참조.

### 4.3 두 테이블 평가 JOIN 패턴

```sql
SELECT gt.household_id, gt.channel_num,
       gt.start_ts, gt.end_ts,
       m.status_code, m.confidence
FROM activity_intervals gt
LEFT JOIN appliance_status_intervals m
  ON gt.household_id = m.household_id
 AND gt.channel_num  = m.channel_num
 AND m.model_version = 'cnn_tda_v1'
 AND tstzrange(gt.start_ts, gt.end_ts, '[]')
     && tstzrange(m.start_ts, COALESCE(m.end_ts, 'infinity'), '[)');
```

이상탐지 로직은 `appliance_status_intervals` 에서 INSERT 트리거로 발화 → 이상 판정 시 `anomaly_events` (후속 PR) 로 승격.

## 5. ETL 시 필수 정제 규칙

`dataset_spec.md §6` 갭 반영:

1. **집계**: 30Hz CSV → 1분 버킷 `[bucket_ts, bucket_ts+1min)` avg/min/max 계산
2. **에너지**: `energy_wh = Σ(active_power × dt)`, dt≈33.333ms (샘플 간격)
3. `sampling_frequency = "30Hz"` → 시스템 상수 전제, DB 미저장
4. `type = "type_1" | "type4" | "main power"` → `appliance_types.nilm_type SMALLINT` 로 정규화 (main=NULL)
5. `temperature, humidity, windchill` 문자열 → `NUMERIC` 변환, 파싱 실패 시 NULL
6. `extra_appliances` 배열 원소 `strip()` 적용
7. `power_consumption = "unknown"` → NULL
8. `energy_efficiency = "unknown"` → NULL
9. `weather = ""` → NULL
10. CSV `voltage_phase`, `current_phase` 컬럼은 집계 시 drop
    (voltage_phase=0 상수, current_phase==phase_difference 동일)
11. `labels.active_inactive` 구간 배열은 **초 정밀도 그대로** `activity_intervals` 삽입

## 6. 향후 확장 여지

| 기능 | 예상 추가 위치 |
|------|---------------|
| 1일 집계 추가 계층 (월간 리포트 가속) | `power_1day` cagg — `power_1hour` 에서 파생 |
| 이상 이벤트 고해상도 윈도우 | 별도 hypertable (현재 연기) |
| 이상탐지 결과 (REQ-002) | `anomaly_events` 신규 테이블 (후속 PR) |
| DR 감축 실적 (REQ-005) | `dr_events`, `dr_results` 신규 테이블 (후속 PR) |
| `appliance_status_codes` seed 적재 | 모델 팀 상태 세트 확정 후 마이그레이션 |
| `appliance_status_intervals` 컬럼 추가 | TDA feature 메타 / transition_reason 등 — 모델 초기 결과 확인 후 `ALTER TABLE` |
| 실시간 알림 백엔드 | 초기 `pg_notify`/`LISTEN`, 부하 가시화 시 Kafka/Redis Streams |
| B2B 지역 집계 (REQ-009) | 지역 차원 추가 or 별도 집계 hypertable |
| 사용자 계정/인증 (REQ-007) | `users`, `oauth_tokens` 별도 도메인 |

## 7. 미결 사항

- [ ] `docs/context/architecture.md` 의 데이터 레이어 섹션 갱신 — **docs 브랜치 후속 PR 필요**
- [ ] `docs/context/decisions.md` 에 ADR-001(스토리지 선택·30Hz 비저장 정책) 추가 — 동일 사유로 docs 브랜치에서
- [ ] `Database/CLAUDE.md` 의 "핵심 테이블" 섹션을 NILM 테이블로 교체 (현재 워크플로우 엔진 템플릿 잔존)
- [ ] 압축/보존 정책 migration SQL 분리 (`migrations/20260421_compression_policy.sql`)
- [ ] ETL 스크립트(`scripts/ingest_aihub.py`) — CSV/JSON → 1분 집계 → DB 로딩
