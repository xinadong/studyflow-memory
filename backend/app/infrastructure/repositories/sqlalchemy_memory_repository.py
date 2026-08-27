from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.memory import Memory
from app.domain.repositories.memory_repository import MemoryFilter, MemoryRepository, MemoryUpdate
from app.domain.value_objects.memory_type import BlockType, ConfirmationStatus, MemoryType
from app.infrastructure.models.memory import MemoryRecord


def _to_entity(record: MemoryRecord) -> Memory:
    return Memory(
        id=record.id,
        user_id=record.user_id,
        memory_type=MemoryType(record.memory_type),
        course=record.course,
        task_type=record.task_type,
        knowledge_point=record.knowledge_point,
        block_type=BlockType(record.block_type) if record.block_type else None,
        content=record.content,
        source_feedback=record.source_feedback,
        confidence=record.confidence,
        confirmation_status=ConfirmationStatus(record.confirmation_status),
        active=record.active,
        created_at=record.created_at,
        last_used_at=record.last_used_at,
        use_count=record.use_count,
    )


def _apply_entity(record: MemoryRecord, memory: Memory) -> None:
    record.id = memory.id
    record.user_id = memory.user_id
    record.memory_type = memory.memory_type.value
    record.course = memory.course
    record.task_type = memory.task_type
    record.knowledge_point = memory.knowledge_point
    record.block_type = memory.block_type.value if memory.block_type else None
    record.content = memory.content
    record.source_feedback = memory.source_feedback
    record.confidence = memory.confidence
    record.confirmation_status = memory.confirmation_status.value
    record.active = memory.active
    record.created_at = memory.created_at
    record.last_used_at = memory.last_used_at
    record.use_count = memory.use_count


class SqlAlchemyMemoryRepository(MemoryRepository):
    def __init__(self, session: Session):
        self.session = session

    def add(self, memory: Memory, *, commit: bool = True) -> Memory:
        record = MemoryRecord()
        _apply_entity(record, memory)
        self.session.add(record)
        self.session.flush()
        if commit:
            self.session.commit()
        self.session.refresh(record)
        return _to_entity(record)

    def get(self, memory_id: str) -> Memory | None:
        record = self.session.get(MemoryRecord, memory_id)
        return _to_entity(record) if record else None

    def list(self, filters: MemoryFilter | None = None) -> list[Memory]:
        statement = select(MemoryRecord)
        if filters is not None:
            conditions = []
            values = (
                (filters.user_id, MemoryRecord.user_id),
                (filters.memory_type, MemoryRecord.memory_type),
                (filters.course, MemoryRecord.course),
                (filters.task_type, MemoryRecord.task_type),
                (filters.knowledge_point, MemoryRecord.knowledge_point),
                (filters.block_type, MemoryRecord.block_type),
                (filters.confirmation_status, MemoryRecord.confirmation_status),
                (filters.active, MemoryRecord.active),
            )
            for expected, column in values:
                if expected is not None:
                    value = expected.value if hasattr(expected, "value") else expected
                    conditions.append(column == value)
            if conditions:
                statement = statement.where(*conditions)
        records = self.session.scalars(statement).all()
        return [_to_entity(record) for record in records]

    def update(self, memory_id: str, changes: MemoryUpdate) -> Memory | None:
        record = self.session.get(MemoryRecord, memory_id)
        if record is None:
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
                setattr(record, field_name, value.value if hasattr(value, "value") else value)
        if changes.confidence is not None:
            record.confidence = max(0.0, min(1.0, float(changes.confidence)))
        self.session.commit()
        self.session.refresh(record)
        return _to_entity(record)

    def delete(self, memory_id: str) -> bool:
        record = self.session.get(MemoryRecord, memory_id)
        if record is None:
            return False
        self.session.delete(record)
        self.session.commit()
        return True

    def touch(self, memory_id: str, *, commit: bool = True) -> bool:
        record = self.session.get(MemoryRecord, memory_id)
        if record is None:
            return False
        record.use_count += 1
        record.last_used_at = datetime.now(timezone.utc)
        if commit:
            self.session.commit()
        return True
