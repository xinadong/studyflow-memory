"""Extract one controlled memory candidate from a feedback event."""

from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from app.memory.policy import build_memory_from_feedback


def extract_memory_from_feedback(
    *, user_id: str, course: str, feedback_type: MemoryType, content: str,
    explicit: bool, task_type: str | None = None, knowledge_point: str | None = None,
    block_type=None, source_feedback: str | None = None,
) -> Memory:
    memory = build_memory_from_feedback(
        user_id=user_id, memory_type=feedback_type, course=course, content=content,
        explicit=explicit, task_type=task_type, knowledge_point=knowledge_point,
        source_feedback=source_feedback,
    )
    if feedback_type == MemoryType.RECOVERY_EXPERIENCE:
        memory.block_type = block_type
    return memory
