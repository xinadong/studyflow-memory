"""Validated tool schemas and server-side execution for the learning Agent."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.agents.tools.adjust_learning_plan import adjust_learning_plan
from app.agents.tools.generate_recovery_action import generate_recovery_action
from app.agents.tools.generate_understanding_question import generate_understanding_question
from app.agents.tools.get_learning_state import get_learning_state
from app.agents.tools.split_learning_task import split_learning_task
from app.domain.value_objects.memory_type import BlockType
from app.infrastructure.llm.adapter import LLMCallError


class LearningStateArgs(BaseModel):
    user_id: str
    course: str


class SplitTaskArgs(BaseModel):
    goal: str = Field(min_length=1)
    available_minutes: int = Field(ge=1, le=240)
    preferred_minutes: int | None = Field(default=None, ge=1, le=240)
    task_type: str = "study"
    knowledge_point: str | None = None


class AdjustPlanArgs(BaseModel):
    task: dict[str, Any]
    available_minutes: int = Field(ge=1, le=240)
    preferred_minutes: int | None = Field(default=None, ge=1, le=240)


class UnderstandingQuestionArgs(BaseModel):
    knowledge_point: str = Field(min_length=1)
    level: Literal["recall", "relate", "transfer"] = "recall"
    example_first: bool = False
    explanation_style: Literal["example_first", "definition_first", "diagram_first"] | None = None


class RecoveryActionArgs(BaseModel):
    block_type: BlockType
    context: str = ""
    knowledge_point: str | None = None
    preferred_action: str | None = Field(default=None, min_length=1)


ARGUMENT_MODELS = {
    "get_learning_state": LearningStateArgs,
    "split_learning_task": SplitTaskArgs,
    "adjust_learning_plan": AdjustPlanArgs,
    "generate_understanding_question": UnderstandingQuestionArgs,
    "generate_recovery_action": RecoveryActionArgs,
}


TOOL_DESCRIPTIONS = {
    "get_learning_state": "读取指定用户和课程的任务与知识状态。",
    "split_learning_task": "把课程目标拆成一个1到240分钟且不超过当前可用时间的可执行微任务。",
    "adjust_learning_plan": "根据已确认的时长偏好调整已生成任务。",
    "generate_understanding_question": "生成复述、关联或迁移层级的一次一问理解检验。",
    "generate_recovery_action": "根据阻塞类型生成一个低压力恢复动作。",
}


PLAN_TOOL_NAMES = ("get_learning_state", "split_learning_task", "adjust_learning_plan")
CHECK_TOOL_NAMES = ("get_learning_state", "generate_understanding_question")
RECOVERY_TOOL_NAMES = ("get_learning_state", "generate_recovery_action")


def tool_definitions(names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "parameters": _inline_local_schema_refs(
                    ARGUMENT_MODELS[name].model_json_schema()
                ),
            },
        }
        for name in names
    ]


def _inline_local_schema_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Expand Pydantic's local ``$defs``/``$ref`` before provider submission.

    Some OpenAI-compatible providers reject otherwise valid JSON Schema
    references in tool definitions.  Tool schemas are small, so inlining
    local definitions keeps the wire format portable without changing the
    server-side Pydantic validation contract.
    """
    definitions = schema.get("$defs", {})

    def expand(value: Any, stack: tuple[str, ...] = ()) -> Any:
        if isinstance(value, list):
            return [expand(item, stack) for item in value]
        if not isinstance(value, dict):
            return value

        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            name = reference.removeprefix("#/$defs/")
            target = definitions.get(name)
            if target is not None and name not in stack:
                merged = deepcopy(target)
                merged.update({key: item for key, item in value.items() if key != "$ref"})
                return expand(merged, (*stack, name))

        return {
            key: expand(item, stack)
            for key, item in value.items()
            if key != "$defs"
        }

    return expand(schema)


def execute_tool(session: Session, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    model = ARGUMENT_MODELS.get(name)
    if model is None:
        raise LLMCallError("unknown_tool", "模型调用失败：模型选择了未授权工具")
    try:
        validated = model.model_validate(arguments)
    except ValidationError as error:
        raise LLMCallError("invalid_tool_arguments", "模型调用失败：工具参数无效") from error

    values = validated.model_dump()
    if name == "get_learning_state":
        return get_learning_state(session, **values)
    if name == "split_learning_task":
        return split_learning_task(**values)
    if name == "adjust_learning_plan":
        return adjust_learning_plan(**values)
    if name == "generate_understanding_question":
        return generate_understanding_question(**values)
    if name == "generate_recovery_action":
        return generate_recovery_action(**values)
    raise LLMCallError("unknown_tool", "模型调用失败：模型选择了未授权工具")
