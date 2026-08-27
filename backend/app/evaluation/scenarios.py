"""Scripted data-structure learning scenarios.

每个 Scenario 是「记忆检索契约」的一次期望 vs 实际测试：
- seed_memories 种入一个独立的 InMemory 仓库；
- filters 决定本轮检索条件；
- expected_retrieved / expected_used / expected_candidates 用记忆的 content 作为稳定标识
  （Memory.id 是运行时生成的 UUID，不能跨运行比较，故用 content 作键）。

语义（与 B 的 retriever 契约一致）：
- retrieved = used ∪ candidates，且二者不相交；
- used = retrieved 中的 confirmed，candidates = retrieved 中的 pending；
- 只有 confirmed 记忆能直接影响 Agent 输出。

因此每个场景都必须满足：expected_retrieved == expected_used ∪ expected_candidates
（validate_scenario 会强制校验，防止场景定义本身出错）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.domain.entities.memory import Memory
from app.domain.repositories.memory_repository import MemoryFilter
from app.domain.value_objects.memory_type import (
    BlockType,
    ConfirmationStatus,
    MemoryType,
)

# 六类场景（对应项目优化版 md 8.3）
CATEGORY_SAME_COURSE_SAME_TASK = "same_course_same_task"
CATEGORY_SAME_COURSE_DIFF_KNOWLEDGE = "same_course_diff_knowledge"
CATEGORY_DIFF_COURSE_SAME_PREFERENCE = "diff_course_same_preference"
CATEGORY_CONFLICTING_PREFERENCE = "conflicting_preference"
CATEGORY_DELETED_MEMORY = "deleted_memory"
CATEGORY_COLD_START = "cold_start"

CATEGORY_NAMES = {
    CATEGORY_SAME_COURSE_SAME_TASK: "同课程同任务",
    CATEGORY_SAME_COURSE_DIFF_KNOWLEDGE: "同课程不同知识点",
    CATEGORY_DIFF_COURSE_SAME_PREFERENCE: "不同课程同偏好",
    CATEGORY_CONFLICTING_PREFERENCE: "冲突偏好",
    CATEGORY_DELETED_MEMORY: "已删除/失效记忆",
    CATEGORY_COLD_START: "无相关记忆（冷启动）",
}

_USER = "evaluation-user"
_DS = "数据结构与算法"
_MATH = "高等数学"

# 枚举简写，让 seed 定义更紧凑
_PENDING = ConfirmationStatus.PENDING
_CONFIRMED = ConfirmationStatus.CONFIRMED
_REJECTED = ConfirmationStatus.REJECTED
_ARCHIVED = ConfirmationStatus.ARCHIVED
_TASK = MemoryType.TASK_PREFERENCE
_EXPL = MemoryType.EXPLANATION_PREFERENCE
_KNOW = MemoryType.KNOWLEDGE_STATE
_RECOV = MemoryType.RECOVERY_EXPERIENCE

# 「冲突偏好」场景的基准时间：以导入时刻为基准，保证新旧相对顺序与运行时系统时钟无关
_NOW = datetime.now(timezone.utc)


def _m(
    *,
    memory_type: MemoryType,
    course: str,
    content: str,
    task_type: str | None = None,
    knowledge_point: str | None = None,
    block_type: BlockType | None = None,
    status: ConfirmationStatus = _PENDING,
    confidence: float = 0.5,
    user_id: str = _USER,
    active: bool = True,
    created_at: datetime | None = None,
) -> Memory:
    """构造一条 seed 记忆；created_at 仅在需要覆盖默认值时传入。"""
    memory = Memory(
        user_id=user_id,
        memory_type=memory_type,
        course=course,
        content=content,
        task_type=task_type,
        knowledge_point=knowledge_point,
        block_type=block_type,
        confirmation_status=status,
        confidence=confidence,
        active=active,
    )
    if created_at is not None:
        memory.created_at = created_at
    return memory


@dataclass
class Scenario:
    id: str
    category: str
    description: str
    seed_memories: tuple[Memory, ...]
    filters: MemoryFilter
    expected_retrieved: set[str] = field(default_factory=set)
    expected_used: set[str] = field(default_factory=set)
    expected_candidates: set[str] = field(default_factory=set)
    limit: int = 5
    max_memory_tokens: int = 300

    def content_map(self) -> dict[str, Memory]:
        return {memory.content: memory for memory in self.seed_memories}


SCENARIOS: list[Scenario] = [
    # ───────────────────────────── 类别 1：同课程同任务 ─────────────────────────
    Scenario(
        id="bfs_confirmed_preferences_used",
        category=CATEGORY_SAME_COURSE_SAME_TASK,
        description="再次学习 BFS 时，已确认的任务偏好与讲解偏好都应被召回并直接使用。",
        seed_memories=(
            _m(memory_type=_TASK, course=_DS, content="先看动画再写代码",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.9),
            _m(memory_type=_EXPL, course=_DS, content="讲解用定义优先",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.8),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="study", knowledge_point="BFS"),
        expected_retrieved={"先看动画再写代码", "讲解用定义优先"},
        expected_used={"先看动画再写代码", "讲解用定义优先"},
    ),
    Scenario(
        id="bfs_pending_is_candidate",
        category=CATEGORY_SAME_COURSE_SAME_TASK,
        description="pending 记忆应被召回，但只作为候选（candidates），不进入 used。",
        seed_memories=(
            _m(memory_type=_TASK, course=_DS, content="先做题再讲解",
               task_type="study", knowledge_point="BFS", status=_PENDING, confidence=0.7),
            _m(memory_type=_EXPL, course=_DS, content="讲解用示例优先",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.8),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="study", knowledge_point="BFS"),
        expected_retrieved={"先做题再讲解", "讲解用示例优先"},
        expected_used={"讲解用示例优先"},
        expected_candidates={"先做题再讲解"},
    ),
    Scenario(
        id="limit_caps_to_three",
        category=CATEGORY_SAME_COURSE_SAME_TASK,
        description="limit=3 时只取置信度最高的前 3 条 confirmed 记忆。",
        seed_memories=tuple(
            _m(memory_type=_TASK, course=_DS, content=f"确认偏好{i}",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED,
               confidence=1.0 - 0.1 * (i - 1))
            for i in range(1, 7)
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="study", knowledge_point="BFS"),
        expected_retrieved={"确认偏好1", "确认偏好2", "确认偏好3"},
        expected_used={"确认偏好1", "确认偏好2", "确认偏好3"},
        limit=3,
    ),
    Scenario(
        id="token_budget_only_first_fits",
        category=CATEGORY_SAME_COURSE_SAME_TASK,
        description="token 预算为 1 时（estimate_tokens=len//4），只保留第一条，第二条因超预算被跳过。",
        seed_memories=(
            _m(memory_type=_TASK, course=_DS, content="先看动画演示",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.9),
            _m(memory_type=_TASK, course=_DS, content="再手写代码",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.8),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="study", knowledge_point="BFS"),
        expected_retrieved={"先看动画演示"},
        expected_used={"先看动画演示"},
        max_memory_tokens=1,
    ),

    # ───────────────────────── 类别 2：同课程不同知识点 ─────────────────────────
    Scenario(
        id="toposort_filter_excludes_bfs",
        category=CATEGORY_SAME_COURSE_DIFF_KNOWLEDGE,
        description="学习拓扑排序时，BFS 的具体薄弱点与偏好不跨知识点召回。",
        seed_memories=(
            _m(memory_type=_KNOW, course=_DS, content="BFS薄弱点：不会写递归",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.9),
            _m(memory_type=_KNOW, course=_DS, content="拓扑排序掌握良好",
               task_type="study", knowledge_point="拓扑排序", status=_CONFIRMED, confidence=0.9),
            _m(memory_type=_TASK, course=_DS, content="BFS偏好：先看动画",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.7),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="study", knowledge_point="拓扑排序"),
        expected_retrieved={"拓扑排序掌握良好"},
        expected_used={"拓扑排序掌握良好"},
    ),
    Scenario(
        id="generic_course_preference_no_kp",
        category=CATEGORY_SAME_COURSE_DIFF_KNOWLEDGE,
        description="不带 knowledge_point 的过滤命中课程级通用偏好，且不跨课程。",
        seed_memories=(
            _m(memory_type=_TASK, course=_DS, content="课程通用偏好：任务拆小步",
               task_type="study", status=_CONFIRMED, confidence=0.7),
            _m(memory_type=_TASK, course=_MATH, content="高数通用偏好：多刷题",
               task_type="study", status=_CONFIRMED, confidence=0.7),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="study"),
        expected_retrieved={"课程通用偏好：任务拆小步"},
        expected_used={"课程通用偏好：任务拆小步"},
    ),
    Scenario(
        id="task_type_exact_match",
        category=CATEGORY_SAME_COURSE_DIFF_KNOWLEDGE,
        description="task_type 精确匹配，复习偏好不与学习偏好混淆。",
        seed_memories=(
            _m(memory_type=_TASK, course=_DS, content="学习偏好：先看动画",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.8),
            _m(memory_type=_TASK, course=_DS, content="复习偏好：先做错题",
               task_type="review", knowledge_point="BFS", status=_CONFIRMED, confidence=0.8),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="review", knowledge_point="BFS"),
        expected_retrieved={"复习偏好：先做错题"},
        expected_used={"复习偏好：先做错题"},
    ),
    Scenario(
        id="block_type_filter",
        category=CATEGORY_SAME_COURSE_DIFF_KNOWLEDGE,
        description="block_type 精确匹配，疲劳型与难度型恢复经验分开召回。",
        seed_memories=(
            _m(memory_type=_RECOV, course=_DS, content="卡壳时：先休息5分钟",
               task_type="study", knowledge_point="BFS", block_type=BlockType.FATIGUE,
               status=_CONFIRMED, confidence=0.8),
            _m(memory_type=_RECOV, course=_DS, content="卡壳时：降低题目难度",
               task_type="study", knowledge_point="BFS", block_type=BlockType.TOO_HARD,
               status=_CONFIRMED, confidence=0.8),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, block_type=BlockType.FATIGUE),
        expected_retrieved={"卡壳时：先休息5分钟"},
        expected_used={"卡壳时：先休息5分钟"},
    ),

    # ───────────────────────── 类别 3：不同课程同偏好 ─────────────────────────
    Scenario(
        id="cross_course_no_knowledge_leak",
        category=CATEGORY_DIFF_COURSE_SAME_PREFERENCE,
        description="高数学习不召回数据结构课程的知识点记忆。",
        seed_memories=(
            _m(memory_type=_KNOW, course=_DS, content="数据结构：栈用数组实现",
               task_type="study", knowledge_point="栈", status=_CONFIRMED, confidence=0.9),
            _m(memory_type=_KNOW, course=_MATH, content="高数：极限定义要理解",
               task_type="study", knowledge_point="极限", status=_CONFIRMED, confidence=0.9),
        ),
        filters=MemoryFilter(user_id=_USER, course=_MATH, knowledge_point="极限"),
        expected_retrieved={"高数：极限定义要理解"},
        expected_used={"高数：极限定义要理解"},
    ),
    Scenario(
        id="same_type_diff_course",
        category=CATEGORY_DIFF_COURSE_SAME_PREFERENCE,
        description="同是讲解偏好，也不跨课程召回。",
        seed_memories=(
            _m(memory_type=_EXPL, course=_MATH, content="高数：公式推导优先",
               task_type="study", status=_CONFIRMED, confidence=0.8),
            _m(memory_type=_EXPL, course=_DS, content="数据结构：动画优先",
               task_type="study", status=_CONFIRMED, confidence=0.8),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="study"),
        expected_retrieved={"数据结构：动画优先"},
        expected_used={"数据结构：动画优先"},
    ),
    Scenario(
        id="user_isolation",
        category=CATEGORY_DIFF_COURSE_SAME_PREFERENCE,
        description="user_id 隔离，只召回当前用户的记忆。",
        seed_memories=(
            _m(memory_type=_TASK, course=_DS, content="别人的偏好：喜欢刷题",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED,
               confidence=0.9, user_id="other-user"),
            _m(memory_type=_TASK, course=_DS, content="我的偏好：喜欢看动画",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.9),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, knowledge_point="BFS"),
        expected_retrieved={"我的偏好：喜欢看动画"},
        expected_used={"我的偏好：喜欢看动画"},
    ),

    # ───────────────────────── 类别 4：冲突偏好 ─────────────────────────
    Scenario(
        id="conflict_newer_ranks_first",
        category=CATEGORY_CONFLICTING_PREFERENCE,
        description="同置信度时，更近（新的）偏好排在前面，limit=1 时旧偏好被挤出。",
        seed_memories=(
            _m(memory_type=_EXPL, course=_DS, content="旧偏好：示例优先",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.5,
               created_at=_NOW - timedelta(days=100)),
            _m(memory_type=_EXPL, course=_DS, content="新偏好：定义优先",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.5,
               created_at=_NOW - timedelta(days=1)),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="study", knowledge_point="BFS"),
        expected_retrieved={"新偏好：定义优先"},
        expected_used={"新偏好：定义优先"},
        limit=1,
    ),
    Scenario(
        id="conflict_old_soft_deleted",
        category=CATEGORY_CONFLICTING_PREFERENCE,
        description="新偏好确认后旧偏好被软删除（active=False），不再召回。",
        seed_memories=(
            _m(memory_type=_EXPL, course=_DS, content="新偏好：定义优先",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.8),
            _m(memory_type=_EXPL, course=_DS, content="旧偏好：示例优先",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.9,
               active=False),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="study", knowledge_point="BFS"),
        expected_retrieved={"新偏好：定义优先"},
        expected_used={"新偏好：定义优先"},
    ),
    Scenario(
        id="conflict_old_archived",
        category=CATEGORY_CONFLICTING_PREFERENCE,
        description="旧偏好被归档（ARCHIVED）后不再召回，仅新偏好生效。",
        seed_memories=(
            _m(memory_type=_EXPL, course=_DS, content="新偏好：定义优先",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.8),
            _m(memory_type=_EXPL, course=_DS, content="旧偏好：示例优先",
               task_type="study", knowledge_point="BFS", status=_ARCHIVED, confidence=0.9),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="study", knowledge_point="BFS"),
        expected_retrieved={"新偏好：定义优先"},
        expected_used={"新偏好：定义优先"},
    ),

    # ───────────────────────── 类别 5：已删除/失效记忆 ─────────────────────────
    Scenario(
        id="soft_deleted_not_retrieved",
        category=CATEGORY_DELETED_MEMORY,
        description="软删除的记忆即使 confidence 更高也不会被召回。",
        seed_memories=(
            _m(memory_type=_TASK, course=_DS, content="已删除的偏好",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.9,
               active=False),
            _m(memory_type=_TASK, course=_DS, content="保留的偏好",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.7),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="study", knowledge_point="BFS"),
        expected_retrieved={"保留的偏好"},
        expected_used={"保留的偏好"},
    ),
    Scenario(
        id="rejected_not_retrieved",
        category=CATEGORY_DELETED_MEMORY,
        description="被明确拒绝（REJECTED）的记忆不再召回。",
        seed_memories=(
            _m(memory_type=_TASK, course=_DS, content="被拒绝的偏好",
               task_type="study", knowledge_point="BFS", status=_REJECTED, confidence=0.9),
            _m(memory_type=_TASK, course=_DS, content="保留的偏好",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.7),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="study", knowledge_point="BFS"),
        expected_retrieved={"保留的偏好"},
        expected_used={"保留的偏好"},
    ),
    Scenario(
        id="archived_not_retrieved",
        category=CATEGORY_DELETED_MEMORY,
        description="已归档（ARCHIVED）的记忆不再召回。",
        seed_memories=(
            _m(memory_type=_TASK, course=_DS, content="已归档的偏好",
               task_type="study", knowledge_point="BFS", status=_ARCHIVED, confidence=0.9),
            _m(memory_type=_TASK, course=_DS, content="保留的偏好",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED, confidence=0.7),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="study", knowledge_point="BFS"),
        expected_retrieved={"保留的偏好"},
        expected_used={"保留的偏好"},
    ),

    # ───────────────────────── 类别 6：无相关记忆（冷启动） ─────────────────────────
    Scenario(
        id="empty_repo_cold_start",
        category=CATEGORY_COLD_START,
        description="空仓库冷启动，retrieved 应为空（走默认策略）。",
        seed_memories=(),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="study", knowledge_point="BFS"),
        expected_retrieved=set(),
        expected_used=set(),
        expected_candidates=set(),
    ),
    Scenario(
        id="wrong_course_cold_start",
        category=CATEGORY_COLD_START,
        description="只存在其他课程的回忆，当前课程冷启动 retrieved 为空。",
        seed_memories=(
            _m(memory_type=_TASK, course=_MATH, content="高数：先看推导",
               task_type="study", knowledge_point="极限", status=_CONFIRMED, confidence=0.9),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="study", knowledge_point="BFS"),
        expected_retrieved=set(),
        expected_used=set(),
        expected_candidates=set(),
    ),
    Scenario(
        id="wrong_user_cold_start",
        category=CATEGORY_COLD_START,
        description="只有其他用户的记忆，当前用户冷启动 retrieved 为空。",
        seed_memories=(
            _m(memory_type=_TASK, course=_DS, content="他人：喜欢看动画",
               task_type="study", knowledge_point="BFS", status=_CONFIRMED,
               confidence=0.9, user_id="other-user"),
        ),
        filters=MemoryFilter(user_id=_USER, course=_DS, task_type="study", knowledge_point="BFS"),
        expected_retrieved=set(),
        expected_used=set(),
        expected_candidates=set(),
    ),
]


def validate_scenario(scenario: Scenario) -> list[str]:
    """校验单个场景定义自洽，返回错误列表（空表示通过）。"""
    errors: list[str] = []

    contents = [memory.content for memory in scenario.seed_memories]
    if len(contents) != len(set(contents)):
        errors.append("seed 记忆 content 存在重复，无法用作稳定标识")

    by_content = scenario.content_map()
    for name, label in (
        ("expected_retrieved", scenario.expected_retrieved),
        ("expected_used", scenario.expected_used),
        ("expected_candidates", scenario.expected_candidates),
    ):
        for content in label:
            if content not in by_content:
                errors.append(f"{name} 引用了不存在的 content：{content!r}")

    if not scenario.expected_used <= scenario.expected_retrieved:
        errors.append("expected_used 必须是 expected_retrieved 的子集")
    if not scenario.expected_candidates <= scenario.expected_retrieved:
        errors.append("expected_candidates 必须是 expected_retrieved 的子集")
    if scenario.expected_used & scenario.expected_candidates:
        errors.append("expected_used 与 expected_candidates 不能有交集")
    if scenario.expected_used | scenario.expected_candidates != scenario.expected_retrieved:
        errors.append("expected_retrieved 必须等于 expected_used ∪ expected_candidates")

    for content in scenario.expected_used:
        if by_content[content].confirmation_status != _CONFIRMED:
            errors.append(f"expected_used 里的 {content!r} 不是 confirmed")
    for content in scenario.expected_candidates:
        if by_content[content].confirmation_status != _PENDING:
            errors.append(f"expected_candidates 里的 {content!r} 不是 pending")

    if scenario.limit < 1:
        errors.append("limit 必须 >= 1")

    return errors


def validate_scenarios(scenarios: list[Scenario]) -> list[tuple[Scenario, list[str]]]:
    """返回所有存在定义错误的 (场景, 错误列表)。"""
    problems: list[tuple[Scenario, list[str]]] = []
    for scenario in scenarios:
        errors = validate_scenario(scenario)
        if errors:
            problems.append((scenario, errors))
    return problems
