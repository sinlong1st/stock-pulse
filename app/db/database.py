"""Database engine, session factory, and declarative base.

Synchronous SQLAlchemy over SQLite for the MVP. A single-user local
service does not need async DB access, and sync keeps Alembic simple.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_settings = get_settings()
_connect_args = (
    {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(_settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Yield a database session (FastAPI dependency friendly)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
