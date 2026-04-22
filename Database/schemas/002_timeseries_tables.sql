-- ax_nilm — 시계열/라벨 테이블
-- 전제: 001_core_tables.sql 선행 적용
--
-- 정책:
--   * 30Hz 원시 데이터는 DB에 저장하지 않는다. NILM 엔진이 로컬 파일에서
--     직접 읽어 분해/이상탐지 한 뒤 폐기.
--   * DB에는 1분 집계만 저장 (avg/min/max + 누적 Wh).
--     - 분전반(ch01)과 AI Hub가 이미 가전별로 분리해 둔 ch02~ch23 를 동일
--       스키마(`power_1min`)로 함께 적재. 채널 의미는 `household_channels`
--       조인으로 해석.
--   * 축적 메타데이터(가구 속성/가전 속성/날씨)는 `households`,
--     `household_channels`, `household_pii`, `household_daily_env` 에 이미
--     정규화 저장되어 있음 → `power_1min` 은 측정값만 보관, 조회 시 조인.

BEGIN;

-- ─── 1분 집계 전력 측정 ───────────────────────────────────────────────
-- 원천: AI Hub 71685 30Hz CSV → ETL 단계에서 1분 버킷으로 집계.
-- 규모: 1채널/일 2,592,000 rows → 1,440 rows (1,800× 축소).
-- 버킷 규칙: [bucket_ts, bucket_ts + 1min). bucket_ts 는 00, 01, 02... 분 시작.
CREATE TABLE power_1min (
    bucket_ts              TIMESTAMPTZ NOT NULL,
    household_id           TEXT NOT NULL,
    channel_num            SMALLINT NOT NULL,

    -- 유효전력 집계 (분해/이상탐지의 주 신호)
    active_power_avg       DOUBLE PRECISION,
    active_power_min       DOUBLE PRECISION,
    active_power_max       DOUBLE PRECISION,
    energy_wh              DOUBLE PRECISION,   -- 1분간 누적 소비전력량 (Wh)

    -- 나머지 전기적 특성 평균치 (피크/밸리는 분석 수요 없을 때까지 보류)
    voltage_avg            DOUBLE PRECISION,
    current_avg            DOUBLE PRECISION,
    frequency_avg          DOUBLE PRECISION,
    apparent_power_avg     DOUBLE PRECISION,
    reactive_power_avg     DOUBLE PRECISION,
    power_factor_avg       DOUBLE PRECISION,
    phase_difference_avg   DOUBLE PRECISION,

    sample_count           INTEGER,            -- 정상 적재 시 1,800

    CHECK (channel_num BETWEEN 1 AND 23),
    CHECK (power_factor_avg IS NULL OR power_factor_avg BETWEEN 0 AND 1),
    CHECK (sample_count IS NULL OR sample_count BETWEEN 0 AND 1800)
);

-- 하이퍼테이블: 시간 7일 청크 + household_id 해시 공간 분할 4
-- (30Hz 시절 1일 청크 대비 축소되어 chunk 당 행 수가 훨씬 작음 → 7일로 병합)
SELECT create_hypertable(
    'power_1min',
    'bucket_ts',
    partitioning_column   => 'household_id',
    number_partitions     => 4,
    chunk_time_interval   => INTERVAL '7 days',
    if_not_exists         => TRUE
);

CREATE UNIQUE INDEX idx_power_1min_pk
    ON power_1min (household_id, channel_num, bucket_ts);

-- 대시보드 쿼리: 최근 데이터 우선
CREATE INDEX idx_power_1min_recent
    ON power_1min (household_id, channel_num, bucket_ts DESC);

COMMENT ON TABLE power_1min IS
    '1분 집계 전력 측정 — 30Hz 원시 데이터는 NILM 엔진 내부에서만 처리, DB 비저장.';
COMMENT ON COLUMN power_1min.channel_num IS
    '1=분전반(mains), 2~23=AI Hub 제공 가전별 분리 채널. household_channels 조인으로 해석.';
COMMENT ON COLUMN power_1min.energy_wh IS
    '해당 1분 구간의 누적 소비전력량 (Wh). ETL 단계에서 active_power × dt 적분.';

-- ─── 가전 활성 구간 라벨 ───────────────────────────────────────────────
-- JSON labels.active_inactive 배열 원소를 행 단위로 저장.
-- 의미: 해당 시간대에 가전이 ON 상태. 암묵적 여집합이 OFF.
-- 라벨은 1분 버킷과 독립적으로 초 단위 정밀도 유지 (NILM 평가/학습용).
CREATE TABLE activity_intervals (
    id                 BIGSERIAL PRIMARY KEY,
    household_id       TEXT NOT NULL,
    channel_num        SMALLINT NOT NULL,
    start_ts           TIMESTAMPTZ NOT NULL,
    end_ts             TIMESTAMPTZ NOT NULL,
    source             TEXT NOT NULL DEFAULT 'aihub_71685',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (start_ts < end_ts),
    FOREIGN KEY (household_id, channel_num)
        REFERENCES household_channels(household_id, channel_num) ON DELETE CASCADE,
    EXCLUDE USING gist (
        household_id WITH =,
        channel_num  WITH =,
        tstzrange(start_ts, end_ts, '[]') WITH &&
    )
);

CREATE INDEX idx_activity_intervals_lookup
    ON activity_intervals (household_id, channel_num, start_ts);

COMMENT ON COLUMN activity_intervals.source IS
    '라벨 출처 (예: aihub_71685, human_annotator_v2, model_unet_nilm_v1). '
    'NILM 엔진 출력도 동일 테이블에 저장 가능하지만 현 정책상 평가용 비교만 수행 — 미적재.';

