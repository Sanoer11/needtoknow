import json

import psycopg
from pgvector.psycopg import register_vector                     # NEW
from sentence_transformers import SentenceTransformer            # NEW

from config import DB_URL

company = json.load(open("data/company.json"))
model = SentenceTransformer("BAAI/bge-small-en-v1.5")            # NEW

with psycopg.connect(DB_URL, autocommit=True) as conn:
    conn.execute("DROP TABLE IF EXISTS chunk_acl, chunks, documents, user_groups, groups, users CASCADE")
    conn.execute(open("db/schema.sql").read())
    register_vector(conn)          # NEW: must come AFTER the schema creates the extension

    for g in company["groups"]:
        conn.execute("INSERT INTO groups (id) VALUES (%s)", (g,))

    for u in company["users"]:
        conn.execute("INSERT INTO users (id, name, role) VALUES (%s, %s, %s)",
                     (u["id"], u["name"], u["role"]))
        for g in u["groups"]:
            conn.execute("INSERT INTO user_groups (user_id, group_id) VALUES (%s, %s)", (u["id"], g))

    for d in company["documents"]:
        conn.execute("INSERT INTO documents (id, title, department, updated_at) VALUES (%s, %s, %s, %s)",
                     (d["id"], d["title"], d["department"], d["updated_at"]))

        # NEW: embed all sections of this document in one batch
        texts = [f"{d['title']} - {s['section']}: {s['content']}" for s in d["sections"]]
        vectors = model.encode(texts, normalize_embeddings=True)

        for s, vec in zip(d["sections"], vectors):
            chunk_id = conn.execute(
                "INSERT INTO chunks (doc_id, section, content, embedding) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (d["id"], s["section"], s["content"], vec),
            ).fetchone()[0]
            for g in s["acl"]:
                conn.execute("INSERT INTO chunk_acl (chunk_id, group_id) VALUES (%s, %s)", (chunk_id, g))

    for table in ["users", "groups", "user_groups", "documents", "chunks", "chunk_acl"]:
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:<12} {n} rows")