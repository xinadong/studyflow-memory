"""反馈记忆领域实体。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from app.domain.value_objects.memory_type import (
    BlockType,
    ConfirmationStatus,
    MemoryType,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Memory:
    user_id: str
    memory_type: MemoryType
    course: str
    content: str
    task_type: str | None = None
    knowledge_point: str | None = None
    block_type: BlockType | None = None
    source_feedback: str | None = None
    confidence: float = 0.5
    confirmation_status: ConfirmationStatus = ConfirmationStatus.PENDING
    active: bool = True
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=_utcnow)
    last_used_at: datetime | None = None
    use_count: int = 0

    def __post_init__(self) -> None:
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        if self.use_count < 0:
            raise ValueError("use_count cannot be negative")

    @property
    def is_usable(self) -> bool:
        """硬过滤规则：pending可作为候选，confirmed可直接使用。"""
        return self.active and self.confirmation_status in (
            ConfirmationStatus.PENDING,
            ConfirmationStatus.CONFIRMED,
        )
