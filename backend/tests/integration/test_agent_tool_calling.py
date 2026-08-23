import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_db, get_llm
from app.infrastructure.database import Base
from app.infrastructure.llm.adapter import LLMCallError, LLMResult, ToolCall
from app.infrastructure.models.agent_runs import AgentRunRecord
from app.infrastructure.models.knowledge_state import KnowledgeStateRecord
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

    def chat(self, messages, *, tools=None, tool_choice="auto"):
        self.calls.append({"messages": messages, "tools": tools, "tool_choice": tool_choice})
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
            "content": "以后请先给我看例子，再讲定义。",
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
        llm = SequencedLLM([LLMResult(
            text="not-json", tool_calls=[], model="gpt-5.6-terra",
        )])
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
        self.assertEqual(response.json()["action"], "先看遍历示例，再完成一道小题。")
        self.assertIn(memory.id, response.json()["used_memory_ids"])

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
