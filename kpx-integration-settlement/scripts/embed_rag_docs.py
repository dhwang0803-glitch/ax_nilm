"""RAG 문서 임베딩 파이프라인.

rag_docs/raw/*.md → 512토큰 청크 (50 overlap) → text-embedding-3-small → pgvector 저장.

실행 예:
    cd kpx-integration-settlement
    python scripts/embed_rag_docs.py           # 전체 문서 임베딩 + 저장
    python scripts/embed_rag_docs.py --dry-run # 청크 목록만 출력, DB 저장 안 함

의존 패키지:
    pip install openai tiktoken psycopg2-binary

환경변수:
    OPENAI_API_KEY   — OpenAI API 키
    DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD  — PostgreSQL 연결
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import tiktoken

# ─── 상수 ────────────────────────────────────────────────────────────────────

RAG_DIR = Path(__file__).parent.parent / "rag_docs" / "raw"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
MAX_TOKENS = 512
OVERLAP_TOKENS = 50
BATCH_SIZE = 100   # OpenAI 임베딩 API 한 번에 최대 처리 건수

# 파일명 prefix → 카테고리 매핑
_CATEGORY_MAP = {
    "guide_": "가입 가이드",
    "tips_": "절감 팁",
    "policy_": "정책 참조",
}

# 처리 대상 문서 (cashback_overview.md 등 이전 잔여 파일 제외)
_TARGET_DOCS = {
    "guide_cashback_enrollment",
    "guide_baseline_explained",
    "tips_appliance_patterns",
    "tips_peak_hours",
    "policy_cashback_tiers",
    "policy_progressive_rate",
    "policy_measurement_period",
}


# ─── 청크 분할 ────────────────────────────────────────────────────────────────

def _get_category(doc_id: str) -> str:
    for prefix, cat in _CATEGORY_MAP.items():
        if doc_id.startswith(prefix):
            return cat
    return "기타"


def _split_sections(text: str) -> list[str]:
    """H2 헤더(## )를 기준으로 섹션 분리. 첫 서두(H1 포함)도 하나의 섹션으로 처리."""
    sections: list[str] = []
    current: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.startswith("## ") and current:
            sections.append("".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("".join(current).strip())
    return [s for s in sections if s]


def _token_chunks(text: str, enc: tiktoken.Encoding) -> list[str]:
    """단일 텍스트를 MAX_TOKENS / OVERLAP_TOKENS 기준으로 청크 분할."""
    tokens = enc.encode(text)
    if len(tokens) <= MAX_TOKENS:
        return [text]

    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + MAX_TOKENS, len(tokens))
        chunks.append(enc.decode(tokens[start:end]))
        if end == len(tokens):
            break
        start += MAX_TOKENS - OVERLAP_TOKENS
    return chunks


def build_chunks(doc_id: str) -> list[dict]:
    """문서 하나를 읽어 청크 목록 반환.

    Returns:
        list of {"doc_id", "chunk_index", "content", "category"}
    """
    path = RAG_DIR / f"{doc_id}.md"
    text = path.read_text(encoding="utf-8")
    enc = tiktoken.get_encoding("cl100k_base")
    category = _get_category(doc_id)

    raw_chunks: list[str] = []
    for section in _split_sections(text):
        raw_chunks.extend(_token_chunks(section, enc))

    return [
        {
            "doc_id": doc_id,
            "chunk_index": idx,
            "content": chunk,
            "category": category,
        }
        for idx, chunk in enumerate(raw_chunks)
    ]


# ─── OpenAI 임베딩 ────────────────────────────────────────────────────────────

def embed_chunks(chunks: list[dict]) -> list[dict]:
    """content 필드를 임베딩해 embedding 키를 추가한 새 리스트 반환."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    texts = [c["content"] for c in chunks]
    result = list(chunks)  # shallow copy

    for batch_start in range(0, len(texts), BATCH_SIZE):
        batch_texts = texts[batch_start: batch_start + BATCH_SIZE]
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=batch_texts)
        for i, emb_obj in enumerate(resp.data):
            result[batch_start + i]["embedding"] = emb_obj.embedding
        # OpenAI rate-limit 여유
        if batch_start + BATCH_SIZE < len(texts):
            time.sleep(0.2)

    return result


# ─── DB 저장 ──────────────────────────────────────────────────────────────────

def _get_db_conn():
    pw = os.getenv("DB_PASSWORD")
    if not pw:
        return None
    try:
        import psycopg2
        return psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5436")),
            dbname=os.getenv("DB_NAME", "ax_nilm"),
            user=os.getenv("DB_USER", "ax_nilm_team"),
            password=pw,
            connect_timeout=5,
        )
    except Exception as e:
        print(f"[ERROR] DB 연결 실패: {e}", file=sys.stderr)
        return None


def upsert_chunks(conn, chunks: list[dict]) -> int:
    """rag_chunks 테이블에 UPSERT. 저장된 행 수 반환."""
    sql = """
        INSERT INTO rag_chunks (doc_id, chunk_index, content, embedding, category)
        VALUES (%s, %s, %s, %s::vector, %s)
        ON CONFLICT (doc_id, chunk_index) DO UPDATE
            SET content   = EXCLUDED.content,
                embedding = EXCLUDED.embedding,
                category  = EXCLUDED.category,
                created_at = NOW()
    """
    with conn.cursor() as cur:
        for c in chunks:
            cur.execute(sql, (
                c["doc_id"],
                c["chunk_index"],
                c["content"],
                str(c["embedding"]),  # psycopg2 → pgvector: 문자열 '[x,y,...]'
                c["category"],
            ))
    conn.commit()
    return len(chunks)


# ─── 진입점 ──────────────────────────────────────────────────────────────────

def main():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[1] / "config" / ".env")

    parser = argparse.ArgumentParser(description="RAG 문서 임베딩 파이프라인")
    parser.add_argument("--dry-run", action="store_true", help="청크 목록 출력만, DB 저장 안 함")
    parser.add_argument("--doc", help="단일 문서 doc_id만 처리 (예: policy_cashback_tiers)")
    args = parser.parse_args()

    target_docs = {args.doc} if args.doc else _TARGET_DOCS

    all_chunks: list[dict] = []
    for doc_id in sorted(target_docs):
        path = RAG_DIR / f"{doc_id}.md"
        if not path.exists():
            print(f"[WARN] 파일 없음: {path}", file=sys.stderr)
            continue
        chunks = build_chunks(doc_id)
        all_chunks.extend(chunks)
        print(f"  {doc_id}: {len(chunks)}청크")

    print(f"총 {len(all_chunks)}청크")

    if args.dry_run:
        for c in all_chunks:
            tok_count = len(tiktoken.get_encoding("cl100k_base").encode(c["content"]))
            preview = c['content'][:60].replace(chr(10), ' ')
            enc = sys.stdout.encoding or 'utf-8'
            safe = preview.encode(enc, errors='replace').decode(enc)
            print(f"  [{c['doc_id']}#{c['chunk_index']}] {tok_count}토큰 | {safe}...")
        return

    if "OPENAI_API_KEY" not in os.environ:
        print("[ERROR] OPENAI_API_KEY 환경변수 미설정", file=sys.stderr)
        sys.exit(1)

    print("임베딩 생성 중...")
    embedded = embed_chunks(all_chunks)
    print("임베딩 완료.")

    conn = _get_db_conn()
    if not conn:
        print("[ERROR] DB 연결 실패. DB_PASSWORD 환경변수를 확인하세요.", file=sys.stderr)
        sys.exit(1)

    try:
        saved = upsert_chunks(conn, embedded)
        print(f"pgvector 저장 완료: {saved}행")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
