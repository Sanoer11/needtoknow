import sys

import psycopg
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

from config import DB_URL
model = SentenceTransformer("BAAI/bge-small-en-v1.5")

# bge works better when questions start with this instruction (documents don't need it)
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def vector_search(conn, question, k=5):
    qvec = model.encode(QUERY_PREFIX + question, normalize_embeddings=True)
    return conn.execute("""
        SELECT c.id, d.title, c.section, 1 - (c.embedding <=> %s) AS score
        FROM chunks c JOIN documents d ON d.id = c.doc_id
        ORDER BY c.embedding <=> %s
        LIMIT %s""", (qvec, qvec, k)).fetchall()


def keyword_search(conn, question, k=5):
    return conn.execute("""
        SELECT c.id, d.title, c.section, ts_rank(c.tsv, q) AS score
        FROM chunks c JOIN documents d ON d.id = c.doc_id,
             websearch_to_tsquery('english', %s) q
        WHERE c.tsv @@ q
        ORDER BY score DESC
        LIMIT %s""", (question, k)).fetchall()


def hybrid_search(conn, question, k=5, rrf_k=60):
    scores, info = {}, {}
    # take the top 20 from each method, then merge with RRF
    for results in (vector_search(conn, question, 20), keyword_search(conn, question, 20)):
        for rank, (chunk_id, title, section, _) in enumerate(results, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (rrf_k + rank)
            info[chunk_id] = (title, section)
    best = sorted(scores, key=scores.get, reverse=True)[:k]
    return [(cid, *info[cid], scores[cid]) for cid in best]


if __name__ == "__main__":
    question = sys.argv[1]
    with psycopg.connect(DB_URL) as conn:
        register_vector(conn)
        for name, fn in [("VECTOR", vector_search), ("KEYWORD", keyword_search), ("HYBRID", hybrid_search)]:
            print(f"\n{name}:")
            rows = fn(conn, question)
            if not rows:
                print("  (no results)")
            for _, title, section, score in rows:
                print(f"  {score:.4f}  {title} > {section}")