"""记忆 API 的输入输出模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.value_objects.memory_type import (
    BlockType,
    ConfirmationStatus,
    MemoryType,
)


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    memory_type: MemoryType
    course: str
    task_type: str | None
    knowledge_point: str | None
    block_type: BlockType | None
    content: str
    source_feedback: str | None
    confidence: float
    confirmation_status: ConfirmationStatus
    created_at: datetime
    last_used_at: datetime | None
    use_count: int
    active: bool


class MemoryCreate(BaseModel):
    user_id: str
    memory_type: MemoryType
    course: str
    content: str
    task_type: str | None = None
    knowledge_point: str | None = None
    block_type: BlockType | None = None
    source_feedback: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    confirmation_status: ConfirmationStatus = ConfirmationStatus.PENDING


class MemoryUpdate(BaseModel):
    content: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    confirmation_status: ConfirmationStatus | None = None
    active: bool | None = None
    task_type: str | None = None
    knowledge_point: str | None = None
    block_type: BlockType | None = None
    source_feedback: str | None = None


class MemoryList(BaseModel):
    items: list[MemoryOut]
    total: int


class MemoryFilterQuery(BaseModel):
    user_id: str | None = None
    memory_type: MemoryType | None = None
    course: str | None = None
    task_type: str | None = None
    knowledge_point: str | None = None
    block_type: BlockType | None = None
    confirmation_status: ConfirmationStatus | None = None
    active: bool | None = None
