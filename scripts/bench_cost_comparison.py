"""§8.1 记忆成本对照：记忆注入 vs 完整历史对话注入。

对应方案指标：项目方案 §8.1「记忆成本：单轮最多 5 条、平均记忆上下文 ≤300 token，
与完整历史对话直接注入进行成本对照」。

方法（纯本地、零第三方依赖）：
- 用 B 的 estimate_tokens（len//4）估算两种注入方式的 token。
- 「记忆注入」= 只注入检索到的 ≤5 条记忆条目（并受 300 token 预算封顶），
  与对话轮数无关，始终有上界。
- 「完整历史对话注入」= 把产生这些记忆的原始多轮对话（用户陈述 + Agent 追问 + 用户确认）
  全部塞进 prompt，随反馈事件数线性增长。
- 输出不同反馈事件数 K 下的两者 token 与压缩比。

用法（项目根目录下）：
    python scripts/bench_cost_comparison.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.infrastructure.telemetry.token_tracker import estimate_tokens  # noqa: E402

LIMIT = 5
MAX_MEMORY_TOKENS = 300

# 6 组「记忆条目 vs 原始对话」。记忆条目 ≈ 系统实际存储/注入的一句话；
# 历史 = 产生它的完整多轮对话（含 Agent 追问与确认）。
EVENTS = [
    {
        "memory": "习惯每次专注学习40分钟",
        "history": "用户：我学数据结构时发现自己一口气最多专注40分钟，超过就走神。\n"
                   "助手：明白，以后帮你按40分钟左右拆分任务，这样好坚持吗？\n"
                   "用户：好，就按40分钟。\n"
                   "助手：记住了，规划会参考你的40分钟专注习惯。",
    },
    {
        "memory": "讲新概念时先给定义再举例",
        "history": "用户：你以后讲新概念，能不能先告诉我定义是什么，再举例子？我直接看例子容易懵。\n"
                   "助手：可以，我调整讲解顺序：先定义、再例子。\n"
                   "用户：对，这样我能跟上。",
    },
    {
        "memory": "学到疲劳时先休息5分钟再回来",
        "history": "用户：昨天连续学了一个半小时，后面脑子都不转了，效率特别低。\n"
                   "助手：建议你感觉疲劳时先停下来休息几分钟，再回来学。\n"
                   "用户：好，以后累了我先歇5分钟再继续。",
    },
    {
        "memory": "卡在难题时退回做基础题",
        "history": "用户：级数收敛性证明我完全看不懂，卡了半小时。\n"
                   "助手：可以先退回做基础题巩固，再回头攻难点。\n"
                   "用户：行，太难的我先放一放。",
    },
    {
        "memory": "时间不够时只做最核心的一道题",
        "history": "用户：晚上就剩20分钟了，任务还有一堆，我该做哪个？\n"
                   "助手：时间紧就挑最核心的一道题做完，别贪多。\n"
                   "用户：好，就做最核心那道。",
    },
    {
        "memory": "学完新课后第3天复习一次",
        "history": "用户：我发现学完的东西过三天不复习就忘得差不多了。\n"
                   "助手：那我帮你安排第3天复习一次，巩固记忆。\n"
                   "用户：可以，就第3天复习。",
    },
]


def _memory_injection_tokens(k: int) -> tuple[int, int]:
    """按 B 的检索上限：最多 LIMIT 条、且受 MAX_MEMORY_TOKENS 预算封顶。"""
    picked: list[str] = []
    total = 0
    for i in range(k):
        content = EVENTS[i % len(EVENTS)]["memory"]
        cost = estimate_tokens(content)
        if len(picked) >= LIMIT:
            break
        if picked and total + cost > MAX_MEMORY_TOKENS:
            break
        picked.append(content)
        total += cost
    return total, len(picked)


def _history_injection_tokens(k: int) -> int:
    return estimate_tokens(*[EVENTS[i % len(EVENTS)]["history"] for i in range(k)])


def main() -> int:
    print("记忆注入（≤5 条、≤300 token） vs 完整历史对话注入，token 对照：\n")
    print(f"{'反馈事件数 K':>10} | {'记忆 token':>9} {'条数':>4} | {'历史 token':>9} | {'节省比例':>8}")
    print("-" * 52)

    for k in (5, 10, 20, 50):
        mem_tokens, mem_count = _memory_injection_tokens(k)
        hist_tokens = _history_injection_tokens(k)
        saved = (1.0 - mem_tokens / hist_tokens) if hist_tokens else 0.0
        print(f"{k:>10} | {mem_tokens:>9} {mem_count:>4} | {hist_tokens:>9} | {saved:>7.1%}")

    print("-" * 52)
    print("结论：记忆注入的上下文始终封顶（≤5 条、≤300 token），")
    print("      而完整历史注入随对话轮数线性增长，K 越大记忆省得越多。")
    print("\n说明：本对照用「代表性原始对话 vs 记忆条目」构造，")
    print("      当前实现里 /feedback 存的是用户原话（非 LLM 摘要），")
    print("      省 token 主要来自①丢掉了 Agent 追问/确认等冗余轮次 ②检索的 5 条/300token 上限。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
