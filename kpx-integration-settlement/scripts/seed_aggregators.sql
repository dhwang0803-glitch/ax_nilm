-- 수요관리사업자(aggregator) 초기 데이터
-- 실행 대상: Database 브랜치 migrations/ 에 포함 필요
-- settlement_rate 단위: 원/kWh

CREATE TABLE IF NOT EXISTS aggregators (
    aggregator_id   TEXT             PRIMARY KEY,
    name            TEXT             NOT NULL,
    settlement_rate DOUBLE PRECISION NOT NULL CHECK (settlement_rate > 0),
    updated_at      TIMESTAMPTZ      NOT NULL DEFAULT now()
);

INSERT INTO aggregators (aggregator_id, name, settlement_rate)
VALUES
    ('AGG_PARAN',   '파란에너지', 1000.0),
    ('AGG_BYUKSAN', '벽산파워',   1200.0),
    ('AGG_LG',      'LG전자',     1300.0)
ON CONFLICT (aggregator_id) DO UPDATE
    SET settlement_rate = EXCLUDED.settlement_rate,
        updated_at      = now();
