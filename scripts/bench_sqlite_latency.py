"""§8.2 真实 SQLite 检索性能复测（P95<100ms，额外本地处理<200ms）。

对应方案指标：项目方案 §8.2「对话速度：SQLite 检索 P95<100ms，额外本地处理<200ms」。

方法：
- 用独立的 bench SQLite 文件（outputs/bench_studyflow.db），不污染真实 data/studyflow.db，
  但仍是文件级真实 SQLite（非 InMemory），直接 import B 的 SqlAlchemyMemoryRepository。
- 分别在 100 / 1000 条记忆两档下，对三种路径各测 N 轮取 P50/P95/P99/max：
    1. SQLite 查询（repo.list + 实体映射）        → 对应「SQLite 检索」目标 <100ms
    2. 本地处理（retrieve_memory_candidates：排序 + token 预算）→ 对应「额外本地处理」目标 <200ms
    3. 完整检索链路（retrieve_memories：SQL + 本地）→ 参考值

用法（项目根目录下执行，需 Python 环境已装 sqlalchemy）：
    python scripts/bench_sqlite_latency.py
    python scripts/bench_sqlite_latency.py --scales 100,1000,5000 --iter 300
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from time import perf_counter

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.domain.entities.memory import Memory  # noqa: E402
from app.domain.repositories.memory_repository import MemoryFilter  # noqa: E402
from app.domain.value_objects.memory_type import (  # noqa: E402
    ConfirmationStatus,
    MemoryType,
)
from app.infrastructure.database import Base  # noqa: E402
from app.infrastructure import models as _models  # noqa: E402,F401  注册 ORM 表
from app.infrastructure.repositories.sqlalchemy_memory_repository import (  # noqa: E402
    SqlAlchemyMemoryRepository,
)
from app.memory.retriever import (  # noqa: E402
    retrieve_memories,
    retrieve_memory_candidates,
)

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs"
BENCH_DB = OUTPUT_DIR / "bench_studyflow.db"

FILTER = MemoryFilter(
    user_id="bench-user",
    course="数据结构与算法",
    memory_type=MemoryType.TASK_PREFERENCE,
)

TARGET_SQL_P95_MS = 100.0
TARGET_LOCAL_P95_MS = 200.0


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = k - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def _stats(latencies: list[float]) -> dict[str, float]:
    ordered = sorted(latencies)
    return {
        "p50": _percentile(ordered, 0.50),
        "p95": _percentile(ordered, 0.95),
        "p99": _percentile(ordered, 0.99),
        "max": ordered[-1] if ordered else 0.0,
        "mean": sum(ordered) / len(ordered) if ordered else 0.0,
    }


def _seed(repo: SqlAlchemyMemoryRepository, n: int) -> None:
    for i in range(n):
        repo.add(
            Memory(
                user_id="bench-user",
                memory_type=MemoryType.TASK_PREFERENCE,
                course="数据结构与算法",
                content=f"习惯每次专注学习{i % 200 + 20}分钟，配合例题练习",
                task_type="study",
                knowledge_point=f"知识点{i % 50}",
                confirmation_status=(
                    ConfirmationStatus.CONFIRMED if i % 5 != 0 else ConfirmationStatus.PENDING
                ),
                confidence=0.5 + (i % 10) / 20.0,
            ),
            commit=False,
        )
    repo.session.commit()


_current_engine = None


def _make_session_factory():
    global _current_engine
    # 释放上一个档位的引擎连接池：否则 Windows 下 SQLite 文件仍被占用，unlink 会 PermissionError
    if _current_engine is not None:
        _current_engine.dispose()
        _current_engine = None
    if BENCH_DB.exists():
        BENCH_DB.unlink()
    OUTPUT_DIR.mkdir(exist_ok=True)
    _current_engine = create_engine(
        f"sqlite:///{BENCH_DB.as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=_current_engine)
    return sessionmaker(bind=_current_engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _run_scale(n: int, n_iter: int) -> dict:
    Session = _make_session_factory()

    seeding = Session()
    repo = SqlAlchemyMemoryRepository(seeding)
    _seed(repo, n)
    seeding.close()

    # 1. SQLite 查询 + 实体映射（每轮独立 session，模拟每次请求）
    sql_lat: list[float] = []
    for _ in range(n_iter):
        s = Session()
        r = SqlAlchemyMemoryRepository(s)
        t0 = perf_counter()
        r.list(FILTER)
        sql_lat.append((perf_counter() - t0) * 1000.0)
        s.close()

    # 2. 本地处理：排序 + token 预算（一次性拉取后反复跑，隔离出非 DB 部分）
    s = Session()
    r = SqlAlchemyMemoryRepository(s)
    eligible = [m for m in r.list(FILTER) if m.is_usable]
    s.close()
    local_lat: list[float] = []
    for _ in range(n_iter):
        t0 = perf_counter()
        retrieve_memory_candidates(eligible, limit=5, max_memory_tokens=300)
        local_lat.append((perf_counter() - t0) * 1000.0)

    # 3. 完整检索链路（SQL + 本地）
    full_lat: list[float] = []
    for _ in range(n_iter):
        s = Session()
        r = SqlAlchemyMemoryRepository(s)
        t0 = perf_counter()
        retrieve_memories(r, FILTER, limit=5, max_memory_tokens=300)
        full_lat.append((perf_counter() - t0) * 1000.0)
        s.close()

    return {"n": n, "sql": _stats(sql_lat), "local": _stats(local_lat), "full": _stats(full_lat)}


def _fmt_ms(v: float) -> str:
    return f"{v:7.2f}ms"


def _print_row(label: str, stats: dict) -> None:
    print(
        f"  {label:14} P50 {_fmt_ms(stats['p50'])}  P95 {_fmt_ms(stats['p95'])}  "
        f"P99 {_fmt_ms(stats['p99'])}  max {_fmt_ms(stats['max'])}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="§8.2 SQLite 检索性能复测")
    parser.add_argument("--scales", default="100,1000", help="记忆条数档位，逗号分隔")
    parser.add_argument("--iter", type=int, default=200, help="每档每路径计时轮数")
    args = parser.parse_args()

    scales = [int(x) for x in args.scales.split(",") if x.strip().isdigit()]
    if not scales:
        print("--scales 需为数字，如 100,1000")
        return 1

    print(f"bench DB: {BENCH_DB}")
    print(f"指标目标：SQLite 检索 P95 < {TARGET_SQL_P95_MS:.0f}ms；额外本地处理 P95 < {TARGET_LOCAL_P95_MS:.0f}ms\n")

    all_ok = True
    for n in scales:
        result = _run_scale(n, args.iter)
        print(f"—— {n} 条记忆（每路径 {args.iter} 轮）——")
        _print_row("SQLite 查询", result["sql"])
        _print_row("本地处理", result["local"])
        _print_row("完整检索链路", result["full"])
        sql_ok = result["sql"]["p95"] < TARGET_SQL_P95_MS
        local_ok = result["local"]["p95"] < TARGET_LOCAL_P95_MS
        print(f"    达标：SQLite 检索 {'✅' if sql_ok else '❌'}  本地处理 {'✅' if local_ok else '❌'}")
        all_ok = all_ok and sql_ok and local_ok
        print()

    print("结论：", "全部档位达标" if all_ok else "存在未达标档位，请查看上方 P95")
    print("注：这是真实文件级 SQLite（非 InMemory），与 mock 模式的 0ms 数据不同源。")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
