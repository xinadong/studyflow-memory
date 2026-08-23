from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.infrastructure.models.agent_runs import AgentRunRecord


def record_agent_run(
    session: Session,
    *,
    operation: str,
    user_id: str | None,
    input_tokens: int = 0,
    memory_tokens: int = 0,
    output_tokens: int = 0,
    retrieval_latency_ms: int = 0,
    model_latency_ms: int = 0,
    retrieved_memory_ids: list[str] | None = None,
    used_memory_ids: list[str] | None = None,
    model: str | None = None,
    status: str = "success",
    tool_calls: list[dict] | None = None,
    retry_count: int = 0,
    error_code: str | None = None,
    error_message: str | None = None,
    user_acceptance: bool | None = None,
) -> AgentRunRecord:
    run = AgentRunRecord(
        id=uuid4().hex,
        user_id=user_id,
        operation=operation,
        input_tokens=input_tokens,
        memory_tokens=memory_tokens,
        output_tokens=output_tokens,
        retrieval_latency_ms=retrieval_latency_ms,
        model_latency_ms=model_latency_ms,
        retrieved_memory_ids=retrieved_memory_ids or [],
        used_memory_ids=used_memory_ids or [],
        model=model,
        status=status,
        tool_calls=tool_calls or [],
        retry_count=retry_count,
        error_code=error_code,
        error_message=error_message,
        user_acceptance=user_acceptance,
        created_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run
