"""Conservative duration parsing. Ambiguous feedback is never guessed."""
import re


def _number(text: str) -> int:
    if text.isdigit():
        return int(text)
    digits = dict(zip("零一二三四五六七八九", range(10)))
    text = text.replace("两", "二")
    total = current = 0
    for char in text:
        if char in digits:
            current = digits[char]
        elif char in "十百":
            total += (current or 1) * (10 if char == "十" else 100)
            current = 0
    return total + current


def parse_duration(content: str) -> tuple[int | None, int | None]:
    text = content.lower().replace("半小时", "30分钟").replace("一刻钟", "15分钟")
    pattern = r"([0-9零一二两三四五六七八九十百]+)\s*(分钟|min(?:utes?)?|小时)"
    found = list(re.finditer(pattern, text))
    preferred, maximum = [], []
    for index, match in enumerate(found):
        value = _number(match[1]) * (60 if match[2] == "小时" else 1)
        if not 1 <= value <= 240:
            return None, None
        left = text[found[index - 1].end() if index else 0:match.start()]
        right = text[match.end():found[index + 1].start() if index + 1 < len(found) else len(text)]
        if re.search(r"至少|最少|不低于|不少于|大于|超过(?!.*(?:不要超过|不超过))", left) and not re.search(r"不要超过|不超过|不能超过|最多|上限", left):
            return None, None
        if re.search(r"最多|至多|不超过|不要超过|不能超过|上限|控制在", left) or re.match(r"\s*(以内|以下|为上限)", right):
            maximum.append(value)
        else:
            preferred.append(value)
    if len(set(preferred)) > 1 or len(set(maximum)) > 1:
        return None, None
    p = preferred[0] if preferred else None
    m = maximum[0] if maximum else None
    if p and m and p > m:
        return None, None
    return p, m
