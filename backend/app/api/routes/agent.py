"""Agent planning, understanding-check and recovery routes."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_agent_service, get_current_user
from app.agents.orchestrator import AgentService
from app.infrastructure.models.auth import UserRecord
from app.infrastructure.llm.adapter import LLMCallError
from app.schemas.agent import (
    PlanRequest, PlanResponse, RecoveryRequest, RecoveryResponse,
    UnderstandingCheckRequest, UnderstandingCheckResponse,
)

router = APIRouter()


@router.post("/plan", response_model=PlanResponse)
def plan(
    request: PlanRequest,
    user: UserRecord = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    try:
        return service.plan(user_id=user.id, **request.model_dump(exclude={"user_id"}))
    except LLMCallError as error:
        service.record_failure("plan", user.id, error)
        raise


@router.post("/check", response_model=UnderstandingCheckResponse)
def check(
    request: UnderstandingCheckRequest,
    user: UserRecord = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    try:
        return service.check(user_id=user.id, **request.model_dump(exclude={"user_id"}))
    except LLMCallError as error:
        service.record_failure("check", user.id, error)
        raise


@router.post("/recover", response_model=RecoveryResponse)
def recover(
    request: RecoveryRequest,
    user: UserRecord = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    try:
        return service.recover(user_id=user.id, **request.model_dump(exclude={"user_id"}))
    except LLMCallError as error:
        service.record_failure("recover", user.id, error)
        raise
