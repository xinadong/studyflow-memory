"""FastAPI dependency providers."""

from collections.abc import Generator
from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import SESSION_COOKIE_NAME, hash_session_token
from app.infrastructure.database import get_session
from app.infrastructure.models.auth import AuthSessionRecord, UserRecord
from app.infrastructure.repositories.sqlalchemy_memory_repository import (
    SqlAlchemyMemoryRepository,
)


def get_db() -> Generator[Session, None, None]:
    yield from get_session()


def get_memory_repository(db: Session = Depends(get_db)) -> SqlAlchemyMemoryRepository:
    return SqlAlchemyMemoryRepository(db)


def auth_required() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "auth_required", "message": "请先登录"},
    )


def get_current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> UserRecord:
    if not session_token:
        raise auth_required()
    record = db.scalar(
        select(AuthSessionRecord).where(
            AuthSessionRecord.token_hash == hash_session_token(session_token),
            AuthSessionRecord.revoked_at.is_(None),
            AuthSessionRecord.expires_at > datetime.now(timezone.utc),
        )
    )
    if record is None:
        raise auth_required()
    user = db.get(UserRecord, record.user_id)
    if user is None:
        raise auth_required()
    return user


def get_llm():
    from app.infrastructure.llm.adapter import get_llm_adapter

    return get_llm_adapter()


def get_agent_service(db: Session = Depends(get_db), llm=Depends(get_llm)):
    from app.agents.orchestrator import AgentService

    return AgentService(db, SqlAlchemyMemoryRepository(db), llm)
