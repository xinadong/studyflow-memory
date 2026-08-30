"""User feedback route."""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_llm, get_memory_repository
from app.agents.orchestrator import _json_object
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import BlockType, ConfirmationStatus, MemoryType
from app.infrastructure.llm.adapter import LLMAdapter, LLMCallError, LLMResult
from app.infrastructure.models.feedback import FeedbackRecord
from app.infrastructure.repositories.sqlalchemy_memory_repository import SqlAlchemyMemoryRepository
from app.infrastructure.telemetry.agent_run import record_agent_run
from app.memory.review_schedule import parse_review_interval_days
from app.schemas.feedback import FeedbackCreate, FeedbackResponse
from app.schemas.memory import MemoryOut

router = APIRouter()
PROMPT_PATH = Path(__file__).resolve().parents[2] / "agents" / "prompts" / "memory_extraction.txt"


@dataclass
class ClassificationTrace:
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    retry_count: int = 0
    format_repair_count: int = 0


def _add_result(trace: ClassificationTrace, result: LLMResult) -> None:
    trace.model = result.model or trace.model
    trace.input_tokens += result.input_tokens
    trace.output_tokens += result.output_tokens
    trace.latency_ms += result.latency_ms
    trace.retry_count += result.retry_count


def _add_error(trace: ClassificationTrace, error: LLMCallError) -> None:
    trace.model = error.model or trace.model
    trace.input_tokens += error.input_tokens
    trace.output_tokens += error.output_tokens
    trace.latency_ms += error.model_latency_ms
    trace.retry_count += error.retry_count


def _classification_data(text: str | None) -> tuple[MemoryType, bool, float, BlockType | None]:
    try:
        data = _json_object(text)
        memory_type = MemoryType(data["memory_type"])
        if memory_type == MemoryType.KNOWLEDGE_STATE:
            raise LLMCallError(
                "unsupported_memory_type",
                "知识状态必须通过理解检验提交",
                status_code=422,
            )
        explicit = data["explicit"]
        confidence = float(data["confidence"])
        block_value = data.get("block_type")
        block_type = BlockType(block_value) if block_value else None
        if not isinstance(explicit, bool):
            raise TypeError("explicit must be bool")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence out of range")
    except LLMCallError:
        raise
    except (ValueError, KeyError, TypeError) as error:
        raise LLMCallError(
            "invalid_model_output",
            "模型调用失败：反馈分类结果格式错误",
        ) from error
    return memory_type, explicit, confidence, block_type


def _correct_memory_type_from_explicit_cue(
    content: str,
    memory_type: MemoryType,
) -> MemoryType:
    """Guard the model classifier with narrow, unambiguous user cues.

    The model is still responsible for the general classification, but a
    clear phrase such as "先看例子" must not be persisted as a task-duration
    preference just because the provider returned the wrong enum.  Only
    high-signal cues override the model; ambiguous feedback remains unchanged.
    """
    # Strong schedule and recovery language must win over generic words such
    # as "分钟", "任务" or "例子".  Real users often combine a block reason
    # with a small recovery action (for example, "学累了休息5分钟").
    if _is_review_schedule_cue(content):
        return MemoryType.REVIEW_SCHEDULE
    recovery_type = _recovery_type_from_content(content)
    if recovery_type is not None:
        return MemoryType.RECOVERY_EXPERIENCE

    explanation_cues = (
        "示例优先", "例子优先", "先看示例", "先给我看示例",
        "先看例子", "先给我看例子", "先看案例",
        "图示优先", "先看图示", "先看流程图", "先画图",
        "定义优先", "先看定义", "先讲定义",
    )
    task_cues = (
        "分钟", "任务时长", "任务时间", "拆分任务", "提醒强度",
    )
    explanation_match = any(cue in content for cue in explanation_cues) or bool(
        re.search(r"先.{0,6}(?:示例|例子|案例|图示|流程图|定义|概念)", content)
    )
    task_match = any(cue in content for cue in task_cues)
    if explanation_match and task_match:
        return memory_type
    if explanation_match:
        return MemoryType.EXPLANATION_PREFERENCE
    if task_match:
        return MemoryType.TASK_PREFERENCE
    return memory_type


def _is_review_schedule_cue(content: str) -> bool:
    if parse_review_interval_days(content) is None:
        return False
    return any(marker in content for marker in ("复习", "间隔", "隔"))


