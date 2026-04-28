-- ax_nilm — P0 1.3 + 1.4 + 1.5 DR(수요반응) 테이블 신규
-- 의존:
--   * 20260426_01_add_aggregators.sql (settlement_rate 참조)
--   * 20260426_02_extend_households.sql (households.dr_enrolled / aggregator_id)
--   * schemas/001_core_tables.sql (households, household_channels, appliance_types)
--
-- 구성:
--   * dr_events             — KPX 발행 DR 이벤트 헤더
--   * dr_results            — 가구별 정산 결과 (KPX UC-2 calc_savings 출력)
--   * dr_appliance_savings  — 채널별 분해 (UI 표시 전용, KPX 정산은 ch01 기준)
--
-- KPX 호환:
--   src/settlement/calculator.py 의 AggregatorRepository.get_settlement_rate
--   가 dr_results.settlement_rate 의 단가를 결정 (이벤트 시점 스냅샷 보관).

BEGIN;

-- ─── 1.3 DR 이벤트 ──────────────────────────────────────────────────────
-- KPX 가 발행. event_id 는 KPX 가 발급한 식별자를 그대로 사용.
CREATE TABLE dr_events (
    event_id     TEXT        PRIMARY KEY,
    start_ts     TIMESTAMPTZ NOT NULL,
    end_ts       TIMESTAMPTZ NOT NULL,
    target_kw    DOUBLE PRECISION NOT NULL,
    issued_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status       TEXT        NOT NULL DEFAULT 'pending',

    CHECK (start_ts < end_ts),
    CHECK (target_kw > 0),
    CHECK (status IN ('pending', 'active', 'completed', 'cancelled'))
);

CREATE INDEX idx_dr_events_status_time
    ON dr_events(status, start_ts DESC);

COMMENT ON TABLE dr_events IS
    'KPX 발행 DR(수요반응) 이벤트 헤더. status 전이: pending → active → completed. cancelled 는 KPX 취소 시.';
COMMENT ON COLUMN dr_events.target_kw IS
    'KPX 가 요청한 목표 감축량 (kW).';

-- ─── 1.4 DR 가구 정산 결과 ──────────────────────────────────────────────
-- KPX UC-2 calc_savings 출력. (event_id, household_id) 로 단일 행.
-- settlement_rate 는 이벤트 시점 단가 스냅샷 — 추후 aggregators.settlement_rate
-- 가 갱신되어도 정산 기록은 불변.
CREATE TABLE dr_results (
    event_id        TEXT             NOT NULL REFERENCES dr_events(event_id) ON DELETE CASCADE,
    household_id    TEXT             NOT NULL REFERENCES households(household_id) ON DELETE CASCADE,
    cbl_kwh         DOUBLE PRECISION NOT NULL,
    actual_kwh      DOUBLE PRECISION NOT NULL,
    savings_kwh     DOUBLE PRECISION NOT NULL,
    refund_krw      INTEGER          NOT NULL,
    settlement_rate DOUBLE PRECISION NOT NULL,
    cbl_method      TEXT             NOT NULL,
    created_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW(),

    PRIMARY KEY (event_id, household_id),

    CHECK (cbl_kwh        >= 0),
    CHECK (actual_kwh     >= 0),
    CHECK (settlement_rate > 0),
    CHECK (cbl_method IN ('mid_6_10', 'proxy_cluster'))
);

CREATE INDEX idx_dr_results_household
    ON dr_results(household_id, created_at DESC);

COMMENT ON TABLE dr_results IS
    'KPX UC-2 calc_savings 출력. settlement_rate 는 이벤트 시점 스냅샷 (불변).';
COMMENT ON COLUMN dr_results.cbl_method IS
    'CBL 산정 방식. mid_6_10 = 표준 (직전 10영업일 중 상하위 제외 평균). '
    'proxy_cluster = 데이터 부족 시 동일 cluster_label 가구 평균 사용.';
COMMENT ON COLUMN dr_results.refund_krw IS
    '환급액 (원, 정수). savings_kwh × settlement_rate 반올림.';

-- ─── 1.5 DR 채널별 절감 분해 (UI 표시 전용) ─────────────────────────────
-- KPX 정산은 ch01(분전반) 기준이지만, 사용자 화면에서는 가전별 기여도를 표시.
-- household_channels FK 로 (household_id, channel_num) 의 유효성 보장.
-- appliance_code 는 household_channels 에서 도출 가능하지만 KPX 모듈
-- (src/settlement/appliance.py) 호환을 위해 컬럼으로 비정규화 보관.
CREATE TABLE dr_appliance_savings (
    event_id            TEXT             NOT NULL,
    household_id        TEXT             NOT NULL,
    channel_num         SMALLINT         NOT NULL,
    appliance_code      TEXT             NOT NULL REFERENCES appliance_types(appliance_code),
    channel_cbl_kwh     DOUBLE PRECISION NOT NULL,
    channel_actual_kwh  DOUBLE PRECISION NOT NULL,
    channel_savings_kwh DOUBLE PRECISION NOT NULL,

    PRIMARY KEY (event_id, household_id, channel_num),

    FOREIGN KEY (event_id, household_id)
        REFERENCES dr_results(event_id, household_id) ON DELETE CASCADE,
    FOREIGN KEY (household_id, channel_num)
        REFERENCES household_channels(household_id, channel_num) ON DELETE CASCADE,

    CHECK (channel_num BETWEEN 1 AND 23),
    CHECK (channel_cbl_kwh    >= 0),
    CHECK (channel_actual_kwh >= 0)
);

CREATE INDEX idx_dr_appliance_savings_household
    ON dr_appliance_savings(household_id, event_id);

COMMENT ON TABLE dr_appliance_savings IS
    'DR 절감의 채널별 분해 — UI 표시 전용. KPX 정산 자체는 dr_results 의 ch01 기준값.';
COMMENT ON COLUMN dr_appliance_savings.appliance_code IS
    'household_channels 에서 도출 가능하지만 KPX appliance.py 모듈 호환을 위해 비정규화 보관.';

COMMIT;
