"""结构化优先的记忆检索，并区分可直接使用与候选记忆。"""

from dataclasses import dataclass

from app.domain.entities.memory import Memory
from app.domain.repositories.memory_repository import MemoryFilter, MemoryRepository
from app.domain.value_objects.memory_type import ConfirmationStatus
from app.memory.ranker import rank_memories
from app.infrastructure.telemetry.token_tracker import estimate_tokens


@dataclass(frozen=True)
class RetrievalResult:
    retrieved: list[Memory]
    used: list[Memory]
    candidates: list[Memory]

    @property
    def retrieved_memory_ids(self) -> list[str]:
        return [memory.id for memory in self.retrieved]

    @property
    def used_memory_ids(self) -> list[str]:
        return [memory.id for memory in self.used]

    @property
    def candidate_memory_ids(self) -> list[str]:
        return [memory.id for memory in self.candidates]


def retrieve_memories(
    repository: MemoryRepository,
    filters: MemoryFilter,
    *,
    limit: int = 5,
    max_memory_tokens: int = 300,
) -> RetrievalResult:
    if limit < 1:
        raise ValueError("limit must be at least 1")
    eligible = [memory for memory in repository.list(filters) if memory.is_usable]
    return retrieve_memory_candidates(
        eligible,
        limit=limit,
        max_memory_tokens=max_memory_tokens,
    )


def retrieve_memory_candidates(
    memories: list[Memory],
    *,
    limit: int = 5,
    max_memory_tokens: int = 300,
) -> RetrievalResult:
    """Rank an already context-filtered set of memories.

    Agent operations use this helper after applying their own generic-memory
    matching rules. The repository-level function above remains the strict
    contract implementation used by unit tests and other callers.
    """
    if limit < 1:
        raise ValueError("limit must be at least 1")
    eligible = [memory for memory in memories if memory.is_usable]
    retrieved = []
    token_count = 0
    for memory in rank_memories(eligible)[:limit]:
        memory_tokens = estimate_tokens(memory.content)
        if retrieved and token_count + memory_tokens > max_memory_tokens:
            continue
        retrieved.append(memory)
        token_count += memory_tokens
    used = [
        memory
        for memory in retrieved
        if memory.confirmation_status == ConfirmationStatus.CONFIRMED
    ]
    candidates = [
        memory
        for memory in retrieved
        if memory.confirmation_status == ConfirmationStatus.PENDING
    ]
    return RetrievalResult(retrieved=retrieved, used=used, candidates=candidates)


def select_used_memories(result: RetrievalResult, memory_ids: list[str]) -> RetrievalResult:
    """Return a copy whose used set contains only memories that changed output."""
    wanted = set(memory_ids)
    used = [
        memory for memory in result.retrieved
        if memory.id in wanted and memory.confirmation_status == ConfirmationStatus.CONFIRMED
    ]
    return RetrievalResult(
        retrieved=result.retrieved,
        used=used,
        candidates=result.candidates,
    )


def merge_retrieval_results(
    *results: RetrievalResult,
    limit: int = 5,
    max_memory_tokens: int = 300,
) -> RetrievalResult:
    """Merge independently scoped retrievals under one shared budget."""
    memories: list[Memory] = []
    seen: set[str] = set()
    for result in results:
        for memory in result.retrieved:
            if memory.id not in seen:
                seen.add(memory.id)
                memories.append(memory)
    return retrieve_memory_candidates(
        memories,
        limit=limit,
        max_memory_tokens=max_memory_tokens,
    )


def mark_used(result: RetrievalResult) -> RetrievalResult:
    """返回结果本身，供调用方明确哪些 confirmed 记忆影响了输出。"""
    return result
