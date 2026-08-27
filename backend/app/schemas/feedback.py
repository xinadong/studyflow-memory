"""用户反馈 API 模型。"""

from pydantic import BaseModel, Field, field_validator

from app.domain.value_objects.memory_type import BlockType, MemoryType


class FeedbackCreate(BaseModel):
    user_id: str
    course: str
    feedback_type: MemoryType | None = None
    content: str = Field(min_length=1)
    explicit: bool | None = None
    task_type: str | None = None
    knowledge_point: str | None = None
    block_type: BlockType | None = None

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value


class FeedbackResponse(BaseModel):
    feedback_id: str
    memories: list[dict]
