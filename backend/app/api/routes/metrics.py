"""Runtime metrics route."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.infrastructure.models.agent_runs import AgentRunRecord

router = APIRouter()


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    runs = db.scalars(select(AgentRunRecord).order_by(AgentRunRecord.created_at.desc())).all()
    successful = sum(run.status == "success" for run in runs)
    failed = sum(run.status == "failed" for run in runs)
    operation_counts: dict[str, int] = {}
    for run in runs:
        operation_counts[run.operation] = operation_counts.get(run.operation, 0) + 1
    return {
        "agent_runs": len(runs),
        "success_count": successful,
        "failure_count": failed,
        "successful_runs": successful,
        "failed_runs": failed,
        "input_tokens": sum(run.input_tokens for run in runs),
        "memory_tokens": sum(run.memory_tokens for run in runs),
        "memory_tokens_semantics": "estimated_injected_confirmed_context",
        "output_tokens": sum(run.output_tokens for run in runs),
        "retrieval_latency_ms": sum(run.retrieval_latency_ms for run in runs),
        "model_latency_ms": sum(run.model_latency_ms for run in runs),
        "retry_count": sum(run.retry_count or 0 for run in runs),
        "models": sorted({run.model for run in runs if run.model}),
        "statuses": {
            "success": successful,
            "failed": failed,
        },
        "operation_counts": operation_counts,
        "errors": [
            {
                "operation": run.operation,
                "model": run.model,
                "status": run.status,
                "retry_count": run.retry_count or 0,
                "error_code": run.error_code,
                "error_message": run.error_message,
                "tool_calls": run.tool_calls or [],
            }
            for run in runs
            if run.status == "failed"
        ],
        "runs": [
            {
                "id": run.id,
                "operation": run.operation,
                "user_id": run.user_id,
                "model": run.model,
                "status": run.status,
                "retry_count": run.retry_count or 0,
                "error_code": run.error_code,
                "error_message": run.error_message,
                "tool_calls": run.tool_calls or [],
            }
            for run in runs
        ],
        "retrieved_memory_ids": [item for run in runs for item in (run.retrieved_memory_ids or [])],
        "used_memory_ids": [item for run in runs for item in (run.used_memory_ids or [])],
    }
