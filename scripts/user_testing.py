"""§8.4 用户测试驱动脚本：研发者测试（按 10 个画像跑功能覆盖），跑四步会话并记录 5 项指标。

设计：研发者按 10 个画像做功能覆盖，每个画像 = 一种不同的测试维度，
覆盖三类记忆消费点（task_preference / explanation_preference / recovery_experience）
与四个边界（冷启动、跨课程隔离、冲突偏好软删、混合全链路）。

预热方式（已选定「直写 + 顺带演示反馈闭环」）：
- 画像 1、10 用 POST /feedback 走「说一句话 → LLM 分类 → 生成记忆」主链路；
- 其余画像用 POST /memories 直写 confirmed 记忆（快、确定）。

用法（需后端已启动）：
    python scripts/user_testing.py --base-url http://127.0.0.1:8000        # 跑全部 10 个
    python scripts/user_testing.py --base-url ... --only 1,10              # 只跑部分
    python scripts/user_testing.py --list                                 # 只看画像清单

每个画像会话：预热 → plan（含「修改→反馈→重排」闭环）→ check（两步：问题→回答→评估）→ recover（含「接受→存记忆」闭环）→ compare（仅部分）。
每步打印 Agent 输出 + used 记忆数，主观评分由研发者（按该画像）基于真实交互录入。

产出：结果追加写入 outputs/user_testing_results.csv，结束打印 5 项指标汇总。
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
TIMEOUT = 300.0  # api.openai-next.com 延迟波动大（5s~128s），单步可能包含多次 LLM 调用

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs"
CSV_PATH = OUTPUT_DIR / "user_testing_results.csv"

COLUMNS = [
    "timestamp", "persona_id", "name", "dimension", "warmup",
    "plan_goal", "plan_used_count", "plan_modified", "plan_accepted",
    "check_used_count", "check_accepted", "check_answer", "check_assessed_level",
    "recover_used_count", "recover_continued",
    "understanding", "memory_preference", "note",
]

# 10 个画像。每个画像 = 一种不同的测试维度。
PERSONAS = [
    {
        "id": "tester-01", "name": "时长偏好型",
        "dimension": "task_preference：规划时长个性化",
        "warmup": "feedback",
        "seeds": [
            {"course": "数据结构与算法", "content": "我习惯每次专注学习40分钟",
             "task_type": "study", "knowledge_point": "BFS", "explicit": True},
        ],
        "plan": {"course": "数据结构与算法", "goal": "学习图的 BFS",
                 "available_minutes": 25, "task_type": "study", "knowledge_point": "BFS"},
        "check": None, "recover": None, "compare": True,
    },
    {
        "id": "tester-02", "name": "讲解偏好型",
        "dimension": "explanation_preference：讲解风格个性化",
        "warmup": "memories",
        "seeds": [
            {"memory_type": "explanation_preference", "course": "高等数学",
             "content": "讲新概念时先给定义，再举例", "task_type": "study",
             "knowledge_point": "极限", "confirmation_status": "confirmed", "confidence": 0.9},
        ],
        "plan": None,
        "check": {"course": "高等数学", "knowledge_point": "极限",
                  "task_type": "study", "material": "极限的 ε-δ 定义", "level": "recall"},
        "recover": None, "compare": False,
    },
    {
        "id": "tester-03", "name": "疲劳恢复型",
        "dimension": "recovery_experience(fatigue)：疲劳卡点恢复",
        "warmup": "memories",
        "seeds": [
            {"memory_type": "recovery_experience", "course": "数据结构与算法",
             "content": "学到疲劳时先休息5分钟再回来", "block_type": "fatigue",
             "task_type": "study", "knowledge_point": "图",
             "confirmation_status": "confirmed", "confidence": 0.9},
        ],
        "plan": None, "check": None,
        "recover": {"course": "数据结构与算法", "block_type": "fatigue",
                    "context": "已经连续学了1小时，有点累", "task_type": "study", "knowledge_point": "图"},
        "compare": False,
    },
    {
        "id": "tester-04", "name": "难度卡点型",
        "dimension": "recovery_experience(too_hard)：难题卡点恢复",
        "warmup": "memories",
        "seeds": [
            {"memory_type": "recovery_experience", "course": "高等数学",
             "content": "卡在太难的题时，退回做基础题", "block_type": "too_hard",
             "task_type": "study", "knowledge_point": "级数",
             "confirmation_status": "confirmed", "confidence": 0.85},
        ],
        "plan": None, "check": None,
        "recover": {"course": "高等数学", "block_type": "too_hard",
                    "context": "级数收敛性证明完全看不懂", "task_type": "study", "knowledge_point": "级数"},
        "compare": False,
    },
    {
        "id": "tester-05", "name": "分心恢复型",
        "dimension": "recovery_experience(distraction)：分心卡点恢复",
        "warmup": "memories",
        "seeds": [
            {"memory_type": "recovery_experience", "course": "英语",
             "content": "分心时用番茄钟，专注25分钟", "block_type": "distraction",
             "task_type": "study", "knowledge_point": "单词",
             "confirmation_status": "confirmed", "confidence": 0.8},
        ],
        "plan": None, "check": None,
        "recover": {"course": "英语", "block_type": "distraction",
                    "context": "总想刷手机，静不下心", "task_type": "study", "knowledge_point": "单词"},
        "compare": False,
    },
    {
        "id": "tester-06", "name": "时间不够型",
        "dimension": "recovery_experience(time)：时间冲突恢复",
        "warmup": "memories",
        "seeds": [
            {"memory_type": "recovery_experience", "course": "数据结构与算法",
             "content": "时间不够时只做最核心的一道题", "block_type": "time",
             "task_type": "study", "knowledge_point": "动态规划",
             "confirmation_status": "confirmed", "confidence": 0.85},
        ],
        "plan": None, "check": None,
        "recover": {"course": "数据结构与算法", "block_type": "time",
                    "context": "只剩20分钟，任务太多做不完", "task_type": "study", "knowledge_point": "动态规划"},
        "compare": False,
    },
    {
        "id": "tester-07", "name": "冷启动型",
        "dimension": "无记忆：默认策略兜底",
        "warmup": "none", "seeds": [],
        "plan": {"course": "大学物理", "goal": "学习牛顿第二定律",
                 "available_minutes": 30, "task_type": "study", "knowledge_point": "牛顿第二定律"},
        "check": None, "recover": None, "compare": False,
    },
    {
        "id": "tester-08", "name": "跨课程不串型",
        "dimension": "记忆隔离：高数偏好不串到数据结构",
        "warmup": "memories",
        "seeds": [
            {"memory_type": "task_preference", "course": "高等数学",
             "content": "习惯每次专注学习40分钟", "task_type": "study",
             "knowledge_point": "极限", "confirmation_status": "confirmed", "confidence": 0.9},
        ],
        "plan": {"course": "数据结构与算法", "goal": "学习链表",
                 "available_minutes": 30, "task_type": "study", "knowledge_point": "链表"},
        "check": None, "recover": None, "compare": False,
    },
    {
        "id": "tester-09", "name": "冲突偏好型",
        "dimension": "偏好更新：旧偏好软删除后只用新的",
        "warmup": "memories",
        "seeds": [
            {"memory_type": "task_preference", "course": "数据结构与算法",
             "content": "习惯每次专注学习40分钟", "task_type": "study",
             "knowledge_point": "排序", "confirmation_status": "confirmed", "confidence": 0.9},
            {"memory_type": "task_preference", "course": "数据结构与算法",
             "content": "习惯每次专注学习30分钟", "task_type": "study",
             "knowledge_point": "排序", "confirmation_status": "confirmed", "confidence": 0.9},
        ],
        "soft_delete_indices": [0],
        "plan": {"course": "数据结构与算法", "goal": "学习快速排序",
                 "available_minutes": 35, "task_type": "study", "knowledge_point": "排序"},
        "check": None, "recover": None, "compare": False,
    },
    {
        "id": "tester-10", "name": "混合全链路型",
        "dimension": "时长+讲解+恢复三类记忆，plan→check→recover 全链路",
        "warmup": "feedback",
        "seeds": [
            {"course": "数据结构与算法", "content": "我习惯每次专注学习45分钟",
             "task_type": "study", "knowledge_point": "图的遍历", "explicit": True},
            {"course": "数据结构与算法", "content": "讲新概念时先给我讲定义，再举例",
             "task_type": "study", "knowledge_point": "图的遍历", "explicit": True},
            {"course": "数据结构与算法", "content": "学到疲劳时我会先起身活动一下再继续",
             "task_type": "study", "knowledge_point": "图的遍历", "block_type": "fatigue", "explicit": True},
        ],
        "plan": {"course": "数据结构与算法", "goal": "学习图的 DFS",
                 "available_minutes": 25, "task_type": "study", "knowledge_point": "图的遍历"},
        "check": {"course": "数据结构与算法", "knowledge_point": "图的遍历",
                  "task_type": "study", "material": "图的深度优先遍历", "level": "recall"},
        "recover": {"course": "数据结构与算法", "block_type": "fatigue",
                    "context": "图遍历学到后面有点累", "task_type": "study", "knowledge_point": "图的遍历"},
        "compare": True,
    },
]


# ---------- 交互录入 ----------

def _ask(prompt: str, default: str | None = None) -> str:
    ans = input(prompt + " ").strip()
    if ans == "" and default is not None:
        return str(default)
    return ans


def _ask_int(prompt: str, lo: int | None = None, hi: int | None = None,
             default: int | None = None) -> int:
    while True:
        raw = _ask(prompt, str(default) if default is not None else None)
        try:
            value = int(raw)
        except ValueError:
            print("  请输入数字")
            continue
        if lo is not None and value < lo:
            print(f"  需 ≥ {lo}")
            continue
        if hi is not None and value > hi:
            print(f"  需 ≤ {hi}")
            continue
        return value


def _ask_bool(prompt: str, default: str = "y") -> bool:
    while True:
        raw = _ask(prompt, default).lower()
        if raw in ("y", "yes", "是", "1"):
            return True
        if raw in ("n", "no", "否", "0"):
            return False
        print("  请输入 y/n")


# ---------- HTTP ----------

def _post(path: str, payload: dict) -> dict:
    resp = httpx.post(f"{BASE}{path}", json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _delete(path: str) -> None:
    httpx.delete(f"{BASE}{path}", timeout=TIMEOUT).raise_for_status()


# ---------- 预热 ----------

def _cleanup_user(user_id: str) -> None:
    """软删除该画像已有的活跃记忆，保证重跑幂等、不产生重复记忆。"""
    try:
        resp = httpx.get(
            f"{BASE}/memories",
            params={"user_id": user_id, "active": "true"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except httpx.HTTPError:
        print("  [提示] 清理该画像已有记忆失败，可能有重复，建议人工核对")
        return
    for item in items:
        try:
            httpx.delete(f"{BASE}/memories/{item['id']}", timeout=TIMEOUT).raise_for_status()
        except httpx.HTTPError:
            pass
    if items:
        print(f"  [清理] 软删除该画像已有 {len(items)} 条活跃记忆（幂等重跑）")


def _warmup(persona: dict) -> list[str]:
    """种记忆，返回按 seed 顺序的 memory id 列表。"""
    created: list[str] = []
    method = persona["warmup"]
    if method == "none":
        print("  无预热（冷启动）")
        return created

    for seed in persona["seeds"]:
        if method == "memories":
            data = _post("/memories", {"user_id": persona["id"], **seed})
            created.append(data["id"])
            print(f"  [seed] {data['memory_type']} / {data['knowledge_point'] or '-'}：{data['content']}")
        elif method == "feedback":
            data = _post("/feedback", {"user_id": persona["id"], **seed})
            for mem in data.get("memories", []):
                created.append(mem["id"])
                print(f"  [feedback→{mem['memory_type']}] {mem['knowledge_point'] or '-'}：{mem['content']}")

    for idx in persona.get("soft_delete_indices", []):
        mid = created[idx]
        _delete(f"/memories/{mid}")
        print(f"  [软删除] 旧偏好 {mid}")

    return created


# ---------- 会话步骤 ----------

def _print_plan(data: dict, goal: str, available: int) -> None:
    print(f"\n  [plan] {goal}（可用 {available} 分钟）")
    for t in data["tasks"]:
        print(f"    任务：{t['title']}（{t['duration_minutes']} 分钟）")
    print(f"    说明：{data['explanation']}")
    print(f"    used={len(data['used_memory_ids'])} retrieved={len(data['retrieved_memory_ids'])} "
          f"memory_tokens={data['metrics'].get('memory_tokens', 0)}")


def _step_plan(persona: dict, row: dict) -> None:
    plan = persona["plan"]
    data = _post("/agent/plan", {"user_id": persona["id"], **plan})
    row["plan_goal"] = plan["goal"]
    row["plan_used_count"] = len(data["used_memory_ids"])
    _print_plan(data, plan["goal"], plan["available_minutes"])

    # 修改闭环：画像不满意 → 提反馈（生成记忆）→ 重排看是否自动用上
    modified = 0
    while True:
        if row["plan_used_count"] == 0:
            print("    （冷启动/隔离：无记忆被应用。可改一次，观察「反馈→记忆→重排自动用上」闭环）")
        want = _ask_bool("    作为该画像，要修改这个计划吗？(y/n)", "n")
        if not want:
            break
        content = _ask("    改成什么？一句话说清（含「分钟」会记成时长偏好）：").strip()
        if not content:
            continue
        try:
            _post("/feedback", {
                "user_id": persona["id"], "course": plan["course"],
                "content": content, "task_type": plan.get("task_type", "study"),
                "knowledge_point": plan.get("knowledge_point"), "explicit": True,
            })
        except httpx.HTTPError as exc:
            print(f"    [错误] 提交反馈失败：{exc}")
            row["note"] = f"反馈失败：{exc}"
            break
        print(f"    [反馈] 已提交：{content}")
        data = _post("/agent/plan", {"user_id": persona["id"], **plan})
        row["plan_used_count"] = len(data["used_memory_ids"])
        _print_plan(data, plan["goal"], plan["available_minutes"])
        modified += 1
    row["plan_modified"] = modified
    if row["plan_used_count"] > 0:
        row["plan_accepted"] = _ask_bool("    这个计划你接受吗？(y/n)", "y")
    else:
        print("    （无记忆被应用 → 冷启动/隔离，跳过接受度，属预期）")


def _step_check(persona: dict, row: dict) -> None:
    check = persona["check"]
    # 第一步：生成问题（不传 answer，看讲解风格是否命中偏好）
    q = _post("/agent/check", {"user_id": persona["id"], **check})
    row["check_used_count"] = len(q["used_memory_ids"])
    print(f"\n  [check] {check['knowledge_point']}（level={check.get('level', 'recall')}）")
    print(f"    问题：{q['question']}")
    print(f"    used={row['check_used_count']}")
    # 第二步：画像回答 → 评估层级 + 针对回答的真实反馈
    answer = _ask("    作为该画像，你怎么回答这个问题？").strip()
    if not answer:
        answer = "（未作答）"
    a = _post("/agent/check", {"user_id": persona["id"], **check, "answer": answer})
    row["check_answer"] = answer
    row["check_assessed_level"] = a.get("assessed_level")
    print(f"    你的回答：{answer}")
    print(f"    评估层级：{row['check_assessed_level']}")
    print(f"    反馈：{a['feedback']}")
    if row["check_used_count"] > 0:
        row["check_accepted"] = _ask_bool("    个性化讲解是否符合你的偏好？(y/n)", "y")
    else:
        print("    （无讲解偏好被应用，跳过接受度）")


def _step_recover(persona: dict, row: dict) -> None:
    recover = persona["recover"]
    data = _post("/agent/recover", {"user_id": persona["id"], **recover})
    row["recover_used_count"] = len(data["used_memory_ids"])
    print(f"\n  [recover] block_type={recover['block_type']}（{recover['context']}）")
    print(f"    建议动作：{data['action']}")
    print(f"    理由：{data['reason']}")
    print(f"    used={row['recover_used_count']}")
    row["recover_continued"] = _ask_bool("    看完建议，是否继续学习（接受）？(y/n)", "y")
    if row["recover_continued"]:
        # 接受闭环：带 user_acceptance=true 再调一次，把本次动作存成新恢复记忆
        try:
            _post("/agent/recover", {"user_id": persona["id"], **recover, "user_acceptance": True})
            print("    [闭环] 已接受，本次恢复动作已存为新记忆")
        except httpx.HTTPError as exc:
            print(f"    [提示] 接受闭环存记忆失败：{exc}")


def _step_compare(persona: dict, row: dict) -> None:
    plan = persona["plan"]
    data = _post("/evaluation/compare", {"user_id": persona["id"], **plan})
    delta = data.get("delta", {})
    wm = data["with_memory"]["tasks"][0]["duration_minutes"] if data["with_memory"]["tasks"] else None
    wom = data["without_memory"]["tasks"][0]["duration_minutes"] if data["without_memory"]["tasks"] else None
    print(f"\n  [compare] {plan['goal']}")
    print(f"    无记忆时长={wom}，有记忆时长={wm}，时长差={delta.get('duration_minutes')}，"
          f"memory_count={delta.get('memory_count')}，memory_tokens={delta.get('memory_tokens')}")
    row["memory_preference"] = _ask_int(
        "    有记忆版本更贴合你的习惯吗？(1-5，5=有记忆明显更好)", lo=1, hi=5, default=5)


# ---------- 单个画像 ----------

def _run_persona(persona: dict, writer: csv.DictWriter) -> dict:
    row = {c: "" for c in COLUMNS}
    row.update({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "persona_id": persona["id"], "name": persona["name"],
        "dimension": persona["dimension"], "warmup": persona["warmup"],
    })
    print("\n" + "=" * 64)
    print(f"{persona['id']} · {persona['name']}（{persona['dimension']}）")
    print("=" * 64)
    try:
        _cleanup_user(persona["id"])
        _warmup(persona)
        if persona.get("plan"):
            _step_plan(persona, row)
        if persona.get("check"):
            _step_check(persona, row)
        if persona.get("recover"):
            _step_recover(persona, row)
        if persona.get("compare"):
            _step_compare(persona, row)
        if (row["plan_used_count"] or row["check_used_count"] or row["recover_used_count"]):
            row["understanding"] = _ask_int(
                "  理解 Agent 为什么这样调整吗？(1-5，5=完全理解)", lo=1, hi=5, default=5)
    except httpx.HTTPError as exc:
        row["note"] = f"HTTP 错误：{exc}"
        print(f"\n  [错误] {exc}")
    writer.writerow(row)
    return row


# ---------- 汇总 ----------

def _summarize(rows: list[dict]) -> None:
    accept_num = accept_den = 0
    recover_num = recover_den = 0
    plan_mods: list[int] = []
    understandings: list[int] = []
    preferences: list[int] = []

    for r in rows:
        if r["plan_accepted"] not in ("", None):
            accept_den += 1
            accept_num += 1 if str(r["plan_accepted"]).lower() in ("true", "1", "y", "yes") else 0
        if r["check_accepted"] not in ("", None):
            accept_den += 1
            accept_num += 1 if str(r["check_accepted"]).lower() in ("true", "1", "y", "yes") else 0
        if r["recover_continued"] not in ("", None):
            recover_den += 1
            recover_num += 1 if str(r["recover_continued"]).lower() in ("true", "1", "y", "yes") else 0
        if r["plan_modified"] not in ("", None):
            plan_mods.append(int(r["plan_modified"]))
        if r["understanding"] not in ("", None):
            understandings.append(int(r["understanding"]))
        if r["memory_preference"] not in ("", None):
            preferences.append(int(r["memory_preference"]))

    print("\n" + "=" * 64)
    print("§8.4 用户测试指标汇总（10 画像，研发者测试）")
    print("=" * 64)
    print(f"  个性化结果接受率 : {accept_num}/{accept_den}"
          + (f" = {accept_num/accept_den:.0%}" if accept_den else "  （无有效样本）"))
    print(f"  恢复后继续学习率 : {recover_num}/{recover_den}"
          + (f" = {recover_num/recover_den:.0%}" if recover_den else "  （无有效样本）"))
    if plan_mods:
        print(f"  平均计划修改次数 : {sum(plan_mods)/len(plan_mods):.1f} 次（样本 {len(plan_mods)}）")
    if understandings:
        print(f"  平均理解程度     : {sum(understandings)/len(understandings):.1f}/5（样本 {len(understandings)}）")
    if preferences:
        print(f"  有记忆偏好评分   : {sum(preferences)/len(preferences):.1f}/5（样本 {len(preferences)}）")
    print(f"\n结果已写入：{CSV_PATH}")


# ---------- main ----------

def main() -> int:
    global BASE
    parser = argparse.ArgumentParser(description="§8.4 用户测试驱动（10 画像）")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端地址")
    parser.add_argument("--only", help="只跑指定画像编号，如 1,10")
    parser.add_argument("--list", action="store_true", help="只看画像清单，不运行")
    args = parser.parse_args()

    if args.list:
        for i, p in enumerate(PERSONAS, 1):
            print(f"{i:2}. {p['id']} · {p['name']} — {p['dimension']}")
        return 0

    BASE = args.base_url.rstrip("/")
    selected = PERSONAS
    if args.only:
        indices = {int(x) - 1 for x in args.only.split(",") if x.strip().isdigit()}
        selected = [p for i, p in enumerate(PERSONAS) if i in indices]
        if not selected:
            print("--only 未匹配到任何画像")
            return 1

    OUTPUT_DIR.mkdir(exist_ok=True)
    new_file = not CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        if new_file:
            writer.writeheader()
        rows = [_run_persona(p, writer) for p in selected]

    _summarize(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
