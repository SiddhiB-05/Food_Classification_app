import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

try:
    import neon_http_db
    from neon_http_db import User
except ImportError:
    from backend import neon_http_db
    from backend.neon_http_db import User


load_dotenv(Path(__file__).resolve().parent / ".env")


AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY")
if not AUTH_SECRET_KEY:
    import warnings
    warnings.warn(
        "AUTH_SECRET_KEY environment variable is not set! Using default dev key."
    )
    AUTH_SECRET_KEY = "change-this-dev-secret"

TOKEN_EXPIRE_SECONDS = 60 * 60 * 24 * 7
HASH_ITERATIONS = 180_000
bearer_scheme = HTTPBearer(auto_error=False)


class SignupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: int
    name: str
    email: str

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


def _b64url_encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data):
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        HASH_ITERATIONS,
    )
    return "$".join(
        [
            "pbkdf2_sha256",
            str(HASH_ITERATIONS),
            _b64url_encode(salt),
            _b64url_encode(digest),
        ]
    )


def verify_password(password, stored_hash):
    try:
        algorithm, iterations, salt, expected_digest = stored_hash.split("$")
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        _b64url_decode(salt),
        int(iterations),
    )
    return hmac.compare_digest(_b64url_encode(digest), expected_digest)


def create_access_token(user):
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user.email,
        "name": user.name,
        "uid": user.id,
        "exp": int(time.time()) + TOKEN_EXPIRE_SECONDS,
    }
    signing_input = ".".join(
        [
            _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(
        AUTH_SECRET_KEY.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def decode_access_token(token):
    try:
        header_part, payload_part, signature_part = token.split(".")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.") from exc

    signing_input = f"{header_part}.{payload_part}"
    expected_signature = hmac.new(
        AUTH_SECRET_KEY.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(_b64url_encode(expected_signature), signature_part):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    payload = json.loads(_b64url_decode(payload_part))
    if payload.get("exp", 0) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired.")

    return payload


def normalize_email(email):
    return email.strip().lower()


def signup_user(signup_data):
    email = normalize_email(signup_data.email)
    existing_user = neon_http_db.get_user_by_email(email)
    if existing_user:
        raise HTTPException(status_code=409, detail="Email is already registered.")

    user = neon_http_db.create_user(
        name=signup_data.name.strip(),
        email=email,
        password_hash=hash_password(signup_data.password),
    )
    return user


def authenticate_user(login_data):
    email = normalize_email(login_data.email)
    user = neon_http_db.get_user_by_email(email)
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return user


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required.")

    payload = decode_access_token(credentials.credentials)
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    try:
        user = neon_http_db.get_user_by_email(normalize_email(email))
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
        return user
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Neon Postgres database error: {exc}",
        ) from exc


def token_response(user):
    return TokenResponse(access_token=create_access_token(user), user=user)
