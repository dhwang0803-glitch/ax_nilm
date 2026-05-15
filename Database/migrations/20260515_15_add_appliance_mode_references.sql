-- ax_nilm — 가전 모드 레퍼런스 테이블
-- 의존: schemas/001_core_tables.sql (households, appliance_types)
--
-- 목적:
--   상태 모니터링 모델이 GCS long_term JSON 으로 출력하는
--   가전별 모드 프로파일(avg_energy_wh, avg_duration_min, sample_count)의
--   DB 사본. AI Agent 가 baseline 비교 시 GCS 조회 불가 시 폴백으로 사용.
--
-- long_term JSON 구조:
--   { "에어컨": { "modes": { "송풍": { "avg_energy_wh": 10.95, ... } } } }
--   → (household_id, appliance_code='AC', mode_name='송풍', ...)

BEGIN;

CREATE TABLE appliance_mode_references (
    id                    SERIAL       PRIMARY KEY,
    household_id          TEXT         NOT NULL REFERENCES households(household_id) ON DELETE CASCADE,
    appliance_code        TEXT         NOT NULL REFERENCES appliance_types(appliance_code),
    mode_name             TEXT         NOT NULL,
    avg_energy_wh         NUMERIC(10,3),
    avg_duration_min      NUMERIC(8,2),
    sample_count          INTEGER      NOT NULL DEFAULT 0,
    standby_avg_w         NUMERIC(8,3) DEFAULT 0,
    standby_avg_duration_min NUMERIC(8,2) DEFAULT 0,
    model_version         TEXT         NOT NULL DEFAULT 'tda-v1.0',
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    UNIQUE (household_id, appliance_code, mode_name, model_version)
);

CREATE INDEX idx_mode_ref_household
    ON appliance_mode_references (household_id, appliance_code);

COMMENT ON TABLE appliance_mode_references IS
    '가전별 모드 프로파일 레퍼런스. '
    'GCS long_term JSON 의 DB 사본으로, AI Agent baseline 비교에 사용. '
    'sample_count = 0 이면 스펙 기반 기본값, > 0 이면 실측 학습 통계.';

COMMIT;
