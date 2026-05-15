-- ax_nilm — appliance_status_intervals 에너지 컬럼 확장
-- 의존: schemas/004_nilm_inference_tables.sql
--
-- 목적:
--   NILM 엔진이 상태 전환 시 에너지 메트릭(energy_wh, avg_w, peak_w)도
--   함께 기록할 수 있도록 컬럼 추가.
--   기존 행은 NULL 유지 (NOT NULL 제약 없음).

BEGIN;

ALTER TABLE appliance_status_intervals
    ADD COLUMN energy_wh  NUMERIC(10,3),
    ADD COLUMN avg_w      NUMERIC(10,3),
    ADD COLUMN peak_w     NUMERIC(10,3);

COMMENT ON COLUMN appliance_status_intervals.energy_wh IS
    '해당 상태 구간의 총 소비 에너지 (Wh). end_ts 확정 시 UPDATE.';
COMMENT ON COLUMN appliance_status_intervals.avg_w IS
    '해당 상태 구간의 평균 유효전력 (W).';
COMMENT ON COLUMN appliance_status_intervals.peak_w IS
    '해당 상태 구간의 최대 순시전력 (W).';

COMMIT;
