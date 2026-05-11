-- PoC: power_1min hypertable 의 partitioning column (bucket_ts) UPDATE 가능 여부 확인
-- 1행만 +911일 shift 후 즉시 ROLLBACK. 데이터 변경 없음.
-- 실행: sudo -u postgres psql -d ax_nilm -f /tmp/poc_shift_one_row.sql

\echo '== before =='
SELECT household_id, channel_num, bucket_ts
  FROM power_1min
 ORDER BY bucket_ts
 LIMIT 1;

BEGIN;

\echo '== UPDATE 1 row +911 days =='
WITH target AS (
    SELECT household_id, channel_num, bucket_ts
      FROM power_1min
     ORDER BY bucket_ts
     LIMIT 1
)
UPDATE power_1min p
   SET bucket_ts = p.bucket_ts + INTERVAL '911 days'
  FROM target
 WHERE p.household_id = target.household_id
   AND p.channel_num  = target.channel_num
   AND p.bucket_ts    = target.bucket_ts;

\echo '== after (within tx) =='
SELECT household_id, channel_num, bucket_ts
  FROM power_1min
 WHERE household_id = (SELECT household_id FROM power_1min ORDER BY bucket_ts LIMIT 1)
   AND channel_num  = 1
 ORDER BY bucket_ts
 LIMIT 3;

ROLLBACK;

\echo '== after rollback =='
SELECT household_id, channel_num, bucket_ts
  FROM power_1min
 ORDER BY bucket_ts
 LIMIT 1;
