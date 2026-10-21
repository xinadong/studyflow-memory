"""验证 B 修复 #2：恢复习惯分类边界（recovery / review 触发词优先于「分钟」和任务措辞）。

端到端：POST /feedback 走真实 LLM 分类 + 守卫，断言最终 memory_type / block_type；
对 recovery 用例再走 /agent/recover 确认 used 命中（记忆真正被应用）。

用法（后端已启动）：
    python scripts/verify_fix_boundary.py --base-url http://127.0.0.1:8000

产出：控制台逐条 PASS/FAIL + outputs/verify_fix_boundary.json
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
TIMEOUT = 300.0  # api.openai-next.com 延迟波动大（5s~128s）

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs"
JSON_PATH = OUTPUT_DIR / "verify_fix_boundary.json"

CASES = [
    {
        "id": "boundary-recovery-minutes",
        "desc": "恢复习惯含「分钟」不再被误判成时长偏好",
        "user_id": "verify-r02",
        "course": "高等数学",
        "knowledge_point": "极限",
        "content": "学累了休息5分钟",
        "expect_type": "recovery_experience",
        "expect_block": "fatigue",
        "recover": {"block_type": "fatigue", "context": "学累了"},
    },
    {
        "id": "boundary-recovery-task-words",
        "desc": "恢复习惯含任务措辞不再被误判成时长偏好",
        "user_id": "verify-r06",
        "course": "数据结构与算法",
        "knowledge_point": "动态规划",
        "content": "时间不够只做核心一题",
        "expect_type": "recovery_experience",
        "expect_block": "time",
        "recover": {"block_type": "time", "context": "时间不够了"},
    },
    {
        "id": "boundary-too-hard-vs-explanation",
        "desc": "「太难」触发词优先于讲解措辞",
        "user_id": "verify-b03",
        "course": "高等数学",
        "knowledge_point": "级数",
        "content": "任务太难，先看一个例子",
        "expect_type": "recovery_experience",
        "expect_block": "too_hard",
        "recover": None,
    },
    {
        "id": "boundary-review-schedule",
        "desc": "复习日程措辞优先于分钟/任务措辞",
        "user_id": "verify-b04",
        "course": "数据结构与算法",
        "knowledge_point": "图的BFS",
        "content": "以后每2天复习一次 BFS",
        "expect_type": "review_schedule",
        "expect_block": None,
        "recover": None,
    },
]


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
    """软删除该 user 已有活跃记忆，保证幂等、不累积。"""
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


def run_case(case: dict) -> dict:
    result = {
        "id": case["id"],
        "desc": case["desc"],
        "ok": False,
        "memory_type": None,
        "block_type": None,
        "recover_used": None,
        "detail": "",
    }
    uid = case["user_id"]
    _cleanup_user(uid)
    try:
        data = _post("/feedback", {
            "user_id": uid,
            "course": case["course"],
            "content": case["content"],
            "task_type": "study",
            "knowledge_point": case["knowledge_point"],
            "explicit": True,
        })
        mems = data.get("memories", [])
        if not mems:
            result["detail"] = "feedback 未返回记忆"
            return result
        mem = mems[0]
        result["memory_type"] = mem.get("memory_type")
        result["block_type"] = mem.get("block_type")

        type_ok = mem.get("memory_type") == case["expect_type"]
        if case["expect_block"]:
            block_ok = mem.get("block_type") == case["expect_block"]
        else:
            block_ok = mem.get("block_type") is None
        if not (type_ok and block_ok):
            result["detail"] = (
                f"分类不符：type={mem.get('memory_type')} block={mem.get('block_type')}，"
                f"期望 type={case['expect_type']} block={case['expect_block']}"
            )
            return result

        if case.get("recover"):
            r = _post("/agent/recover", {
                "user_id": uid,
                "course": case["course"],
                "block_type": case["recover"]["block_type"],
                "context": case["recover"]["context"],
                "task_type": "study",
                "knowledge_point": case["knowledge_point"],
            })
            result["recover_used"] = len(r.get("used_memory_ids", []))
            if result["recover_used"] < 1:
                result["detail"] = "分类正确但 recover used=0（恢复记忆未命中）"
                return result

        result["ok"] = True
        result["detail"] = "PASS"
        return result
    except httpx.HTTPError as exc:
        result["detail"] = f"HTTP 错误：{exc}"
        return result


def main() -> int:
    global BASE
    parser = argparse.ArgumentParser(description="验证恢复习惯分类边界修复（#2）")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端地址")
    args = parser.parse_args()
    BASE = args.base_url.rstrip("/")

    OUTPUT_DIR.mkdir(exist_ok=True)
    results = [run_case(c) for c in CASES]
    passed = sum(1 for r in results if r["ok"])

    for r in results:
        mark = "PASS" if r["ok"] else "FAIL"
        print(f"[{mark}] {r['id']} — {r['desc']}")
        print(f"       memory_type={r['memory_type']} block_type={r['block_type']} recover_used={r['recover_used']}")
        if not r["ok"]:
            print(f"       → {r['detail']}")
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
