from __future__ import annotations

import secrets
import bcrypt
from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from app.db import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def new_api_key() -> str:
    # 64 hex chars
    return secrets.token_hex(32)


def require_api_key(authorization: str = Header(default="")) -> str:
    # Expect: Authorization: Bearer <api_key>
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    key = authorization.replace("Bearer ", "", 1).strip()
    if not key:
        raise HTTPException(status_code=401, detail="Missing API key")
    return key


def get_user_by_api_key(db: Session, api_key: str) -> User | None:
    return db.query(User).filter(User.api_key == api_key).first()
