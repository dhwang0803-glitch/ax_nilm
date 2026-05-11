-- ax_nilm — ax_nilm_team PG 역할 권한 설계 (REQ-007 권한 분리 강화)
--
-- 목적:
--   팀원이 본인 모델 결과 테이블에만 INSERT/UPDATE/DELETE 가능,
--   시드/그라운드트루스/PII/raw power 는 SELECT-only 로 동결.
--
-- 사전조건: ax_nilm_team 역할이 이미 존재 — scripts/gcp/05_create_team_pg_role.sh
--          가 먼저 비밀번호 생성 + CREATE ROLE 수행.
--
-- 정책:
--   * 동결 (SELECT only): appliance_types, appliance_status_codes, aggregators,
--                          households, household_pii, household_channels,
--                          household_daily_env, activity_intervals,
--                          power_1min, power_1hour
--   * DML 가능: appliance_status_intervals, household_embeddings,
--               dr_events, dr_results, dr_appliance_savings, ingestion_log
--   * 향후 신규 테이블: default-deny (ALTER DEFAULT PRIVILEGES 사용 안 함).
--                       스키마 변경 시 본 마이그레이션 갱신 후 owner 가 재적용.

BEGIN;

-- ─── 0. 역할 존재 확인 ────────────────────────────────────────────
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ax_nilm_team') THEN
        RAISE EXCEPTION 'ax_nilm_team 역할이 없습니다. scripts/gcp/05_create_team_pg_role.sh 를 먼저 실행하세요.';
    END IF;
END $$;

-- ─── 1. 기존 권한 일괄 회수 (재실행 안전성) ──────────────────────
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ax_nilm_team;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM ax_nilm_team;
REVOKE ALL ON DATABASE ax_nilm FROM ax_nilm_team;

-- ─── 2. CONNECT + 스키마 USAGE ────────────────────────────────────
GRANT CONNECT ON DATABASE ax_nilm TO ax_nilm_team;
GRANT USAGE ON SCHEMA public TO ax_nilm_team;

-- ─── 3. SELECT — 모든 테이블/뷰 (분석/탐색 용) ────────────────────
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ax_nilm_team;

-- ─── 4. DML — 모델 결과 적재 테이블만 ────────────────────────────
GRANT INSERT, UPDATE, DELETE ON
    appliance_status_intervals,
    household_embeddings,
    dr_events,
    dr_results,
    dr_appliance_savings,
    ingestion_log
TO ax_nilm_team;

-- ─── 5. 시퀀스 — DML 가능 테이블의 BIGSERIAL 만 ──────────────────
GRANT USAGE, SELECT ON
    appliance_status_intervals_id_seq,
    ingestion_log_id_seq
TO ax_nilm_team;

-- ─── 6. 적용 결과 요약 (NOTICE) ──────────────────────────────────
DO $$
DECLARE
    v_select_count INT;
    v_insert_tables TEXT;
BEGIN
    SELECT count(DISTINCT table_name) INTO v_select_count
    FROM information_schema.role_table_grants
    WHERE grantee = 'ax_nilm_team' AND privilege_type = 'SELECT';

    SELECT string_agg(table_name, ', ' ORDER BY table_name) INTO v_insert_tables
    FROM information_schema.role_table_grants
    WHERE grantee = 'ax_nilm_team' AND privilege_type = 'INSERT';

    RAISE NOTICE 'ax_nilm_team SELECT on % tables', v_select_count;
    RAISE NOTICE 'ax_nilm_team DML on: %', v_insert_tables;
END $$;

COMMIT;
