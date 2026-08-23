"""Agent 工具：根据阻塞原因生成低压力恢复动作。"""

from app.domain.value_objects.memory_type import BlockType


RECOVERY_ACTIONS = {
    BlockType.TIME: "把任务缩小为一道核心练习，先完成最小可交付步骤。",
    BlockType.TOO_HARD: "先看一个遍历示例，再完成一道最小练习。",
    BlockType.DISTRACTION: "把杂事记录下来，安排一个10分钟专注片段。",
    BlockType.FATIGUE: "保存当前进度，切换到低压力复习并只完成一个回顾问题。",
}


def generate_recovery_action(
    *,
    block_type: BlockType,
    context: str = "",
    preferred_action: str | None = None,
) -> dict:
    action = preferred_action.strip() if preferred_action and preferred_action.strip() else RECOVERY_ACTIONS[block_type]
    return {
        "action": action,
        "reason": (
            f"根据“{context or block_type.value}”复用此前有效恢复方式。"
            if preferred_action and preferred_action.strip()
            else f"根据“{context or block_type.value}”生成恢复建议。"
        ),
    }
