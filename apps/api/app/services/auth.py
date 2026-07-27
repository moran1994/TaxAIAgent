"""Expert/user session auth (token in DB; PBKDF2 password hash)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditLog, User, UserSession


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${dk.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("pbkdf2_sha256$"):
        return False
    try:
        _, salt, digest = stored.split("$", 2)
    except ValueError:
        return False
    check = hash_password(password, salt=salt)
    return secrets.compare_digest(check, stored)


def create_session(db: Session, user: User, *, days: int = 7) -> UserSession:
    token = secrets.token_urlsafe(32)
    row = UserSession(
        user_id=user.id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(days=days),
    )
    db.add(row)
    db.add(
        AuditLog(
            actor=user.display_name or str(user.id),
            action="login",
            entity_type="user",
            entity_id=str(user.id),
            detail=user.role,
        )
    )
    db.commit()
    db.refresh(row)
    return row


def revoke_session(db: Session, token: str) -> bool:
    row = db.query(UserSession).filter(UserSession.token == token).one_or_none()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def user_from_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    row = (
        db.query(UserSession)
        .filter(UserSession.token == token)
        .one_or_none()
    )
    if not row:
        return None
    if row.expires_at and row.expires_at < datetime.utcnow():
        db.delete(row)
        db.commit()
        return None
    return db.get(User, row.user_id)


def login(db: Session, *, phone: str, password: str) -> tuple[User, UserSession]:
    phone = (phone or "").strip()
    user = db.query(User).filter(User.phone == phone).one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("invalid credentials")
    if user.role not in {"expert", "admin"}:
        raise ValueError("not an expert account")
    session = create_session(db, user)
    return user, session


def ensure_demo_experts(db: Session) -> list[User]:
    """Seed trial experts with passwords from settings (dev/demo only)."""
    settings = get_settings()
    password = settings.demo_expert_password or "demo1234"
    seeds = [
        ("expert-demo", "试接专家甲"),
        ("expert-demo-b", "试接专家乙"),
    ]
    out: list[User] = []
    for phone, name in seeds:
        user = db.query(User).filter(User.phone == phone).one_or_none()
        if not user:
            user = User(
                phone=phone,
                display_name=name,
                role="expert",
                password_hash=hash_password(password),
            )
            db.add(user)
            db.flush()
        else:
            if user.role != "expert":
                user.role = "expert"
            # Demo accounts: keep password in sync with DEMO_EXPERT_PASSWORD
            user.password_hash = hash_password(password)
        out.append(user)
    return out


def parse_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip() or None
