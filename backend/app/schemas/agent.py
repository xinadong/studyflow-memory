"""Agent 计划、理解检验和恢复 API 模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.value_objects.memory_type import BlockType


class ImportedTaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: datetime


class PlanRequest(BaseModel):
    user_id: str
    course: str
    goal: str = Field(min_length=1)
    available_minutes: int = Field(ge=1, le=240)
    task_type: str = "study"
    knowledge_point: str | None = None
    imported_tasks: list[ImportedTaskInput] = Field(default_factory=list, max_length=50)


class TaskOut(BaseModel):
    id: str
    title: str
    description: str
    duration_minutes: int
    task_type: str
    knowledge_point: str | None = None
    due_at: datetime | None = None


class PlanResponse(BaseModel):
    tasks: list[TaskOut]
    explanation: str
    retrieved_memory_ids: list[str]
    used_memory_ids: list[str]
    candidate_memory_ids: list[str]
    metrics: dict[str, int]


class UnderstandingCheckRequest(BaseModel):
    user_id: str
    course: str
    knowledge_point: str
    task_type: str = "study"
    material: str = ""
    level: Literal["recall", "relate", "transfer"] = "recall"
    answer: str | None = None


class UnderstandingCheckResponse(BaseModel):
    level: str
    assessed_level: str | None = None
    question: str
    feedback: str
    missing_dimensions: list[str]
    retrieved_memory_ids: list[str]
    used_memory_ids: list[str]
    candidate_memory_ids: list[str]
    metrics: dict[str, int]


class RecoveryRequest(BaseModel):
    user_id: str
    course: str
    block_type: BlockType
    context: str = ""
    task_type: str = "study"
    knowledge_point: str | None = None
    user_acceptance: bool | None = None


class RecoveryResponse(BaseModel):
    action: str
    reason: str
    retrieved_memory_ids: list[str]
    used_memory_ids: list[str]
    candidate_memory_ids: list[str]
    metrics: dict[str, int]