-- ─── 파일 수집 이력 ────────────────────────────────────────────────────
-- ETL 단계에서 CSV(30Hz 원천) + JSON(라벨/메타) 1쌍 처리마다 1행 기록.
-- 중복 적재 방지 및 집계 품질 추적용.
CREATE TABLE ingestion_log (
    id                 BIGSERIAL PRIMARY KEY,
    source_file        TEXT NOT NULL,
    household_id       TEXT NOT NULL,
    channel_num        SMALLINT NOT NULL,
    file_date          DATE NOT NULL,
    raw_row_count      BIGINT,            -- CSV 원행 수 (정상 2,592,000)
    agg_row_count      BIGINT,            -- power_1min 에 적재된 행 수 (정상 1,440)
    intervals_count    INTEGER,           -- activity_intervals 에 적재된 구간 수
    ingested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status             TEXT NOT NULL DEFAULT 'ok',
    notes              TEXT,
    CHECK (status IN ('ok', 'partial', 'failed', 'skipped'))
);

CREATE UNIQUE INDEX uq_ingestion_log_file ON ingestion_log(source_file);
CREATE INDEX idx_ingestion_log_lookup
    ON ingestion_log(household_id, channel_num, file_date);

COMMIT;

-- ─── 1시간 다운샘플 연속집계 (Continuous Aggregate) ─────────────────────
-- 정책:
--   * 최근 7일: power_1min 에 1분 해상도로 보관 (hot tier)
--   * 7일 이상: power_1hour 에 1시간 해상도로 보관 (cold tier, 1분 원본은 retention 으로 삭제)
-- 1일 집계가 아닌 1시간 집계를 택한 이유: 시간대별 이상탐지 패턴
-- (예: "가구A가 평소 08~10시에 B 가전 사용") 을 cold tier 에서도 유지해야 하므로
-- REQ-002 (이상탐지) 요건상 24× 더 높은 해상도가 필요. 전구간 1시간 보관해도
-- ~120 MB 수준으로 저장 부담은 여전히 작음.
--
-- 집계 규칙(1분 → 1시간)은 30Hz → 1분 때와 동일한 방식:
--   * active_power     : avg = avg(avg),  min = min(min),  max = max(max)
--   * energy_wh        : sum (1시간 누적 Wh)
--   * 나머지 전기 특성 : avg(avg) (1분 버킷당 sample_count 가 거의 균일하므로 단순 평균으로 근사)
--   * sample_count     : sum (1시간 원시 샘플 수, 정상 30Hz × 3,600s = 108,000)
--
-- CAUTION: Continuous aggregate 는 트랜잭션 블록 외부에서 생성해야 함 (Timescale 제약).

CREATE MATERIALIZED VIEW power_1hour
WITH (timescaledb.continuous) AS
SELECT
    time_bucket(INTERVAL '1 hour', bucket_ts)         AS hour_bucket,
    household_id,
    channel_num,
    avg(active_power_avg)                             AS active_power_avg,
    min(active_power_min)                             AS active_power_min,
    max(active_power_max)                             AS active_power_max,
    sum(energy_wh)                                    AS energy_wh,
    avg(voltage_avg)                                  AS voltage_avg,
    avg(current_avg)                                  AS current_avg,
    avg(frequency_avg)                                AS frequency_avg,
    avg(apparent_power_avg)                           AS apparent_power_avg,
    avg(reactive_power_avg)                           AS reactive_power_avg,
    avg(power_factor_avg)                             AS power_factor_avg,
    avg(phase_difference_avg)                         AS phase_difference_avg,
    sum(sample_count)                                 AS sample_count,
    count(*)                                          AS minute_bucket_count  -- 정상 60
FROM power_1min
GROUP BY hour_bucket, household_id, channel_num
WITH NO DATA;

CREATE INDEX idx_power_1hour_lookup
    ON power_1hour (household_id, channel_num, hour_bucket DESC);

COMMENT ON MATERIALIZED VIEW power_1hour IS
    '1시간 다운샘플 연속집계 — 7일 이상 지난 데이터의 장기 저장 계층. '
    'power_1min 이 retention 으로 삭제되기 전 마지막 refresh 에서 스냅샷. '
    '시간대별 이상탐지 패턴 보존을 위해 1일이 아닌 1시간 해상도 채택 (REQ-002).';

-- ─── 리프레시 + 보존 정책 (수동 실행: migrations/ 또는 운영 스크립트) ──
--
-- 1) 연속집계 자동 리프레시:
--    - start_offset 30d: 지난 30일 범위 재계산 (지각 도착 데이터 반영)
--    - end_offset 2h   : 최근 2시간 (미완성 시간 버킷) 제외
--    - schedule 1h     : 한 시간에 한 번 실행 (1시간 버킷이 채워지는 대로 반영)
--
-- SELECT add_continuous_aggregate_policy('power_1hour',
--     start_offset       => INTERVAL '30 days',
--     end_offset         => INTERVAL '2 hours',
--     schedule_interval  => INTERVAL '1 hour');
--
-- 2) hot tier retention: 7일 이상 지난 1분 chunk 삭제.
--    순서 중요: cagg 가 해당 범위를 이미 refresh 한 상태에서 retention 실행.
--    (1) 이 시간 단위로 돌고 (2) 는 7일 경계에서 drop → cagg 에는 이미 반영 완료.
--
-- SELECT add_retention_policy('power_1min', INTERVAL '7 days');
--
-- 3) (선택) power_1hour 자체 압축 — 1년 이상 지난 chunk:
--    ALTER MATERIALIZED VIEW power_1hour SET (
--        timescaledb.compress = true,
--        timescaledb.compress_segmentby = 'household_id, channel_num'
--    );
--    SELECT add_compression_policy('power_1hour', INTERVAL '365 days');
