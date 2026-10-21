"""Recall, misuse, confirmation-application, token and latency metrics.

三项目标指标（对应优化版 md 8.3）：

1. 召回率（recall）
   应检索到的相关记忆中被 retrieved 命中的比例，目标 ≥ 90%。
   recall = |expected_retrieved ∩ actual_retrieved| / |expected_retrieved|

2. 误用率（misuse rate）
   used（直接影响了输出的记忆）中「不该用却用了」的比例，目标 ≤ 10%。
   misuse = |actual_used - expected_used| / |actual_used|

3. 确认应用率（confirmation-application）
   应应用的 confirmed 记忆中被 used 命中的比例，目标 ≥ 85%。
   confirmation_application = |expected_used ∩ actual_used| / |expected_used|

另统计平均记忆 token 与平均检索耗时，用于成本/延迟评估。
"""

from __future__ import annotations

from dataclasses import dataclass, field

TARGET_RECALL = 0.90
TARGET_MISUSE_MAX = 0.10
TARGET_CONFIRMATION_APPLICATION = 0.85


@dataclass
class ScenarioMetrics:
    """单个场景跑完后的指标与断言结果。"""

    scenario_id: str
    category: str
    passed: bool
    recall: float
    misuse_rate: float
    confirmation_application: float
    retrieved_count: int
    used_count: int
    candidate_count: int
    memory_tokens: int
    latency_ms: int
    failures: list[str] = field(default_factory=list)


@dataclass
class EvaluationSummary:
    """全量评测的汇总。"""

    metrics: list[ScenarioMetrics]
    total: int = 0
    passed_count: int = 0
    macro_recall: float = 0.0
    macro_misuse: float = 0.0
    macro_confirmation_application: float = 0.0
    avg_memory_tokens: float = 0.0
    avg_latency_ms: float = 0.0

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.passed_count == self.total

    @property
    def targets_met(self) -> bool:
        return (
            self.macro_recall >= TARGET_RECALL
            and self.macro_misuse <= TARGET_MISUSE_MAX
            and self.macro_confirmation_application >= TARGET_CONFIRMATION_APPLICATION
        )


def _ratio(numerator: int, denominator: int) -> float:
    """分母为 0 时视为 1.0（没有期望项，不算失分）。"""
    if denominator == 0:
        return 1.0
    return numerator / denominator


def compute_recall(expected: set[str], actual: set[str]) -> float:
    return _ratio(len(expected & actual), len(expected))


def compute_misuse_rate(expected_used: set[str], actual_used: set[str]) -> float:
    if not actual_used:
        return 0.0
    return len(actual_used - expected_used) / len(actual_used)


def compute_confirmation_application(expected_used: set[str], actual_used: set[str]) -> float:
    return _ratio(len(expected_used & actual_used), len(expected_used))


def summarize(metrics: list[ScenarioMetrics]) -> EvaluationSummary:
    total = len(metrics)
    if total == 0:
        return EvaluationSummary(metrics=metrics)
    passed = sum(1 for metric in metrics if metric.passed)
    return EvaluationSummary(
        metrics=metrics,
        total=total,
        passed_count=passed,
        macro_recall=sum(m.recall for m in metrics) / total,
        macro_misuse=sum(m.misuse_rate for m in metrics) / total,
        macro_confirmation_application=sum(m.confirmation_application for m in metrics) / total,
        avg_memory_tokens=sum(m.memory_tokens for m in metrics) / total,
        avg_latency_ms=sum(m.latency_ms for m in metrics) / total,
    )
