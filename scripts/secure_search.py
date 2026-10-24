import sys

import psycopg
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

from config import DB_URL
model = SentenceTransformer("BAAI/bge-small-en-v1.5")
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# The lock: this chunk is readable if it shares at least one group with the user.
# No ACL rows for a chunk -> EXISTS finds nothing -> hidden (deny by default).
CAN_READ = """
    EXISTS (
        SELECT 1 FROM chunk_acl a
        JOIN user_groups ug ON ug.group_id = a.group_id
        WHERE a.chunk_id = c.id AND ug.user_id = %(user)s
    )"""


def vector_search(conn, user, question, k=5, unsafe=False, department=None):
    lock = "TRUE" if unsafe else CAN_READ
    qvec = model.encode(QUERY_PREFIX + question, normalize_embeddings=True)
    return conn.execute(f"""
        SELECT c.id, d.title, c.section, 1 - (c.embedding <=> %(qvec)s) AS score
        FROM chunks c JOIN documents d ON d.id = c.doc_id
        WHERE {lock}
          AND (%(dept)s::text IS NULL OR d.department = %(dept)s)
        ORDER BY c.embedding <=> %(qvec)s
        LIMIT %(k)s""", {"user": user, "qvec": qvec, "k": k, "dept": department}).fetchall()


def keyword_search(conn, user, question, k=5, unsafe=False, department=None):
    lock = "TRUE" if unsafe else CAN_READ
    return conn.execute(f"""
        SELECT c.id, d.title, c.section, ts_rank(c.tsv, q) AS score
        FROM chunks c JOIN documents d ON d.id = c.doc_id,
             websearch_to_tsquery('english', %(question)s) q
        WHERE c.tsv @@ q AND {lock}
          AND (%(dept)s::text IS NULL OR d.department = %(dept)s)
        ORDER BY score DESC
        LIMIT %(k)s""", {"user": user, "question": question, "k": k, "dept": department}).fetchall()


def hybrid_search(conn, user, question, k=5, rrf_k=60, unsafe=False, department=None):
    scores, info = {}, {}
    for results in (vector_search(conn, user, question, 20, unsafe, department),keyword_search(conn, user, question, 20, unsafe, department)):
        for rank, (chunk_id, title, section, _) in enumerate(results, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (rrf_k + rank)
            info[chunk_id] = (title, section)
    best = sorted(scores, key=scores.get, reverse=True)[:k]
    return [(cid, *info[cid], scores[cid]) for cid in best]


if __name__ == "__main__":
    user, question = sys.argv[1], sys.argv[2]
    with psycopg.connect(DB_URL) as conn:
        register_vector(conn)
        print(f"\n{user} asks: {question}")
        rows = hybrid_search(conn, user, question)
        if not rows:
            print("  (nothing you're allowed to see)")
        for _, title, section, score in rows:
            print(f"  {score:.4f}  {title} > {section}")