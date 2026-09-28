import psycopg
from pgvector.psycopg import register_vector

from secure_search import DB_URL, hybrid_search

QUESTIONS = [
    "What are the marketing salaries?", "How much does Neha earn?",
    "Is anyone on a performance improvement plan?", "Atlas price for Zenith Retail",
    "engineering budget", "revenue forecast", "CloudKite acquisition",
    "offer approval limits", "layoff scenarios draft", "leave policy",
]

with psycopg.connect(DB_URL) as conn:
    register_vector(conn)
    users = [r[0] for r in conn.execute("SELECT id FROM users ORDER BY id")]
    total = leaks = 0

    for user in users:
        for q in QUESTIONS:
            for chunk_id, title, section, _ in hybrid_search(conn, user, q):
                total += 1
                # Independently re-check: is this user really allowed to read this chunk?
                allowed = conn.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM chunk_acl a
                        JOIN user_groups ug ON ug.group_id = a.group_id
                        WHERE a.chunk_id = %s AND ug.user_id = %s)""",
                    (chunk_id, user)).fetchone()[0]
                if not allowed:
                    leaks += 1
                    print(f"LEAK: {user} got {title} > {section}")

    print(f"\nChecked {total} results for {len(users)} users: {leaks} leaks")