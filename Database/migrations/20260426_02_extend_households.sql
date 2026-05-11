-- ax_nilm — P0 1.2 households 컬럼 추가
-- 의존: 20260426_01_add_aggregators.sql (aggregator_id FK)
-- 출처:
--   * cluster_label : dr-savings-prediction (KMeans n=9)
--   * dr_enrolled / aggregator_id : kpx-integration-settlement
--
-- 컬럼 모두 nullable — 기존 행 영향 없음. NULL = 미가입/미군집화.

BEGIN;

ALTER TABLE households
    ADD COLUMN IF NOT EXISTS cluster_label SMALLINT,
    ADD COLUMN IF NOT EXISTS dr_enrolled   BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS aggregator_id TEXT
        REFERENCES aggregators(aggregator_id) ON DELETE SET NULL;

-- KMeans n=9 결과 저장. 0~8 범위. 미군집화 가구는 NULL.
ALTER TABLE households
    ADD CONSTRAINT chk_households_cluster_label
        CHECK (cluster_label IS NULL OR cluster_label BETWEEN 0 AND 8);

CREATE INDEX IF NOT EXISTS idx_households_cluster_label
    ON households(cluster_label)
    WHERE cluster_label IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_households_aggregator
    ON households(aggregator_id)
    WHERE aggregator_id IS NOT NULL;

COMMENT ON COLUMN households.cluster_label IS
    'dr-savings-prediction KMeans (n=9) 결과. 0~8. 미군집화 = NULL.';
COMMENT ON COLUMN households.dr_enrolled IS
    'KPX DR 프로그램 가입 여부. 미가입 가구는 dr_events 발행 시 제외.';
COMMENT ON COLUMN households.aggregator_id IS
    '소속 수요관리사업자. NULL = 미가입. aggregator 삭제 시 SET NULL.';

COMMIT;
