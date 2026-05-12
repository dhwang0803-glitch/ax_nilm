-- Migration: 20260512_14_create_rag_chunks
-- 의존성: 20260426_05_enable_pgvector_skeleton (vector extension 활성화)
-- 목적: LLM RAG 문서 청크 및 임베딩 저장 테이블

BEGIN;

CREATE TABLE IF NOT EXISTS rag_chunks (
    id           BIGSERIAL PRIMARY KEY,
    doc_id       TEXT        NOT NULL,
    chunk_index  INT         NOT NULL,
    content      TEXT        NOT NULL,
    category     TEXT,
    embedding    vector(1536) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_rag_chunks_doc_chunk UNIQUE (doc_id, chunk_index)
);

COMMENT ON TABLE  rag_chunks                IS 'RAG 문서 청크 및 text-embedding-3-small 임베딩 (1536차원)';
COMMENT ON COLUMN rag_chunks.doc_id         IS '문서 식별자 (예: tariff_guide, anomaly_handbook)';
COMMENT ON COLUMN rag_chunks.chunk_index    IS '문서 내 청크 순번 (0-based)';
COMMENT ON COLUMN rag_chunks.content        IS '청크 원문 텍스트';
COMMENT ON COLUMN rag_chunks.category       IS '문서 카테고리 (예: tariff, anomaly, dr) — 필터 검색용';
COMMENT ON COLUMN rag_chunks.embedding      IS 'OpenAI text-embedding-3-small 벡터 (1536차원)';

-- 코사인 유사도 HNSW 인덱스 (ANN 검색)
CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding
    ON rag_chunks USING hnsw (embedding vector_cosine_ops);

-- 카테고리별 필터 검색 인덱스
CREATE INDEX IF NOT EXISTS idx_rag_chunks_category
    ON rag_chunks (category);

-- ax_nilm_team 앱 계정에 읽기/쓰기 권한 부여 (embed 파이프라인 UPSERT용)
GRANT SELECT, INSERT, UPDATE ON rag_chunks TO ax_nilm_team;
GRANT USAGE, SELECT ON SEQUENCE rag_chunks_id_seq TO ax_nilm_team;

COMMIT;
