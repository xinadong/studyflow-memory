"""FastAPI dependency providers."""

from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.infrastructure.database import get_session
from app.infrastructure.repositories.sqlalchemy_memory_repository import (
    SqlAlchemyMemoryRepository,
)


def get_db() -> Generator[Session, None, None]:
    yield from get_session()


def get_memory_repository(db: Session = Depends(get_db)) -> SqlAlchemyMemoryRepository:
    return SqlAlchemyMemoryRepository(db)


def get_llm():
    from app.infrastructure.llm.adapter import get_llm_adapter

    return get_llm_adapter()


def get_agent_service(db: Session = Depends(get_db), llm=Depends(get_llm)):
    from app.agents.orchestrator import AgentService

    return AgentService(db, SqlAlchemyMemoryRepository(db), llm)
