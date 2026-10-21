"""Persistent learning tasks and user-confirmed reviews."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

TaskStatus = Literal["pending", "active", "completed", "deferred"]


class TaskCreate(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    course: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10000)
    task_type: str = Field(default="study", min_length=1, max_length=128)
    knowledge_point: str | None = Field(default=None, max_length=255)
    duration_minutes: int = Field(ge=1, le=240)
    due_at: AwareDatetime | None = None

    @field_validator("due_at")
    @classmethod
    def normalize_date(cls, value):
        return value.astimezone(timezone.utc) if value else value

    @field_validator("user_id", "course", "title", "task_type", "id")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def review_date_required(self):
        if self.task_type == "review" and self.due_at is None:
            raise ValueError("review tasks require due_at")
        return self


class TaskUpdate(BaseModel):
    status: TaskStatus


class TaskOut(BaseModel):
    id: str
    course: str
    title: str
    description: str
    task_type: str
    knowledge_point: str | None
    duration_minutes: int
    status: TaskStatus
    due_at: datetime | None
    created_at: datetime


class TaskList(BaseModel):
    items: list[TaskOut]
