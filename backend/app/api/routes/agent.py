"""Agent planning, understanding-check and recovery routes."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_agent_service
from app.agents.orchestrator import AgentService
from app.infrastructure.llm.adapter import LLMCallError
from app.schemas.agent import (
    PlanRequest, PlanResponse, RecoveryRequest, RecoveryResponse,
    UnderstandingCheckRequest, UnderstandingCheckResponse,
)

router = APIRouter()


@router.post("/plan", response_model=PlanResponse)
def plan(request: PlanRequest, service: AgentService = Depends(get_agent_service)):
    try:
        return service.plan(**request.model_dump())
    except LLMCallError as error:
        service.record_failure("plan", request.user_id, error)
        raise


@router.post("/check", response_model=UnderstandingCheckResponse)
def check(request: UnderstandingCheckRequest, service: AgentService = Depends(get_agent_service)):
    try:
        return service.check(**request.model_dump())
    except LLMCallError as error:
        service.record_failure("check", request.user_id, error)
        raise


@router.post("/recover", response_model=RecoveryResponse)
def recover(request: RecoveryRequest, service: AgentService = Depends(get_agent_service)):
    try:
        return service.recover(**request.model_dump())
    except LLMCallError as error:
        service.record_failure("recover", request.user_id, error)
        raise
