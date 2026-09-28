"""Authentication (who are you?) and authorization (what may you do?)."""
import datetime as dt
from functools import wraps

import jwt
from flask import g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from .config import Config
from .database import fetch_one
from .utils.errors import Forbidden, Unauthorized

# --------------------------------------------------------------------------
# Passwords — PBKDF2-SHA256, salted per user. Plaintext is never stored.
# --------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)


def verify_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash, password)


# --------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------
def create_token(user: dict) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": user["user_id"],
        "email": user["email"],
        "role": user["role"],
        "iat": now,
        "exp": now + dt.timedelta(minutes=Config.JWT_EXP_MINUTES),
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, Config.JWT_SECRET, algorithms=[Config.JWT_ALGORITHM])


def _user_from_token(token: str) -> dict | None:
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Token has expired")
    except jwt.InvalidTokenError:
        raise Unauthorized("Invalid token")

    user = fetch_one(
        "SELECT user_id, email, full_name, role FROM users WHERE user_id = ?",
        (payload["sub"],),
    )
    if not user:
        raise Unauthorized("User no longer exists")
    return user


def _extract_token(allow_query: bool = False) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    if allow_query:
        return request.args.get("token")
    return None


def auth_required(fn):
    """Require a valid bearer token; loads the user into flask.g.user."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _extract_token()
        if not token:
            return jsonify(error="Missing bearer token"), 401
        g.user = _user_from_token(token)
        return fn(*args, **kwargs)
    return wrapper


def auth_required_query(fn):
    """Same as auth_required but also accepts ?token= (needed by EventSource)."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _extract_token(allow_query=True)
        if not token:
            return jsonify(error="Missing token"), 401
        g.user = _user_from_token(token)
        return fn(*args, **kwargs)
    return wrapper


def optional_auth(fn):
    """Populate g.user when a valid token is present, otherwise continue anonymously."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        g.user = None
        token = _extract_token()
        if token:
            try:
                g.user = _user_from_token(token)
            except Unauthorized:
                g.user = None
        return fn(*args, **kwargs)
    return wrapper


def roles_required(*roles: str):
    """Role-based access control on top of auth_required."""
    def decorator(fn):
        @wraps(fn)
        @auth_required
        def wrapper(*args, **kwargs):
            if g.user["role"] not in roles:
                raise Forbidden(
                    f"Requires role: {', '.join(roles)} (you are {g.user['role']})"
                )
            return fn(*args, **kwargs)
        return wrapper
    return decorator