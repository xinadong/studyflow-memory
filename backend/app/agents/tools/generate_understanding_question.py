"""Agent 工具：生成一轮苏格拉底理解检验问题。"""


LEVEL_QUESTIONS = {
    "recall": "请用自己的话复述这个知识点的核心概念，并说明它解决什么问题？",
    "relate": "这个知识点和你已经学过的哪个概念有关？请说明它们的联系。",
    "transfer": "如果把这个知识点应用到一个新的场景，你会如何选择或改造它？",
}


def generate_understanding_question(*, knowledge_point: str, level: str = "recall", example_first: bool = False) -> dict:
    normalized = level if level in LEVEL_QUESTIONS else "recall"
    prefix = "先看一个简短例子，再回答：" if example_first else ""
    return {
        "level": normalized,
        "question": f"{prefix}{knowledge_point}：{LEVEL_QUESTIONS[normalized]}",
    }
