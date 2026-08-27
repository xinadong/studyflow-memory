"""§8.4 真实用户测试驱动脚本：3 名真实同学，各约 10 分钟。

与 scripts/user_testing.py（研发者测试 · 10 画像）的分工（两层设计）：
- 层一 · 研发者测试（user_testing.py）：研发者按 10 画像做功能覆盖，验证四步会话的功能正确性，
  产出客观证据（used 计数、跨课程隔离、软删、时长差）与功能覆盖设计；
- 层二 · 3 名真实同学（本脚本）：真实学生按自己的话题与真实反应走会话，
  产出 5 项主观指标（接受率 / 继续学习率 / 计划修改次数 / 理解程度 / 有记忆偏好评分）。
  主观指标只采信本层真实数据，避免「设计者自评」偏差。

同学不碰键盘：C 当主持人，把同学的口头回答与评分录入本脚本，脚本负责调后端并落 CSV。

每位同学流程：
  1. 定任务（课程 / 目标 / 知识点 / 可用时长）
  2. 说一句学习习惯（POST /feedback，explicit=True 表示同学已确认）→ 生成记忆
  3. plan（含「改 → 反馈 → 重排」闭环）
  4. check（两步：问题 → 回答 → 评估层级 + 反馈）
  5. recover（设卡点场景，含「接受 → 存新记忆」闭环）
  6. compare（有 / 无记忆 A/B 对照）
  7. 理解程度（1-5）+ 一句开放反馈（原话记录）

用法（需后端已启动）：
    python scripts/real_user_testing.py --base-url http://127.0.0.1:8000
    python scripts/real_user_testing.py --base-url ... --student r-01   # 指定学生编号

产出：追加写入 outputs/real_user_results.csv；每次跑完读取全表，打印截至当前的 5 项主观指标汇总。
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
TIMEOUT = 300.0  # api.openai-next.com 延迟波动大（5s~128s），单步可能包含多次 LLM 调用

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs"
CSV_PATH = OUTPUT_DIR / "real_user_results.csv"

COLUMNS = [
    "timestamp", "student_id", "preference", "course", "goal",
    "knowledge_point", "available_minutes",
    "plan_used_count", "plan_modified", "plan_accepted",
    "check_used_count", "check_accepted", "check_answer", "check_assessed_level",
    "recover_used_count", "recover_continued",
    "understanding", "memory_preference", "open_feedback", "note",
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
    """POST 带重试：中转站（api.openai-next.com）抖动会返回 5xx 或超时。"""
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


def _cleanup_user(user_id: str) -> None:
    """软删除该学生已有的活跃记忆，保证重跑幂等、不产生重复记忆。"""
    try:
        resp = httpx.get(
            f"{BASE}/memories",
            params={"user_id": user_id, "active": "true"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except httpx.HTTPError:
        print("  [提示] 清理该学生已有记忆失败，可能有重复，建议人工核对")
        return
    for item in items:
        try:
            httpx.delete(f"{BASE}/memories/{item['id']}", timeout=TIMEOUT).raise_for_status()
        except httpx.HTTPError:
            pass
    if items:
        print(f"  [清理] 软删除该学生已有 {len(items)} 条活跃记忆（幂等重跑）")


# ---------- 会话步骤 ----------

def _print_plan(data: dict, goal: str, available: int) -> None:
    print(f"\n  [plan] {goal}（可用 {available} 分钟）")
    for t in data["tasks"]:
        print(f"    任务：{t['title']}（{t['duration_minutes']} 分钟）")
    print(f"    说明：{data['explanation']}")
    print(f"    used={len(data['used_memory_ids'])} retrieved={len(data['retrieved_memory_ids'])} "
          f"memory_tokens={data['metrics'].get('memory_tokens', 0)}")


def _step_plan(plan: dict, row: dict) -> None:
    data = _post("/agent/plan", plan)
    row["plan_used_count"] = len(data["used_memory_ids"])
    _print_plan(data, plan["goal"], plan["available_minutes"])

    # 修改闭环：同学不满意 → 提反馈（生成记忆）→ 重排看是否自动用上
    modified = 0
    while True:
        if row["plan_used_count"] == 0:
            print("    （无记忆被应用：冷启动或习惯没命中。同学可改一次，观察「反馈→记忆→重排」闭环）")
        want = _ask_bool("  同学想改这个计划吗？(y/n)", "n")
        if not want:
            break
        content = _ask("  改成什么？同学原话（含「分钟」会记成时长偏好）：").strip()
        if not content:
            continue
        try:
            _post("/feedback", {
                "user_id": plan["user_id"], "course": plan["course"],
                "content": content, "task_type": plan.get("task_type", "study"),
                "knowledge_point": plan.get("knowledge_point"), "explicit": True,
            })
        except httpx.HTTPError as exc:
            print(f"    [错误] 提交反馈失败：{exc}")
            row["note"] = f"反馈失败：{exc}"
            break
        print(f"    [反馈] 已提交：{content}")
        data = _post("/agent/plan", plan)
        row["plan_used_count"] = len(data["used_memory_ids"])
        _print_plan(data, plan["goal"], plan["available_minutes"])
        modified += 1
    row["plan_modified"] = modified
    if row["plan_used_count"] > 0:
        row["plan_accepted"] = _ask_bool("  同学接受这个计划吗？(y/n)", "y")
    else:
        print("    （无记忆被应用 → 跳过接受度，属预期）")


def _step_check(check: dict, row: dict) -> None:
    # 第一步：生成问题（不传 answer，看讲解风格是否命中偏好）
    q = _post("/agent/check", check)
    row["check_used_count"] = len(q["used_memory_ids"])
    print(f"\n  [check] {check['knowledge_point']}（level=recall）")
    print(f"    问题：{q['question']}")
    print(f"    used={row['check_used_count']}")
    # 第二步：同学回答 → 评估层级 + 针对回答的真实反馈
    answer = _ask("  同学怎么回答这个问题？（原话/大意）").strip()
    if not answer:
        answer = "（未作答）"
    a = _post("/agent/check", {**check, "answer": answer})
    row["check_answer"] = answer
    row["check_assessed_level"] = a.get("assessed_level")
    print(f"    同学回答：{answer}")
    print(f"    评估层级：{row['check_assessed_level']}")
    print(f"    反馈：{a['feedback']}")
    if row["check_used_count"] > 0:
        row["check_accepted"] = _ask_bool("  同学觉得这个讲解符合自己的习惯吗？(y/n)", "y")
    else:
        print("    （无讲解偏好被应用，跳过接受度）")


def _step_recover(base: dict, row: dict) -> None:
    block_type = _ask("  卡点类型（time/too_hard/distraction/fatigue）：", "fatigue").strip().lower()
    if block_type not in ("time", "too_hard", "distraction", "fatigue"):
        block_type = "fatigue"
    context = _ask("  同学用自己的话说卡在哪：").strip() or "学不进去了"
    payload = {**base, "block_type": block_type, "context": context}
    data = _post("/agent/recover", payload)
    row["recover_used_count"] = len(data["used_memory_ids"])
    print(f"\n  [recover] block_type={block_type}（{context}）")
    print(f"    建议动作：{data['action']}")
    print(f"    理由：{data['reason']}")
    print(f"    used={row['recover_used_count']}")
    row["recover_continued"] = _ask_bool("  同学会继续学习吗？(y/n)", "y")
    if row["recover_continued"]:
        # 接受闭环：带 user_acceptance=true 再调一次，把本次动作存成新恢复记忆
        try:
            _post("/agent/recover", {**payload, "user_acceptance": True})
            print("    [闭环] 已接受，本次恢复动作已存为新记忆")
        except httpx.HTTPError as exc:
            print(f"    [提示] 接受闭环存记忆失败：{exc}")


def _step_compare(plan: dict, row: dict) -> None:
    data = _post("/evaluation/compare", plan)
    delta = data.get("delta", {})
    wm = data["with_memory"]["tasks"][0]["duration_minutes"] if data["with_memory"]["tasks"] else None
    wom = data["without_memory"]["tasks"][0]["duration_minutes"] if data["without_memory"]["tasks"] else None
    print(f"\n  [compare] {plan['goal']}")
    print(f"    无记忆时长={wom}，有记忆时长={wm}，时长差={delta.get('duration_minutes')}，"
          f"memory_count={delta.get('memory_count')}，memory_tokens={delta.get('memory_tokens')}")
    row["memory_preference"] = _ask_int(
        "  问同学：有记忆版本更贴合你的习惯吗？(1-5，5=有记忆明显更好)", lo=1, hi=5, default=5)


# ---------- 单名同学 ----------

def _run_student(student_id: str, writer: csv.DictWriter) -> dict:
    row = {c: "" for c in COLUMNS}
    row.update({"timestamp": datetime.now().isoformat(timespec="seconds"), "student_id": student_id})
    print("\n" + "=" * 64)
    print(f"真实用户 · {student_id}")
    print("=" * 64)
    print("主持提示：先问「今天想学什么」，再问「学习习惯」，过程按同学真实反应录。")
    try:
        _cleanup_user(student_id)

        # 1. 定任务
        course = _ask("  同学今天想学哪门课？").strip()
        goal = _ask("  具体想学/想做什么？（一句话目标）").strip()
        kp = _ask("  知识点（用于记忆匹配，尽量精确）").strip()
        available = _ask_int("  今天大概有多少分钟？", lo=1, default=30)
        row["course"], row["goal"], row["knowledge_point"], row["available_minutes"] = \
            course, goal, kp, available

        plan = {"user_id": student_id, "course": course, "goal": goal,
                "available_minutes": available, "task_type": "study", "knowledge_point": kp}

        # 2. 说一句学习习惯
        habit = _ask("  问同学：你学习上有什么习惯？一句话说清（含「分钟」记时长、含「先看定义/先看例子」记讲解）：").strip()
        if habit:
            row["preference"] = habit
            data = _post("/feedback", {
                "user_id": student_id, "course": course, "content": habit,
                "task_type": "study", "knowledge_point": kp, "explicit": True,
            })
            for mem in data.get("memories", []):
                print(f"  [feedback→{mem['memory_type']}] {mem['content']}")
        else:
            print("  （未说习惯，按冷启动处理）")

        # 3. plan（含修改闭环）
        _step_plan(plan, row)

        # 4. check（两步）
        material = _ask("  check 用：这个知识点的一句话教材（可空，回车跳过）").strip()
        check_payload = {"user_id": student_id, "course": course, "knowledge_point": kp,
                         "task_type": "study", "level": "recall"}
        if material:
            check_payload["material"] = material
        _step_check(check_payload, row)

        # 5. recover（含接受闭环）
        _step_recover({"user_id": student_id, "course": course, "knowledge_point": kp}, row)

        # 6. compare（有/无记忆对照）
        _step_compare(plan, row)

        # 7. 理解程度 + 开放反馈
        if row["plan_used_count"] or row["check_used_count"] or row["recover_used_count"]:
            row["understanding"] = _ask_int(
                "  问同学：理解系统为什么这样调整吗？(1-5，5=完全理解)", lo=1, hi=5, default=5)
        row["open_feedback"] = _ask("  问同学：整个过程哪里最有帮助 / 最别扭？（原话记录）").strip()
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
    print(f"§8.4 真实用户测试指标汇总（{len(rows)} 名真实同学）")
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
    parser = argparse.ArgumentParser(description="§8.4 真实用户测试（3 名真实同学）")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端地址")
    parser.add_argument("--student", help="学生编号，如 r-01 / r-02 / r-03")
    args = parser.parse_args()

    BASE = args.base_url.rstrip("/")
    student_id = args.student or _ask("学生编号（r-01 / r-02 / r-03）：").strip()
    if not student_id:
        print("需要学生编号")
        return 1

    OUTPUT_DIR.mkdir(exist_ok=True)
    # 文件不存在或为空都算「需要写表头」，避免上次空跑留下 0 字节文件后无表头
    new_file = not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0
    with open(CSV_PATH, "a", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        if new_file:
            writer.writeheader()
        _run_student(student_id, writer)

    # 汇总全表（截至当前所有已录学生）
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    _summarize(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
