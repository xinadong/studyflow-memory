import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_db, get_llm
from app.infrastructure.database import Base
from app.infrastructure.llm.adapter import LLMCallError, LLMResult, ToolCall
from app.infrastructure.models.agent_runs import AgentRunRecord
from app.infrastructure.models.feedback import FeedbackRecord
from app.infrastructure.models.knowledge_state import KnowledgeStateRecord
from app.infrastructure.models.memory import MemoryRecord
from app.infrastructure.models.task import TaskRecord
from app.infrastructure.repositories.sqlalchemy_memory_repository import SqlAlchemyMemoryRepository
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import BlockType, ConfirmationStatus, MemoryType
from app.main import app


class SequencedLLM:
    model = "gpt-5.6-terra"

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def chat(self, messages, *, tools=None, tool_choice="auto", response_format=None):
        self.calls.append({
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "response_format": response_format,
        })
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class AgentToolCallingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_db = NamedTemporaryFile(suffix=".db", delete=False)
        cls.temp_db.close()
        cls.engine = create_engine(
            f"sqlite:///{Path(cls.temp_db.name).as_posix()}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)

        def override_db():
            session = cls.Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.engine.dispose()
        Path(cls.temp_db.name).unlink(missing_ok=True)

    def tearDown(self):
        app.dependency_overrides.pop(get_llm, None)

    def test_plan_requires_model_tool_call_and_records_trace(self):
        llm = SequencedLLM([
            LLMResult(
                text=None,
                tool_calls=[ToolCall("call-1", "split_learning_task", {
                    "goal": "学习BFS", "available_minutes": 25,
                    "preferred_minutes": None, "task_type": "study",
                    "knowledge_point": "BFS",
                })],
                input_tokens=31, output_tokens=8, latency_ms=12,
                model="gpt-5.6-terra", retry_count=0,
            ),
            LLMResult(
                text='{"explanation":"已生成25分钟微任务"}', tool_calls=[],
                input_tokens=19, output_tokens=9, latency_ms=7,
                model="gpt-5.6-terra", retry_count=0,
            ),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/plan", json={
            "user_id": "tool-user", "course": "数据结构与算法",
            "goal": "学习BFS", "available_minutes": 25,
            "knowledge_point": "BFS",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tasks"][0]["duration_minutes"], 25)
        self.assertEqual(len(llm.calls), 2)
        self.assertEqual(llm.calls[0]["tool_choice"], "required")
        self.assertIn("split_learning_task", [
            item["function"]["name"] for item in llm.calls[0]["tools"]
        ])

        session = self.Session()
        run = session.scalar(select(AgentRunRecord).where(
            AgentRunRecord.user_id == "tool-user"
        ))
        session.close()
        self.assertEqual(run.model, "gpt-5.6-terra")
        self.assertEqual(run.status, "success")
        self.assertEqual(run.tool_calls[0]["name"], "split_learning_task")
        self.assertEqual(run.input_tokens, 50)
        self.assertEqual(run.output_tokens, 17)
        self.assertEqual(run.model_latency_ms, 19)

    def test_plan_surfaces_current_knowledge_state_as_prerequisite_reminder(self):
        session = self.Session()
        session.add(KnowledgeStateRecord(
            id="knowledge-reminder-state",
            user_id="knowledge-reminder-user",
            course="数据结构与算法",
            knowledge_point="BFS",
            understanding_level="recall",
            evidence="我能说出遍历顺序，但还没解释队列作用。",
            updated_at=datetime.now(timezone.utc),
        ))
        session.commit()
        session.close()

        llm = SequencedLLM([
            LLMResult(
                text=None,
                tool_calls=[ToolCall("reminder-tool", "split_learning_task", {
                    "goal": "复习BFS",
                    "available_minutes": 25,
                    "preferred_minutes": None,
                    "task_type": "study",
                    "knowledge_point": "BFS",
                })],
                model="gemini-3.7-flash",
            ),
            LLMResult(
                text='{"explanation":"已安排BFS复习"}',
                model="gemini-3.7-flash",
            ),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/plan", json={
            "user_id": "knowledge-reminder-user",
            "course": "数据结构与算法",
            "goal": "复习BFS",
            "available_minutes": 25,
            "knowledge_point": "BFS",
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn("前置提醒", response.json()["explanation"])
        self.assertIn("BFS", response.json()["explanation"])

    def test_plan_repairs_invalid_final_output_once(self):
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "repair-tool", "split_learning_task", {
                    "goal": "学习BFS", "available_minutes": 25,
                    "preferred_minutes": None, "task_type": "study",
                    "knowledge_point": "BFS",
                },
            )], model="gemini-3.7-flash"),
            LLMResult(text="任务已经生成。", input_tokens=10, output_tokens=4,
                      latency_ms=5, model="gemini-3.7-flash"),
            LLMResult(text='{"explanation":"已生成25分钟任务"}',
                      input_tokens=12, output_tokens=6, latency_ms=7,
                      model="gemini-3.7-flash"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/plan", json={
            "user_id": "repair-user", "course": "数据结构与算法",
            "goal": "学习BFS", "available_minutes": 25,
            "knowledge_point": "BFS",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["explanation"], "已生成25分钟任务")
        self.assertIsNone(llm.calls[0]["response_format"])
        self.assertEqual(llm.calls[2]["response_format"], {"type": "json_object"})
        session = self.Session()
        run = session.scalar(select(AgentRunRecord).where(
            AgentRunRecord.user_id == "repair-user"
        ))
        session.close()
        self.assertEqual(run.format_repair_count, 1)

    def test_plan_repair_falls_back_when_json_mode_is_rejected(self):
        rejected = LLMCallError("provider_rejected", "模型调用失败")
        rejected.input_tokens = 8
        rejected.model_latency_ms = 3
        rejected.model = "gemini-3.7-flash"
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "fallback-tool", "split_learning_task", {
                    "goal": "学习DFS", "available_minutes": 25,
                    "preferred_minutes": None, "task_type": "study",
                    "knowledge_point": "DFS",
                },
            )], model="gemini-3.7-flash"),
            LLMResult(text="已完成。", model="gemini-3.7-flash"),
            rejected,
            LLMResult(text='{"explanation":"已生成DFS任务"}',
                      model="gemini-3.7-flash"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/plan", json={
            "user_id": "json-fallback-user", "course": "数据结构与算法",
            "goal": "学习DFS", "available_minutes": 25,
            "knowledge_point": "DFS",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(llm.calls[2]["response_format"], {"type": "json_object"})
        self.assertIsNone(llm.calls[3]["response_format"])

    def test_plan_returns_failure_when_repaired_output_is_still_invalid(self):
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "bad-repair-tool", "split_learning_task", {
                    "goal": "学习BFS", "available_minutes": 25,
                    "preferred_minutes": None, "task_type": "study",
                    "knowledge_point": "BFS",
                },
            )], model="gemini-3.7-flash"),
            LLMResult(text="第一次不是JSON", model="gemini-3.7-flash"),
            LLMResult(text="第二次仍不是JSON", model="gemini-3.7-flash"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/plan", json={
            "user_id": "bad-repair-user", "course": "数据结构与算法",
            "goal": "学习BFS", "available_minutes": 25,
            "knowledge_point": "BFS",
        })

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["code"], "invalid_model_output")
        self.assertEqual(response.json()["detail"]["retry_count"], 1)
        session = self.Session()
        run = session.scalar(select(AgentRunRecord).where(
            AgentRunRecord.user_id == "bad-repair-user"
        ))
        session.close()
        self.assertEqual(run.format_repair_count, 1)

    def test_plan_repair_provider_failure_does_not_double_count_metrics(self):
        repair_error = LLMCallError(
            "provider_unavailable", "模型调用失败", retry_count=2,
        )
        repair_error.model = "gemini-3.7-flash"
        repair_error.input_tokens = 7
        repair_error.output_tokens = 0
        repair_error.model_latency_ms = 5
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "repair-failure-tool", "split_learning_task", {
                    "goal": "学习BFS", "available_minutes": 25,
                    "preferred_minutes": None, "task_type": "study",
                    "knowledge_point": "BFS",
                },
            )], input_tokens=10, output_tokens=1, latency_ms=2,
               model="gemini-3.7-flash"),
            LLMResult(text="不是JSON", input_tokens=20, output_tokens=3,
                      latency_ms=4, model="gemini-3.7-flash"),
            repair_error,
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/plan", json={
            "user_id": "repair-provider-failure", "course": "数据结构与算法",
            "goal": "学习BFS", "available_minutes": 25,
            "knowledge_point": "BFS",
        })

        self.assertEqual(response.status_code, 502)
        session = self.Session()
        run = session.scalar(select(AgentRunRecord).where(
            AgentRunRecord.user_id == "repair-provider-failure"
        ))
        session.close()
        self.assertEqual(run.input_tokens, 37)
        self.assertEqual(run.output_tokens, 4)
        self.assertEqual(run.model_latency_ms, 11)
        self.assertEqual(run.retry_count, 2)
        self.assertEqual(run.format_repair_count, 1)

    def test_model_failure_returns_structured_502_and_records_failure(self):
        llm = SequencedLLM([
            LLMCallError("provider_unavailable", "模型调用失败", retry_count=2),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/recover", json={
            "user_id": "failed-user", "course": "数据结构与算法",
            "block_type": "too_hard", "context": "任务太难",
        })

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["code"], "provider_unavailable")
        self.assertEqual(response.json()["detail"]["message"], "模型调用失败")

        session = self.Session()
        run = session.scalar(select(AgentRunRecord).where(
            AgentRunRecord.user_id == "failed-user"
        ))
        session.close()
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.retry_count, 2)
        self.assertEqual(run.error_code, "provider_unavailable")

    def test_cors_preflight_is_allowed_for_vite_origin(self):
        response = self.client.options(
            "/agent/plan",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")

    def test_required_tool_omission_is_recorded_once_as_failure(self):
        llm = SequencedLLM([
            LLMResult(
                text=None,
                tool_calls=[ToolCall("call-state", "get_learning_state", {
                    "user_id": "missing-tool-user", "course": "数据结构与算法",
                })],
                model="gpt-5.6-terra",
            ),
            LLMResult(
                text='{"explanation":"没有生成任务"}',
                tool_calls=[],
                model="gpt-5.6-terra",
            ),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/plan", json={
            "user_id": "missing-tool-user", "course": "数据结构与算法",
            "goal": "学习BFS", "available_minutes": 25,
        })

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["code"], "missing_required_tool")
        session = self.Session()
        runs = session.scalars(select(AgentRunRecord).where(
            AgentRunRecord.user_id == "missing-tool-user"
        )).all()
        session.close()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].status, "failed")
        self.assertEqual(runs[0].tool_calls[0]["name"], "get_learning_state")

    def test_feedback_without_classification_uses_model_and_writes_memory(self):
        llm = SequencedLLM([LLMResult(
            text=(
                '{"memory_type":"explanation_preference",'
                '"explicit":true,"confidence":0.95,"block_type":null}'
            ),
            input_tokens=22,
            output_tokens=11,
            latency_ms=8,
            model="gpt-5.6-terra",
        )])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/feedback", json={
            "user_id": "classify-user",
            "course": "数据结构与算法",
            "content": "以后先看一个例子，再做一道小题。",
        })

        self.assertEqual(response.status_code, 201)
        memory = response.json()["memories"][0]
        self.assertEqual(memory["memory_type"], "explanation_preference")
        self.assertEqual(memory["confirmation_status"], "confirmed")
        self.assertEqual(len(llm.calls), 1)
        session = self.Session()
        run = session.scalar(select(AgentRunRecord).where(
            AgentRunRecord.user_id == "classify-user"
        ))
        session.close()
        self.assertEqual(run.operation, "feedback_classification")
        self.assertEqual(run.status, "success")
        self.assertEqual(run.input_tokens, 22)

    def test_natural_feedback_recovery_cue_with_break_minutes_is_recovery_memory(self):
        llm = SequencedLLM([LLMResult(
            text=(
                '{"memory_type":"task_preference",'
                '"explicit":true,"confidence":0.95,"block_type":null}'
            ),
            model="gemini-3.7-flash",
        )])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/feedback", json={
            "user_id": "fatigue-minutes-user",
            "course": "数据结构与算法",
            "content": "学累了5分钟，想先休息一下",
        })

        self.assertEqual(response.status_code, 201)
        memory = response.json()["memories"][0]
        self.assertEqual(memory["memory_type"], "recovery_experience")
        self.assertEqual(memory["block_type"], "fatigue")
        self.assertEqual(memory["confirmation_status"], "confirmed")

    def test_natural_feedback_review_interval_is_review_schedule(self):
        llm = SequencedLLM([LLMResult(
            text=(
                '{"memory_type":"task_preference",'
                '"explicit":true,"confidence":0.95,"block_type":null}'
            ),
            model="gemini-3.7-flash",
        )])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/feedback", json={
            "user_id": "review-feedback-user",
            "course": "数据结构与算法",
            "content": "以后每2天复习一次 BFS",
        })

        self.assertEqual(response.status_code, 201)
        memory = response.json()["memories"][0]
        self.assertEqual(memory["memory_type"], "review_schedule")
        self.assertIsNone(memory["block_type"])

    def test_explicit_recovery_feedback_infers_missing_block_type(self):
        response = self.client.post("/feedback", json={
            "user_id": "explicit-fatigue-user",
            "course": "数据结构与算法",
            "feedback_type": "recovery_experience",
            "explicit": True,
            "content": "很累，先休息一下",
        })

        self.assertEqual(response.status_code, 201)
        memory = response.json()["memories"][0]
        self.assertEqual(memory["memory_type"], "recovery_experience")
        self.assertEqual(memory["block_type"], "fatigue")

    def test_natural_feedback_classification_respects_explicit_explanation_cue(self):
        llm = SequencedLLM([LLMResult(
            text=(
                '{"memory_type":"task_preference",'
                '"explicit":true,"confidence":0.95,"block_type":null}'
            ),
            model="gemini-3.7-flash",
        )])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/feedback", json={
            "user_id": "classification-correction-user",
            "course": "数据结构与算法",
            "content": "以后先看一个例子，再做一道小题。",
        })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["memories"][0]["memory_type"],
            "explanation_preference",
        )

    def test_corrected_natural_feedback_clears_classifier_block_scope(self):
        llm = SequencedLLM([LLMResult(
            text=(
                '{"memory_type":"task_preference",'
                '"explicit":true,"confidence":0.95,"block_type":"too_hard"}'
            ),
            model="gemini-3.7-flash",
        )])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/feedback", json={
            "user_id": "classifier-scope-user",
            "course": "数据结构与算法",
            "content": "以后先看一个例子，再做一道小题。",
            "task_type": "study",
            "knowledge_point": "BFS",
        })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["memories"][0]["memory_type"],
            "explanation_preference",
        )
        self.assertIsNone(response.json()["memories"][0]["block_type"])

    def test_natural_language_knowledge_state_classification_is_rejected_without_writes(self):
        llm = SequencedLLM([LLMResult(
            text=(
                '{"memory_type":"knowledge_state",'
                '"explicit":true,"confidence":0.95,"block_type":null}'
            ), model="gemini-3.7-flash",
        )])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/feedback", json={
            "user_id": "classified-knowledge-state-user",
            "course": "数据结构与算法",
            "content": "我还不理解BFS中的队列作用",
            "knowledge_point": "BFS",
        })

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "unsupported_memory_type")
        session = self.Session()
        self.assertIsNone(session.scalar(select(FeedbackRecord).where(
            FeedbackRecord.user_id == "classified-knowledge-state-user"
        )))
        self.assertIsNone(session.scalar(select(MemoryRecord).where(
            MemoryRecord.user_id == "classified-knowledge-state-user"
        )))
        session.close()

    def test_feedback_write_failure_rolls_back_feedback_event(self):
        client = TestClient(app, raise_server_exceptions=False)
        with patch.object(SqlAlchemyMemoryRepository, "add", side_effect=RuntimeError("write failed")):
            response = client.post("/feedback", json={
                "user_id": "feedback-transaction-user",
                "course": "数据结构与算法",
                "feedback_type": "task_preference",
                "explicit": True,
                "content": "以后任务控制在20分钟",
            })

        self.assertEqual(response.status_code, 500)
        session = self.Session()
        self.assertIsNone(session.scalar(select(FeedbackRecord).where(
            FeedbackRecord.user_id == "feedback-transaction-user"
        )))
        session.close()

    def test_feedback_classification_repairs_invalid_json_once(self):
        llm = SequencedLLM([
            LLMResult(text="这是解释偏好。", model="gemini-3.7-flash"),
            LLMResult(text=(
                '{"memory_type":"explanation_preference",'
                '"explicit":true,"confidence":0.95,"block_type":null}'
            ), model="gemini-3.7-flash"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/feedback", json={
            "user_id": "feedback-repair-user",
            "course": "数据结构与算法",
            "content": "以后先看例子，再讲定义。",
        })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(llm.calls[0]["response_format"], {"type": "json_object"})
        self.assertEqual(llm.calls[1]["response_format"], {"type": "json_object"})
        session = self.Session()
        run = session.scalar(select(AgentRunRecord).where(
            AgentRunRecord.user_id == "feedback-repair-user"
        ))
        session.close()
        self.assertEqual(run.format_repair_count, 1)

    def test_feedback_provider_failure_does_not_double_count_metrics(self):
        provider_error = LLMCallError(
            "provider_unavailable", "模型调用失败", retry_count=2,
        )
        provider_error.model = "gemini-3.7-flash"
        provider_error.input_tokens = 9
        provider_error.output_tokens = 0
        provider_error.model_latency_ms = 4
        llm = SequencedLLM([provider_error])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/feedback", json={
            "user_id": "feedback-provider-failure",
            "course": "数据结构与算法",
            "content": "帮我调整一下。",
        })

        self.assertEqual(response.status_code, 502)
        session = self.Session()
        run = session.scalar(select(AgentRunRecord).where(
            AgentRunRecord.user_id == "feedback-provider-failure"
        ))
        session.close()
        self.assertEqual(run.input_tokens, 9)
        self.assertEqual(run.output_tokens, 0)
        self.assertEqual(run.model_latency_ms, 4)
        self.assertEqual(run.retry_count, 2)

    def test_recovery_memory_write_failure_does_not_leave_success_run(self):
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "recovery-transaction-tool", "generate_recovery_action", {
                    "block_type": "too_hard", "context": "任务太难",
                },
            )], model="gemini-3.7-flash"),
            LLMResult(text='{"reason":"先看示例再做小题"}', model="gemini-3.7-flash"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm
        with patch("app.agents.orchestrator.save_feedback_memory", side_effect=RuntimeError("write failed")):
            response = TestClient(app, raise_server_exceptions=False).post("/agent/recover", json={
                "user_id": "recovery-transaction-user",
                "course": "数据结构与算法",
                "block_type": "too_hard",
                "context": "任务太难",
                "knowledge_point": "BFS",
                "user_acceptance": True,
            })

        self.assertEqual(response.status_code, 500)
        session = self.Session()
        run = session.scalar(select(AgentRunRecord).where(
            AgentRunRecord.user_id == "recovery-transaction-user",
            AgentRunRecord.operation == "recover",
        ))
        self.assertIsNone(run)
        session.close()

    def test_plan_success_trace_failure_rolls_back_task(self):
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "plan-transaction-tool", "split_learning_task", {
                    "goal": "学习BFS", "available_minutes": 25,
                    "preferred_minutes": None, "task_type": "study",
                    "knowledge_point": "BFS",
                },
            )], model="gemini-3.7-flash"),
            LLMResult(text='{"explanation":"已生成任务"}', model="gemini-3.7-flash"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm
        with patch("app.agents.orchestrator.record_agent_run", side_effect=RuntimeError("trace failed")):
            response = TestClient(app, raise_server_exceptions=False).post("/agent/plan", json={
                "user_id": "plan-transaction-user",
                "course": "数据结构与算法",
                "goal": "学习BFS",
                "available_minutes": 25,
                "knowledge_point": "BFS",
            })

        self.assertEqual(response.status_code, 500)
        session = self.Session()
        self.assertIsNone(session.scalar(select(TaskRecord).where(
            TaskRecord.user_id == "plan-transaction-user"
        )))
        session.close()

    def test_check_success_trace_failure_rolls_back_knowledge_state(self):
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "check-transaction-tool", "generate_understanding_question", {
                    "knowledge_point": "BFS", "level": "recall", "example_first": False,
                },
            )], model="gemini-3.7-flash"),
            LLMResult(text=(
                '{"feedback":"理解了基本概念","missing_dimensions":[],'
                '"assessed_level":"recall"}'
            ), model="gemini-3.7-flash"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm
        with patch("app.agents.orchestrator.record_agent_run", side_effect=RuntimeError("trace failed")):
            response = TestClient(app, raise_server_exceptions=False).post("/agent/check", json={
                "user_id": "check-transaction-user",
                "course": "数据结构与算法",
                "knowledge_point": "BFS",
                "level": "recall",
                "answer": "BFS使用队列逐层遍历。",
            })

        self.assertEqual(response.status_code, 500)
        session = self.Session()
        self.assertIsNone(session.scalar(select(KnowledgeStateRecord).where(
            KnowledgeStateRecord.user_id == "check-transaction-user"
        )))
        session.close()

    def test_explanation_preferences_change_question_guidance(self):
        cases = (
            ("以后示例优先", "简短例子"),
            ("以后定义优先", "核心定义"),
            ("以后图示优先", "简图"),
        )
        for index, (content, expected_phrase) in enumerate(cases):
            user_id = f"explanation-style-user-{index}"
            session = self.Session()
            memory = SqlAlchemyMemoryRepository(session).add(Memory(
                user_id=user_id,
                memory_type=MemoryType.EXPLANATION_PREFERENCE,
                course="数据结构与算法",
                knowledge_point="BFS",
                content=content,
                confirmation_status=ConfirmationStatus.CONFIRMED,
            ))
            session.close()
            llm = SequencedLLM([
                LLMResult(text=None, tool_calls=[ToolCall(
                    f"explanation-style-tool-{index}", "generate_understanding_question", {
                        "knowledge_point": "BFS", "level": "recall", "example_first": False,
                    },
                )], model="gemini-3.7-flash"),
                LLMResult(
                    text='{"feedback":"请继续","missing_dimensions":[],"assessed_level":null}',
                    model="gemini-3.7-flash",
                ),
            ])
            app.dependency_overrides[get_llm] = lambda llm=llm: llm

            response = self.client.post("/agent/check", json={
                "user_id": user_id,
                "course": "数据结构与算法",
                "knowledge_point": "BFS",
                "level": "recall",
            })

            self.assertEqual(response.status_code, 200)
            self.assertIn(expected_phrase, response.json()["question"])
            self.assertIn(memory.id, response.json()["used_memory_ids"])

    def test_explanation_preference_does_not_cross_task_types(self):
        session = self.Session()
        memory = SqlAlchemyMemoryRepository(session).add(Memory(
            user_id="explanation-task-scope-user",
            memory_type=MemoryType.EXPLANATION_PREFERENCE,
            course="数据结构与算法",
            task_type="exam",
            knowledge_point="BFS",
            content="图示优先",
            confirmation_status=ConfirmationStatus.CONFIRMED,
        ))
        session.close()
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "explanation-task-scope-tool", "generate_understanding_question", {
                    "knowledge_point": "BFS", "level": "recall", "example_first": False,
                },
            )], model="gemini-3.7-flash"),
            LLMResult(
                text='{"feedback":"请继续","missing_dimensions":[],"assessed_level":null}',
                model="gemini-3.7-flash",
            ),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/check", json={
            "user_id": "explanation-task-scope-user",
            "course": "数据结构与算法",
            "knowledge_point": "BFS",
            "task_type": "study",
            "level": "recall",
        })

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(memory.id, response.json()["retrieved_memory_ids"])
        self.assertNotIn("简图", response.json()["question"])

    def test_plan_explanation_uses_actual_clamped_duration(self):
        session = self.Session()
        SqlAlchemyMemoryRepository(session).add(Memory(
            user_id="clamped-duration-user",
            memory_type=MemoryType.TASK_PREFERENCE,
            course="数据结构与算法",
            task_type="study",
            content="任务时长30分钟",
            confirmation_status=ConfirmationStatus.CONFIRMED,
        ))
        session.close()
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "clamped-duration-tool", "split_learning_task", {
                    "goal": "学习BFS", "available_minutes": 20,
                    "preferred_minutes": None, "task_type": "study", "knowledge_point": "BFS",
                },
            )], model="gemini-3.7-flash"),
            LLMResult(text='{"explanation":"已生成任务"}', model="gemini-3.7-flash"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/plan", json={
            "user_id": "clamped-duration-user",
            "course": "数据结构与算法",
            "goal": "学习BFS",
            "available_minutes": 20,
            "knowledge_point": "BFS",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tasks"][0]["duration_minutes"], 20)
        self.assertIn("20分钟", response.json()["explanation"])
        self.assertNotIn("按30分钟拆分", response.json()["explanation"])

    def test_plan_explanation_does_not_duplicate_spaced_duration_preference(self):
        session = self.Session()
        SqlAlchemyMemoryRepository(session).add(Memory(
            user_id="spaced-duration-user",
            memory_type=MemoryType.TASK_PREFERENCE,
            course="数据结构与算法",
            task_type="study",
            content="任务时长20分钟",
            confirmation_status=ConfirmationStatus.CONFIRMED,
        ))
        session.close()
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "spaced-duration-tool", "split_learning_task", {
                    "goal": "学习BFS", "available_minutes": 25,
                    "preferred_minutes": 20, "task_type": "study", "knowledge_point": "BFS",
                },
            )], model="gemini-3.7-flash"),
            LLMResult(
                text='{"explanation":"根据你已确认的偏好，本次按 20 分钟拆分。"}',
                model="gemini-3.7-flash",
            ),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/plan", json={
            "user_id": "spaced-duration-user",
            "course": "数据结构与算法",
            "goal": "学习BFS",
            "available_minutes": 25,
            "knowledge_point": "BFS",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["explanation"],
            "根据你已确认的任务时长偏好，本次按20分钟拆分。",
        )

    def test_plan_overrides_contradictory_model_duration_explanation(self):
        session = self.Session()
        SqlAlchemyMemoryRepository(session).add(Memory(
            user_id="contradictory-duration-user",
            memory_type=MemoryType.TASK_PREFERENCE,
            course="数据结构与算法",
            task_type="study",
            content="任务时长30分钟",
            confirmation_status=ConfirmationStatus.CONFIRMED,
        ))
        session.close()
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "contradictory-duration-tool", "split_learning_task", {
                    "goal": "学习BFS", "available_minutes": 20,
                    "preferred_minutes": 30, "task_type": "study", "knowledge_point": "BFS",
                },
            )], model="gemini-3.7-flash"),
            LLMResult(
                text='{"explanation":"根据偏好，本次按30分钟拆分。"}',
                model="gemini-3.7-flash",
            ),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/plan", json={
            "user_id": "contradictory-duration-user",
            "course": "数据结构与算法",
            "goal": "学习BFS",
            "available_minutes": 20,
            "knowledge_point": "BFS",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tasks"][0]["duration_minutes"], 20)
        self.assertIn("安排为20分钟", response.json()["explanation"])
        self.assertNotIn("本次按30分钟拆分", response.json()["explanation"])

    def test_success_trace_failure_rolls_back_memory_usage(self):
        session = self.Session()
        memory = SqlAlchemyMemoryRepository(session).add(Memory(
            user_id="touch-transaction-user",
            memory_type=MemoryType.EXPLANATION_PREFERENCE,
            course="数据结构与算法",
            task_type="study",
            knowledge_point="BFS",
            content="示例优先",
            confirmation_status=ConfirmationStatus.CONFIRMED,
        ))
        session.close()
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "touch-transaction-tool", "generate_understanding_question", {
                    "knowledge_point": "BFS", "level": "recall", "example_first": True,
                },
            )], model="gemini-3.7-flash"),
            LLMResult(
                text='{"feedback":"请继续","missing_dimensions":[],"assessed_level":null}',
                model="gemini-3.7-flash",
            ),
        ])
        app.dependency_overrides[get_llm] = lambda: llm
        with patch("app.agents.orchestrator.record_agent_run", side_effect=RuntimeError("trace failed")):
            response = TestClient(app, raise_server_exceptions=False).post("/agent/check", json={
                "user_id": "touch-transaction-user",
                "course": "数据结构与算法",
                "knowledge_point": "BFS",
                "task_type": "study",
            })

        self.assertEqual(response.status_code, 500)
        session = self.Session()
        persisted = SqlAlchemyMemoryRepository(session).get(memory.id)
        session.close()
        self.assertEqual(persisted.use_count, 0)
        self.assertIsNone(persisted.last_used_at)

    def test_explicit_feedback_overrides_model_classification(self):
        llm = SequencedLLM([LLMResult(
            text=(
                '{"memory_type":"task_preference",'
                '"explicit":false,"confidence":0.4,"block_type":null}'
            ),
            model="gpt-5.6-terra",
        )])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/feedback", json={
            "user_id": "explicit-user", "course": "数据结构与算法",
            "content": "请始终把任务控制在20分钟", "explicit": True,
        })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["memories"][0]["confirmation_status"], "confirmed")

    def test_invalid_feedback_classification_returns_failure_without_writing(self):
        llm = SequencedLLM([
            LLMResult(text="not-json", tool_calls=[], model="gpt-5.6-terra"),
            LLMResult(text="still-not-json", tool_calls=[], model="gpt-5.6-terra"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/feedback", json={
            "user_id": "bad-classify-user",
            "course": "数据结构与算法",
            "content": "帮我调整一下。",
        })

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["code"], "invalid_model_output")
        session = self.Session()
        run = session.scalar(select(AgentRunRecord).where(
            AgentRunRecord.user_id == "bad-classify-user"
        ))
        session.close()
        self.assertEqual(run.operation, "feedback_classification")
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.format_repair_count, 1)
        session = self.Session()
        self.assertEqual(session.scalars(select(FeedbackRecord).where(
            FeedbackRecord.user_id == "bad-classify-user"
        )).all(), [])
        self.assertEqual(session.scalars(select(MemoryRecord).where(
            MemoryRecord.user_id == "bad-classify-user"
        )).all(), [])
        session.close()

    def test_plan_check_and_recover_require_operation_fields(self):
        cases = [
            ("/agent/plan", {
                "user_id": "missing-plan-field", "course": "数据结构与算法",
                "goal": "学习BFS", "available_minutes": 25,
                "knowledge_point": "BFS",
            }, ToolCall("missing-plan", "split_learning_task", {
                "goal": "学习BFS", "available_minutes": 25,
                "preferred_minutes": None, "task_type": "study",
                "knowledge_point": "BFS",
            })),
            ("/agent/check", {
                "user_id": "missing-check-field", "course": "数据结构与算法",
                "knowledge_point": "BFS", "level": "recall",
            }, ToolCall("missing-check", "generate_understanding_question", {
                "knowledge_point": "BFS", "level": "recall", "example_first": False,
            })),
            ("/agent/recover", {
                "user_id": "missing-recover-field", "course": "数据结构与算法",
                "block_type": "too_hard", "context": "任务太难",
            }, ToolCall("missing-recover", "generate_recovery_action", {
                "block_type": "too_hard", "context": "任务太难",
            })),
        ]
        for route, payload, tool_call in cases:
            with self.subTest(route=route):
                llm = SequencedLLM([
                    LLMResult(text=None, tool_calls=[tool_call], model="gemini-3.7-flash"),
                    LLMResult(text="{}", model="gemini-3.7-flash"),
                    LLMResult(text="{}", model="gemini-3.7-flash"),
                ])
                app.dependency_overrides[get_llm] = lambda llm=llm: llm
                response = self.client.post(route, json=payload)
                self.assertEqual(response.status_code, 502)
                self.assertEqual(response.json()["detail"]["code"], "invalid_model_output")

    def test_evaluation_without_memory_mode_injects_no_memories(self):
        session = self.Session()
        SqlAlchemyMemoryRepository(session).add(Memory(
            user_id="eval-user",
            memory_type=MemoryType.TASK_PREFERENCE,
            course="数据结构与算法",
            content="每次20分钟",
            confirmation_status=ConfirmationStatus.CONFIRMED,
        ))
        session.close()
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall("with-tool", "split_learning_task", {
                "goal": "学习BFS", "available_minutes": 25,
                "preferred_minutes": 20, "task_type": "study", "knowledge_point": None,
            })], model="gpt-5.6-terra"),
            LLMResult(text='{"explanation":"with"}', model="gpt-5.6-terra"),
            LLMResult(text=None, tool_calls=[ToolCall("without-tool", "split_learning_task", {
                "goal": "学习BFS", "available_minutes": 25,
                "preferred_minutes": None, "task_type": "study", "knowledge_point": None,
            })], model="gpt-5.6-terra"),
            LLMResult(text='{"explanation":"without"}', model="gpt-5.6-terra"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/evaluation/compare", json={
            "user_id": "eval-user", "course": "数据结构与算法",
            "goal": "学习BFS", "available_minutes": 25,
        })

        self.assertEqual(response.status_code, 200)
        with_payload = __import__("json").loads(llm.calls[0]["messages"][1]["content"])
        without_payload = __import__("json").loads(llm.calls[2]["messages"][1]["content"])
        self.assertEqual(with_payload["confirmed_memories"], ["每次20分钟"])
        self.assertEqual(without_payload["confirmed_memories"], [])
        self.assertEqual(response.json()["without_memory"]["used_memory_ids"], [])
        self.assertEqual(response.json()["without_memory"]["metrics"]["memory_tokens"], 0)

        session = self.Session()
        self.assertEqual(session.scalars(select(TaskRecord).where(
            TaskRecord.user_id == "eval-user"
        )).all(), [])
        session.close()

    def test_evaluation_compare_preserves_task_and_knowledge_scope(self):
        session = self.Session()
        memory = SqlAlchemyMemoryRepository(session).add(Memory(
            user_id="scoped-evaluation-user",
            memory_type=MemoryType.TASK_PREFERENCE,
            course="数据结构与算法",
            task_type="review",
            knowledge_point="BFS",
            content="每次20分钟",
            confirmation_status=ConfirmationStatus.CONFIRMED,
        ))
        session.close()
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "scoped-eval-with-tool", "split_learning_task", {
                    "goal": "复习BFS", "available_minutes": 25,
                    "preferred_minutes": 20, "task_type": "review", "knowledge_point": "BFS",
                },
            )], model="gemini-3.7-flash"),
            LLMResult(text='{"explanation":"with"}', model="gemini-3.7-flash"),
            LLMResult(text=None, tool_calls=[ToolCall(
                "scoped-eval-without-tool", "split_learning_task", {
                    "goal": "复习BFS", "available_minutes": 25,
                    "preferred_minutes": None, "task_type": "review", "knowledge_point": "BFS",
                },
            )], model="gemini-3.7-flash"),
            LLMResult(text='{"explanation":"without"}', model="gemini-3.7-flash"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/evaluation/compare", json={
            "user_id": "scoped-evaluation-user",
            "course": "数据结构与算法",
            "goal": "复习BFS",
            "available_minutes": 25,
            "task_type": "review",
            "knowledge_point": "BFS",
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn(memory.id, response.json()["with_memory"]["used_memory_ids"])
        self.assertEqual(response.json()["with_memory"]["tasks"][0]["task_type"], "review")
        self.assertEqual(response.json()["without_memory"]["tasks"][0]["task_type"], "review")
        self.assertEqual(response.json()["with_memory"]["tasks"][0]["knowledge_point"], "BFS")
        self.assertEqual(response.json()["without_memory"]["tasks"][0]["knowledge_point"], "BFS")

    def test_pending_and_unrelated_memories_do_not_enter_plan_decision(self):
        session = self.Session()
        repo = SqlAlchemyMemoryRepository(session)
        pending = repo.add(Memory(
            user_id="isolated-user", memory_type=MemoryType.TASK_PREFERENCE,
            course="数据结构与算法", task_type="study", knowledge_point="BFS",
            content="每次 10 分钟", confirmation_status=ConfirmationStatus.PENDING,
        ))
        unrelated = repo.add(Memory(
            user_id="isolated-user", memory_type=MemoryType.TASK_PREFERENCE,
            course="数据结构与算法", task_type="study", knowledge_point="DFS",
            content="每次 20 分钟", confirmation_status=ConfirmationStatus.CONFIRMED,
        ))
        session.close()
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall("isolated-tool", "split_learning_task", {
                "goal": "学习BFS", "available_minutes": 25,
                "preferred_minutes": None, "task_type": "study", "knowledge_point": "BFS",
            })], model="gpt-5.6-terra"),
            LLMResult(text='{"explanation":"默认任务"}', model="gpt-5.6-terra"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/plan", json={
            "user_id": "isolated-user", "course": "数据结构与算法",
            "goal": "学习BFS", "available_minutes": 25,
            "knowledge_point": "BFS",
        })

        self.assertEqual(response.status_code, 200)
        payload = __import__("json").loads(llm.calls[0]["messages"][1]["content"])
        self.assertNotIn(pending.content, payload.get("confirmed_memories", []))
        self.assertNotIn(pending.content, payload.get("candidate_memories", []))
        self.assertNotIn(unrelated.id, response.json()["used_memory_ids"])
        self.assertNotIn(pending.id, response.json()["used_memory_ids"])
        self.assertEqual(response.json()["tasks"][0]["duration_minutes"], 25)
        self.assertEqual(response.json()["metrics"]["memory_tokens"], 0)

    def test_generic_confirmed_task_preference_is_applied_to_similar_task(self):
        session = self.Session()
        memory = SqlAlchemyMemoryRepository(session).add(Memory(
            user_id="generic-user", memory_type=MemoryType.TASK_PREFERENCE,
            course="数据结构与算法", task_type="study", knowledge_point=None,
            content="默认任务时长 20 分钟", confirmation_status=ConfirmationStatus.CONFIRMED,
        ))
        session.close()
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall("generic-tool", "split_learning_task", {
                "goal": "学习拓扑排序", "available_minutes": 25,
                "preferred_minutes": 20, "task_type": "study", "knowledge_point": "拓扑排序",
            })], model="gpt-5.6-terra"),
            LLMResult(text='{"explanation":"根据已确认的20分钟偏好拆分"}', model="gpt-5.6-terra"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/plan", json={
            "user_id": "generic-user", "course": "数据结构与算法",
            "goal": "学习拓扑排序", "available_minutes": 25,
            "knowledge_point": "拓扑排序",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tasks"][0]["duration_minutes"], 20)
        self.assertIn(memory.id, response.json()["used_memory_ids"])

    def test_specific_memory_is_not_used_when_request_omits_knowledge_point(self):
        session = self.Session()
        memory = SqlAlchemyMemoryRepository(session).add(Memory(
            user_id="missing-scope-user",
            memory_type=MemoryType.TASK_PREFERENCE,
            course="数据结构与算法",
            task_type="study",
            knowledge_point="BFS",
            content="任务时长20分钟",
            confirmation_status=ConfirmationStatus.CONFIRMED,
        ))
        session.close()
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "missing-scope-tool", "split_learning_task", {
                    "goal": "学习数据结构", "available_minutes": 30,
                    "preferred_minutes": None, "task_type": "study",
                    "knowledge_point": None,
                },
            )], model="gemini-3.7-flash"),
            LLMResult(text='{"explanation":"使用默认策略"}', model="gemini-3.7-flash"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/plan", json={
            "user_id": "missing-scope-user",
            "course": "数据结构与算法",
            "goal": "学习数据结构",
            "available_minutes": 30,
        })

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(memory.id, response.json()["retrieved_memory_ids"])
        self.assertEqual(response.json()["tasks"][0]["duration_minutes"], 25)

    def test_feedback_then_similar_plan_forms_continuous_learning_loop(self):
        feedback = self.client.post("/feedback", json={
            "user_id": "loop-user", "course": "数据结构与算法",
            "feedback_type": "task_preference", "explicit": True,
            "content": "请把后续学习任务控制在20分钟",
        })
        self.assertEqual(feedback.status_code, 201)
        memory_id = feedback.json()["memories"][0]["id"]

        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall("loop-tool", "split_learning_task", {
                "goal": "学习栈与表达式求值", "available_minutes": 25,
                "preferred_minutes": 20, "task_type": "study", "knowledge_point": "表达式求值",
            })], model="gpt-5.6-terra"),
            LLMResult(text='{"explanation":"根据你确认的20分钟偏好进行拆分"}', model="gpt-5.6-terra"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/plan", json={
            "user_id": "loop-user", "course": "数据结构与算法",
            "goal": "学习栈与表达式求值", "available_minutes": 25,
            "knowledge_point": "表达式求值",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tasks"][0]["duration_minutes"], 20)
        self.assertIn(memory_id, response.json()["used_memory_ids"])
        self.assertIn("20分钟", response.json()["explanation"])

    def test_recovery_reuses_confirmed_experience(self):
        session = self.Session()
        memory = SqlAlchemyMemoryRepository(session).add(Memory(
            user_id="recovery-user", memory_type=MemoryType.RECOVERY_EXPERIENCE,
            course="数据结构与算法", task_type="study", block_type=BlockType.TOO_HARD,
            content="先看遍历示例，再完成一道小题。",
            confirmation_status=ConfirmationStatus.CONFIRMED,
        ))
        session.close()
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall("recovery-tool", "generate_recovery_action", {
                "block_type": "too_hard", "context": "任务太难",
            })], model="gpt-5.6-terra"),
            LLMResult(text='{"reason":"复用了上次有效恢复方式"}', model="gpt-5.6-terra"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/recover", json={
            "user_id": "recovery-user", "course": "数据结构与算法",
            "block_type": "too_hard", "context": "任务太难",
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn("定位难点", response.json()["action"])
        self.assertIn("回顾前置", response.json()["action"])
        self.assertIn("基础练习：先看遍历示例，再完成一道小题。", response.json()["action"])
        self.assertIn("返回原题", response.json()["action"])
        self.assertIn(memory.id, response.json()["used_memory_ids"])

    def test_too_hard_recovery_without_history_returns_progressive_path(self):
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "progressive-recovery-tool", "generate_recovery_action", {
                    "block_type": "too_hard", "context": "队列作用不理解",
                },
            )], model="gemini-3.7-flash"),
            LLMResult(text='{"reason":"按步骤降低难度"}', model="gemini-3.7-flash"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/recover", json={
            "user_id": "progressive-recovery-user",
            "course": "数据结构与算法",
            "block_type": "too_hard",
            "context": "队列作用不理解",
            "knowledge_point": "BFS",
        })

        self.assertEqual(response.status_code, 200)
        action = response.json()["action"]
        self.assertIn("定位难点", action)
        self.assertIn("回顾前置", action)
        self.assertIn("基础练习", action)
        self.assertIn("返回原题", action)
        self.assertIn("BFS", action)

    def test_accepted_recovery_action_is_saved_as_confirmed_memory(self):
        user_id = "accepted-recovery-user"
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "accepted-recovery-tool", "generate_recovery_action", {
                    "block_type": "too_hard", "context": "任务太难",
                },
            )], model="gemini-3.7-flash"),
            LLMResult(
                text='{"reason":"先降低难度再继续学习"}',
                model="gemini-3.7-flash",
            ),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/recover", json={
            "user_id": user_id,
            "course": "数据结构与算法",
            "block_type": "too_hard",
            "context": "任务太难",
            "task_type": "study",
            "knowledge_point": "BFS",
            "user_acceptance": True,
        })

        self.assertEqual(response.status_code, 200)
        session = self.Session()
        memories = session.scalars(select(MemoryRecord).where(
            MemoryRecord.user_id == user_id,
            MemoryRecord.memory_type == MemoryType.RECOVERY_EXPERIENCE.value,
        )).all()
        session.close()

        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].confirmation_status, ConfirmationStatus.CONFIRMED.value)
        self.assertTrue(memories[0].active)
        self.assertEqual(memories[0].course, "数据结构与算法")
        self.assertEqual(memories[0].task_type, "study")
        self.assertEqual(memories[0].knowledge_point, "BFS")
        self.assertEqual(memories[0].block_type, BlockType.TOO_HARD.value)
        self.assertEqual(memories[0].content, response.json()["action"])
        self.assertEqual(memories[0].source_feedback, "任务太难")
        session = self.Session()
        run = session.scalar(select(AgentRunRecord).where(
            AgentRunRecord.user_id == user_id,
            AgentRunRecord.operation == "recover",
        ))
        session.close()
        self.assertTrue(run.user_acceptance)

    def test_rejected_or_unconfirmed_recovery_action_is_not_saved_as_memory(self):
        for suffix, acceptance in (("rejected", False), ("unknown", None)):
            user_id = f"{suffix}-recovery-user"
            llm = SequencedLLM([
                LLMResult(text=None, tool_calls=[ToolCall(
                    f"{suffix}-recovery-tool", "generate_recovery_action", {
                        "block_type": "fatigue", "context": "状态疲劳",
                    },
                )], model="gemini-3.7-flash"),
                LLMResult(
                    text='{"reason":"先完成一个最小回顾问题"}',
                    model="gemini-3.7-flash",
                ),
            ])
            app.dependency_overrides[get_llm] = lambda llm=llm: llm

            response = self.client.post("/agent/recover", json={
                "user_id": user_id,
                "course": "数据结构与算法",
                "block_type": "fatigue",
                "context": "状态疲劳",
                "user_acceptance": acceptance,
            })
            self.assertEqual(response.status_code, 200)

            session = self.Session()
            memories = session.scalars(select(MemoryRecord).where(
                MemoryRecord.user_id == user_id,
                MemoryRecord.memory_type == MemoryType.RECOVERY_EXPERIENCE.value,
            )).all()
            session.close()
            self.assertEqual(memories, [])

    def test_accepted_recovery_memory_is_reused_by_next_similar_recovery(self):
        user_id = "recovery-closed-loop-user"
        first_llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "first-recovery-tool", "generate_recovery_action", {
                    "block_type": "too_hard", "context": "任务太难",
                },
            )], model="gemini-3.7-flash"),
            LLMResult(
                text='{"reason":"先看示例再做小题"}',
                model="gemini-3.7-flash",
            ),
        ])
        app.dependency_overrides[get_llm] = lambda: first_llm
        first = self.client.post("/agent/recover", json={
            "user_id": user_id,
            "course": "数据结构与算法",
            "block_type": "too_hard",
            "context": "任务太难",
            "task_type": "study",
            "knowledge_point": "BFS",
            "user_acceptance": True,
        })
        self.assertEqual(first.status_code, 200)

        second_llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "second-recovery-tool", "generate_recovery_action", {
                    "block_type": "too_hard", "context": "又一次任务太难",
                },
            )], model="gemini-3.7-flash"),
            LLMResult(
                text='{"reason":"复用了上次有效恢复方式"}',
                model="gemini-3.7-flash",
            ),
        ])
        app.dependency_overrides[get_llm] = lambda: second_llm
        second = self.client.post("/agent/recover", json={
            "user_id": user_id,
            "course": "数据结构与算法",
            "block_type": "too_hard",
            "context": "又一次任务太难",
            "task_type": "study",
            "knowledge_point": "BFS",
        })

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["action"], first.json()["action"])
        self.assertTrue(second.json()["used_memory_ids"])
        self.assertIn(second.json()["used_memory_ids"][0], second.json()["retrieved_memory_ids"])

    def test_recovery_memory_does_not_cross_knowledge_points(self):
        session = self.Session()
        memory = SqlAlchemyMemoryRepository(session).add(Memory(
            user_id="scoped-recovery-user",
            memory_type=MemoryType.RECOVERY_EXPERIENCE,
            course="数据结构与算法",
            task_type="study",
            knowledge_point="BFS",
            block_type=BlockType.TOO_HARD,
            content="先画出BFS队列变化，再做一道小题。",
            confirmation_status=ConfirmationStatus.CONFIRMED,
        ))
        session.close()
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall(
                "scoped-recovery-tool", "generate_recovery_action", {
                    "block_type": "too_hard", "context": "拓扑排序太难",
                },
            )], model="gemini-3.7-flash"),
            LLMResult(
                text='{"reason":"为当前知识点生成新的恢复动作"}',
                model="gemini-3.7-flash",
            ),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/recover", json={
            "user_id": "scoped-recovery-user",
            "course": "数据结构与算法",
            "block_type": "too_hard",
            "context": "拓扑排序太难",
            "task_type": "study",
            "knowledge_point": "拓扑排序",
        })

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(memory.id, response.json()["retrieved_memory_ids"])
        self.assertNotIn(memory.id, response.json()["used_memory_ids"])
        recovery_call = next(
            call for call in llm.calls[0]["messages"]
            if call.get("role") == "user"
        )
        self.assertNotIn(memory.content, recovery_call["content"])

    def test_deleted_and_archived_recovery_memories_are_not_reused(self):
        for suffix, disable in (
            ("deleted", lambda memory_id: self.client.delete(f"/memories/{memory_id}")),
            ("archived", lambda memory_id: self.client.patch(
                f"/memories/{memory_id}",
                json={"confirmation_status": "archived"},
            )),
        ):
            user_id = f"{suffix}-recovery-memory-user"
            session = self.Session()
            memory = SqlAlchemyMemoryRepository(session).add(Memory(
                user_id=user_id,
                memory_type=MemoryType.RECOVERY_EXPERIENCE,
                course="数据结构与算法",
                task_type="study",
                knowledge_point="BFS",
                block_type=BlockType.TOO_HARD,
                content="先看BFS示例，再完成一道小题。",
                confirmation_status=ConfirmationStatus.CONFIRMED,
            ))
            session.close()
            disabled = disable(memory.id)
            self.assertIn(disabled.status_code, (200, 204))

            llm = SequencedLLM([
                LLMResult(text=None, tool_calls=[ToolCall(
                    f"{suffix}-disabled-recovery-tool", "generate_recovery_action", {
                        "block_type": "too_hard", "context": "任务太难",
                    },
                )], model="gemini-3.7-flash"),
                LLMResult(
                    text='{"reason":"生成默认恢复动作"}',
                    model="gemini-3.7-flash",
                ),
            ])
            app.dependency_overrides[get_llm] = lambda llm=llm: llm
            response = self.client.post("/agent/recover", json={
                "user_id": user_id,
                "course": "数据结构与算法",
                "block_type": "too_hard",
                "context": "任务太难",
                "task_type": "study",
                "knowledge_point": "BFS",
            })

            self.assertEqual(response.status_code, 200)
            self.assertNotIn(memory.id, response.json()["retrieved_memory_ids"])
            self.assertNotIn(memory.id, response.json()["used_memory_ids"])

    def test_soft_deleted_memory_is_not_used_by_next_similar_task(self):
        session = self.Session()
        memory = SqlAlchemyMemoryRepository(session).add(Memory(
            user_id="deleted-user", memory_type=MemoryType.TASK_PREFERENCE,
            course="数据结构与算法", task_type="study", content="默认任务时长 20 分钟",
            confirmation_status=ConfirmationStatus.CONFIRMED,
        ))
        session.close()
        deleted = self.client.delete(f"/memories/{memory.id}")
        self.assertEqual(deleted.status_code, 204)
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall("deleted-tool", "split_learning_task", {
                "goal": "学习DFS", "available_minutes": 25,
                "preferred_minutes": None, "task_type": "study", "knowledge_point": "DFS",
            })], model="gpt-5.6-terra"),
            LLMResult(text='{"explanation":"默认任务"}', model="gpt-5.6-terra"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/plan", json={
            "user_id": "deleted-user", "course": "数据结构与算法",
            "goal": "学习DFS", "available_minutes": 25, "knowledge_point": "DFS",
        })

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(memory.id, response.json()["retrieved_memory_ids"])
        self.assertEqual(response.json()["tasks"][0]["duration_minutes"], 25)

    def test_check_persists_model_assessed_level(self):
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall("check-tool", "generate_understanding_question", {
                "knowledge_point": "BFS", "level": "recall", "example_first": False,
            })], model="gpt-5.6-terra"),
            LLMResult(text=(
                '{"feedback":"已能迁移到新场景",'
                '"missing_dimensions":[],"assessed_level":"transfer"}'
            ), model="gpt-5.6-terra"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/check", json={
            "user_id": "assessed-user", "course": "数据结构与算法",
            "knowledge_point": "BFS", "level": "recall", "answer": "我可以把它迁移到新图上。",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["level"], "recall")
        self.assertEqual(response.json()["assessed_level"], "transfer")
        session = self.Session()
        state = session.scalar(select(KnowledgeStateRecord).where(
            KnowledgeStateRecord.user_id == "assessed-user"
        ))
        session.close()
        self.assertEqual(state.understanding_level, "transfer")

    def test_invalid_assessed_level_fails_without_writing_knowledge_state(self):
        llm = SequencedLLM([
            LLMResult(text=None, tool_calls=[ToolCall("bad-check-tool", "generate_understanding_question", {
                "knowledge_point": "BFS", "level": "recall", "example_first": False,
            })], model="gpt-5.6-terra"),
            LLMResult(text=(
                '{"feedback":"反馈","missing_dimensions":[],"assessed_level":"mastered"}'
            ), model="gpt-5.6-terra"),
            LLMResult(text=(
                '{"feedback":"反馈","missing_dimensions":[],"assessed_level":"mastered"}'
            ), model="gpt-5.6-terra"),
        ])
        app.dependency_overrides[get_llm] = lambda: llm

        response = self.client.post("/agent/check", json={
            "user_id": "bad-assessed-user", "course": "数据结构与算法",
            "knowledge_point": "BFS", "level": "recall", "answer": "答案",
        })

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["code"], "invalid_model_output")
        session = self.Session()
        state = session.scalar(select(KnowledgeStateRecord).where(
            KnowledgeStateRecord.user_id == "bad-assessed-user"
        ))
        session.close()
        self.assertIsNone(state)

    def test_failure_records_retrieval_and_memory_metrics(self):
        session = self.Session()
        memory = SqlAlchemyMemoryRepository(session).add(Memory(
            user_id="telemetry-user", memory_type=MemoryType.RECOVERY_EXPERIENCE,
            course="数据结构与算法", task_type="study", block_type=BlockType.TOO_HARD,
            content="先看示例", confirmation_status=ConfirmationStatus.CONFIRMED,
        ))
        session.close()
        app.dependency_overrides[get_llm] = lambda: SequencedLLM([
            LLMCallError("provider_unavailable", "模型调用失败", retry_count=2),
        ])

        response = self.client.post("/agent/recover", json={
            "user_id": "telemetry-user", "course": "数据结构与算法",
            "block_type": "too_hard", "context": "任务太难",
        })

        self.assertEqual(response.status_code, 502)
        session = self.Session()
        run = session.scalar(select(AgentRunRecord).where(
            AgentRunRecord.user_id == "telemetry-user"
        ))
        session.close()
        self.assertIn(memory.id, run.retrieved_memory_ids)
        self.assertIn(memory.id, run.used_memory_ids)
        self.assertGreater(run.memory_tokens, 0)
        self.assertIsNotNone(run.retrieval_latency_ms)


if __name__ == "__main__":
    unittest.main()
