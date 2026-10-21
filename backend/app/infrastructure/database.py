"""SQLite 数据库引擎、Session 和 ORM 元数据。"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect, select, text
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
    from app.infrastructure.models import agent_runs, auth, feedback, knowledge_state, memory, task  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        _upgrade_agent_runs_schema(connection)
        _upgrade_tasks_schema(connection)
        _upgrade_memory_scope(connection)
        _upgrade_duration_schema(connection)
        _cleanup_memory_scope(connection)
        _migrate_legacy_data_to_demo_user(connection)
    _ensure_demo_account()


def _migrate_legacy_data_to_demo_user(connection) -> None:
    """Assign pre-authentication records to the dedicated demo account once."""
    connection.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS data_migrations "
        "(name VARCHAR(128) PRIMARY KEY, applied_at DATETIME NOT NULL)"
    )
    already_applied = connection.execute(
        text("SELECT 1 FROM data_migrations WHERE name = :name"),
        {"name": "legacy_users_to_demo_user"},
    ).first()
    if already_applied:
        return

    tables = inspect(connection).get_table_names()
    for table_name in (
        "tasks",
        "memories",
        "feedback_events",
        "knowledge_states",
        "agent_runs",
    ):
        if table_name in tables:
            columns = {column["name"] for column in inspect(connection).get_columns(table_name)}
            if "user_id" in columns:
                connection.exec_driver_sql(
                    f"UPDATE {table_name} SET user_id = 'demo-user' "
                    "WHERE user_id IS NOT NULL AND user_id <> 'demo-user'"
                )
    connection.execute(
        text("INSERT INTO data_migrations (name, applied_at) VALUES (:name, :applied_at)"),
        {"name": "legacy_users_to_demo_user", "applied_at": datetime.now(timezone.utc)},
    )


def _ensure_demo_account() -> None:
    """Create or update the configured demo account without storing credentials in code."""
    from app.core.security import hash_password
    from app.schemas.auth import normalize_email
    from app.infrastructure.models.auth import UserRecord

    settings = get_settings()
    if not settings.demo_email or not settings.demo_password:
        return
    email = normalize_email(settings.demo_email)
    with SessionLocal() as session:
        user = session.get(UserRecord, "demo-user")
        owner = session.scalar(select(UserRecord).where(UserRecord.email == email))
        if owner is not None and owner.id != "demo-user":
            raise RuntimeError("DEMO_EMAIL is already used by another account")
        now = datetime.now(timezone.utc)
        if user is None:
            user = UserRecord(
                id="demo-user",
                email=email,
                password_hash=hash_password(settings.demo_password),
                created_at=now,
            )
            session.add(user)
        else:
            user.email = email
            user.password_hash = hash_password(settings.demo_password)
        session.commit()


def _upgrade_duration_schema(connection) -> None:
    from sqlalchemy import text
    from app.memory.durations import parse_duration
    inspector = inspect(connection)
    if "memories" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("memories")}
    for name, kind in {"preferred_minutes": "INTEGER", "max_minutes": "INTEGER",
                       "duration_source": "VARCHAR(16)", "replaced_by_id": "VARCHAR(32)",
                       "supersedes_id": "VARCHAR(32)"}.items():
        if name not in existing:
            connection.exec_driver_sql(f"ALTER TABLE memories ADD COLUMN {name} {kind}")
    rows = connection.execute(text("SELECT id, content FROM memories WHERE memory_type = 'task_preference' AND duration_source IS NULL")).all()
    for row in rows:
        preferred, maximum = parse_duration(row.content)
        connection.execute(text("UPDATE memories SET preferred_minutes=:p, max_minutes=:m, duration_source=:s WHERE id=:id"),
                           {"p": preferred, "m": maximum, "s": "parsed" if preferred or maximum else "unresolved", "id": row.id})


def _upgrade_memory_scope(connection) -> None:
    inspector = inspect(connection)
    if "memories" not in inspector.get_table_names():
        return
    if "scope" not in {column["name"] for column in inspector.get_columns("memories")}:
        connection.exec_driver_sql("ALTER TABLE memories ADD COLUMN scope VARCHAR(16)")
    # Old records keep their original course / knowledge-point boundary.
    connection.exec_driver_sql(
        "UPDATE memories SET scope = CASE WHEN knowledge_point IS NOT NULL "
        "THEN 'knowledge_point' ELSE 'course' END WHERE scope IS NULL"
    )


def _upgrade_tasks_schema(connection) -> None:
    """Preserve existing SQLite tasks while adding review scheduling."""
    inspector = inspect(connection)
    if "tasks" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("tasks")}
        if "due_at" not in columns:
            connection.exec_driver_sql("ALTER TABLE tasks ADD COLUMN due_at DATETIME")


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
