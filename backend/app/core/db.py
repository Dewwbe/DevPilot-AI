"""Database engine and session factory."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = get_settings().database_url
        kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
        _engine = create_engine(url, pool_pre_ping=True, **kwargs)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def run_migrations() -> None:
    """Apply Alembic migrations up to head (idempotent)."""
    from pathlib import Path

    from alembic.config import Config

    from alembic import command

    root = Path(__file__).resolve().parents[2]  # backend/ locally, /app in the image
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")


def init_db() -> None:
    from app.models import entities  # noqa: F401  (register tables)

    settings = get_settings()
    if settings.env == "test":
        Base.metadata.create_all(get_engine())  # tests use throwaway SQLite
    elif settings.auto_migrate:
        run_migrations()
    # else: a migration Job (Helm hook) owns the schema; the API must not race it


def get_session() -> Iterator[Session]:
    get_engine()
    assert _SessionLocal is not None
    with _SessionLocal() as session:
        yield session
