"""Agent 工具：读取当前课程学习状态。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models.knowledge_state import KnowledgeStateRecord
from app.infrastructure.models.task import TaskRecord


def get_learning_state(session: Session, *, user_id: str, course: str) -> dict:
    tasks = session.scalars(
        select(TaskRecord).where(TaskRecord.user_id == user_id, TaskRecord.course == course)
    ).all()
    knowledge = session.scalars(
        select(KnowledgeStateRecord).where(
            KnowledgeStateRecord.user_id == user_id,
            KnowledgeStateRecord.course == course,
        )
    ).all()
    return {
        "tasks": [
            {
                "id": task.id,
                "title": task.title,
                "duration_minutes": task.duration_minutes,
                "status": task.status,
                "knowledge_point": task.knowledge_point,
            }
            for task in tasks
        ],
        "knowledge_states": [
            {
                "knowledge_point": item.knowledge_point,
                "understanding_level": item.understanding_level,
                "evidence": item.evidence,
            }
            for item in knowledge
        ],
    }
