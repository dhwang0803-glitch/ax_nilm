-- PoC 2: 가장 오래된 1 chunk 만 INSERT shifted + drop_chunks 트랜잭션 안 동작 검증
-- 트랜잭션 끝에서 ROLLBACK → 데이터 변경 없음
-- 실행: sudo -u postgres psql -d ax_nilm -f /tmp/poc_insert_drop_one_chunk.sql

\timing on

\echo '== before =='
SELECT count(*) AS total,
       count(*) FILTER (WHERE bucket_ts < '2023-10-01'::timestamptz) AS first_chunk_rows
  FROM power_1min;

BEGIN;

\echo '== INSERT shifted (first chunk) =='
INSERT INTO power_1min (
    bucket_ts, household_id, channel_num,
    active_power_avg, active_power_min, active_power_max, energy_wh,
    voltage_avg, current_avg, frequency_avg,
    apparent_power_avg, reactive_power_avg, power_factor_avg, phase_difference_avg,
    sample_count
)
SELECT bucket_ts + INTERVAL '911 days', household_id, channel_num,
       active_power_avg, active_power_min, active_power_max, energy_wh,
       voltage_avg, current_avg, frequency_avg,
       apparent_power_avg, reactive_power_avg, power_factor_avg, phase_difference_avg,
       sample_count
  FROM power_1min
 WHERE bucket_ts < '2023-10-01'::timestamptz;

\echo '== mid-tx counts =='
SELECT count(*) AS total,
       count(*) FILTER (WHERE bucket_ts >= '2026-01-01'::timestamptz) AS shifted_rows,
       count(*) FILTER (WHERE bucket_ts < '2023-10-01'::timestamptz) AS originals_remaining
  FROM power_1min;

\echo '== drop_chunks (originals) =='
SELECT drop_chunks('power_1min', older_than => '2023-10-01'::timestamptz);

\echo '== post-drop counts =='
SELECT count(*) AS total,
       count(*) FILTER (WHERE bucket_ts >= '2026-01-01'::timestamptz) AS shifted_rows,
       count(*) FILTER (WHERE bucket_ts < '2023-10-01'::timestamptz) AS originals_remaining,
       min(bucket_ts) AS min_ts,
       max(bucket_ts) AS max_ts
  FROM power_1min;

ROLLBACK;

\echo '== after ROLLBACK =='
SELECT count(*) AS total, min(bucket_ts) AS min_ts, max(bucket_ts) AS max_ts
  FROM power_1min;
