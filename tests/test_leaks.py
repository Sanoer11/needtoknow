import jwt
import pytest

from auth import AuthError, issue_token, verify_token
from secure_search import hybrid_search

QUESTIONS = [
    "What are the marketing salaries?", "How much does Neha earn?",
    "Is anyone on a performance improvement plan?", "Atlas price for Zenith Retail",
    "engineering budget", "revenue forecast", "CloudKite acquisition",
    "offer approval limits", "layoff scenarios draft", "leave policy",
]
USERS = ["riya", "arjun", "meera", "kabir", "ananya"]


def is_allowed(conn, user, chunk_id):
    return conn.execute("""
        SELECT EXISTS (
            SELECT 1 FROM chunk_acl a
            JOIN user_groups ug ON ug.group_id = a.group_id
            WHERE a.chunk_id = %s AND ug.user_id = %s)""", (chunk_id, user)).fetchone()[0]


def count_leaks(conn, unsafe=False):
    total = leaks = 0
    for user in USERS:
        for q in QUESTIONS:
            for chunk_id, *_ in hybrid_search(conn, user, q, unsafe=unsafe):
                total += 1
                if not is_allowed(conn, user, chunk_id):
                    leaks += 1
    return leaks, total


def sections(results):
    return {(title, section) for _, title, section, _ in results}


# ---------- 1. The main guarantee ----------

def test_zero_leaks_for_every_user_and_question(conn):
    leaks, total = count_leaks(conn)
    assert total > 0
    assert leaks == 0, f"{leaks}/{total} results leaked"


# ---------- 2. Ablation: prove the test can actually catch leaks ----------

def test_removing_the_lock_causes_leaks(conn):
    leaks, _ = count_leaks(conn, unsafe=True)
    assert leaks > 0, "test is blind: no leaks even with the lock removed"


# ---------- 3. Specific traps from company.json ----------

def test_intern_cannot_see_salaries(conn):
    found = sections(hybrid_search(conn, "riya", "marketing salaries", k=10))
    assert ("Compensation Register 2026", "Marketing salaries") not in found


def test_hr_can_see_salaries(conn):
    found = sections(hybrid_search(conn, "meera", "marketing salaries", k=10))
    assert ("Compensation Register 2026", "Marketing salaries") in found


def test_engineer_sees_atlas_architecture_but_not_pricing(conn):
    found = sections(hybrid_search(conn, "arjun", "Atlas architecture pricing", k=10))
    assert ("Project Atlas", "Architecture") in found
    assert ("Project Atlas", "Client pricing appendix") not in found


def test_draft_with_no_acl_is_hidden_even_from_ceo(conn):
    found = sections(hybrid_search(conn, "ananya", "layoff scenarios draft", k=10))
    assert ("Unreviewed Draft", "Draft notes") not in found


def test_unknown_user_sees_nothing(conn):
    assert hybrid_search(conn, "mallory", "salaries budget acquisition", k=10) == []


# ---------- 4. Tokens ----------

def test_valid_token_returns_user():
    assert verify_token(issue_token("riya")) == "riya"


def test_token_signed_with_wrong_key_rejected():
    forged = jwt.encode({"sub": "ananya", "exp": 9999999999}, "attacker-guessed-secret-that-is-long-enough", algorithm="HS256")
    with pytest.raises(AuthError):
        verify_token(forged)


def test_unsigned_alg_none_token_rejected():
    unsigned = jwt.encode({"sub": "ananya", "exp": 9999999999}, None, algorithm="none")
    with pytest.raises(AuthError):
        verify_token(unsigned)


def test_expired_token_rejected():
    with pytest.raises(AuthError):
        verify_token(issue_token("riya", minutes=-1))