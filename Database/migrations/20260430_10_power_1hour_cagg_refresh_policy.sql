-- ax_nilm — power_1hour cagg 첫 수동 refresh + 자동 정책 등록
--
-- 배경
--   schemas/002_timeseries_tables.sql 의 cagg 정의는 WITH NO DATA (line 164) 로 생성되어
--   비어 있는 상태이고, add_continuous_aggregate_policy 호출은 같은 파일 line 181~ 에
--   주석으로만 남아 있어 자동 refresh 가 동작하지 않았다. 결과적으로 power_1min 에
--   7,499,520 행이 적재돼 있어도 power_1hour 는 0 행.
--
-- 본 마이그레이션
--   1) 전체 범위 수동 refresh — NULL, NULL = (-infinity, +infinity)
--   2) 자동 refresh 정책 등록 — 30일 lookback / 2h end_offset / 1h schedule
--      (schemas/002 line 181~ 의 주석 정책과 동일 파라미터)
--
-- retention policy 는 본 마이그레이션에서 적용하지 않는다.
--   시연용 2023년 power_1min 7.5M 행 보존 필요. 별도 메모리
--   project_db_demo_data_plan_2026_04_30 §주의사항 참조. shift 작업 후 별도 마이그레이션.
--
-- 트랜잭션 정책
--   refresh_continuous_aggregate 는 TimescaleDB 제약상 BEGIN 블록 내부 호출 불가
--   (내부적으로 자체 트랜잭션 관리). add_continuous_aggregate_policy 는 일반 함수라
--   트랜잭션 내부 가능. psql 기본 자동커밋 모드 가정 (각 문장 = 독립 트랜잭션).
--
-- 검증
--   SELECT count(*) FROM power_1hour;
--     -- 0 → 수만~수십만 (7.5M / 60 ÷ 채널·가구 분포)
--   SELECT job_id, application_name, schedule_interval
--     FROM timescaledb_information.jobs
--    WHERE proc_name = 'policy_refresh_continuous_aggregate'
--      AND hypertable_name = '_materialized_hypertable_X';
--     -- 1 job 등록 확인 (X 는 cagg 의 내부 hypertable id)


-- 1) 첫 수동 refresh ────────────────────────────────────────────────
CALL refresh_continuous_aggregate('power_1hour', NULL, NULL);


-- 2) 자동 refresh 정책 등록 ──────────────────────────────────────────
SELECT add_continuous_aggregate_policy(
    'power_1hour',
    start_offset      => INTERVAL '30 days',
    end_offset        => INTERVAL '2 hours',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists     => TRUE
);


-- 3) 검증 — 행 수 0 이면 RAISE ───────────────────────────────────────
DO $$
DECLARE
    row_count BIGINT;
    job_count INTEGER;
BEGIN
    SELECT count(*) INTO row_count FROM power_1hour;
    IF row_count = 0 THEN
        RAISE EXCEPTION
            'power_1hour 가 여전히 비어 있음. refresh 실패 또는 power_1min 미적재 의심.';
    END IF;

    SELECT count(*) INTO job_count
      FROM timescaledb_information.jobs
     WHERE proc_name = 'policy_refresh_continuous_aggregate';
    IF job_count = 0 THEN
        RAISE EXCEPTION 'add_continuous_aggregate_policy 미등록.';
    END IF;

    RAISE NOTICE 'power_1hour rows = %, refresh policy jobs = %',
        row_count, job_count;
END $$;
