-- ============================================================================
-- power_daily_historical : 시연용 더미 일별 사용량 (캐시백 baseline 입력)
-- ============================================================================
-- 동기:
--   캐시백 도구는 직전 24 개월 baseline 평균을 입력으로 받는다. 실측 power_1min
--   은 50 일치 (2026-03-26 ~ 2026-05-14, shift 후) 만 있어 baseline 길이 부족.
--   가구별 의도된 절감률 (5/8/12/15/18 %) 분포를 부여한 일 단위 더미를 적재해
--   agent baseline 도구가 의미 있는 값을 반환하게 한다.
--
-- 적재 스크립트: scripts/load_dummy_historical.py (synthetic_v1)
-- 적재 기간    : 시연(2026-05-15) - 24 개월 ~ 시연 - 50 일
--                 = 2024-05-15 ~ 2026-03-25 (~680 일)
-- 규모        : 10 가구 × 680 일 ≈ 6,800 행
--
-- 컬럼 의미:
--   savings_rate — 가구별 의도된 시나리오 절감률 (시연 시 단가 구간 다양성)
--   source       — 생성 알고리즘 버전. 알고리즘 바뀌면 v2 / v3 으로 신규 INSERT
--   seed_value   — sha256(household_id || day.isoformat()) 의 상위 16 hex →
--                  numpy rng seed. 재생성 시 동일 값 보장 (시연 안전성)
-- ============================================================================

CREATE TABLE IF NOT EXISTS power_daily_historical (
    household_id   TEXT             NOT NULL REFERENCES households(household_id) ON DELETE CASCADE,
    day            DATE             NOT NULL,
    kwh            DOUBLE PRECISION NOT NULL CHECK (kwh > 0),
    savings_rate   DOUBLE PRECISION NOT NULL CHECK (savings_rate BETWEEN 0 AND 1),
    source         TEXT             NOT NULL DEFAULT 'synthetic_v1',
    seed_value     BIGINT           NOT NULL,
    generated_at   TIMESTAMPTZ      NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, day, source)
);

CREATE INDEX IF NOT EXISTS idx_power_daily_historical_lookup
    ON power_daily_historical (household_id, day DESC);

CREATE INDEX IF NOT EXISTS idx_power_daily_historical_day
    ON power_daily_historical (day);

-- 권한 — ax_nilm_app 가 적재 + 조회
GRANT SELECT, INSERT, UPDATE, DELETE ON power_daily_historical TO ax_nilm_app;

COMMENT ON TABLE power_daily_historical IS
    '시연용 더미 일별 사용량 (가구 총합). 캐시백 baseline 입력 전용. '
    'synthetic_v1: 가구별 실측 ch01 평균 × (1+savings_rate) × 계절성 × noise(σ=5%, seed=hash(h,d)). '
    'load_dummy_historical.py 가 적재.';
COMMENT ON COLUMN power_daily_historical.kwh IS
    '해당 일의 가구 총 사용량 (kWh). 가전 분해 없음 (메인 분전반 ch01 상응).';
COMMENT ON COLUMN power_daily_historical.savings_rate IS
    '의도된 시나리오 절감률 (0.05/0.08/0.12/0.15/0.18). 시연 캐시백 단가 구간 다양성 확보 목적.';
COMMENT ON COLUMN power_daily_historical.source IS
    '생성 알고리즘 버전. v1 = 가구별 실측 평균 base + 계절성 + noise. 알고리즘 변경 시 신규 source 로 병존 INSERT.';
COMMENT ON COLUMN power_daily_historical.seed_value IS
    'numpy rng seed (재현성). sha256(household_id || day.isoformat()) 상위 16 hex → int.';
