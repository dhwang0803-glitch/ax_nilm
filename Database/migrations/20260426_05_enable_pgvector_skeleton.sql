-- ax_nilm — P1 2.1 pgvector 확장 enable + household_embeddings 스켈레톤
-- 의존: schemas/001_core_tables.sql (households)
-- 후속:
--   * 20260???_finalize_household_embeddings.sql
--     KPX 측 임베딩 ADR 발행 후 차원 확정 (예: vector(384) 또는 vector(768)) +
--     ANN 인덱스(IVFFlat 또는 HNSW) 추가. 본 마이그레이션은 데이터 로드 가능 상태까지만.
--
-- 분리 사유:
--   임베딩 차원(384 vs 768)과 모델 선택(Chronos / TimesFM / 자체)이 KPX 측에서 미결.
--   차원을 잘못 못박으면 후속에 ALTER COLUMN TYPE 강제 변환이 필요하고, ANN 인덱스도
--   재생성해야 하므로 차원 미지정(`vector`) 으로 두고 데이터 적재 시점에 결정.
--
-- 쓰기:
--   가구 × 기준일 × 모델 단위로 1행. 동일 가구·기준일에 여러 모델 임베딩 병존 허용.
--
-- 읽기:
--   * 가구 단일 조회: PK 인덱스 사용 (household_id, ref_date DESC)
--   * 유사 가구 검색 (코사인/L2): 후속 ANN 인덱스 발행 후 가능. 그 전에는 시퀀셜 스캔.

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS household_embeddings (
    household_id TEXT        NOT NULL REFERENCES households(household_id) ON DELETE CASCADE,
    ref_date     DATE        NOT NULL,
    embed_model  TEXT        NOT NULL,
    embedding    vector      NOT NULL,                  -- 차원 미지정. 후속 마이그레이션에서 vector(N) 으로 고정.
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (household_id, ref_date, embed_model)
);

-- 가구 단일 시계열 조회 (최근 임베딩) 용
CREATE INDEX IF NOT EXISTS idx_household_embeddings_recent
    ON household_embeddings (household_id, ref_date DESC);

-- 모델별 일자 횡단 조회 (전체 가구 유사도 계산 배치) 용
CREATE INDEX IF NOT EXISTS idx_household_embeddings_model_date
    ON household_embeddings (embed_model, ref_date);

COMMENT ON TABLE household_embeddings IS
    '가구별 시계열 임베딩 — KPX RAG / 유사 가구 검색 / 클러스터 보강용. '
    '차원·모델 미확정 상태이므로 ANN 인덱스는 후속 마이그레이션에서 추가.';
COMMENT ON COLUMN household_embeddings.embedding IS
    'pgvector. 차원 미지정 — 후속 마이그레이션에서 vector(384|768) 로 고정 예정. '
    '동일 가구·날짜라도 embed_model 별로 별도 행을 보관해 모델 비교 가능.';
COMMENT ON COLUMN household_embeddings.embed_model IS
    '임베딩 모델 식별자 (예: chronos-t5-small, timesfm-200m, ax-nilm-encoder-v1). '
    'PK 일부이므로 모델 변경 시 새 행 INSERT.';
COMMENT ON COLUMN household_embeddings.ref_date IS
    '임베딩이 요약하는 시계열 윈도우의 기준일 (보통 윈도우 마지막 날짜).';

COMMIT;
