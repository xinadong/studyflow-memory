"""Agent 工具：根据已确认偏好调整学习计划。"""


def adjust_learning_plan(task: dict, *, available_minutes: int, preferred_minutes: int | None) -> dict:
    adjusted = dict(task)
    if preferred_minutes is not None:
        adjusted["duration_minutes"] = max(1, min(available_minutes, preferred_minutes))
        adjusted["description"] = f"用{adjusted['duration_minutes']}分钟完成：{task['title']}"
    return adjusted
