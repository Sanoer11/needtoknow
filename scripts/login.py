import sys

import psycopg

from auth import issue_token
from secure_search import DB_URL

user_id = sys.argv[1]

with psycopg.connect(DB_URL) as conn:
    exists = conn.execute("SELECT 1 FROM users WHERE id = %s", (user_id,)).fetchone()

if not exists:
    sys.exit(f"No such user: {user_id}")

print(issue_token(user_id))