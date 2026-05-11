-- ax_nilm — NILM 추론 결과 테이블
-- 전제: 001_core_tables.sql, 002_timeseries_tables.sql 선행 적용
--
-- 목적:
--   CNN+TDA 하이브리드 NILM 모델의 출력을 구간(interval) 단위로 저장.
--   각 행 = 한 상태가 유지되는 시간 범위. 상태 전환 시점이 곧 이벤트 타임스탬프.
--
-- activity_intervals 와의 관계:
--   * activity_intervals         — AI Hub 제공 라벨 (ground truth, 학습/평가용)
--   * appliance_status_intervals — 우리 모델 출력 (실서비스 + 이상탐지 입력)
--   두 테이블은 동일 (household_id, channel_num, 시간범위) 단위로 JOIN 하여
--   IoU / precision / recall / F1 평가에 사용.
--
-- 상세 스펙: Database/docs/model_interface.md

BEGIN;

-- ─── 상태 코드 마스터 ──────────────────────────────────────────────────
-- CNN+TDA 모델이 출력하는 status_code 의 의미 정의.
-- 초기 PR 에는 seed 데이터 없이 빈 테이블로만 생성 — 모델 팀이 초기 모델 실행
-- 결과를 바탕으로 상태 세트를 제안하면 후속 마이그레이션에서 seed INSERT.
CREATE TABLE appliance_status_codes (
    status_code    SMALLINT    PRIMARY KEY,
    label_en       TEXT        NOT NULL,
    label_ko       TEXT,
    appliance_code TEXT        REFERENCES appliance_types(appliance_code),
    description    TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE appliance_status_codes IS
    'CNN+TDA NILM 모델의 status_code 의미 정의 마스터. '
    'appliance_code NULL = 범용 상태 (off/standby/active/peak). '
    'appliance_code 값 있음 = 특정 가전 전용 상태 (세탁기 wash/rinse/spin 등). '
    '코드 범위 가이드: 0-9 범용 / 10-19 Type2 가전 / 20-29 Type4 주기성 / 30-99 예약.';

-- ─── NILM 모델 출력 — 구간 기반 ────────────────────────────────────────
-- 각 INSERT = 한 번의 상태 전환 이벤트 발행.
-- 진행 중 구간은 end_ts = NULL. 다음 전환 시 UPDATE 로 end_ts 채움 + 새 행 INSERT
-- 을 단일 트랜잭션으로 수행 (Repository 가 보장).
CREATE TABLE appliance_status_intervals (
    id             BIGSERIAL   PRIMARY KEY,
    household_id   TEXT        NOT NULL,
    channel_num    SMALLINT    NOT NULL,
    start_ts       TIMESTAMPTZ NOT NULL,
    end_ts         TIMESTAMPTZ,
    status_code    SMALLINT    NOT NULL REFERENCES appliance_status_codes(status_code),
    confidence     REAL,
    model_version  TEXT        NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (end_ts IS NULL OR start_ts < end_ts),
    CHECK (confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0),
    CHECK (channel_num BETWEEN 1 AND 23),

    FOREIGN KEY (household_id, channel_num)
        REFERENCES household_channels(household_id, channel_num) ON DELETE CASCADE,

    -- 동일 (가구, 채널, 모델버전) 에서 두 열린/닫힌 구간의 시간 겹침 차단.
    -- end_ts NULL 인 "진행 중" 구간도 COALESCE('infinity') 로 겹침 판정에 포함.
    EXCLUDE USING gist (
        household_id  WITH =,
        channel_num   WITH =,
        model_version WITH =,
        tstzrange(start_ts, COALESCE(end_ts, 'infinity'), '[)') WITH &&
    )
);

-- 현재 진행 중 구간 = "지금 상태" O(log N) 조회 (partial index)
CREATE INDEX idx_status_open
    ON appliance_status_intervals (household_id, channel_num, model_version)
    WHERE end_ts IS NULL;

-- 전환 히스토리 / 시간대별 패턴 조회
CREATE INDEX idx_status_history
    ON appliance_status_intervals (household_id, channel_num, start_ts DESC);

-- 모델 버전별 평가 조회 (A/B 비교)
CREATE INDEX idx_status_by_model
    ON appliance_status_intervals (model_version, household_id, channel_num, start_ts);

COMMENT ON TABLE appliance_status_intervals IS
    'CNN+TDA NILM 모델의 가전 상태 출력 — 구간 기반. '
    'INSERT 시점이 곧 상태 전환 이벤트. '
    'activity_intervals (AI Hub ground truth) 와 쌍을 이뤄 평가 및 이상탐지 입력으로 사용.';
COMMENT ON COLUMN appliance_status_intervals.end_ts IS
    'NULL = 현재 진행 중인 구간. 다음 전환 시 UPDATE 로 채움.';
COMMENT ON COLUMN appliance_status_intervals.confidence IS
    '모델 신뢰도 [0.0, 1.0]. 이상탐지 집계는 confidence >= 0.6 만 사용 (REQ-001). '
    '임계값은 초기 모델 분포 확인 후 재조정 가능.';
COMMENT ON COLUMN appliance_status_intervals.model_version IS
    '예: cnn_tda_v1.0.0. 동일 (가구, 채널, 기간) 에 여러 model_version 공존 허용 (A/B 평가).';

COMMIT;
