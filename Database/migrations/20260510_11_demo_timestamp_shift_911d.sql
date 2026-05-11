-- ============================================================================
-- 시연용 timestamp shift +911 일 (시연 시점 2026-05-15)
-- ============================================================================
-- 동기:
--   실측 power_1min 은 2023-09-27 ~ 2023-11-15 (50 일) 만 존재.
--   공모전 시연 시점 (2026-05-15) 의 "현재" 와 정합되도록 모든 시계열을 +911 일 이동.
--   shift 폭 911 일 = 2026-05-14 - 2023-11-15 (실측 끝 → 시연 - 1 일 정렬).
--
-- 영향 범위 (점검 후 확정):
--   power_1min            7,499,520 행  shift   2023-09-27 ~ 2023-11-15  → 2026-03-26 ~ 2026-05-14 UTC
--   household_daily_env       2,449 행  shift   2023-09-22 ~ 2023-12-17  → 2026-03-21 ~ 2026-06-16
--   power_1hour            124,992 행  cagg     본 마이그레이션 적용 후 별도 sudo 스크립트로 재 refresh
--   ingestion_log                 0 행  skip
--   activity_intervals            0 행  skip
--   appliance_status_intervals   12 행  skip    (이미 2026-04 범위, 테스트 데이터)
--   dr_events / dr_results / power_efficiency_30min  0 행  skip
--
-- 처리 패턴:
--   power_1min 은 hypertable. partitioning column UPDATE 는 chunk constraint 위반 →
--   INSERT shifted (새 chunk 자동 생성) + drop_chunks (원본 chunk 통째 drop) 로 우회.
--   PoC 검증 (1 chunk, 82,620 행, ~1.4 s INSERT + 33 ms drop) 완료.
--   본 적용 추정 ~2 분 INSERT + ~0.7 s drop, 단일 트랜잭션 atomic.
--
-- 권한:
--   본 SQL 의 INSERT/UPDATE/DELETE 는 ax_nilm_app 권한으로 실행 가능해야 한다.
--   power_1hour cagg 재 refresh 는 owner=postgres → 별도 스크립트
--   (`migrations/20260510_12_power_1hour_cagg_refresh.sql` + sudo -u postgres) 로 분리.
--
-- 가역성:
--   롤백 시 INTERVAL '-911 days' 동일 패턴으로 역방향 마이그레이션 발행 가능.
-- ============================================================================

-- pre-check ------------------------------------------------------------------
DO $$
DECLARE
    v_count   BIGINT;
    v_min_ts  TIMESTAMPTZ;
    v_max_ts  TIMESTAMPTZ;
BEGIN
    SELECT count(*), min(bucket_ts), max(bucket_ts)
      INTO v_count, v_min_ts, v_max_ts
      FROM power_1min;
    IF v_count <> 7499520 THEN
        RAISE EXCEPTION 'pre-check fail: power_1min row count = %, expected 7499520', v_count;
    END IF;
    IF v_min_ts <> '2023-09-27 15:00:00+00'::timestamptz THEN
        RAISE EXCEPTION 'pre-check fail: power_1min min = %, expected 2023-09-27 15:00:00+00', v_min_ts;
    END IF;
    IF v_max_ts <> '2023-11-15 14:59:00+00'::timestamptz THEN
        RAISE EXCEPTION 'pre-check fail: power_1min max = %, expected 2023-11-15 14:59:00+00', v_max_ts;
    END IF;
END $$;

BEGIN;

-- 1. power_1min : shifted 행 INSERT (새 chunk 자동 생성)
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
 WHERE bucket_ts < '2024-01-01'::timestamptz;  -- 2023 원본만 대상 (재실행 안전)

-- 2. 원본 chunk (2023 년) 통째 drop. shifted (2026 년) 은 영향 없음.
SELECT drop_chunks('power_1min', older_than => '2024-01-01'::timestamptz);

-- 3. household_daily_env : DATE 컬럼 UPDATE (hypertable 아님, PK 충돌 없음)
UPDATE household_daily_env
   SET observed_date = observed_date + INTERVAL '911 days'
 WHERE observed_date < '2024-01-01'::date;  -- 2023 원본만 대상 (재실행 안전)

-- post-check -----------------------------------------------------------------
DO $$
DECLARE
    v_count   BIGINT;
    v_min_ts  TIMESTAMPTZ;
    v_max_ts  TIMESTAMPTZ;
BEGIN
    SELECT count(*), min(bucket_ts), max(bucket_ts)
      INTO v_count, v_min_ts, v_max_ts
      FROM power_1min;
    IF v_count <> 7499520 THEN
        RAISE EXCEPTION 'post-check fail: power_1min row count = %, expected 7499520', v_count;
    END IF;
    IF v_min_ts <> '2026-03-26 15:00:00+00'::timestamptz THEN
        RAISE EXCEPTION 'post-check fail: power_1min min = %, expected 2026-03-26 15:00:00+00', v_min_ts;
    END IF;
    IF v_max_ts <> '2026-05-14 14:59:00+00'::timestamptz THEN
        RAISE EXCEPTION 'post-check fail: power_1min max = %, expected 2026-05-14 14:59:00+00', v_max_ts;
    END IF;
END $$;

DO $$
DECLARE
    v_count    BIGINT;
    v_min_d    DATE;
    v_max_d    DATE;
BEGIN
    SELECT count(*), min(observed_date), max(observed_date)
      INTO v_count, v_min_d, v_max_d
      FROM household_daily_env;
    IF v_count <> 2449 THEN
        RAISE EXCEPTION 'post-check fail: household_daily_env row count = %, expected 2449', v_count;
    END IF;
    IF v_min_d < '2024-01-01'::date THEN
        RAISE EXCEPTION 'post-check fail: household_daily_env min = %, still 2023', v_min_d;
    END IF;
END $$;

COMMIT;
