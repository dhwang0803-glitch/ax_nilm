-- ax_nilm — P0 1.1 aggregators 테이블 신규 + 시드
-- 출처: kpx-integration-settlement/scripts/seed_aggregators.sql 회수
-- 의존: 없음 (독립 마스터)
-- 후속: 20260426_02_extend_households.sql 가 households.aggregator_id FK 로 참조

BEGIN;

CREATE TABLE IF NOT EXISTS aggregators (
    aggregator_id   TEXT             PRIMARY KEY,
    name            TEXT             NOT NULL,
    settlement_rate DOUBLE PRECISION NOT NULL CHECK (settlement_rate > 0),
    updated_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE aggregators IS
    '수요관리사업자 마스터 — KPX 정산 단가 (원/kWh) 보관. '
    'household.aggregator_id 가 이 테이블을 참조.';
COMMENT ON COLUMN aggregators.settlement_rate IS
    'KPX 정산 단가 (원/kWh). 변경 시 ON CONFLICT DO UPDATE 로 갱신.';

INSERT INTO aggregators (aggregator_id, name, settlement_rate)
VALUES
    ('AGG_PARAN',   '파란에너지', 1000.0),
    ('AGG_BYUKSAN', '벽산파워',   1200.0),
    ('AGG_LG',      'LG전자',     1300.0)
ON CONFLICT (aggregator_id) DO UPDATE
    SET settlement_rate = EXCLUDED.settlement_rate,
        updated_at      = NOW();

COMMIT;
