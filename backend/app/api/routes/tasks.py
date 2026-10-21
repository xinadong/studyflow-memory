"""Task persistence for the single-user demo; user_id is not authentication."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.infrastructure.models.task import TaskRecord
from app.schemas.task import TaskCreate, TaskList, TaskOut, TaskUpdate

router = APIRouter()


def _out(task: TaskRecord) -> TaskOut:
    def utc(value):
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value

    return TaskOut(
        id=task.id, course=task.course, title=task.title,
        description=task.description or "", task_type=task.task_type or "study",
        knowledge_point=task.knowledge_point, duration_minutes=task.duration_minutes,
        status="pending" if task.status == "planned" else task.status,
        due_at=utc(task.due_at), created_at=utc(task.created_at),
    )


def _owned(db: Session, task_id: str, user_id: str) -> TaskRecord:
    task = db.scalar(select(TaskRecord).where(
        TaskRecord.id == task_id, TaskRecord.user_id == user_id,
        TaskRecord.status != "deleted",
    ))
    if task is None:
        raise HTTPException(404, "Task not found")
    return task


@router.get("/tasks", response_model=TaskList)
def list_tasks(user_id: str = Query(min_length=1, max_length=128), db: Session = Depends(get_db)):
    rows = db.scalars(select(TaskRecord).where(
        TaskRecord.user_id == user_id, TaskRecord.status != "deleted",
    ).order_by(TaskRecord.created_at, TaskRecord.id)).all()
    return TaskList(items=[_out(row) for row in rows])


@router.post("/tasks", response_model=TaskOut)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    # A client-generated ID allows a retry after a lost response without
    # inserting a second review. Never let an existing ID overwrite a task.
    existing = db.get(TaskRecord, payload.id)
    if existing is not None:
        if existing.user_id != payload.user_id or existing.status == "deleted":
            raise HTTPException(409, "Task ID already exists")
        current = _out(existing).model_dump()
        submitted = payload.model_dump(exclude={"user_id"})
        if any(current[key] != value for key, value in submitted.items()):
            raise HTTPException(409, "Task ID already exists with different content")
        return _out(existing)
    task = TaskRecord(**payload.model_dump(), status="pending", created_at=datetime.now(timezone.utc))
    db.add(task)
    db.commit()
    db.refresh(task)
    return _out(task)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: str, payload: TaskUpdate,
                user_id: str = Query(min_length=1, max_length=128), db: Session = Depends(get_db)):
    task = _owned(db, task_id, user_id)
    task.status = payload.status
    db.commit()
    db.refresh(task)
    return _out(task)


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: str, user_id: str = Query(min_length=1, max_length=128),
                db: Session = Depends(get_db)):
    task = _owned(db, task_id, user_id)
    task.status = "deleted"
    db.commit()
    return Response(status_code=204)
