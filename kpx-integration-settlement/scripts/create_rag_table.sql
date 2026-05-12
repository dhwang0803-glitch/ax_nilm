-- RAG 청크 테이블 + pgvector 인덱스
-- 실행: psql -h localhost -p 5436 -U ax_nilm_team -d ax_nilm -f scripts/create_rag_table.sql

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_chunks (
    id            SERIAL PRIMARY KEY,
    doc_id        TEXT NOT NULL,        -- 파일명 (확장자 제외, 예: policy_cashback_tiers)
    chunk_index   INTEGER NOT NULL,     -- 문서 내 청크 순서 (0-based)
    content       TEXT NOT NULL,        -- 청크 본문
    embedding     vector(1536),         -- text-embedding-3-small 출력
    category      TEXT,                 -- 가입 가이드 | 절감 팁 | 정책 참조
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (doc_id, chunk_index)
);

-- cosine 유사도 기반 IVFFLAT 인덱스 (청크 수 < 1000이므로 lists=10)
CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx
    ON rag_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);
