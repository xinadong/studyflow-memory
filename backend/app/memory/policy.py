"""记忆写入、确认和删除策略。"""

from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import ConfirmationStatus, MemoryType


def status_for_feedback(*, explicit: bool) -> ConfirmationStatus:
    """明确反馈直接确认，模型推断保留为候选。"""
    return ConfirmationStatus.CONFIRMED if explicit else ConfirmationStatus.PENDING


def build_memory_from_feedback(
    *,
    user_id: str,
    memory_type: MemoryType,
    course: str,
    content: str,
    explicit: bool,
    task_type: str | None = None,
    knowledge_point: str | None = None,
    source_feedback: str | None = None,
    confidence: float = 0.5,
) -> Memory:
    return Memory(
        user_id=user_id,
        memory_type=memory_type,
        course=course,
        content=content,
        task_type=task_type,
        knowledge_point=knowledge_point,
        source_feedback=source_feedback,
        confidence=confidence,
        confirmation_status=status_for_feedback(explicit=explicit),
    )


def can_directly_influence(memory: Memory) -> bool:
    return memory.is_usable and memory.confirmation_status == ConfirmationStatus.CONFIRMED


def soft_delete_memory(memory: Memory) -> Memory:
    memory.active = False
    return memory


def archive_memory(memory: Memory) -> Memory:
    memory.confirmation_status = ConfirmationStatus.ARCHIVED
    return memory
