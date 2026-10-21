"""「先 check 后 plan」知识状态闭环验证脚本。

验证链路（api.md 承诺）：
  1. /agent/check 带答案 → 后端把 assessed_level 写进 knowledge_states（同课程+知识点）；
  2. /agent/plan 命中同一课程+知识点的「低层级」知识状态时，explanation 会追加
     「前置提醒：先回顾 X（上次层级 Y）」。

本脚本做「前/后对照」：
  A. 先 plan（此时无知识状态）→ 预期 explanation 无前置提醒；
  B. 再 check 带答案（写 knowledge_state）→ 打印评估层级；
  C. 再 plan 同课程知识点 → 预期 explanation 出现「前置提醒」。

用法（需后端已启动）：
    python scripts/verify_check_plan_loop.py --base-url http://127.0.0.1:8000
    python scripts/verify_check_plan_loop.py --course 高等数学 --knowledge-point 极限 \
        --answer "极限就是函数在某一点附近，函数值无限接近的那个常数"

产出：纯文本打印，含 PASS/FAIL 判定，可直接作为 user_testing.md §7.1 客观证据。
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime

import httpx

BASE = "http://127.0.0.1:8000"
TIMEOUT = 300.0  # api.openai-next.com 延迟波动大（5s~128s）


def _post(path: str, payload: dict) -> dict:
    """POST 带重试：中转站抖动会返回 5xx 或超时。"""
    for attempt in range(4):
        if attempt:
            print(f"    [重试] {path} 第 {attempt} 次（中转站 5xx/超时）…")
            time.sleep(3 * attempt)
        try:
            resp = httpx.post(f"{BASE}{path}", json=payload, timeout=TIMEOUT)
        except httpx.TimeoutException:
            if attempt < 3:
                continue
            raise
        if resp.status_code >= 500:
            if attempt < 3:
                print(f"    [5xx] {path} 返回 {resp.status_code}，稍后重试")
                continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"{path} 重试耗尽")


def _has_reminder(explanation: str) -> bool:
    """以 B 的前置提醒固定前缀「前置提醒」为判定信号。"""
    return "前置提醒" in explanation


def main() -> int:
    global BASE
    parser = argparse.ArgumentParser(description="先 check 后 plan 知识状态闭环验证")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端地址")
    parser.add_argument("--user-id", default=f"verify-{datetime.now():%m%d%H%M%S}",
                        help="默认带时间戳的新用户，保证无历史知识状态（前后对照干净）")
    parser.add_argument("--course", default="高等数学")
    parser.add_argument("--knowledge-point", default="极限")
    parser.add_argument("--goal", default="理解极限的定义")
    parser.add_argument("--material", default="极限的 ε-δ 定义")
    parser.add_argument("--level", default="recall")
    parser.add_argument("--answer", default="极限就是函数在某一点附近，函数值无限接近的那个常数")
    parser.add_argument("--available-minutes", type=int, default=25)
    args = parser.parse_args()
    BASE = args.base_url.rstrip("/")

    print("=" * 64)
    print("先 check 后 plan 知识状态闭环验证")
    print(f"  user={args.user_id}  course={args.course}  kp={args.knowledge_point}")
    print("=" * 64)

    plan_payload = {
        "user_id": args.user_id, "course": args.course, "goal": args.goal,
        "available_minutes": args.available_minutes, "task_type": "study",
        "knowledge_point": args.knowledge_point,
    }
    check_payload = {
        "user_id": args.user_id, "course": args.course,
        "knowledge_point": args.knowledge_point, "task_type": "study",
        "material": args.material, "level": args.level,
    }

    # A. 先 plan（无知识状态，预期无前置提醒）
    print("\n[A] plan（before check，预期无前置提醒）")
    plan_before = _post("/agent/plan", plan_payload)
    print(f"    explanation: {plan_before['explanation']}")
    print(f"    前置提醒出现：{'是' if _has_reminder(plan_before['explanation']) else '否'}")

    # B. check 带答案（写 knowledge_state）
    print("\n[B] check（带答案，写 knowledge_state）")
    check_resp = _post("/agent/check", {**check_payload, "answer": args.answer})
    print(f"    问题：{check_resp['question']}")
    print(f"    回答：{args.answer}")
    print(f"    评估层级：{check_resp.get('assessed_level')}")
    print(f"    反馈：{check_resp['feedback']}")

    # C. 再 plan（命中知识状态，预期出现前置提醒）
    print("\n[C] plan（after check，预期出现前置提醒）")
    plan_after = _post("/agent/plan", plan_payload)
    print(f"    explanation: {plan_after['explanation']}")
    after_has = _has_reminder(plan_after["explanation"])
    print(f"    前置提醒出现：{'是' if after_has else '否'}")

    # 判定
    print("\n" + "=" * 64)
    if after_has:
        print("判定：PASS —— check 写知识状态后，plan 出现了前置提醒，闭环生效")
    else:
        print("判定：FAIL —— plan 未出现前置提醒，需排查")
        print("  可能原因：① 答案 assessed_level 过高（非低层级），② 前置提醒机制未触发")
        print("  若上面 [B] 的评估层级是 relate/transfer，可换个更浅的 recall 答案重跑")
    print("=" * 64)
    return 0 if after_has else 1


if __name__ == "__main__":
    raise SystemExit(main())
