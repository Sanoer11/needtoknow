import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from pgvector.psycopg import register_vector

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))      # so tests can import secure_search, auth

from secure_search import DB_URL                 # noqa: E402


@pytest.fixture(scope="session")
def conn():
    # Rebuild the database from company.json so every test run starts from a known state
    subprocess.run([sys.executable, "scripts/load_db.py"], cwd=ROOT, check=True, capture_output=True)
    with psycopg.connect(DB_URL) as c:
        register_vector(c)
        yield c