"""验证 B 新增 #1：review_schedule 间隔复习（轻量实现：解析间隔 + plan 到期提醒）。

5 用例：
  1. 分类落库：feedback「每2天复习一次 BFS」→ 生成 REVIEW_SCHEDULE 记忆
  2. 到期提醒(正)：created_at 改 2 天前 → plan 同知识点 → explanation 含「复习提醒」
  3. 未到期(负)：created_at 改 1 天前 → plan → explanation 不含「复习提醒」
  4. 跨知识点(负)：plan 不同知识点 → 不含「复习提醒」（knowledge_point 过滤）
  5. 无效间隔(负)：「每0天复习一次 BFS」→ 即使过很久也不提醒（parse 返回 None）

用法（后端已启动，库已生成）：
    python scripts/verify_review_schedule.py --base-url http://127.0.0.1:8000 --db ..\\data\\studyflow.db

产出：控制台逐条 PASS/FAIL + outputs/verify_review_schedule.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
TIMEOUT = 300.0  # api.openai-next.com 延迟波动大（5s~128s）

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs"
JSON_PATH = OUTPUT_DIR / "verify_review_schedule.json"


def _post(path: str, payload: dict) -> dict:
    for attempt in range(4):
        if attempt:
            time.sleep(3 * attempt)
        try:
            resp = httpx.post(f"{BASE}{path}", json=payload, timeout=TIMEOUT)
        except httpx.TimeoutException:
            if attempt < 3:
                continue
            raise
        if resp.status_code >= 500 and attempt < 3:
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"{path} 重试耗尽")


def _cleanup_user(user_id: str) -> None:
    try:
        resp = httpx.get(
            f"{BASE}/memories",
            params={"user_id": user_id, "active": "true"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except httpx.HTTPError:
        return
    for item in items:
        try:
            httpx.delete(f"{BASE}/memories/{item['id']}", timeout=TIMEOUT).raise_for_status()
        except httpx.HTTPError:
            pass


def _shift_created_at(db_path: str, mem_id: str, days_ago: int) -> None:
    """把某条记忆的 created_at 改成 N 天前，模拟「到期」状态。"""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT created_at FROM memories WHERE id=?", (mem_id,)).fetchone()
        if row is None:
            raise RuntimeError(f"记忆 {mem_id} 不在库中（{db_path}）")
        raw = row[0]
        try:
            dt = datetime.fromisoformat(raw)  # Python 3.11 支持空格/T/时区
        except ValueError:
            dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S.%f")
        new_dt = dt - timedelta(days=days_ago)
        # 写回 SQLAlchemy 兼容的 naive UTC 格式（is_review_due 内会按 UTC 处理）
        conn.execute(
            "UPDATE memories SET created_at=? WHERE id=?",
            (new_dt.strftime("%Y-%m-%d %H:%M:%S.%f"), mem_id),
        )
        conn.commit()
    finally:
        conn.close()


def _feedback(user_id: str, course: str, knowledge_point: str, content: str) -> dict:
    return _post("/feedback", {
        "user_id": user_id,
        "course": course,
        "content": content,
        "task_type": "study",
        "knowledge_point": knowledge_point,
        "explicit": True,
    })


def _plan(user_id: str, course: str, knowledge_point: str) -> dict:
    return _post("/agent/plan", {
        "user_id": user_id,
        "course": course,
        "goal": f"复习 {knowledge_point}",
        "available_minutes": 30,
        "task_type": "study",
        "knowledge_point": knowledge_point,
    })


def _make_review_memory(db_path: str, user_id: str, course: str, kp: str, days_ago: int) -> str:
    """造一条 review_schedule 记忆并把 created_at 改成 days_ago 天前，返回记忆 id。"""
    _cleanup_user(user_id)
    data = _feedback(user_id, course, kp, "以后每2天复习一次 BFS")
    mems = data.get("memories", [])
    if not mems:
        raise RuntimeError(f"{user_id} feedback 未返回记忆")
    mem_id = mems[0]["id"]
    _shift_created_at(db_path, mem_id, days_ago)
    return mem_id


def main() -> int:
    global BASE
    parser = argparse.ArgumentParser(description="验证 review_schedule 间隔复习（#1）")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端地址")
    parser.add_argument("--db", required=True, help="SQLite 库路径，如 ..\\data\\studyflow.db")
    args = parser.parse_args()
    BASE = args.base_url.rstrip("/")
    db_path = str(Path(args.db).resolve())

    OUTPUT_DIR.mkdir(exist_ok=True)
    results: list[dict] = []

    def record(case_id: str, desc: str, ok: bool, detail: str, extra: dict | None = None) -> None:
        results.append({"id": case_id, "desc": desc, "ok": ok, "detail": detail, **(extra or {})})

    # 1. 分类落库
    try:
        _cleanup_user("verify-review-classify")
        data = _feedback("verify-review-classify", "数据结构与算法", "图的BFS", "以后每2天复习一次 BFS")
        mem = data["memories"][0]
        ok = mem.get("memory_type") == "review_schedule"
        record("review-classify", "feedback「每2天复习一次 BFS」→ REVIEW_SCHEDULE", ok,
               f"memory_type={mem.get('memory_type')}" if ok else f"memory_type={mem.get('memory_type')}（期望 review_schedule）",
               {"memory_type": mem.get("memory_type")})
    except httpx.HTTPError as exc:
        record("review-classify", "feedback「每2天复习一次 BFS」→ REVIEW_SCHEDULE", False, f"HTTP 错误：{exc}")

    # 2. 到期提醒(正)
    try:
        _make_review_memory(db_path, "verify-review-due", "数据结构与算法", "图的BFS", days_ago=2)
        plan = _plan("verify-review-due", "数据结构与算法", "图的BFS")
        explanation = plan.get("explanation", "")
        ok = "复习提醒" in explanation
        record("review-due-reminder", "created_at=2天前 → plan 同知识点出现「复习提醒」", ok,
               "explanation 含「复习提醒」" if ok else f"explanation 未含提醒：{explanation[:80]}…",
               {"used": len(plan.get("used_memory_ids", []))})
    except (httpx.HTTPError, RuntimeError) as exc:
        record("review-due-reminder", "created_at=2天前 → plan 同知识点出现「复习提醒」", False, str(exc))

    # 3. 未到期(负)
    try:
        _make_review_memory(db_path, "verify-review-notdue", "数据结构与算法", "图的BFS", days_ago=1)
        plan = _plan("verify-review-notdue", "数据结构与算法", "图的BFS")
        explanation = plan.get("explanation", "")
        ok = "复习提醒" not in explanation
        record("review-notdue", "created_at=1天前 → plan 不含「复习提醒」", ok,
               "未到期不提醒" if ok else f"未到期却提醒：{explanation[:80]}…")
    except (httpx.HTTPError, RuntimeError) as exc:
        record("review-notdue", "created_at=1天前 → plan 不含「复习提醒」", False, str(exc))

    # 4. 跨知识点(负)
    try:
        _make_review_memory(db_path, "verify-review-cross", "数据结构与算法", "图的BFS", days_ago=2)
        plan = _plan("verify-review-cross", "数据结构与算法", "动态规划")  # 不同知识点
        explanation = plan.get("explanation", "")
        ok = "复习提醒" not in explanation
        record("review-cross-kp", "plan 不同知识点 → 不含「复习提醒」（knowledge_point 过滤）", ok,
               "跨知识点不串" if ok else f"跨知识点串了：{explanation[:80]}…")
    except (httpx.HTTPError, RuntimeError) as exc:
        record("review-cross-kp", "plan 不同知识点 → 不含「复习提醒」", False, str(exc))

    # 5. 无效间隔(负)
    try:
        _cleanup_user("verify-review-invalid")
        data = _feedback("verify-review-invalid", "数据结构与算法", "图的BFS", "每0天复习一次 BFS")
        mems = data.get("memories", [])
        if mems:
            _shift_created_at(db_path, mems[0]["id"], days_ago=10)
        plan = _plan("verify-review-invalid", "数据结构与算法", "图的BFS")
        explanation = plan.get("explanation", "")
        ok = "复习提醒" not in explanation
        record("review-invalid-interval", "「每0天复习」无效间隔 → 不提醒", ok,
               f"memory_type={mems[0].get('memory_type') if mems else None}，不提醒" if ok
               else f"无效间隔却提醒：{explanation[:80]}…",
               {"memory_type": mems[0].get("memory_type") if mems else None})
    except (httpx.HTTPError, RuntimeError) as exc:
        record("review-invalid-interval", "「每0天复习」无效间隔 → 不提醒", False, str(exc))

    passed = sum(1 for r in results if r["ok"])
    for r in results:
        mark = "PASS" if r["ok"] else "FAIL"
        print(f"[{mark}] {r['id']} — {r['desc']}")
        print(f"       {r['detail']}")
    print(f"\n结果：{passed}/{len(results)} 通过")

    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "total": len(results),
        "passed": passed,
        "cases": results,
    }
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入：{JSON_PATH}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
