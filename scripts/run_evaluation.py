"""Run scripted memory evaluation scenarios.

用法（在项目根目录 G:\\华为计算机大赛\\黑客松\\黑客松 下执行）：

    python scripts/run_evaluation.py --mock          # 默认：直调检索器，不依赖模型/后端
    python scripts/run_evaluation.py --real          # 端到端有/无记忆对照（需后端 + LLM 已启动）
    python scripts/run_evaluation.py --mock --json   # 输出 JSON 报告

--mock 会先校验 20 个场景定义的一致性，再逐个运行并打印报告；
全部通过则退出码为 0，任一失败或指标不达标则退出码为 1。
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.evaluation.metrics import (  # noqa: E402
    TARGET_CONFIRMATION_APPLICATION,
    TARGET_MISUSE_MAX,
    TARGET_RECALL,
    EvaluationSummary,
)
from app.evaluation.runner import run_all  # noqa: E402
from app.evaluation.scenarios import (  # noqa: E402
    CATEGORY_NAMES,
    SCENARIOS,
    validate_scenarios,
)

# 表格列定义：(表头, 显示宽度, 对齐)；宽度按终端显示宽度（全角字符占 2 格）
_COLUMNS = (
    ("场景", 32, "left"),
    ("类别", 18, "left"),
    ("结果", 6, "left"),
    ("召回", 7, "right"),
    ("误用", 7, "right"),
    ("确认", 7, "right"),
    ("ret/u/c", 9, "right"),
    ("tok", 5, "right"),
    ("ms", 6, "right"),
)


def _summary_to_dict(summary: EvaluationSummary) -> dict:
    return {
        "total": summary.total,
        "passed": summary.passed_count,
        "all_passed": summary.all_passed,
        "targets_met": summary.targets_met,
        "macro_recall": round(summary.macro_recall, 4),
        "macro_misuse": round(summary.macro_misuse, 4),
        "macro_confirmation_application": round(summary.macro_confirmation_application, 4),
        "avg_memory_tokens": round(summary.avg_memory_tokens, 2),
        "avg_latency_ms": round(summary.avg_latency_ms, 2),
        "scenarios": [
            {
                "id": m.scenario_id,
                "category": m.category,
                "passed": m.passed,
                "recall": round(m.recall, 4),
                "misuse_rate": round(m.misuse_rate, 4),
                "confirmation_application": round(m.confirmation_application, 4),
                "retrieved_count": m.retrieved_count,
                "used_count": m.used_count,
                "candidate_count": m.candidate_count,
                "memory_tokens": m.memory_tokens,
                "latency_ms": m.latency_ms,
                "failures": m.failures,
            }
            for m in summary.metrics
        ],
    }


def _display_width(text: str) -> int:
    """按终端显示宽度计算（中文等全角字符占 2 格）。"""
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
        for ch in text
    )


def _pad(text: str, width: int, align: str = "left") -> str:
    gap = width - _display_width(text)
    if gap <= 0:
        return text
    if align == "right":
        return " " * gap + text
    return text + " " * gap


def _format_row(cells: list[str]) -> str:
    row = ""
    for cell, (_, width, align) in zip(cells, _COLUMNS):
        row += _pad(cell, width, align) + "  "
    return row.rstrip()


def _table_width() -> int:
    return sum(width for _, width, _ in _COLUMNS) + 2 * (len(_COLUMNS) - 1)


def _print_mock_report(summary: EvaluationSummary) -> None:
    bar = "=" * _table_width()
    dash = "-" * _table_width()
    print()
    print(bar)
    print("StudyFlow 记忆检索评测报告（mock 模式，直调 retrieve_memories）")
    print(bar)
    print(_format_row([header for header, _, _ in _COLUMNS]))
    print(dash)
    for m in summary.metrics:
        cells = [
            m.scenario_id,
            CATEGORY_NAMES.get(m.category, m.category),
            "通过" if m.passed else "失败",
            f"{m.recall:.1%}",
            f"{m.misuse_rate:.1%}",
            f"{m.confirmation_application:.1%}",
            f"{m.retrieved_count}/{m.used_count}/{m.candidate_count}",
            str(m.memory_tokens),
            str(m.latency_ms),
        ]
        print(_format_row(cells))
    print(dash)
    print(f"通过：{summary.passed_count}/{summary.total}")
    print(f"  宏平均召回率     : {summary.macro_recall:.2%}   （目标 ≥ {TARGET_RECALL:.0%}）")
    print(f"  宏平均误用率     : {summary.macro_misuse:.2%}   （目标 ≤ {TARGET_MISUSE_MAX:.0%}）")
    print(
        f"  宏平均确认应用率 : {summary.macro_confirmation_application:.2%}   "
        f"（目标 ≥ {TARGET_CONFIRMATION_APPLICATION:.0%}）"
    )
    print(f"  平均记忆 token   : {summary.avg_memory_tokens:.1f}")
    print(f"  平均检索耗时     : {summary.avg_latency_ms:.1f} ms")

    failed = [m for m in summary.metrics if not m.passed]
    if failed:
        print()
        print("失败明细：")
        for m in failed:
            for failure in m.failures:
                print(f"  [{m.scenario_id}] {failure}")
    print(bar)


def _run_real(base_url: str, timeout: float = 300.0) -> int:
    """端到端有/无记忆对照：对一组代表性目标调用 /evaluation/compare。"""
    try:
        import httpx  # noqa: F401
    except ImportError:
        print("--real 需要 httpx（后端依赖中已包含），请先安装：pip install httpx")
        return 1

    cases = [
        {"user_id": "evaluation-user", "course": "数据结构与算法", "goal": "学习图的 BFS",
         "available_minutes": 25, "task_type": "study", "knowledge_point": "BFS"},
        {"user_id": "evaluation-user", "course": "数据结构与算法", "goal": "学习拓扑排序",
         "available_minutes": 30, "task_type": "study", "knowledge_point": "拓扑排序"},
        {"user_id": "evaluation-user", "course": "高等数学", "goal": "理解极限的定义",
         "available_minutes": 25, "task_type": "study", "knowledge_point": "极限"},
    ]
    url = f"{base_url.rstrip('/')}/evaluation/compare"
    print(f"端到端有/无记忆对照 → {url}")
    for case in cases:
        print(f"请求中：{case['goal']}（{case['course']}）—— compare 内部约 4 次 LLM 调用，较慢请等待…")
        try:
            response = httpx.post(url, json=case, timeout=timeout)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException:
            print(f"[超时] {case['goal']}（{case['course']}）: 等待 {timeout:.0f}s 未返回")
            print("可能原因：LLM 提供方当前较慢/限流（compare 内部要跑 2 次规划、约 4 次 LLM 调用）。")
            print("建议：① 观察 uvicorn 终端是否仍在处理/重试；② 用 --timeout 600 重试；③ 稍后再试。")
            return 1
        except httpx.HTTPError as exc:
            print(f"[失败] {case['goal']}（{case['course']}）: {exc}")
            print("请确认后端已启动（uvicorn app.main:app --reload），且已配置 LLM API。")
            return 1
        delta = data.get("delta", {})
        print()
        print(f"目标：{case['goal']}（{case['course']}）")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        print(
            f"→ 记忆带来的差异：使用记忆 {delta.get('memory_count')} 条，"
            f"记忆 token {delta.get('memory_tokens')}，"
            f"时长差 {delta.get('duration_minutes')} 分钟"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="StudyFlow 记忆检索评测")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--mock", action="store_true",
        help="直调检索器（默认，不依赖模型/后端）",
    )
    mode_group.add_argument(
        "--real", action="store_true",
        help="端到端有/无记忆对照（需后端 + LLM 已启动）",
    )
    parser.add_argument("--base-url", default="http://localhost:8000", help="real 模式的后端地址")
    parser.add_argument("--timeout", type=float, default=300.0,
                        help="real 模式单次 /evaluation/compare 的客户端超时（秒，默认 300）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告（mock 模式）")
    args = parser.parse_args()

    if args.real:
        return _run_real(args.base_url, args.timeout)

    problems = validate_scenarios(SCENARIOS)
    if problems:
        for scenario, errors in problems:
            print(f"[场景定义错误] {scenario.id}: {'; '.join(errors)}")
        print("场景定义存在错误，请先修正再运行。")
        return 1

    summary = run_all(SCENARIOS)
    if args.json:
        print(json.dumps(_summary_to_dict(summary), ensure_ascii=False, indent=2))
    else:
        _print_mock_report(summary)

    if not summary.all_passed:
        print("\n存在失败场景，请对照「失败明细」检查（检索归 B，先反馈给 B 再改）。")
        return 1
    if not summary.targets_met:
        print("\n指标未达标：召回率/误用率/确认应用率未达到目标阈值。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
