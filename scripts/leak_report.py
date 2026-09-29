import psycopg
from pgvector.psycopg import register_vector

from secure_search import DB_URL, hybrid_search

QUESTIONS = [
    "What are the marketing salaries?", "How much does Neha earn?",
    "Is anyone on a performance improvement plan?", "Atlas price for Zenith Retail",
    "engineering budget", "revenue forecast", "CloudKite acquisition",
    "offer approval limits", "layoff scenarios draft", "leave policy",
]

ALLOWED_SQL = """
    SELECT EXISTS (
        SELECT 1 FROM chunk_acl a
        JOIN user_groups ug ON ug.group_id = a.group_id
        WHERE a.chunk_id = %s AND ug.user_id = %s)"""

with psycopg.connect(DB_URL) as conn:
    register_vector(conn)
    users = [r[0] for r in conn.execute("SELECT id FROM users ORDER BY id")]

    print(f"{'user':<8} {'lock ON':>10} {'lock OFF':>10}")
    totals = {False: [0, 0], True: [0, 0]}
    for user in users:
        row = []
        for unsafe in (False, True):
            leaks = total = 0
            for q in QUESTIONS:
                for chunk_id, *_ in hybrid_search(conn, user, q, unsafe=unsafe):
                    total += 1
                    leaks += not conn.execute(ALLOWED_SQL, (chunk_id, user)).fetchone()[0]
            totals[unsafe][0] += leaks
            totals[unsafe][1] += total
            row.append(f"{leaks}/{total}")
        print(f"{user:<8} {row[0]:>10} {row[1]:>10}")

    for unsafe, label in [(False, "Lock ON "), (True, "Lock OFF")]:
        leaks, total = totals[unsafe]
        print(f"\n{label}: {leaks}/{total} results leaked = {leaks / total:.1%}")