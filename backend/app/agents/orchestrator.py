"""LLM-controlled, server-validated Agent orchestration."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


def _validate_plan_final(data: dict[str, Any]) -> dict[str, Any]:
    data["explanation"] = _required_text(data, "explanation")
    return data


def _validate_check_final(data: dict[str, Any], *, answer: str | None) -> dict[str, Any]:
    data["feedback"] = _required_text(data, "feedback")
    missing = data.get("missing_dimensions")
    if not isinstance(missing, list) or not all(isinstance(item, str) for item in missing):
        raise LLMCallError("invalid_model_output", "模型调用失败：反馈字段格式错误")
    assessed_level = data.get("assessed_level")
    if answer and assessed_level not in {"recall", "relate", "transfer"}:
        raise LLMCallError("invalid_model_output", "模型调用失败：理解层级评估结果无效")
    if assessed_level is not None and assessed_level not in {"recall", "relate", "transfer"}:
        raise LLMCallError("invalid_model_output", "模型调用失败：理解层级评估结果无效")
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
                            return validate_final(_json_object(repaired.text)), outputs, trace
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
        task_type: str = "study",
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

        final, outputs, trace = self._run_model(
            operation="check",
            user_id=user_id,
            system_prompt=_prompt("socratic_check.txt"),
            user_payload={
                "user_id": user_id, "course": course, "knowledge_point": knowledge_point,
                "task_type": task_type, "level": level, "material": material, "answer": answer,
                "confirmed_memories": [m.content for m in memories.used],
                "instruction": "必须调用问题生成工具；最终仅返回JSON对象，字段为 feedback、missing_dimensions 和 assessed_level。提供 answer 时 assessed_level 必须为 recall、relate 或 transfer。",
            },
            tool_names=CHECK_TOOL_NAMES,
            bind_arguments=bind,
            validate_final=lambda data: _validate_check_final(data, answer=answer),
        )
        questions = [output for name, output in outputs if name == "generate_understanding_question"]
        if not questions:
            raise LLMCallError("missing_required_tool", "模型调用失败：模型未生成理解检验问题")
        question = questions[-1]
        missing = final["missing_dimensions"]
        assessed_level = final.get("assessed_level")
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
            "feedback": final["feedback"],
            "missing_dimensions": [str(item) for item in missing],
            "assessed_level": assessed_level,
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
