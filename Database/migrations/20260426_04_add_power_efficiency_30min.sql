-- ax_nilm — P0 1.6 power_efficiency_30min 신규 (Database 브랜치 자체 요청)
-- 의존:
--   * 20260426_03_add_dr_tables.sql (event_id FK)
--   * schemas/001_core_tables.sql (household_channels FK)
--   * schemas/002_timeseries_tables.sql (TimescaleDB 확장 enable)
--
-- 목적:
--   KPX UC-2 calc_savings 가 매 호출마다 power_1min/power_1hour 를 반복 집계하지 않도록
--   30분 버킷 단위 사전 집계. 일반 30분 효율 패널 + DR 윈도우 절감 동시 보관.
--
-- 쓰기:
--   * 일반 1시간 주기 Celery 배치: is_dr_window=FALSE, event_id=NULL, savings_wh=0
--   * DR 이벤트 트리거 (status: pending→active 또는 completed): 해당 30분 버킷에
--     is_dr_window=TRUE, event_id=<DR id>, cbl_wh/savings_wh 채움
--
-- 읽기:
--   KPX UC-2 calc_savings 가 power_1min 직접 조회 대신 이 테이블만 사용.
--
-- 규모 (REQ-008 10K 가구 가정):
--   30min × 365일 × 23ch × 10K = 약 4.0e9 행/년 → hypertable 필수
--   초기 79가구 기준 ≈ 31M 행/년 (단일 chunk 로도 가능하나 향후 확장 일관성)

BEGIN;

CREATE TABLE power_efficiency_30min (
    bucket_ts      TIMESTAMPTZ      NOT NULL,
    household_id   TEXT             NOT NULL,
    channel_num    SMALLINT         NOT NULL,

    energy_wh      DOUBLE PRECISION NOT NULL,            -- 30분 실측 누적
    cbl_wh         DOUBLE PRECISION,                     -- DR 비교 기준 (CBL). 일반 구간 NULL
    savings_wh     DOUBLE PRECISION NOT NULL DEFAULT 0,  -- cbl_wh - energy_wh (음수 = 초과 사용)

    is_dr_window   BOOLEAN          NOT NULL DEFAULT FALSE,
    event_id       TEXT             REFERENCES dr_events(event_id) ON DELETE SET NULL,
    computed_at    TIMESTAMPTZ      NOT NULL DEFAULT NOW(),

    CHECK (channel_num BETWEEN 1 AND 23),
    CHECK (energy_wh >= 0),
    CHECK (cbl_wh IS NULL OR cbl_wh >= 0),
    -- DR 윈도우면 event_id 필수. 일반 구간이면 event_id NULL 강제.
    CHECK (
        (is_dr_window AND event_id IS NOT NULL)
        OR (NOT is_dr_window AND event_id IS NULL)
    ),

    FOREIGN KEY (household_id, channel_num)
        REFERENCES household_channels(household_id, channel_num) ON DELETE CASCADE
);

-- 하이퍼테이블 — power_1min 과 동일 패턴 (household_id 4파티션, 30일 chunk).
-- 30분 해상도라 chunk 당 행수가 작으므로 7일이 아닌 30일 채택.
SELECT create_hypertable(
    'power_efficiency_30min',
    'bucket_ts',
    partitioning_column   => 'household_id',
    number_partitions     => 4,
    chunk_time_interval   => INTERVAL '30 days',
    if_not_exists         => TRUE
);

-- 가장 빈번한 쿼리: (가구, 채널, 기간) 조회
CREATE UNIQUE INDEX idx_power_efficiency_30min_pk
    ON power_efficiency_30min (household_id, channel_num, bucket_ts);

CREATE INDEX idx_power_efficiency_30min_recent
    ON power_efficiency_30min (household_id, channel_num, bucket_ts DESC);

-- DR 이벤트별 정산 검증 (event_id → 모든 가구·채널 절감 합)
CREATE INDEX idx_power_efficiency_30min_event
    ON power_efficiency_30min (event_id, household_id, channel_num)
    WHERE is_dr_window;

COMMENT ON TABLE power_efficiency_30min IS
    '30분 버킷 사전 집계. KPX UC-2 calc_savings 가 power_1min 직접 조회 대신 사용. '
    'is_dr_window=FALSE 행은 일반 효율 패널, TRUE 행은 DR 정산 데이터.';
COMMENT ON COLUMN power_efficiency_30min.cbl_wh IS
    '해당 30분 구간의 CBL (Customer Baseline Load) — DR 윈도우에서만 산정. '
    '일반 구간은 NULL.';
COMMENT ON COLUMN power_efficiency_30min.savings_wh IS
    'cbl_wh - energy_wh. 일반 구간(cbl_wh NULL)에서는 0. 음수 = 초과 사용.';
COMMENT ON COLUMN power_efficiency_30min.event_id IS
    'is_dr_window=TRUE 일 때 해당 DR 이벤트 ID. 일반 구간 NULL. '
    'CHECK 제약으로 두 컬럼 정합성 강제.';

COMMIT;
