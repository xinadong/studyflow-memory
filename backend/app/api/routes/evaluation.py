"""Evaluation comparison route."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_agent_service
from app.agents.orchestrator import AgentService
from app.infrastructure.llm.adapter import LLMCallError
from app.schemas.evaluation import EvaluationCompareRequest, EvaluationCompareResponse

router = APIRouter()


@router.post("/evaluation/compare", response_model=EvaluationCompareResponse)
def compare(payload: EvaluationCompareRequest, service: AgentService = Depends(get_agent_service)):
    try:
        with_memory = service.plan(
            **payload.model_dump(),
            persist_task=False,
            operation="evaluation_with_memory",
        )
        without_memory = service.plan(
            user_id=payload.user_id, course=payload.course, goal=payload.goal,
            available_minutes=payload.available_minutes,
            task_type=payload.task_type,
            knowledge_point=payload.knowledge_point,
            use_memory=False,
            persist_task=False,
            operation="evaluation_without_memory",
        )
    except LLMCallError as error:
        service.record_failure("evaluation_compare", payload.user_id, error)
        raise
    delta = {
        "duration_minutes": with_memory["tasks"][0]["duration_minutes"] - without_memory["tasks"][0]["duration_minutes"],
        "memory_count": len(with_memory["used_memory_ids"]),
        "memory_tokens": with_memory["metrics"].get("memory_tokens", 0),
        "with_memory_operation": "evaluation_with_memory",
        "without_memory_operation": "evaluation_without_memory",
    }
    return {"without_memory": without_memory, "with_memory": with_memory, "delta": delta}
