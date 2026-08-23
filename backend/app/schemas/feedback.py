"""用户反馈 API 模型。"""

from pydantic import BaseModel

from app.domain.value_objects.memory_type import BlockType, MemoryType


class FeedbackCreate(BaseModel):
    user_id: str
    course: str
    feedback_type: MemoryType | None = None
    content: str
    explicit: bool | None = None
    task_type: str | None = None
    knowledge_point: str | None = None
    block_type: BlockType | None = None


class FeedbackResponse(BaseModel):
    feedback_id: str
    memories: list[dict]
