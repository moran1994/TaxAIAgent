"""SQLAlchemy engine and session + light SQLite migrations."""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine():
    settings = get_settings()
    url = settings.database_url
    if url.startswith("sqlite:///./"):
        db_path = Path(url.replace("sqlite:///./", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = _engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sqlite_migrate() -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        cols = {
            r[1]
            for r in conn.execute(text("PRAGMA table_info(tickets)")).fetchall()
        }
        if not cols:
            return
        alters = [
            ("plan_code", "VARCHAR(32) DEFAULT 'standard'"),
            ("context_summary", "TEXT"),
            ("suggest_reflow", "BOOLEAN DEFAULT 0"),
            ("rating", "INTEGER"),
            ("rating_comment", "TEXT"),
            ("refund_requested", "BOOLEAN DEFAULT 0"),
            ("payment_channel", "VARCHAR(32)"),
            ("updated_at", "DATETIME"),
        ]
        for name, typ in alters:
            if name not in cols:
                conn.execute(text(f"ALTER TABLE tickets ADD COLUMN {name} {typ}"))


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _sqlite_migrate()
