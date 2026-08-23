"""评测和运行指标 API 模型。"""

from pydantic import BaseModel, Field


class EvaluationCompareRequest(BaseModel):
    user_id: str = "evaluation-user"
    course: str = "数据结构与算法"
    goal: str = "学习图的 BFS"
    available_minutes: int = Field(default=25, ge=1, le=240)


class EvaluationCompareResponse(BaseModel):
    without_memory: dict
    with_memory: dict
    delta: dict
