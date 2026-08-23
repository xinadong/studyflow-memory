"""Token 使用估算与记录辅助。"""


def estimate_tokens(*texts: str) -> int:
    return max(0, sum(len(text) for text in texts) // 4)
