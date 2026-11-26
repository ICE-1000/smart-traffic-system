"""Database engine/session. SQLite by default; set DATABASE_URL to a
postgresql+psycopg:// URL to use PostgreSQL (Phase 9)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.app.core.config import settings

if settings.database_url.startswith("sqlite:///"):
    Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def check_database() -> bool:
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return True
    except Exception:
        return False


def run_migrations() -> None:
    """Bring the schema to the latest Alembic revision (SQLite or PostgreSQL).

    A Phase-1 SQLite file (tables created without Alembic, demo data only) is
    moved aside to *.phase1-backup.db and a fresh database is created.
    """
    import logging
    import shutil

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    from backend.app.core.config import ROOT

    log = logging.getLogger("database")
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if tables and "alembic_version" not in tables:
        if settings.database_url.startswith("sqlite:///"):
            path = Path(settings.database_url.removeprefix("sqlite:///"))
            engine.dispose()
            backup = path.with_suffix(".phase1-backup.db")
            shutil.move(str(path), str(backup))
            log.warning("Pre-migration SQLite database moved to %s; creating a fresh one", backup)
        else:
            raise RuntimeError("Database has tables but no alembic_version. Use an empty database or run "
                               "'alembic stamp head' if the schema is already current.")
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "database" / "migrations"))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
