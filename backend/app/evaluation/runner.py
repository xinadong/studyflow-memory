"""Evaluation runner for memory and no-memory comparisons.

核心原则：调 B 的 retriever，不自己写检索——这样测的就是线上真实行为。

每个场景：
1. 建一个独立的 InMemoryMemoryRepository；
2. 种入 seed_memories；
3. 调 B 的 retrieve_memories(repo, filters, limit, max_memory_tokens)；
4. 用 content 作稳定标识，对 retrieved / used / candidates 做精确比对；
5. 汇总召回率、误用率、确认应用率、token 与耗时。
"""

from __future__ import annotations

from app.evaluation.metrics import (
    EvaluationSummary,
    ScenarioMetrics,
    compute_confirmation_application,
    compute_misuse_rate,
    compute_recall,
    summarize,
)
from app.evaluation.scenarios import Scenario
from app.infrastructure.repositories.in_memory_memory_repository import (
    InMemoryMemoryRepository,
)
from app.infrastructure.telemetry.latency_tracker import LatencyTimer
from app.infrastructure.telemetry.token_tracker import estimate_tokens
from app.memory.retriever import retrieve_memories


def run_scenario(scenario: Scenario) -> ScenarioMetrics:
    """运行单个场景，返回指标与断言结果。"""
    repo = InMemoryMemoryRepository()
    for memory in scenario.seed_memories:
        repo.add(memory)

    with LatencyTimer() as timer:
        result = retrieve_memories(
            repo,
            scenario.filters,
            limit=scenario.limit,
            max_memory_tokens=scenario.max_memory_tokens,
        )

    retrieved = {memory.content for memory in result.retrieved}
    used = {memory.content for memory in result.used}
    candidates = {memory.content for memory in result.candidates}

    failures: list[str] = []

    def assert_set(name: str, expected: set[str], actual: set[str]) -> None:
        if actual == expected:
            return
        parts: list[str] = []
        if expected - actual:
            parts.append(f"缺少 {sorted(expected - actual)}")
        if actual - expected:
            parts.append(f"多余 {sorted(actual - expected)}")
        failures.append(f"{name} 不符：{'；'.join(parts)}")

    assert_set("retrieved", scenario.expected_retrieved, retrieved)
    assert_set("used", scenario.expected_used, used)
    assert_set("candidates", scenario.expected_candidates, candidates)

    memory_tokens = sum(estimate_tokens(memory.content) for memory in result.retrieved)

    return ScenarioMetrics(
        scenario_id=scenario.id,
        category=scenario.category,
        passed=not failures,
        recall=compute_recall(scenario.expected_retrieved, retrieved),
        misuse_rate=compute_misuse_rate(scenario.expected_used, used),
        confirmation_application=compute_confirmation_application(scenario.expected_used, used),
        retrieved_count=len(result.retrieved),
        used_count=len(result.used),
        candidate_count=len(result.candidates),
        memory_tokens=memory_tokens,
        latency_ms=timer.elapsed_ms,
        failures=failures,
    )


def run_all(scenarios: list[Scenario]) -> EvaluationSummary:
    return summarize([run_scenario(scenario) for scenario in scenarios])
