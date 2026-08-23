"""Memory CRUD routes with soft-delete semantics for user operations."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_memory_repository
from app.domain.entities.memory import Memory
from app.domain.repositories.memory_repository import MemoryFilter, MemoryUpdate as DomainMemoryUpdate
from app.domain.value_objects.memory_type import BlockType, ConfirmationStatus, MemoryType
from app.infrastructure.repositories.sqlalchemy_memory_repository import SqlAlchemyMemoryRepository
from app.memory.policy import soft_delete_memory
from app.schemas.memory import MemoryCreate, MemoryList, MemoryOut, MemoryUpdate

router = APIRouter()


def _out(memory: Memory) -> MemoryOut:
    return MemoryOut.model_validate(memory)


@router.post("/memories", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
def create_memory(payload: MemoryCreate, repo: SqlAlchemyMemoryRepository = Depends(get_memory_repository)):
    memory = Memory(**payload.model_dump())
    return _out(repo.add(memory))


@router.get("/memories", response_model=MemoryList)
def list_memories(
    user_id: str | None = None,
    memory_type: MemoryType | None = None,
    course: str | None = None,
    task_type: str | None = None,
    knowledge_point: str | None = None,
    block_type: BlockType | None = None,
    confirmation_status: ConfirmationStatus | None = None,
    active: bool | None = Query(default=True),
    repo: SqlAlchemyMemoryRepository = Depends(get_memory_repository),
):
    items = repo.list(MemoryFilter(
        user_id=user_id, memory_type=memory_type, course=course, task_type=task_type,
        knowledge_point=knowledge_point, block_type=block_type,
        confirmation_status=confirmation_status, active=active,
    ))
    return MemoryList(items=[_out(item) for item in items], total=len(items))


@router.get("/memories/{memory_id}", response_model=MemoryOut)
def get_memory(memory_id: str, repo: SqlAlchemyMemoryRepository = Depends(get_memory_repository)):
    memory = repo.get(memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return _out(memory)


@router.patch("/memories/{memory_id}", response_model=MemoryOut)
def update_memory(memory_id: str, payload: MemoryUpdate, repo: SqlAlchemyMemoryRepository = Depends(get_memory_repository)):
    memory = repo.update(memory_id, DomainMemoryUpdate(**payload.model_dump(exclude_unset=True)))
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return _out(memory)


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(memory_id: str, repo: SqlAlchemyMemoryRepository = Depends(get_memory_repository)):
    memory = repo.get(memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    # User-facing delete is always a soft delete; repository.delete remains a
    # low-level physical cleanup method for tests and maintenance jobs.
    memory = soft_delete_memory(memory)
    repo.update(memory_id, DomainMemoryUpdate(active=False))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
