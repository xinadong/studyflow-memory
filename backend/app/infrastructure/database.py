"""SQLite 数据库引擎、Session 和 ORM 元数据。"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


DATABASE_URL = get_settings().database_url
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    from app.infrastructure.models import agent_runs, feedback, knowledge_state, memory, task  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        _upgrade_agent_runs_schema(connection)
        _cleanup_memory_scope(connection)


def _upgrade_agent_runs_schema(connection) -> None:
    """Add telemetry columns to databases created by the earlier backend.

    The project does not yet ship a full Alembic migration history. This small,
    idempotent upgrade keeps an existing SQLite database usable without
    dropping any data. New installations are still created by ``create_all``.
    """
    inspector = inspect(connection)
    if "agent_runs" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("agent_runs")}
    additions = {
        "model": "VARCHAR(128)",
        "status": "VARCHAR(32) NOT NULL DEFAULT 'success'",
        "tool_calls": "JSON NOT NULL DEFAULT '[]'",
        "retry_count": "INTEGER NOT NULL DEFAULT 0",
        "format_repair_count": "INTEGER NOT NULL DEFAULT 0",
        "error_code": "VARCHAR(64)",
        "error_message": "TEXT",
        "user_acceptance": "BOOLEAN",
        "candidate_memory_ids": "JSON NOT NULL DEFAULT '[]'",
    }
    for name, definition in additions.items():
        if name not in existing:
            connection.exec_driver_sql(
                f"ALTER TABLE agent_runs ADD COLUMN {name} {definition}"
            )


def _cleanup_memory_scope(connection) -> None:
    """Clear stale block scopes from non-recovery memories.

    Older versions could persist ``block_type`` before a feedback classifier
    corrected the memory type.  The cleanup is idempotent and preserves the
    memory row and its audit fields while restoring the domain scope rule.
    """
    if "memories" not in inspect(connection).get_table_names():
        return
    connection.exec_driver_sql(
        "UPDATE memories SET block_type = NULL "
        "WHERE memory_type <> 'recovery_experience' AND block_type IS NOT NULL"
    )


# Import models after Base is defined so metadata is registered for create_all().
from app.infrastructure import models as _models  # noqa: E402,F401
