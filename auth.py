"""Password hashing + JWT helpers."""
import datetime as dt
import hashlib
import hmac
import os
import secrets

import jwt

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${digest}"


def verify_password(password, stored):
    salt, digest = stored.split("$", 1)
    return hmac.compare_digest(hash_password(password, salt).split("$", 1)[1], digest)


def create_token(username, minutes=720):
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)
    return jwt.encode({"sub": username, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]).get("sub")
    except jwt.PyJWTError:
        return None
