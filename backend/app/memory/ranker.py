"""记忆排序策略：确认记忆优先，候选记忆靠后。"""

from datetime import datetime, timezone

from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import ConfirmationStatus, MemoryType


def rank_memories(memories: list[Memory]) -> list[Memory]:
    now = datetime.now(timezone.utc)

    def key(memory: Memory) -> tuple[int, int, float, float, int]:
        confirmed = int(memory.confirmation_status == ConfirmationStatus.CONFIRMED)
        last_used = memory.created_at if memory.memory_type in (MemoryType.TASK_PREFERENCE, MemoryType.EXPLANATION_PREFERENCE) else memory.last_used_at or memory.created_at
        if last_used.tzinfo is None:
            last_used = last_used.replace(tzinfo=timezone.utc)
        age_seconds = max(0.0, (now - last_used).total_seconds())
        specificity = {"global": 0, "course": 1, "knowledge_point": 2}.get(memory.scope, 1)
        return confirmed, specificity, -age_seconds, memory.confidence, memory.use_count

    return sorted(memories, key=key, reverse=True)
