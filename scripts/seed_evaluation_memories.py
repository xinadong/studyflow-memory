"""为 --real 评测预置「evaluation-user」的已确认记忆。

用法（需后端已启动）：
    python scripts/seed_evaluation_memories.py
    python scripts/seed_evaluation_memories.py --base-url http://127.0.0.1:8000
    python scripts/seed_evaluation_memories.py --reset   # 先清空 evaluation-user 再写入，获得干净归档

作用：通过 B 的 POST /memories 接口写入若干条 confirmed 记忆，
让 run_evaluation.py --real 的「有记忆 vs 无记忆」对照出现真实差异。

关键（B 的编排语义，见 docs/evaluation.md §3 第 7 条）：
- --real 走 plan()（学习规划），plan() 只检索 TASK_PREFERENCE 类型；
- plan() 只会把「content 含『N分钟』时长」的任务偏好算作 used（影响任务时长）；
- explanation_preference 只在 check()（理解检验）被使用，plan() 不检索它。
因此这里的任务偏好必须带时长，才能让 memory_count > 0。

注意：重复运行会新增重复记忆。要干净的 used=1 归档数据，请用 --reset——
先软删除 evaluation-user 现有活跃记忆再写入。后端 DELETE /memories/{id} 是软删除
（active=False），检索时 is_usable 会排除，所以清理后不会污染后续评测。
"""

from __future__ import annotations

import argparse

import httpx

USER_ID = "evaluation-user"

# 三个目标各一条带时长的任务偏好；时长故意和 available_minutes 不同，
# 以便「有记忆」的规划里出现个性化说明（explanation 会提示偏好时长）。
SEEDS = [
    # 目标 1：学习图的 BFS（available=25）
    {"memory_type": "task_preference", "course": "数据结构与算法",
     "content": "习惯每次专注学习40分钟", "task_type": "study",
     "knowledge_point": "BFS", "confirmation_status": "confirmed", "confidence": 0.9},
    # 目标 2：学习拓扑排序（available=30）
    {"memory_type": "task_preference", "course": "数据结构与算法",
     "content": "习惯每次专注学习50分钟", "task_type": "study",
     "knowledge_point": "拓扑排序", "confirmation_status": "confirmed", "confidence": 0.85},
    # 目标 3：理解极限的定义（available=25，高等数学）
    {"memory_type": "task_preference", "course": "高等数学",
     "content": "习惯每次专注学习35分钟", "task_type": "study",
     "knowledge_point": "极限", "confirmation_status": "confirmed", "confidence": 0.8},
]


def _reset_memories(base: str) -> int:
    """软删除 evaluation-user 的所有活跃记忆，以便干净地重新 seed。"""
    try:
        resp = httpx.get(
            f"{base}/memories",
            params={"user_id": USER_ID, "active": "true"},
            timeout=30.0,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except httpx.HTTPError as exc:
        print(f"[失败] 拉取 {USER_ID} 的记忆时出错：{exc}")
        print("请确认后端已启动：python -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
        return 1

    deleted = 0
    for item in items:
        try:
            httpx.delete(f"{base}/memories/{item['id']}", timeout=30.0).raise_for_status()
            deleted += 1
        except httpx.HTTPError as exc:
            print(f"[跳过] 删除 {item['id']} 失败：{exc}")
    print(f"[已清理] 软删除 {USER_ID} 的 {deleted} 条活跃记忆")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="为 --real 预置 evaluation-user 的已确认记忆")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端地址")
    parser.add_argument(
        "--reset", action="store_true",
        help="先软删除 evaluation-user 的现有活跃记忆，再重新写入（获得干净的 used=1 归档数据）",
    )
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    if args.reset:
        if _reset_memories(base) != 0:
            return 1
    ok = 0
    for seed in SEEDS:
        payload = {"user_id": USER_ID, **seed}
        try:
            resp = httpx.post(f"{base}/memories", json=payload, timeout=30.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            print(f"[失败] {seed['content']}：{exc}")
            print("请确认后端已启动：python -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
            return 1
        data = resp.json()
        ok += 1
        print(f"[已写入] {data['id']}  {data['course']} / {data['knowledge_point']}：{data['content']}")

    print(f"\n完成：共写入 {ok} 条已确认记忆（user={USER_ID}）。")
    print("现在可重跑：python scripts/run_evaluation.py --real --base-url http://127.0.0.1:8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
