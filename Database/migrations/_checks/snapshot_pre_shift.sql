-- shift 전 timestamp 적재 현황 스냅샷
-- 실행: sudo -u postgres psql -d ax_nilm -f /tmp/snapshot_pre_shift.sql
\echo '== power_1min =='
SELECT count(*) AS rows,
       min(bucket_ts) AS min_ts,
       max(bucket_ts) AS max_ts,
       count(DISTINCT household_id) AS households,
       count(DISTINCT (household_id, channel_num)) AS pairs
  FROM power_1min;

\echo '== power_1hour (cagg) =='
SELECT count(*) AS rows,
       min(hour_bucket) AS min_ts,
       max(hour_bucket) AS max_ts
  FROM power_1hour;

\echo '== household_daily_env =='
SELECT count(*) AS rows,
       min(observed_date) AS min_d,
       max(observed_date) AS max_d
  FROM household_daily_env;

\echo '== ingestion_log =='
SELECT count(*) AS rows,
       min(file_date) AS min_d,
       max(file_date) AS max_d
  FROM ingestion_log;

\echo '== activity_intervals =='
SELECT count(*) AS rows,
       min(start_ts) AS min_ts,
       max(end_ts) AS max_ts
  FROM activity_intervals;

\echo '== appliance_status_intervals =='
SELECT count(*) AS rows,
       min(start_ts) AS min_ts,
       max(end_ts) AS max_ts
  FROM appliance_status_intervals;

\echo '== dr_events =='
SELECT count(*) AS rows,
       min(start_ts) AS min_ts,
       max(end_ts) AS max_ts
  FROM dr_events;

\echo '== dr_results =='
SELECT count(*) AS rows
  FROM dr_results;

\echo '== power_efficiency_30min =='
SELECT count(*) AS rows,
       min(bucket_ts) AS min_ts,
       max(bucket_ts) AS max_ts
  FROM power_efficiency_30min;

\echo '== power_1min hypertable chunks =='
SELECT count(*) AS chunk_count,
       min(range_start) AS min_chunk,
       max(range_end) AS max_chunk
  FROM timescaledb_information.chunks
 WHERE hypertable_name = 'power_1min';
