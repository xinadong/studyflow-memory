import unittest

from app.domain.entities.memory import Memory
from app.domain.repositories.memory_repository import MemoryFilter, MemoryUpdate
from app.domain.value_objects.memory_type import (
    BlockType,
    ConfirmationStatus,
    MemoryType,
)
from app.infrastructure.repositories.in_memory_memory_repository import (
    InMemoryMemoryRepository,
)
from app.memory.policy import (
    archive_memory,
    build_memory_from_feedback,
    soft_delete_memory,
)
from app.memory.retriever import retrieve_memories
from app.schemas.memory import MemoryOut


class MemoryContractTests(unittest.TestCase):
    def make_memory(self, *, status=ConfirmationStatus.PENDING, content="20分钟任务"):
        return Memory(
            user_id="u1",
            memory_type=MemoryType.TASK_PREFERENCE,
            course="数据结构与算法",
            content=content,
            task_type="reading",
            knowledge_point="BFS",
            block_type=BlockType.TOO_HARD,
            confirmation_status=status,
        )

    def test_memory_defaults_and_usable_status(self):
        memory = self.make_memory()
        self.assertRegex(memory.id, r"^[0-9a-f]{32}$")
        self.assertIsNotNone(memory.created_at.tzinfo)
        self.assertTrue(memory.is_usable)
        self.assertEqual(memory.use_count, 0)

    def test_rejected_archived_and_soft_deleted_memories_are_not_usable(self):
        rejected = self.make_memory(status=ConfirmationStatus.REJECTED)
        archived = self.make_memory(status=ConfirmationStatus.ARCHIVED)
        deleted = self.make_memory()
        deleted.active = False
        self.assertFalse(rejected.is_usable)
        self.assertFalse(archived.is_usable)
        self.assertFalse(deleted.is_usable)

    def test_memory_confidence_is_clamped(self):
        low = self.make_memory()
        low.confidence = -1
        low.__post_init__()
        high = self.make_memory()
        high.confidence = 2
        high.__post_init__()
        self.assertEqual(low.confidence, 0.0)
        self.assertEqual(high.confidence, 1.0)

    def test_repository_crud_and_structured_filters(self):
        repo = InMemoryMemoryRepository()
        memory = repo.add(self.make_memory())
        self.assertIs(repo.get(memory.id), memory)
        self.assertEqual(repo.list(MemoryFilter(knowledge_point="BFS")), [memory])
        self.assertEqual(repo.list(MemoryFilter(block_type=BlockType.TIME)), [])
        updated = repo.update(memory.id, MemoryUpdate(content="15分钟任务"))
        self.assertEqual(updated.content, "15分钟任务")
        self.assertTrue(repo.delete(memory.id))
        self.assertIsNone(repo.get(memory.id))

    def test_pending_is_candidate_but_confirmed_is_directly_used(self):
        repo = InMemoryMemoryRepository()
        pending = repo.add(self.make_memory(content="候选偏好"))
        confirmed = repo.add(
            self.make_memory(
                status=ConfirmationStatus.CONFIRMED,
                content="已确认偏好",
            )
        )
        result = retrieve_memories(
            repo,
            MemoryFilter(user_id="u1", course="数据结构与算法"),
            limit=5,
        )
        self.assertEqual(result.retrieved_memory_ids, [confirmed.id, pending.id])
        self.assertEqual(result.used_memory_ids, [confirmed.id])
        self.assertEqual(result.candidate_memory_ids, [pending.id])

    def test_pending_and_explicit_feedback_statuses(self):
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
        self.assertEqual(inferred.confirmation_status, ConfirmationStatus.PENDING)
        self.assertEqual(explicit.confirmation_status, ConfirmationStatus.CONFIRMED)

    def test_soft_delete_and_archive_preserve_record(self):
        memory = self.make_memory()
        soft_delete_memory(memory)
        self.assertFalse(memory.active)
        self.assertFalse(memory.is_usable)
        memory = self.make_memory()
        archive_memory(memory)
        self.assertEqual(memory.confirmation_status, ConfirmationStatus.ARCHIVED)
        self.assertFalse(memory.is_usable)

    def test_memory_entity_converts_to_api_schema(self):
        output = MemoryOut.model_validate(self.make_memory())
        self.assertEqual(output.memory_type, MemoryType.TASK_PREFERENCE)
        self.assertEqual(output.block_type, BlockType.TOO_HARD)


if __name__ == "__main__":
    unittest.main()
