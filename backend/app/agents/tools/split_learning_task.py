"""Agent 工具：把课程目标拆成一个可执行微任务。"""

from uuid import uuid4


def split_learning_task(
    *,
    goal: str,
    available_minutes: int,
    preferred_minutes: int | None = None,
    task_type: str = "study",
    knowledge_point: str | None = None,
) -> dict:
    duration = min(available_minutes, preferred_minutes or 25)
    duration = max(5, duration)
    return {
        "id": uuid4().hex,
        "title": goal,
        "description": f"用{duration}分钟完成：{goal}",
        "duration_minutes": duration,
        "task_type": task_type,
        "knowledge_point": knowledge_point,
    }