def _recovery_type_from_content(content: str) -> BlockType | None:
    recovery_cues = (
        (BlockType.FATIGUE, ("学累了", "累了", "很累", "疲劳", "困", "没精神", "状态不好", "想休息")),
        (BlockType.TIME, ("没时间", "时间不够", "时间不足", "来不及", "只剩")),
        (BlockType.TOO_HARD, ("太难", "卡住", "不会", "不理解", "看不懂", "难住")),
        (BlockType.DISTRACTION, ("杂事", "被打断", "分心", "干扰", "坐不住")),
    )
    for block_type, cues in recovery_cues:
        if any(cue in content for cue in cues):
            return block_type
    return None


def _infer_block_type_from_content(content: str) -> BlockType | None:
    """Infer a recovery scope only after recovery has won classification."""
    return _recovery_type_from_content(content)


def _json_mode_call(
    llm: LLMAdapter,
    messages: list[dict],
    trace: ClassificationTrace,
) -> LLMResult:
    try:
        result = llm.chat(messages, response_format={"type": "json_object"})
    except LLMCallError as error:
        if error.code != "provider_rejected":
            raise
        _add_error(trace, error)
        result = llm.chat(messages)
    _add_result(trace, result)
    return result


def _classify_feedback(payload: FeedbackCreate, llm: LLMAdapter) -> tuple[
    MemoryType, bool, float, BlockType | None, ClassificationTrace
]:
    started = perf_counter()
    trace = ClassificationTrace(model=getattr(llm, "model", ""))
    messages = [
        {
            "role": "system",
            "content": (
                PROMPT_PATH.read_text(encoding="utf-8").strip()
                + "\nReturn only JSON with memory_type, explicit, confidence, block_type. "
                + "memory_type must be task_preference, explanation_preference, "
                + "recovery_experience, or review_schedule. "
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
    ]
    try:
        result = _json_mode_call(llm, messages, trace)
        try:
            memory_type, explicit, confidence, block_type = _classification_data(result.text)
        except LLMCallError as first_error:
            if first_error.code == "unsupported_memory_type":
                raise first_error
            trace.format_repair_count = 1
            repair_messages = [
                *messages,
                {"role": "assistant", "content": result.text or ""},
                {
                    "role": "user",
                    "content": (
                        "上一条分类格式无效。只修复格式，不改变判断；"
                        "仅返回一个包含 memory_type、explicit、confidence、block_type 的 JSON 对象。"
                    ),
                },
            ]
            repaired = _json_mode_call(llm, repair_messages, trace)
            try:
                memory_type, explicit, confidence, block_type = _classification_data(repaired.text)
            except LLMCallError as repaired_error:
                repaired_error.format_repair_count = 1
                raise repaired_error from first_error
        memory_type = _correct_memory_type_from_explicit_cue(payload.content, memory_type)
        if memory_type == MemoryType.RECOVERY_EXPERIENCE:
            block_type = block_type or _infer_block_type_from_content(payload.content)
        else:
            block_type = None
        return memory_type, explicit, confidence, block_type, trace
    except LLMCallError as error:
        error.model = trace.model or getattr(llm, "model", None)
        error.input_tokens += trace.input_tokens
        error.output_tokens += trace.output_tokens
        error.model_latency_ms += max(
            trace.latency_ms,
            int((perf_counter() - started) * 1000),
        )
        error.retry_count += trace.retry_count
        error.format_repair_count = max(error.format_repair_count, trace.format_repair_count)
        raise


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def create_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    repo: SqlAlchemyMemoryRepository = Depends(get_memory_repository),
    llm: LLMAdapter = Depends(get_llm),
):
    classification_result = None
    if payload.feedback_type == MemoryType.KNOWLEDGE_STATE:
        raise LLMCallError(
            "unsupported_memory_type",
            "知识状态必须通过理解检验提交",
            status_code=422,
        )
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
                format_repair_count=error.format_repair_count,
                error_code=error.code,
                error_message=error.message,
            )
            raise
    else:
        feedback_type = payload.feedback_type
        explicit = bool(payload.explicit) if payload.explicit is not None else False
        confidence = 0.5
        classified_block_type = (
            _infer_block_type_from_content(payload.content)
            if feedback_type == MemoryType.RECOVERY_EXPERIENCE
            else None
        )

    block_type = payload.block_type or classified_block_type
    if feedback_type != MemoryType.RECOVERY_EXPERIENCE:
        block_type = None
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
    try:
        saved = repo.add(memory, commit=False)
    except Exception:
        db.rollback()
        raise
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
            format_repair_count=classification_result.format_repair_count,
        )
    else:
        db.commit()
    return {"feedback_id": feedback_id, "memories": [MemoryOut.model_validate(saved).model_dump(mode="json")]}
