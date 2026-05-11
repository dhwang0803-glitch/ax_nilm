-- ============================================================================
-- 시연용 timestamp shift 후 power_1hour cagg 재 refresh
-- ============================================================================
-- 동기:
--   migrations/20260510_11 가 power_1min 의 모든 행을 +911 일 shift (INSERT 신규 +
--   원본 chunk drop). cagg `power_1hour` 는 invalidation log 가 자동 등록되지만
--   policy refresh 까지 갭이 생긴다. 시연 직전에는 명시적으로 전체 refresh.
--
-- 권한:
--   `power_1hour` continuous aggregate 의 owner = postgres → ax_nilm_app 으로 호출 불가.
--   반드시 `sudo -u postgres psql -d ax_nilm -f /tmp/20260510_12_*.sql` 패턴 (Phase B-7,
--   migrations/20260427_08_*, 20260430_10_* 와 동일).
--
-- 시간:
--   124,992 행 규모 cagg 전체 refresh 는 수 분 내 완료 예상.
-- ============================================================================

-- pre-check (적용 가능 여부)
SELECT view_name, materialization_hypertable_name
  FROM timescaledb_information.continuous_aggregates
 WHERE view_name = 'power_1hour';

-- shift 결과 power_1min 범위 확인 (참고용)
SELECT count(*) AS power_1min_rows,
       min(bucket_ts) AS min_ts,
       max(bucket_ts) AS max_ts
  FROM power_1min;

-- 전체 refresh (NULL,NULL = 전 구간)
CALL refresh_continuous_aggregate('power_1hour', NULL, NULL);

-- post-check
SELECT count(*) AS power_1hour_rows,
       min(hour_bucket) AS min_ts,
       max(hour_bucket) AS max_ts
  FROM power_1hour;

DO $$
DECLARE
    v_count BIGINT;
    v_min   TIMESTAMPTZ;
BEGIN
    SELECT count(*), min(hour_bucket) INTO v_count, v_min FROM power_1hour;
    IF v_count = 0 THEN
        RAISE EXCEPTION 'cagg refresh fail: power_1hour empty';
    END IF;
    IF v_min < '2024-01-01'::timestamptz THEN
        RAISE EXCEPTION 'cagg refresh fail: power_1hour still has 2023 rows (min=%)', v_min;
    END IF;
END $$;
