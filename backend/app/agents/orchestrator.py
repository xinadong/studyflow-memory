"""LLM-controlled, server-validated Agent orchestration."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.tool_registry import (
    CHECK_TOOL_NAMES,
    PLAN_TOOL_NAMES,
    RECOVERY_TOOL_NAMES,
    execute_tool,
    tool_definitions,
)
from app.domain.repositories.memory_repository import MemoryFilter
from app.domain.value_objects.memory_type import BlockType, MemoryType
from app.infrastructure.llm.adapter import LLMAdapter, LLMCallError, ToolCall
from app.infrastructure.models.knowledge_state import KnowledgeStateRecord
from app.infrastructure.models.task import TaskRecord
from app.infrastructure.telemetry.agent_run import record_agent_run
from app.infrastructure.telemetry.token_tracker import estimate_tokens
from app.memory.retriever import (
    RetrievalResult,
    merge_retrieval_results,
    retrieve_memory_candidates,
    select_used_memories,
)
from app.memory.review_schedule import is_review_due, review_reminder
from app.memory.writer import save_feedback_memory


PROMPT_DIR = Path(__file__).with_name("prompts")


def _prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8").strip()


def _minutes(content: str) -> int | None:
    match = re.search(r"(\d+)\s*分钟", content)
    if not match:
        return None
    value = int(match.group(1))
    return value if 1 <= value <= 240 else None


def _explanation_style(content: str) -> str | None:
    explicit_markers = {
        "example_first": (
            "示例优先", "例子优先", "先看示例", "先给我看示例",
            "先看例子", "先给我看例子", "先看案例",
        ),
        "definition_first": (
            "定义优先", "概念优先", "先看定义", "先给我看定义",
            "先讲定义", "先给我讲定义",
        ),
        "diagram_first": (
            "图示优先", "流程图优先", "可视化优先", "先看图示",
            "先给我看图示", "先看流程图", "先给我看流程图",
            "先画图", "先画出图示",
        ),
    }
    matches = [
        (content.find(marker), style)
        for style, markers in explicit_markers.items()
        for marker in markers
        if content.find(marker) >= 0
    ]
    if matches:
        return min(matches, key=lambda item: item[0])[1]

    if any(keyword in content for keyword in ("示例", "例子", "案例")):
        return "example_first"
    if any(keyword in content for keyword in ("定义", "概念", "术语")):
        return "definition_first"
    if any(keyword in content for keyword in ("图示", "画图", "可视化", "流程图")):
        return "diagram_first"
    return None


def _remove_duration_explanation(content: str) -> str:
    """Remove model-written duration claims before adding one canonical sentence."""
    parts = re.split(r"(?<=[。！？；;\n])", content)
    kept: list[str] = []
    for part in parts:
        if re.search(r"\d+\s*分钟", part) and re.search(
            r"偏好|时长|拆分|安排|任务", part,
        ):
            continue
        kept.append(part)
    cleaned = "".join(kept)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.strip(" 。；;，,")


def _contains_review_reminder(content: str, reminder: str) -> bool:
    """Detect the canonical reminder even when the model inserts spaces."""
    normalized_content = re.sub(r"\s+", "", content)
    normalized_reminder = re.sub(r"\s+", "", reminder)
    if normalized_reminder in normalized_content:
        return True
    return (
        "复习提醒" in normalized_content
        and "已到复习时间" in normalized_content
    )


def _json_object(text: str | None) -> dict[str, Any]:
    if not text:
        raise LLMCallError("invalid_model_output", "模型调用失败：模型未返回最终结果")
    candidate = text.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3 and lines[0].strip().startswith("```"):
            candidate = "\n".join(lines[1:-1]).strip()
    try:
        value = json.loads(candidate)
    except ValueError as error:
        decoder = json.JSONDecoder()
        objects: list[dict[str, Any]] = []
        cursor = 0
        while cursor < len(candidate):
            start = candidate.find("{", cursor)
            if start < 0:
                break
            try:
                embedded, end = decoder.raw_decode(candidate, start)
            except ValueError:
                cursor = start + 1
                continue
            if isinstance(embedded, dict):
                objects.append(embedded)
            cursor = max(start + 1, end)
        if len(objects) != 1:
            raise LLMCallError(
                "invalid_model_output",
                "模型调用失败：模型结果不是有效 JSON",
            ) from error
        value = objects[0]
    if not isinstance(value, dict):
        raise LLMCallError("invalid_model_output", "模型调用失败：模型结果格式错误")
    return value


def _required_text(data: dict[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise LLMCallError("invalid_model_output", "模型调用失败：模型结果缺少必需字段")
    return value.strip()


def _is_help_request(answer: str | None) -> bool:
    if not answer:
        return False
    normalized = re.sub(r"[\s，。！？、,.!?]", "", answer).lower()
    if len(normalized) > 30:
        return False
    if any(marker in normalized for marker in (
        "不会", "不知道", "不太会", "不清楚", "没思路", "没有思路",
        "不太知道", "不怎么知道", "卡住了", "卡住", "不理解", "没懂",
        "看不懂", "想不出来", "答不上来", "没概念", "毫无头绪",
        "请提示", "给点提示", "帮我一下", "提示一下",
    )):
        return True
    # Accept natural short variants such as “我不太明白” or “这题完全不懂”
    # without treating a longer answer that contains a local uncertainty as a
    # wholesale help request.
    return bool(re.fullmatch(
        r"(?:我|这个|这题|这个问题)?(?:也|真的|确实|还是)?"
        r"(?:不太|不怎么|完全|实在)?(?:会|知道|清楚|明白|理解|懂)",
        normalized,
    ))


def _chinese_missing_dimension(value: str) -> str:
    """Render provider dimension labels as learner-facing Chinese text."""
    normalized = value.strip().lower()
    known = {
        "mechanism": "运行机制",
        "mechanism (queue-based fifo)": "运行机制（队列的先进先出）",
        "reasoning": "推理依据",
        "reasoning (why layer-by-layer implies shortest path in unweighted graphs)":
            "推理依据（为什么逐层访问能保证无权图最短路径）",
        "definition": "核心定义",
        "example": "具体示例",
        "complexity": "时间与空间复杂度",
        "edge cases": "边界情况",
        "application": "应用场景",
    }
    if normalized in known:
        return known[normalized]
    keyword_labels = (
        ("mechanism", "运行机制"), ("queue", "队列机制"),
        ("reason", "推理依据"), ("shortest path", "最短路径成立的原因"),
        ("complex", "复杂度分析"), ("edge", "边界情况"),
        ("example", "具体示例"), ("application", "应用场景"),
    )
    for keyword, label in keyword_labels:
        if keyword in normalized:
            return label
    # Do not leak an arbitrary English rubric label into the Chinese UI.
    if re.search(r"[a-z]", normalized):
        return "相关原理的完整说明"
    return value.strip()


def _validate_plan_final(data: dict[str, Any]) -> dict[str, Any]:
    data["explanation"] = _required_text(data, "explanation")
    return data


def _validate_check_final(
    data: dict[str, Any], *, answer: str | None, needs_help: bool = False,
    requests_full_answer: bool = False, requested_level: str = "recall",
) -> dict[str, Any]:
    if not answer:
        # A question-generation request has no learner evidence to evaluate.
        # Normalize the provider payload instead of requiring feedback, so an
        # empty response does not trigger repair and leaked answers are hidden.
        data["feedback"] = ""
        data["missing_dimensions"] = []
        data["assessed_level"] = None
        data["next_question"] = None
        data["guidance_type"] = "question"
        data["mastery_status"] = "ongoing"
        return data

    if requests_full_answer:
        explanation = next((
            data.get(field) for field in (
                "feedback", "full_answer", "answer", "explanation", "response",
            )
            if isinstance(data.get(field), str) and data.get(field).strip()
        ), None)
        if explanation is None:
            raise LLMCallError("invalid_model_output", "模型调用失败：完整讲解内容缺失")
        next_question = data.get("next_question")
        data["feedback"] = explanation.strip()
        data["missing_dimensions"] = []
        data["assessed_level"] = "recall"
        data["next_question"] = next_question.strip() if isinstance(next_question, str) else None
        data["guidance_type"] = "full_answer"
        data["mastery_status"] = "ongoing"
        return data

    if needs_help:
        # A short explicit help request is not evidence to grade. Qwen and
        # other compatible providers may return a natural hint object instead
        # of the full assessment schema, so normalize it into a safe tutoring
        # turn rather than failing the whole conversation.
        feedback = next((
            data.get(field) for field in ("feedback", "hint", "response", "explanation")
            if isinstance(data.get(field), str) and data.get(field).strip()
        ), "没关系，我们先把这个问题拆成一个更小的步骤。")
        next_question = data.get("next_question")
        data["feedback"] = feedback.strip()
        data["missing_dimensions"] = []
        data["assessed_level"] = "recall"
        data["next_question"] = next_question.strip() if isinstance(next_question, str) else None
        data["guidance_type"] = "hint"
        data["mastery_status"] = "ongoing"
        return data

    feedback = next((
        data.get(field) for field in (
            "feedback", "evaluation", "analysis", "response", "message", "comment",
            "评价", "反馈",
        )
        if isinstance(data.get(field), str) and data.get(field).strip()
    ), None)
    if feedback is None:
        # A usable tutoring turn is safer than dropping the learner's answer.
        # Keep the judgment deliberately neutral when the provider omitted its
        # assessment text, and continue with a diagnostic question.
        feedback = "我已经记录你的回答。我们再通过一个更具体的问题确认你的理解。"
    data["feedback"] = feedback.strip()
    missing = data.get("missing_dimensions")
    if isinstance(missing, str):
        missing = [missing]
    if not isinstance(missing, list):
        missing = []
    missing = [str(item).strip() for item in missing if str(item).strip()]
    data["missing_dimensions"] = missing
    assessed_level = data.get("assessed_level")
    level_aliases = {
        "记忆": "recall", "复述": "recall", "理解": "relate", "关联": "relate",
        "应用": "transfer", "迁移": "transfer",
    }
    assessed_level = level_aliases.get(str(assessed_level).lower(), assessed_level)
    provider_assessed = assessed_level in {"recall", "relate", "transfer"}
    if not provider_assessed:
        if assessed_level is not None:
            raise LLMCallError("invalid_model_output", "模型调用失败：理解层级评估结果无效")
        assessed_level = requested_level if requested_level in {"recall", "relate", "transfer"} else "recall"
    data["assessed_level"] = assessed_level
    next_question = data.get("next_question")
    if not isinstance(next_question, str):
        next_question = None
    data["next_question"] = next_question
    guidance_type = data.get("guidance_type", "encouragement")
    if guidance_type not in {"hint", "correction", "full_answer", "encouragement"}:
        guidance_type = "correction" if missing else "encouragement"
    mastery_status = data.get("mastery_status", "ongoing")
    if mastery_status not in {"ongoing", "ready"}:
        mastery_status = "ongoing"
    # Missing assessment fields are never enough evidence for mastery, even
    # though the turn remains usable instead of surfacing a format error.
    if not provider_assessed:
        mastery_status = "ongoing"
    data["guidance_type"] = guidance_type
    data["mastery_status"] = mastery_status
    return data


def _validate_recovery_final(data: dict[str, Any]) -> dict[str, Any]:
    data["reason"] = _required_text(data, "reason")
    return data


def _knowledge_prerequisite_reminder(
    learning_state: dict[str, Any], knowledge_point: str | None,
) -> str | None:
    """Turn a current, formative knowledge state into a visible prerequisite.

    Knowledge state is scoped to the exact course/knowledge point and is only
    a reminder. It never changes tool arguments or is counted as a memory
    reference, which keeps the memory/no-memory evaluation boundary explicit.
    """
    if not knowledge_point:
        return None
    level_rank = {"recall": 0, "relate": 1, "transfer": 2}
    states = learning_state.get("knowledge_states") or []
    matching = [
        state for state in states
        if state.get("knowledge_point") == knowledge_point
        and state.get("understanding_level") in level_rank
    ]
    if not matching:
        return None
    state = min(matching, key=lambda item: level_rank[item["understanding_level"]])
    level = state["understanding_level"]
    if level == "transfer":
        return None
    return f"前置提醒：先回顾{knowledge_point}（上次形成性理解层级为{level}）。"


def _memory_payload(result) -> dict[str, list[str]]:
    return {
        "retrieved_memory_ids": result.retrieved_memory_ids,
        "used_memory_ids": result.used_memory_ids,
        "candidate_memory_ids": result.candidate_memory_ids,
    }


@dataclass
class ModelTrace:
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    retry_count: int = 0
    format_repair_count: int = 0
    tool_calls: list[dict[str, Any]] = None

    def __post_init__(self) -> None:
        if self.tool_calls is None:
            self.tool_calls = []


@dataclass
class AgentService:
    session: Session
    repository: Any
    llm: LLMAdapter
    _last_trace: ModelTrace | None = field(default=None, init=False, repr=False)
    _last_retrieval_ms: int = field(default=0, init=False, repr=False)
    _last_memory_result: RetrievalResult | None = field(default=None, init=False, repr=False)

    def _retrieve(self, filters: MemoryFilter):
        scoped = self.repository.list(MemoryFilter(
            user_id=filters.user_id,
            course=filters.course,
            memory_type=filters.memory_type,
        ))

        def matches(memory) -> bool:
            if filters.task_type is not None and memory.task_type not in (None, filters.task_type):
                return False
            if filters.knowledge_point is None:
                if memory.knowledge_point is not None:
                    return False
            elif memory.knowledge_point not in (None, filters.knowledge_point):
                return False
            if filters.block_type is not None and memory.block_type not in (None, filters.block_type):
                return False
            return memory.is_usable

        return retrieve_memory_candidates(
            [memory for memory in scoped if matches(memory)],
            limit=5,
            max_memory_tokens=300,
        )

    def _run_model(
        self,
        *,
        operation: str,
        user_id: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        tool_names: tuple[str, ...],
        bind_arguments,
        validate_final: Callable[[dict[str, Any]], dict[str, Any]],
        text_fallback: Callable[[str | None], dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]], ModelTrace]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]
        definitions = tool_definitions(tool_names)
        trace = ModelTrace()
        self._last_trace = trace
        outputs: list[tuple[str, dict[str, Any]]] = []

        try:
            for turn in range(5):
                result = self.llm.chat(
                    messages,
                    tools=definitions,
                    tool_choice="required" if turn == 0 else "auto",
                )
                trace.model = result.model or self.llm.model
                trace.input_tokens += result.input_tokens
                trace.output_tokens += result.output_tokens
                trace.latency_ms += result.latency_ms
                trace.retry_count += result.retry_count

                if not result.tool_calls:
                    try:
                        return validate_final(_json_object(result.text)), outputs, trace
                    except LLMCallError as validation_error:
                        trace.format_repair_count = 1
                        repair_messages = [
                            *messages,
                            {"role": "assistant", "content": result.text or ""},
                            {
                                "role": "user",
                                "content": (
                                    "上一条最终回答格式无效。只修复格式，不改变语义；"
                                    "现在仅返回一个满足系统字段要求的 JSON 对象，不要代码围栏或说明文字。"
                                ),
                            },
                        ]
                        try:
                            repaired = self.llm.chat(
                                repair_messages,
                                response_format={"type": "json_object"},
                            )
                        except LLMCallError as repair_error:
                            if repair_error.code != "provider_rejected":
                                repair_error.format_repair_count = 1
                                raise
                            trace.input_tokens += repair_error.input_tokens
                            trace.output_tokens += repair_error.output_tokens
                            trace.latency_ms += repair_error.model_latency_ms
                            trace.retry_count += repair_error.retry_count
                            if repair_error.model:
                                trace.model = repair_error.model
                            repaired = self.llm.chat(repair_messages)
                        trace.model = repaired.model or self.llm.model
                        trace.input_tokens += repaired.input_tokens
                        trace.output_tokens += repaired.output_tokens
                        trace.latency_ms += repaired.latency_ms
                        trace.retry_count += repaired.retry_count
                        try:
                            repaired_data = _json_object(repaired.text)
                        except LLMCallError as parse_error:
                            if text_fallback is not None:
                                try:
                                    return validate_final(text_fallback(repaired.text)), outputs, trace
                                except LLMCallError:
                                    pass
                            parse_error.format_repair_count = 1
                            raise parse_error from validation_error
                        try:
                            return validate_final(repaired_data), outputs, trace
                        except LLMCallError as repaired_error:
                            repaired_error.format_repair_count = 1
                            raise repaired_error from validation_error

                messages.append({
                    "role": "assistant",
                    "content": result.text,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments, ensure_ascii=False),
                            },
                        }
                        for call in result.tool_calls
                    ],
                })
                for call in result.tool_calls:
                    if call.name not in tool_names:
                        raise LLMCallError("unknown_tool", "模型调用失败：模型选择了未授权工具")
                    if len(trace.tool_calls) >= 5:
                        raise LLMCallError("tool_call_limit", "模型调用失败：工具调用次数过多")
                    arguments = bind_arguments(call, outputs)
                    output = execute_tool(self.session, call.name, arguments)
                    outputs.append((call.name, output))
                    trace.tool_calls.append({"name": call.name, "arguments": arguments})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(output, ensure_ascii=False),
                    })
        except LLMCallError as error:
            self._last_trace = trace
            raise
        error = LLMCallError("tool_loop_limit", "模型调用失败：工具调用未能结束")
        self._last_trace = trace
        raise error

    def _record_success(
        self, operation: str, user_id: str, retrieval_ms: int, result, trace: ModelTrace,
        *, user_acceptance: bool | None = None, commit: bool = True,
    ) -> dict[str, int]:
        for memory in result.used:
            self.repository.touch(memory.id, commit=False)
        memory_tokens = estimate_tokens(*(memory.content for memory in result.used))
        run = record_agent_run(
            self.session,
            operation=operation,
            user_id=user_id,
            input_tokens=trace.input_tokens,
            memory_tokens=memory_tokens,
            output_tokens=trace.output_tokens,
            retrieval_latency_ms=retrieval_ms,
            model_latency_ms=trace.latency_ms,
            retrieved_memory_ids=result.retrieved_memory_ids,
            used_memory_ids=result.used_memory_ids,
            candidate_memory_ids=result.candidate_memory_ids,
            model=trace.model,
            status="success",
            tool_calls=trace.tool_calls,
            retry_count=trace.retry_count,
            format_repair_count=trace.format_repair_count,
            user_acceptance=user_acceptance,
            commit=False,
        )
        if commit:
            self.session.commit()
        return {
            "input_tokens": run.input_tokens,
            "memory_tokens": run.memory_tokens,
            "output_tokens": run.output_tokens,
            "retrieval_latency_ms": run.retrieval_latency_ms,
            "model_latency_ms": run.model_latency_ms,
        }

    def record_failure(
        self,
        operation: str,
        user_id: str,
        error: LLMCallError,
        *,
        trace: ModelTrace | None = None,
        retrieval_ms: int | None = None,
        result: RetrievalResult | None = None,
    ) -> None:
        trace = trace or self._last_trace
        result = result or self._last_memory_result
        trace_input_tokens = trace.input_tokens if trace else 0
        trace_output_tokens = trace.output_tokens if trace else 0
        trace_latency_ms = trace.latency_ms if trace else 0
        trace_retry_count = trace.retry_count if trace else 0
        input_tokens = trace_input_tokens + getattr(error, "input_tokens", 0)
        output_tokens = trace_output_tokens + getattr(error, "output_tokens", 0)
        model_latency_ms = trace_latency_ms + getattr(error, "model_latency_ms", 0)
        record_agent_run(
            self.session,
            operation=operation,
            user_id=user_id,
            input_tokens=input_tokens,
            memory_tokens=(
                estimate_tokens(*(memory.content for memory in result.used))
                if result else 0
            ),
            output_tokens=output_tokens,
            retrieval_latency_ms=self._last_retrieval_ms if retrieval_ms is None else retrieval_ms,
            model_latency_ms=model_latency_ms,
            retrieved_memory_ids=result.retrieved_memory_ids if result else [],
            used_memory_ids=result.used_memory_ids if result else [],
            candidate_memory_ids=result.candidate_memory_ids if result else [],
            model=(
                trace.model if trace and trace.model
                else getattr(error, "model", None)
                or getattr(self.llm, "model", None)
            ),
            tool_calls=trace.tool_calls if trace else [],
            status="failed",
            retry_count=trace_retry_count + error.retry_count,
            format_repair_count=max(
                trace.format_repair_count if trace else 0,
                error.format_repair_count,
            ),
            error_code=error.code,
            error_message=error.message,
        )

    def plan(
        self, *, user_id: str, course: str, goal: str, available_minutes: int,
        task_type: str = "study", knowledge_point: str | None = None,
        use_memory: bool = True,
        persist_task: bool = True,
        operation: str = "plan",
        imported_tasks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        imported_tasks = imported_tasks or []
        ordered_imports = sorted(imported_tasks, key=lambda item: item["due_at"].timestamp())
        selected_import = ordered_imports[0] if ordered_imports else None
        scheduling_goal = selected_import["title"] if selected_import else goal
        retrieval_started = perf_counter()
        task_memories = (
            self._retrieve(MemoryFilter(
                user_id=user_id, course=course, task_type=task_type,
                memory_type=MemoryType.TASK_PREFERENCE,
                knowledge_point=knowledge_point,
            ))
            if use_memory
            else RetrievalResult(retrieved=[], used=[], candidates=[])
        )
        review_memories = (
            self._retrieve(MemoryFilter(
                user_id=user_id, course=course, task_type=task_type,
                memory_type=MemoryType.REVIEW_SCHEDULE,
                knowledge_point=knowledge_point,
            ))
            if use_memory
            else RetrievalResult(retrieved=[], used=[], candidates=[])
        )
        memories = merge_retrieval_results(task_memories, review_memories)
        retrieval_ms = int((perf_counter() - retrieval_started) * 1000)
        self._last_retrieval_ms = retrieval_ms
        preferred = next((
            _minutes(memory.content)
            for memory in memories.used
            if memory.memory_type == MemoryType.TASK_PREFERENCE and _minutes(memory.content)
        ), None)
        due_review = next((
            memory for memory in memories.used
            if memory.memory_type == MemoryType.REVIEW_SCHEDULE
            and is_review_due(
                memory.content,
                memory.last_used_at or memory.created_at,
            )
        ), None)
        review_reminder_text = review_reminder(due_review.content) if due_review else None
        memories = select_used_memories(
            memories,
            [
                memory.id for memory in memories.used
                if memory.memory_type == MemoryType.TASK_PREFERENCE and _minutes(memory.content)
            ] + ([due_review.id] if due_review else []),
        )
        self._last_memory_result = memories
        learning_state = execute_tool(
            self.session,
            "get_learning_state",
            {"user_id": user_id, "course": course},
        )
        prerequisite_reminder = (
            _knowledge_prerequisite_reminder(learning_state, knowledge_point)
            if use_memory else None
        )

        def bind(call: ToolCall, outputs):
            arguments = dict(call.arguments)
            if call.name == "get_learning_state":
                return {"user_id": user_id, "course": course}
            if call.name == "split_learning_task":
                return {
                    "goal": scheduling_goal, "available_minutes": available_minutes,
                    "preferred_minutes": preferred, "task_type": task_type,
                    "knowledge_point": knowledge_point,
                }
            if call.name == "adjust_learning_plan":
                tasks = [output for name, output in outputs if name in {"split_learning_task", "adjust_learning_plan"}]
                if not tasks:
                    raise LLMCallError("invalid_tool_order", "模型调用失败：调整计划前必须先拆分任务")
                return {"task": tasks[-1], "available_minutes": available_minutes, "preferred_minutes": preferred}
            return arguments

        final, outputs, trace = self._run_model(
            operation=operation,
            user_id=user_id,
            system_prompt=_prompt("planner.txt"),
            user_payload={
                "user_id": user_id, "course": course, "goal": goal,
                "available_minutes": available_minutes, "task_type": task_type,
                "knowledge_point": knowledge_point,
                "confirmed_memories": [m.content for m in memories.used],
                "learning_state": learning_state,
                "knowledge_prerequisite_reminder": prerequisite_reminder,
                "review_schedule_reminder": review_reminder_text,
                "imported_tasks": [
                    {"title": item["title"], "due_at": item["due_at"].isoformat()}
                    for item in ordered_imports
                ],
                "selected_task": (
                    {"title": selected_import["title"], "due_at": selected_import["due_at"].isoformat()}
                    if selected_import else None
                ),
                "instruction": "必须调用工具；最终仅返回JSON对象，字段为 explanation。",
            },
            tool_names=PLAN_TOOL_NAMES,
            bind_arguments=bind,
            validate_final=_validate_plan_final,
        )
        tasks = [output for name, output in outputs if name in {"split_learning_task", "adjust_learning_plan"}]
        if not tasks:
            raise LLMCallError("missing_required_tool", "模型调用失败：模型未生成学习任务")
        task = tasks[-1]
        if selected_import:
            task["due_at"] = selected_import["due_at"].isoformat()
        if persist_task:
            self.session.add(TaskRecord(
                id=task["id"], user_id=user_id, course=course, title=task["title"],
                description=task["description"], task_type=task_type,
                knowledge_point=knowledge_point, duration_minutes=task["duration_minutes"],
                status="planned", created_at=datetime.now(timezone.utc),
            ))
        try:
            metrics = self._record_success(
                operation, user_id, retrieval_ms, memories, trace,
                commit=not persist_task,
            )
            if persist_task:
                self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        explanation = final["explanation"]
        if preferred is not None:
            actual_minutes = task["duration_minutes"]
            explanation = _remove_duration_explanation(explanation)
            if actual_minutes != preferred:
                explanation = (
                    f"{explanation} 你通常偏好{preferred}分钟，但本次只有{available_minutes}分钟可用，"
                    f"因此安排为{actual_minutes}分钟。"
                ).strip()
            else:
                explanation = (
                    f"{explanation} 根据你已确认的任务时长偏好，本次按{actual_minutes}分钟拆分。"
                ).strip()
        if prerequisite_reminder and prerequisite_reminder not in explanation:
            explanation = f"{explanation} {prerequisite_reminder}"
        if review_reminder_text and not _contains_review_reminder(explanation, review_reminder_text):
            explanation = f"{explanation} {review_reminder_text}"
        return {
            "tasks": [task],
            "explanation": explanation,
            **_memory_payload(memories),
            "metrics": metrics,
        }

    def check(
        self, *, user_id: str, course: str, knowledge_point: str,
        level: str, material: str = "", answer: str | None = None,
        task_type: str = "study", conversation_history: list[dict[str, str]] | None = None,
        hint_preference: str | None = None, guidance_request: str | None = None,
    ) -> dict[str, Any]:
        retrieval_started = perf_counter()
        memories = self._retrieve(MemoryFilter(
            user_id=user_id, course=course, task_type=task_type,
            knowledge_point=knowledge_point,
            memory_type=MemoryType.EXPLANATION_PREFERENCE,
        ))
        retrieval_ms = int((perf_counter() - retrieval_started) * 1000)
        preferred_explanation = next(
            (
                (memory, _explanation_style(memory.content))
                for memory in memories.used
                if _explanation_style(memory.content) is not None
            ),
            (None, None),
        )
        preferred_memory, explanation_style = preferred_explanation
        memories = select_used_memories(
            memories,
            [preferred_memory.id] if preferred_memory else [],
        )
        self._last_retrieval_ms = retrieval_ms
        self._last_memory_result = memories

        def bind(call: ToolCall, _):
            if call.name == "get_learning_state":
                return {"user_id": user_id, "course": course}
            if call.name == "generate_understanding_question":
                return {
                    "knowledge_point": knowledge_point,
                    "level": level,
                    "example_first": explanation_style == "example_first",
                    "explanation_style": explanation_style,
                }
            return call.arguments

        safe_history = [
            {"role": item.get("role", ""), "content": item.get("content", "")[:2000]}
            for item in (conversation_history or [])[-24:]
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ]
        needs_help = _is_help_request(answer)
        requests_full_answer = guidance_request == "full_answer"
        hint_styles = {
            "example": "示例：给一个最小具体例子，但不直接完成整题",
            "definition": "定义：只回顾一个解决当前卡点所需的核心定义",
            "analogy": "类比：用一个熟悉事物解释当前概念，但保留关键一步让用户回答",
            "diagram": "图示：用简短文本流程或 ASCII 图表示关系，但不公布完整答案",
        }
        hint_instruction = hint_styles.get(hint_preference)
        final, outputs, trace = self._run_model(
            operation="check",
            user_id=user_id,
            system_prompt=_prompt("socratic_check.txt"),
            user_payload={
                "user_id": user_id, "course": course, "knowledge_point": knowledge_point,
                "task_type": task_type, "level": level, "material": material, "answer": answer,
                "conversation_history": safe_history,
                "learner_needs_help": needs_help,
                "hint_preference": hint_preference,
                "guidance_request": guidance_request,
                "confirmed_memories": [m.content for m in memories.used],
                "instruction": (
                    "必须调用问题生成工具；最终仅返回JSON对象，字段为 feedback、missing_dimensions 和 assessed_level。"
                    + (
                        "已有用户 answer：结合 conversation_history，只依据用户真实回答选择反馈策略。"
                        + (
                            "用户明确请求完整答案：请给出准确、分步骤的完整讲解，但不要据此判定用户已掌握；"
                            "讲解后提出一个简短检查问题。guidance_type 使用 full_answer，mastery_status 使用 ongoing。"
                            if requests_full_answer else ""
                        )
                        + (
                            "用户明确表示不会或卡住：不要评分、不要假装其回答正确、不要立刻公布完整答案；"
                            f"按用户选择的方式提供一个轻量提示（{hint_instruction}），再提出一个更容易的追问。"
                            + (
                                "图示模式必须额外返回 visual_steps 数组，包含 3 到 6 个简短、有顺序的流程节点；"
                                "不要用类比段落代替图示。"
                                if hint_preference == "diagram" else ""
                            )
                            if needs_help and hint_instruction else
                            "用户明确表示不会或卡住：不要评分或假装其回答正确；只给一个最小提示并提出一个更容易的追问。"
                            if needs_help else ""
                        )
                        +
                        "可选择 hint（提示）、correction（指出错误）、full_answer（在多次卡住或存在关键误解时公布完整答案）"
                        "或 encouragement（肯定并提升难度）。同时给出一个自然的 next_question。"
                        "assessed_level 必须为 recall、relate 或 transfer；guidance_type 必须为上述四类之一；"
                        "mastery_status 只能为 ongoing 或 ready。仅在用户已能准确解释并迁移应用时使用 ready。"
                        if answer
                        else
                        "尚无用户 answer：不得回答问题、不得提供参考答案或评估用户；"
                        "feedback 必须为空字符串，missing_dimensions 必须为空数组，"
                        "assessed_level 必须为 null。"
                    )
                ),
            },
            tool_names=CHECK_TOOL_NAMES,
            bind_arguments=bind,
            validate_final=lambda data: _validate_check_final(
                data, answer=answer, needs_help=needs_help,
                requests_full_answer=requests_full_answer,
                requested_level=level,
            ),
            text_fallback=lambda text: {
                "feedback": (text or "").strip() or "我已经记录你的回答。",
                "missing_dimensions": [],
                "assessed_level": level,
                "mastery_status": "ongoing",
            },
        )
        questions = [output for name, output in outputs if name == "generate_understanding_question"]
        if not questions:
            raise LLMCallError("missing_required_tool", "模型调用失败：模型未生成理解检验问题")
        question = questions[-1]
        # The first request only prepares a question. Enforce that boundary in
        # server code as well as in the prompt so a provider cannot leak a
        # reference answer or fabricate an assessment before the learner has
        # submitted evidence.
        if answer:
            feedback = final["feedback"]
            missing = [_chinese_missing_dimension(str(item)) for item in final["missing_dimensions"]]
            assessed_level = final.get("assessed_level")
            next_question = (final.get("next_question") or "").strip()
            guidance_type = final.get("guidance_type", "encouragement")
            user_turns = sum(1 for item in safe_history if item["role"] == "user") + 1
            requested_ready = final.get("mastery_status") == "ready"
            mastery_status = (
                "ready" if requested_ready and assessed_level == "transfer"
                and not missing and user_turns >= 2 else "ongoing"
            )
            raw_visual_steps = final.get("visual_steps")
            visual_steps = (
                [item.strip() for item in raw_visual_steps if isinstance(item, str) and item.strip()][:6]
                if hint_preference == "diagram" and isinstance(raw_visual_steps, list) else []
            )
            if hint_preference == "diagram" and len(visual_steps) < 3:
                fragments = [
                    item.strip(" ：:，,")
                    for item in re.split(r"[。；;\n]+", feedback)
                    if item.strip(" ：:，,")
                ]
                visual_steps = fragments[:6] if len(fragments) >= 3 else [
                    f"定位 {knowledge_point} 的起点",
                    "按核心规则推进一步",
                    "观察结果并回答追问",
                ]
        else:
            feedback = ""
            missing = []
            assessed_level = None
            next_question = ""
            guidance_type = "question"
            mastery_status = "ongoing"
            visual_steps = []
        mastery_summary = None
        review_recommendation = None
        if answer:
            level_labels = {
                "recall": "基础复述（能复述核心概念）",
                "relate": "关联理解（能说明概念之间的联系）",
                "transfer": "迁移应用（能在新情境中运用）",
            }
            interval_days = {"recall": 1, "relate": 3, "transfer": 7}.get(assessed_level, 1)
            duration_minutes = {"recall": 15, "relate": 12, "transfer": 10}.get(assessed_level, 15)
            evidence_turns = sum(1 for item in safe_history if item["role"] == "user") + 1
            gap_text = f"；仍需补充：{'、'.join(missing)}" if missing else "；本轮未发现待补充维度"
            mastery_summary = (
                f"基于本轮 {evidence_turns} 次用户作答，当前形成性层级为"
                f"{level_labels.get(assessed_level, '需要继续巩固')}{gap_text}。"
            )
            review_recommendation = {
                "due_date": (datetime.now().date() + timedelta(days=interval_days)).isoformat(),
                "duration_minutes": duration_minutes,
                "reason": (
                    f"依据本轮对话证据与当前 {assessed_level or 'recall'} 层级，"
                    f"建议 {interval_days} 天后用一道变式题复核；这只是建议，需由用户确认后加入计划。"
                ),
            }
        if answer:
            state = self.session.scalar(select(KnowledgeStateRecord).where(
                KnowledgeStateRecord.user_id == user_id,
                KnowledgeStateRecord.course == course,
                KnowledgeStateRecord.knowledge_point == knowledge_point,
            ))
            if state is None:
                state = KnowledgeStateRecord(
                    id=uuid4().hex, user_id=user_id, course=course,
                    knowledge_point=knowledge_point, understanding_level=assessed_level,
                    evidence=answer, updated_at=datetime.now(timezone.utc),
                )
                self.session.add(state)
            else:
                state.understanding_level = assessed_level
                state.evidence = answer
                state.updated_at = datetime.now(timezone.utc)
        try:
            metrics = self._record_success(
                "check", user_id, retrieval_ms, memories, trace,
                commit=not bool(answer),
            )
            if answer:
                self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return {
            **question,
            "question": next_question or (
                f"关于{knowledge_point}，你目前最不确定的是定义、关键步骤，还是应用场景？"
                if needs_help else question["question"]
            ),
            "feedback": feedback,
            "missing_dimensions": [str(item) for item in missing],
            "assessed_level": assessed_level,
            "guidance_type": guidance_type,
            "mastery_status": mastery_status,
            "visual_steps": visual_steps,
            "mastery_summary": mastery_summary,
            "review_recommendation": review_recommendation,
            **_memory_payload(memories),
            "metrics": metrics,
        }

    def recover(
        self, *, user_id: str, course: str, block_type: BlockType,
        context: str, task_type: str = "study", knowledge_point: str | None = None,
        user_acceptance: bool | None = None,
    ) -> dict[str, Any]:
        retrieval_started = perf_counter()
        memories = self._retrieve(MemoryFilter(
            user_id=user_id, course=course, task_type=task_type,
            knowledge_point=knowledge_point, block_type=block_type,
            memory_type=MemoryType.RECOVERY_EXPERIENCE,
        ))
        retrieval_ms = int((perf_counter() - retrieval_started) * 1000)
        preferred_memory = memories.used[0] if memories.used else None
        memories = select_used_memories(
            memories,
            [preferred_memory.id] if preferred_memory else [],
        )
        self._last_retrieval_ms = retrieval_ms
        self._last_memory_result = memories

        def bind(call: ToolCall, _):
            if call.name == "get_learning_state":
                return {"user_id": user_id, "course": course}
            if call.name == "generate_recovery_action":
                return {
                    "block_type": block_type,
                    "context": context,
                    "preferred_action": preferred_memory.content if preferred_memory else None,
                    "knowledge_point": knowledge_point,
                }
            return call.arguments

        final, outputs, trace = self._run_model(
            operation="recover",
            user_id=user_id,
            system_prompt=_prompt("recovery.txt"),
            user_payload={
                "user_id": user_id, "course": course, "block_type": block_type.value,
                "context": context, "task_type": task_type,
                "knowledge_point": knowledge_point,
                "confirmed_memories": [m.content for m in memories.used],
                "instruction": "必须调用恢复动作工具；最终仅返回JSON对象，字段为 reason。",
            },
            tool_names=RECOVERY_TOOL_NAMES,
            bind_arguments=bind,
            validate_final=_validate_recovery_final,
        )
        actions = [output for name, output in outputs if name == "generate_recovery_action"]
        if not actions:
            raise LLMCallError("missing_required_tool", "模型调用失败：模型未生成恢复动作")
        action = actions[-1]
        try:
            if user_acceptance is True:
                save_feedback_memory(
                    self.repository,
                    user_id=user_id,
                    memory_type=MemoryType.RECOVERY_EXPERIENCE,
                    course=course,
                    task_type=task_type,
                    knowledge_point=knowledge_point,
                    block_type=block_type,
                    content=action["action"],
                    explicit=True,
                    source_feedback=context or None,
                    confidence=1.0,
                    commit=False,
                )
                metrics = self._record_success(
                    "recover", user_id, retrieval_ms, memories, trace,
                    user_acceptance=user_acceptance, commit=False,
                )
                self.session.commit()
            else:
                metrics = self._record_success(
                    "recover", user_id, retrieval_ms, memories, trace,
                    user_acceptance=user_acceptance,
                )
        except Exception:
            self.session.rollback()
            raise
        return {
            "action": action["action"],
            "reason": final["reason"],
            **_memory_payload(memories),
            "metrics": metrics,
        }
