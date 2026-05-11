-- ax_nilm — power_1hour COMMENT 누락 보정
--
-- 배경
--   schemas/002_timeseries_tables.sql:169 에 ``COMMENT ON MATERIALIZED VIEW
--   power_1hour ...`` 가 있으나, TimescaleDB continuous aggregate 는
--   PostgreSQL catalog 상 ``MATERIALIZED VIEW`` 가 아닌 일반 ``VIEW`` 로
--   등록되므로 해당 라인이 ERROR 로 떨어져 COMMENT 가 누락된 상태였다.
--   (cagg 의 데이터/인덱스/refresh policy 에는 영향 없음.)
--
-- 본 마이그레이션
--   ``COMMENT ON VIEW`` 로 동일 문구를 적용. schemas/002 는 immutable 컨벤션이라
--   수정하지 않고 본 파일에서만 보정한다 (Database/CLAUDE.md 의 "schemas 백업데이트
--   금지" 정책).
--
-- 검증
--   SELECT obj_description('power_1hour'::regclass);

BEGIN;

COMMENT ON VIEW power_1hour IS
    '1시간 다운샘플 연속집계 — 7일 이상 지난 데이터의 장기 저장 계층. '
    'power_1min 이 retention 으로 삭제되기 전 마지막 refresh 에서 스냅샷. '
    '시간대별 이상탐지 패턴 보존을 위해 1일이 아닌 1시간 해상도 채택 (REQ-002).';

COMMIT;
