"""§15.3 第 5 条后半：供应商 token 用量归档（唯一待补项）。

拉一次 `GET /metrics`，归档两类 token 口径：
- `input_tokens` / `output_tokens`：**供应商 usage**（B 的 client.py 用
  `usage.prompt_tokens / usage.completion_tokens` 累加，真实发给模型的 token）；
- `memory_tokens`：**本地估算**（`estimate_tokens`，len//4，注入的 confirmed 记忆上下文）。

用法（需后端已启动、且已经跑过若干次 agent 调用，否则用量为 0）：
    python scripts/archive_metrics_usage.py --base-url http://127.0.0.1:8000

产出：
1. 终端打印总模型 token（供应商 usage）、记忆注入 token（本地估算）及占比；
2. 追加归档 `outputs/metrics_usage_archive.json`（每次运行一条记录，带时间戳）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
TIMEOUT = 30.0

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs"
ARCHIVE_PATH = OUTPUT_DIR / "metrics_usage_archive.json"


def _pct(num: float, den: float) -> str:
    if den <= 0:
        return "n/a（分母为 0）"
    return f"{num / den:.2%}"


def main() -> int:
    global BASE
    parser = argparse.ArgumentParser(description="供应商 token 用量归档（GET /metrics）")
    parser.add_argument("--base-url", default=BASE, help="后端地址")
    args = parser.parse_args()
    BASE = args.base_url.rstrip("/")

    try:
        resp = httpx.get(f"{BASE}/metrics", timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        print(f"[错误] 拉取 /metrics 失败：{exc}")
        print("提示：确认后端已启动，且已跑过若干次 agent 调用（否则无用量可归档）。")
        return 1

    input_tokens = int(data.get("input_tokens") or 0)
    output_tokens = int(data.get("output_tokens") or 0)
    memory_tokens = int(data.get("memory_tokens") or 0)
    agent_runs = data.get("agent_runs") or 0
    semantics = data.get("memory_tokens_semantics", "（未标注）")

    total_model_tokens = input_tokens + output_tokens

    print("=" * 64)
    print("供应商 token 用量归档（§15.3 第 5 条后半）")
    print("=" * 64)
    print(f"  agent 调用次数      : {agent_runs}")
    print(f"  输入 token（供应商） : {input_tokens}")
    print(f"  输出 token（供应商） : {output_tokens}")
    print(f"  总模型 token（供应商）: {total_model_tokens}")
    print(f"  记忆注入 token（本地估算）: {memory_tokens}（{semantics}）")
    print(f"  记忆注入占输入比例   : {_pct(memory_tokens, input_tokens)}")
    print(f"  记忆注入占总 token 比例: {_pct(memory_tokens, total_model_tokens)}")
    print("-" * 64)
    print("归档口径：")
    print("  总模型 token = input_tokens + output_tokens，来自供应商 usage")
    print("  （usage.prompt_tokens / usage.completion_tokens 累加），是真实发给模型的量；")
    print("  memory_tokens 为本地估算（len//4），仅供「记忆注入开销」参考。")

    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "base_url": BASE,
        "agent_runs": agent_runs,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_model_tokens": total_model_tokens,
        "memory_tokens": memory_tokens,
        "memory_tokens_semantics": semantics,
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    if ARCHIVE_PATH.exists() and ARCHIVE_PATH.stat().st_size > 0:
        try:
            archive = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            archive = []
    else:
        archive = []
    archive.append(record)
    ARCHIVE_PATH.write_text(
        json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已归档：{ARCHIVE_PATH}（累计 {len(archive)} 条）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
