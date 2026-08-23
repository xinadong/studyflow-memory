"""User feedback route."""

import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_llm, get_memory_repository
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import BlockType, ConfirmationStatus, MemoryType
from app.infrastructure.llm.adapter import LLMAdapter, LLMCallError, LLMResult
from app.infrastructure.models.feedback import FeedbackRecord
from app.infrastructure.repositories.sqlalchemy_memory_repository import SqlAlchemyMemoryRepository
from app.infrastructure.telemetry.agent_run import record_agent_run
from app.schemas.feedback import FeedbackCreate, FeedbackResponse
from app.schemas.memory import MemoryOut

router = APIRouter()
PROMPT_PATH = Path(__file__).resolve().parents[2] / "agents" / "prompts" / "memory_extraction.txt"


def _classify_feedback(payload: FeedbackCreate, llm: LLMAdapter) -> tuple[
    MemoryType, bool, float, BlockType | None, LLMResult
]:
    started = perf_counter()
    try:
        result = llm.chat([
            {
                "role": "system",
                "content": (
                    PROMPT_PATH.read_text(encoding="utf-8").strip()
                    + "\nReturn only JSON with memory_type, explicit, confidence, block_type. "
                    + "memory_type must be task_preference, explanation_preference, "
                    + "knowledge_state, recovery_experience, or review_schedule. "
                    + "block_type must be null, time, too_hard, distraction, or fatigue."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "course": payload.course,
                    "content": payload.content,
                    "task_type": payload.task_type,
                    "knowledge_point": payload.knowledge_point,
                }, ensure_ascii=False),
            },
        ])
        try:
            data = json.loads(result.text or "")
            memory_type = MemoryType(data["memory_type"])
            explicit = data["explicit"]
            confidence = float(data.get("confidence", 0.5))
            block_value = data.get("block_type")
            block_type = BlockType(block_value) if block_value else None
            if not isinstance(explicit, bool):
                raise TypeError("explicit must be bool")
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, KeyError, TypeError) as error:
            output_error = LLMCallError(
                "invalid_model_output",
                "模型调用失败：反馈分类结果格式错误",
                retry_count=result.retry_count,
            )
            output_error.input_tokens = result.input_tokens
            output_error.output_tokens = result.output_tokens
            output_error.model = result.model
            raise output_error from error
        return memory_type, explicit, confidence, block_type, result
    except LLMCallError as error:
        error.model_latency_ms = int((perf_counter() - started) * 1000)
        raise


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def create_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    repo: SqlAlchemyMemoryRepository = Depends(get_memory_repository),
    llm: LLMAdapter = Depends(get_llm),
):
    classification_result = None
    if payload.feedback_type is None:
        try:
            feedback_type, explicit, confidence, classified_block_type, classification_result = _classify_feedback(
                payload, llm
            )
            if payload.explicit is not None:
                explicit = payload.explicit
        except LLMCallError as error:
            record_agent_run(
                db,
                operation="feedback_classification",
                user_id=payload.user_id,
                model=getattr(llm, "model", None),
                status="failed",
                input_tokens=getattr(error, "input_tokens", 0),
                output_tokens=getattr(error, "output_tokens", 0),
                model_latency_ms=getattr(error, "model_latency_ms", 0),
                retry_count=error.retry_count,
                error_code=error.code,
                error_message=error.message,
            )
            raise
    else:
        feedback_type = payload.feedback_type
        explicit = bool(payload.explicit) if payload.explicit is not None else False
        confidence = 0.5
        classified_block_type = None

    block_type = payload.block_type or classified_block_type
    feedback_id = uuid4().hex
    db.add(FeedbackRecord(
        id=feedback_id, user_id=payload.user_id, course=payload.course,
        feedback_type=feedback_type.value, content=payload.content,
        explicit=explicit, created_at=datetime.now(timezone.utc),
    ))
    memory = Memory(
        user_id=payload.user_id, memory_type=feedback_type,
        course=payload.course, content=payload.content,
        task_type=payload.task_type, knowledge_point=payload.knowledge_point,
        block_type=block_type, source_feedback=feedback_id,
        confidence=confidence,
        confirmation_status=(ConfirmationStatus.CONFIRMED if explicit else ConfirmationStatus.PENDING),
    )
    db.commit()
    saved = repo.add(memory)
    if classification_result is not None:
        record_agent_run(
            db,
            operation="feedback_classification",
            user_id=payload.user_id,
            input_tokens=classification_result.input_tokens,
            output_tokens=classification_result.output_tokens,
            model_latency_ms=classification_result.latency_ms,
            model=classification_result.model or getattr(llm, "model", None),
            status="success",
            retry_count=classification_result.retry_count,
        )
    return {"feedback_id": feedback_id, "memories": [MemoryOut.model_validate(saved).model_dump(mode="json")]}
