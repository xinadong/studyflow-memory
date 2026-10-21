"""User-confirmed preference replacement, committed with its new version."""
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from app.domain.value_objects.memory_type import ConfirmationStatus, MemoryType
from app.infrastructure.models.memory import MemoryRecord
from app.infrastructure.repositories.sqlalchemy_memory_repository import _apply_entity


def archive_conflicts(repo, memory):
    if not memory.active or memory.confirmation_status != ConfirmationStatus.CONFIRMED:
        return
    if memory.memory_type not in (MemoryType.TASK_PREFERENCE, MemoryType.EXPLANATION_PREFERENCE):
        return
    if memory.memory_type == MemoryType.TASK_PREFERENCE and not (memory.preferred_minutes or memory.max_minutes):
        return
    from app.domain.repositories.memory_repository import MemoryFilter
    for old in repo.list(MemoryFilter(user_id=memory.user_id, memory_type=memory.memory_type)):
        if old.id == memory.id or not old.active or old.confirmation_status != ConfirmationStatus.CONFIRMED:
            continue
        if (old.scope, old.course, old.knowledge_point, old.task_type) != (
            memory.scope, memory.course, memory.knowledge_point, memory.task_type
        ):
            continue
        if memory.memory_type == MemoryType.TASK_PREFERENCE and not (old.preferred_minutes or old.max_minutes):
            continue
        record = repo.session.get(MemoryRecord, old.id)
        record.confirmation_status = ConfirmationStatus.ARCHIVED.value
        record.replaced_by_id = memory.id


def add_version(repo, memory):
    saved = repo.add(memory, commit=False)
    archive_conflicts(repo, saved)
    return saved


def update_version(repo, memory_id, changes):
    old = repo.get(memory_id)
    if old is None:
        return None
    if old.replaced_by_id and changes.get("confirmation_status") == ConfirmationStatus.CONFIRMED:
        raise ValueError("该版本已被替代；请编辑当前偏好或新建偏好，不要重新启用旧版本。")
    editing = bool({"content", "preferred_minutes", "max_minutes"} & changes.keys())
    fields = {key: value for key, value in changes.items() if value is not None}
    if editing:
        numeric = {"preferred_minutes", "max_minutes"} & changes.keys()
        if "content" in changes:
            fields.update(preferred_minutes=None, max_minutes=None, duration_source=None)
        if numeric:
            for key in numeric:
                fields[key] = changes[key]
            fields["duration_source"] = "structured"
        updated = replace(old, **fields, id=uuid4().hex, created_at=datetime.now(timezone.utc),
                          last_used_at=None, use_count=0, replaced_by_id=None, supersedes_id=old.id)
        if updated.preferred_minutes and updated.max_minutes and updated.preferred_minutes > updated.max_minutes:
            raise ValueError("首选时长不能超过时长上限")
        saved = repo.add(updated, commit=False)
        if old.confirmation_status != ConfirmationStatus.CONFIRMED or saved.confirmation_status == ConfirmationStatus.CONFIRMED:
            old_record = repo.session.get(MemoryRecord, old.id)
            old_record.confirmation_status = ConfirmationStatus.ARCHIVED.value
            old_record.replaced_by_id = saved.id
    else:
        saved = replace(old, **fields)
        _apply_entity(repo.session.get(MemoryRecord, old.id), saved)
    archive_conflicts(repo, saved)
    return saved
