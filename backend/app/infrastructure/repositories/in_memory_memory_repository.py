"""用于契约测试和评测的内存版记忆仓储。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.entities.memory import Memory
from app.domain.repositories.memory_repository import (
    MemoryFilter,
    MemoryRepository,
    MemoryUpdate,
)


def _matches(memory: Memory, filters: MemoryFilter) -> bool:
    fields = (
        (filters.user_id, memory.user_id),
        (filters.memory_type, memory.memory_type),
        (filters.course, memory.course),
        (filters.task_type, memory.task_type),
        (filters.knowledge_point, memory.knowledge_point),
        (filters.block_type, memory.block_type),
        (filters.confirmation_status, memory.confirmation_status),
        (filters.active, memory.active),
    )
    return all(expected is None or expected == actual for expected, actual in fields)


class InMemoryMemoryRepository(MemoryRepository):
    def __init__(self) -> None:
        self._store: dict[str, Memory] = {}

    def add(self, memory: Memory) -> Memory:
        self._store[memory.id] = memory
        return memory

    def get(self, memory_id: str) -> Memory | None:
        return self._store.get(memory_id)

    def list(self, filters: MemoryFilter | None = None) -> list[Memory]:
        values = list(self._store.values())
        if filters is None:
            return values
        return [memory for memory in values if _matches(memory, filters)]

    def update(self, memory_id: str, changes: MemoryUpdate) -> Memory | None:
        memory = self._store.get(memory_id)
        if memory is None:
            return None
        for field_name in (
            "content",
            "confirmation_status",
            "active",
            "task_type",
            "knowledge_point",
            "block_type",
            "source_feedback",
        ):
            value = getattr(changes, field_name)
            if value is not None:
                setattr(memory, field_name, value)
        if changes.confidence is not None:
            memory.confidence = max(0.0, min(1.0, float(changes.confidence)))
        return memory

    def delete(self, memory_id: str) -> bool:
        return self._store.pop(memory_id, None) is not None

    def touch(self, memory_id: str) -> bool:
        memory = self._store.get(memory_id)
        if memory is None:
            return False
        memory.use_count += 1
        memory.last_used_at = datetime.now(timezone.utc)
        return True
