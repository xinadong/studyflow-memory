"""验证记忆契约和内存仓储行为。"""

from app.domain.entities.memory import Memory
from app.domain.repositories.memory_repository import MemoryFilter, MemoryRepository, MemoryUpdate
from app.domain.value_objects.memory_type import BlockType, ConfirmationStatus, MemoryType
from app.infrastructure.repositories.in_memory_memory_repository import InMemoryMemoryRepository
from app.memory.policy import build_memory_from_feedback
from app.memory.retriever import retrieve_memories
from app.schemas.memory import MemoryOut


def make_memory(*, status: ConfirmationStatus = ConfirmationStatus.PENDING, content: str = "20分钟任务") -> Memory:
    return Memory(
        user_id="u1",
        memory_type=MemoryType.TASK_PREFERENCE,
        course="数据结构与算法",
        content=content,
        task_type="reading",
        knowledge_point="BFS",
        block_type=BlockType.TOO_HARD,
        confirmation_status=status,
        confidence=0.9,
    )


def main() -> None:
    assert MemoryType.TASK_PREFERENCE.value == "task_preference"
    assert ConfirmationStatus.PENDING.value == "pending"
    assert BlockType.TOO_HARD.value == "too_hard"

    pending = make_memory()
    confirmed = make_memory(status=ConfirmationStatus.CONFIRMED, content="已确认偏好")
    rejected = make_memory(status=ConfirmationStatus.REJECTED)
    archived = make_memory(status=ConfirmationStatus.ARCHIVED)
    deleted = make_memory()
    deleted.active = False
    assert pending.is_usable and confirmed.is_usable
    assert not rejected.is_usable and not archived.is_usable and not deleted.is_usable

    output = MemoryOut.model_validate(pending)
    assert output.memory_type == MemoryType.TASK_PREFERENCE

    assert MemoryRepository is not None
    repo = InMemoryMemoryRepository()
    repo.add(pending)
    repo.add(confirmed)
    repo.add(rejected)
    repo.add(archived)
    repo.add(deleted)
    assert len(repo.list(MemoryFilter(knowledge_point="BFS"))) == 5
    assert repo.update(pending.id, MemoryUpdate(content="15分钟任务"))
    assert repo.get(pending.id).content == "15分钟任务"

    result = retrieve_memories(repo, MemoryFilter(user_id="u1", course="数据结构与算法"))
    assert result.used_memory_ids == [confirmed.id]
    assert result.candidate_memory_ids == [pending.id]
    assert len(result.retrieved_memory_ids) == 2

    inferred = build_memory_from_feedback(
        user_id="u1",
        memory_type=MemoryType.EXPLANATION_PREFERENCE,
        course="数据结构与算法",
        content="示例优先",
        explicit=False,
    )
    explicit = build_memory_from_feedback(
        user_id="u1",
        memory_type=MemoryType.EXPLANATION_PREFERENCE,
        course="数据结构与算法",
        content="示例优先",
        explicit=True,
    )
    assert inferred.confirmation_status == ConfirmationStatus.PENDING
    assert explicit.confirmation_status == ConfirmationStatus.CONFIRMED

    assert repo.delete(pending.id) is True
    assert repo.get(pending.id) is None
    print("契约验证全部通过")


if __name__ == "__main__":
    main()
