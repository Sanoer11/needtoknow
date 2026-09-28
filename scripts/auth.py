import os
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv

load_dotenv()                        # reads .env into environment variables
SECRET = os.environ["JWT_SECRET"]
ALGORITHM = "HS256"


class AuthError(Exception):
    pass


def issue_token(user_id, minutes=60):
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def verify_token(token):
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM], options={"require": ["sub", "exp"]})
    except jwt.ExpiredSignatureError:
        raise AuthError("token expired - log in again")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"invalid token: {e}")
    return payload["sub"]