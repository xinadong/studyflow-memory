"""记忆排序策略：确认记忆优先，候选记忆靠后。"""

from datetime import datetime, timezone

from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import ConfirmationStatus


def rank_memories(memories: list[Memory]) -> list[Memory]:
    now = datetime.now(timezone.utc)

    def key(memory: Memory) -> tuple[int, float, float, int]:
        confirmed = int(memory.confirmation_status == ConfirmationStatus.CONFIRMED)
        last_used = memory.last_used_at or memory.created_at
        if last_used.tzinfo is None:
            last_used = last_used.replace(tzinfo=timezone.utc)
        age_seconds = max(0.0, (now - last_used).total_seconds())
        return confirmed, memory.confidence, -age_seconds, memory.use_count

    return sorted(memories, key=key, reverse=True)
