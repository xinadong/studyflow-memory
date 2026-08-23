"""记忆系统共享的值对象枚举。"""

from enum import Enum


class MemoryType(str, Enum):
    TASK_PREFERENCE = "task_preference"
    EXPLANATION_PREFERENCE = "explanation_preference"
    KNOWLEDGE_STATE = "knowledge_state"
    RECOVERY_EXPERIENCE = "recovery_experience"
    REVIEW_SCHEDULE = "review_schedule"


class ConfirmationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class BlockType(str, Enum):
    TIME = "time"
    TOO_HARD = "too_hard"
    DISTRACTION = "distraction"
    FATIGUE = "fatigue"
