"""记忆仓储抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import (
    BlockType,
    ConfirmationStatus,
    MemoryType,
)


@dataclass
class MemoryFilter:
    user_id: str | None = None
    memory_type: MemoryType | None = None
    course: str | None = None
    task_type: str | None = None
    knowledge_point: str | None = None
    block_type: BlockType | None = None
    confirmation_status: ConfirmationStatus | None = None
    active: bool | None = None


@dataclass
class MemoryUpdate:
    content: str | None = None
    confidence: float | None = None
    confirmation_status: ConfirmationStatus | None = None
    active: bool | None = None
    task_type: str | None = None
    knowledge_point: str | None = None
    block_type: BlockType | None = None
    source_feedback: str | None = None


class MemoryRepository(ABC):
    @abstractmethod
    def add(self, memory: Memory) -> Memory:
        raise NotImplementedError

    @abstractmethod
    def get(self, memory_id: str) -> Memory | None:
        raise NotImplementedError

    @abstractmethod
    def list(self, filters: MemoryFilter | None = None) -> list[Memory]:
        raise NotImplementedError

    @abstractmethod
    def update(self, memory_id: str, changes: MemoryUpdate) -> Memory | None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, memory_id: str) -> bool:
        raise NotImplementedError

    def touch(self, memory_id: str) -> bool:
        """Record that a memory was used; implementations may override it."""
        return False

    def find_by_filter(self, filters: MemoryFilter) -> Memory | None:
        results = self.list(filters)
        return results[0] if results else None
