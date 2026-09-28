import sys

import psycopg
from pgvector.psycopg import register_vector

from auth import AuthError, verify_token
from secure_search import DB_URL, hybrid_search

token, question = sys.argv[1], sys.argv[2]

try:
    user = verify_token(token)          # WHO is asking - proven by the signature
except AuthError as e:
    sys.exit(f"Access denied: {e}")

with psycopg.connect(DB_URL) as conn:
    register_vector(conn)
    print(f"\nVerified as: {user}")
    rows = hybrid_search(conn, user, question)   # WHAT they may see - decided by the database
    if not rows:
        print("  (nothing you're allowed to see)")
    for _, title, section, score in rows:
        print(f"  {score:.4f}  {title} > {section}")