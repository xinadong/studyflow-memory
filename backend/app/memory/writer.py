"""记忆写入入口，集中执行仓储保存。"""

from app.domain.entities.memory import Memory
from app.domain.repositories.memory_repository import MemoryRepository


def save_memory(repository: MemoryRepository, memory: Memory, *, commit: bool = True) -> Memory:
    if commit:
        return repository.add(memory)
    return repository.add(memory, commit=False)


def record_use(memory: Memory) -> Memory:
    from datetime import datetime, timezone

    memory.last_used_at = datetime.now(timezone.utc)
    memory.use_count += 1
    return memory


def save_feedback_memory(
    repository: MemoryRepository,
    *,
    user_id: str,
    memory_type,
    course: str,
    content: str,
    explicit: bool,
    task_type: str | None = None,
    knowledge_point: str | None = None,
    block_type=None,
    source_feedback: str | None = None,
    confidence: float = 0.5,
    commit: bool = True,
) -> Memory:
    from app.memory.policy import build_memory_from_feedback

    memory = build_memory_from_feedback(
        user_id=user_id,
        memory_type=memory_type,
        course=course,
        content=content,
        explicit=explicit,
        task_type=task_type,
        knowledge_point=knowledge_point,
        source_feedback=source_feedback,
        confidence=confidence,
    )
    memory_type_value = memory_type.value if hasattr(memory_type, "value") else memory_type
    if memory_type_value == "recovery_experience":
        memory.block_type = block_type
    return save_memory(repository, memory, commit=commit)
