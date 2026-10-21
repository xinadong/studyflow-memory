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
    knowledge_point: str | None = None,
    preferred_action: str | None = None,
) -> dict:
    prior = preferred_action.strip() if preferred_action and preferred_action.strip() else None
    if block_type == BlockType.TOO_HARD:
        if prior and all(marker in prior for marker in ("定位难点", "回顾前置", "基础练习", "返回原题")):
            action = prior
        else:
            point = (knowledge_point or "当前知识点").strip()
            difficulty = context.strip() or f"{point}中的卡点"
            basic_practice = prior or RECOVERY_ACTIONS[block_type]
            action = (
                f"1. 定位难点：先用一句话说清{point}中具体卡住的地方（{difficulty}）。\n"
                f"2. 回顾前置：回顾理解{point}所需的前置概念，再看一个简短示例。\n"
                f"3. 基础练习：{basic_practice}\n"
                "4. 返回原题：回到原任务，独立完成原题并检查关键步骤。"
            )
    else:
        action = prior or RECOVERY_ACTIONS[block_type]
    return {
        "action": action,
        "reason": (
            f"根据“{context or block_type.value}”复用此前有效恢复方式。"
            if prior
            else f"根据“{context or block_type.value}”生成恢复建议。"
        ),
    }
