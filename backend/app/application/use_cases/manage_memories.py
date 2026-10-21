"""Confirm, edit, revoke and delete memories."""

from app.domain.repositories.memory_repository import MemoryUpdate
from app.domain.value_objects.memory_type import ConfirmationStatus


def confirm(repository, memory_id: str):
    return repository.update(memory_id, MemoryUpdate(confirmation_status=ConfirmationStatus.CONFIRMED))


def reject(repository, memory_id: str):
    return repository.update(memory_id, MemoryUpdate(confirmation_status=ConfirmationStatus.REJECTED))


def archive(repository, memory_id: str):
    return repository.update(memory_id, MemoryUpdate(confirmation_status=ConfirmationStatus.ARCHIVED))


def soft_delete(repository, memory_id: str):
    return repository.update(memory_id, MemoryUpdate(active=False))
