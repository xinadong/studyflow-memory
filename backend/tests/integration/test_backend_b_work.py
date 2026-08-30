import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy import delete
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_db, get_llm
from app.infrastructure.database import Base
from app.infrastructure.llm.adapter import UnconfiguredLLMAdapter
from app.infrastructure.models.agent_runs import AgentRunRecord
from app.main import app


class _PlanLLM:
    model = "test-model"

    def __init__(self):
        self.calls = []

    def chat(self, messages, *, tools=None, tool_choice="auto", response_format=None):
        from app.infrastructure.llm.adapter import LLMResult, ToolCall
        self.calls.append({"messages": messages, "tools": tools, "tool_choice": tool_choice})
        if len(self.calls) == 1:
            return LLMResult(text=None, tool_calls=[ToolCall(
                "plan-tool", "split_learning_task", {
                    "goal": "复习BFS", "available_minutes": 25,
                    "preferred_minutes": None, "task_type": "study", "knowledge_point": "BFS",
                },
            )], model=self.model)
        return LLMResult(text='{"explanation":"已生成学习任务"}', model=self.model)


class BackendBWorkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_db = NamedTemporaryFile(suffix=".db", delete=False)
        cls.temp_db.close()
        cls.engine = create_engine(
            f"sqlite:///{Path(cls.temp_db.name).as_posix()}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

        def override_get_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    def setUp(self):
        # Keep integration cases independent while reusing one temporary DB.
        session = self.Session()
        try:
            for table in reversed(Base.metadata.sorted_tables):
                session.execute(delete(table))
            session.commit()
        finally:
            session.close()

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.engine.dispose()
        Path(cls.temp_db.name).unlink(missing_ok=True)

    def test_memory_crud_routes_use_sqlite_and_soft_delete(self):
        payload = {
            "user_id": "u1",
            "memory_type": "task_preference",
            "course": "数据结构与算法",
            "content": "默认任务时长 20 分钟",
            "task_type": "reading",
            "knowledge_point": "BFS",
            "confidence": 0.9,
            "confirmation_status": "confirmed",
        }
        created = self.client.post("/memories", json=payload)
        self.assertEqual(created.status_code, 201)
        memory_id = created.json()["id"]

        listed = self.client.get("/memories", params={"user_id": "u1", "course": "数据结构与算法"})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["total"], 1)

        updated = self.client.patch(f"/memories/{memory_id}", json={"content": "默认任务时长 15 分钟"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["content"], "默认任务时长 15 分钟")

        deleted = self.client.delete(f"/memories/{memory_id}")
        self.assertEqual(deleted.status_code, 204)
        hidden = self.client.get("/memories", params={"user_id": "u1", "active": "true"})
        self.assertEqual(hidden.json()["total"], 0)

    def test_memory_route_rejects_direct_knowledge_state_creation(self):
        response = self.client.post("/memories", json={
            "user_id": "direct-knowledge-user",
            "memory_type": "knowledge_state",
            "course": "数据结构与算法",
            "knowledge_point": "BFS",
            "content": "不理解队列作用",
            "confirmation_status": "confirmed",
        })

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "unsupported_memory_type")

    def test_feedback_inferred_memory_is_pending(self):
        response = self.client.post(
            "/feedback",
            json={
                "user_id": "u1",
                "course": "数据结构与算法",
                "feedback_type": "explanation_preference",
                "content": "用户连续选择示例优先",
                "explicit": False,
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["memories"][0]["confirmation_status"], "pending")

    def test_feedback_type_correction_clears_block_scope(self):
        response = self.client.post(
            "/feedback",
            json={
                "user_id": "scope-feedback-user",
                "course": "数据结构与算法",
                "feedback_type": "task_preference",
                "content": "以后任务控制在20分钟",
                "explicit": True,
                "task_type": "study",
                "block_type": "too_hard",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["memories"][0]["memory_type"], "task_preference")
        self.assertIsNone(response.json()["memories"][0]["block_type"])

    def test_knowledge_state_feedback_is_rejected_without_writes(self):
        response = self.client.post(
            "/feedback",
            json={
                "user_id": "knowledge-feedback-user",
                "course": "数据结构与算法",
                "feedback_type": "knowledge_state",
                "content": "我还不理解BFS",
                "explicit": True,
                "knowledge_point": "BFS",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "unsupported_memory_type")
        session = self.Session()
        self.assertEqual(session.query(AgentRunRecord).count(), 0)
        session.close()

    def test_empty_feedback_is_rejected(self):
        response = self.client.post(
            "/feedback",
            json={
                "user_id": "empty-feedback-user",
                "course": "数据结构与算法",
                "feedback_type": "task_preference",
                "content": "   ",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_metrics_exposes_latency_percentiles_and_memory_counts(self):
        session = self.Session()
        now = datetime.now(timezone.utc)
        session.add_all([
            AgentRunRecord(
                id="metrics-run-1", user_id="metrics-user", operation="plan",
                retrieval_latency_ms=10, model_latency_ms=100,
                retrieved_memory_ids=["a", "b"], used_memory_ids=["a"],
                created_at=now,
            ),
            AgentRunRecord(
                id="metrics-run-2", user_id="metrics-user", operation="check",
                retrieval_latency_ms=20, model_latency_ms=200,
                retrieved_memory_ids=["c"], used_memory_ids=[],
                created_at=now,
            ),
        ])
        session.commit()
        session.close()

        response = self.client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["retrieval_latency_ms_percentiles"]["p50"], 10)
        self.assertEqual(data["retrieval_latency_ms_percentiles"]["p95"], 20)
        self.assertEqual(data["model_latency_ms_percentiles"]["p50"], 100)
        self.assertEqual(data["model_latency_ms_percentiles"]["p95"], 200)
        self.assertEqual(data["memory_counts"]["retrieved"], 3)
        self.assertEqual(data["memory_counts"]["used"], 1)

    def test_plan_endpoint_reports_failure_without_model_configuration(self):
        app.dependency_overrides[get_llm] = lambda: UnconfiguredLLMAdapter("test-model")
        try:
            response = self.client.post(
                "/agent/plan",
                json={
                    "user_id": "u1",
                    "course": "数据结构与算法",
                    "goal": "学习图的 BFS",
                    "available_minutes": 25,
                },
            )
        finally:
            app.dependency_overrides.pop(get_llm, None)
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["detail"]["code"], "model_not_configured")
        self.assertIn("模型调用失败", body["detail"]["message"])

    def test_metrics_endpoint_returns_agent_metrics(self):
        response = self.client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertIn("agent_runs", response.json())

    def test_due_review_schedule_is_consumed_by_plan(self):
        from app.domain.entities.memory import Memory
        from app.domain.value_objects.memory_type import ConfirmationStatus, MemoryType
        from app.infrastructure.repositories.sqlalchemy_memory_repository import SqlAlchemyMemoryRepository
        memory_session = self.Session()
        memory = Memory(
            user_id="review-user", memory_type=MemoryType.REVIEW_SCHEDULE,
            course="数据结构与算法", task_type="study", knowledge_point="BFS",
            content="每2天复习一次", confirmation_status=ConfirmationStatus.CONFIRMED,
            created_at=datetime.now(timezone.utc) - timedelta(days=3),
        )
        SqlAlchemyMemoryRepository(memory_session).add(memory)
        memory_session.close()
        llm = _PlanLLM()
        app.dependency_overrides[get_llm] = lambda: llm
        try:
            response = self.client.post("/agent/plan", json={
                "user_id": "review-user", "course": "数据结构与算法",
                "goal": "复习BFS", "available_minutes": 25,
                "task_type": "study", "knowledge_point": "BFS",
            })
        finally:
            app.dependency_overrides.pop(get_llm, None)
        self.assertEqual(response.status_code, 200)
        self.assertIn(memory.id, response.json()["used_memory_ids"])
        self.assertIn("复习提醒", response.json()["explanation"])
        self.assertIn("复习提醒", llm.calls[0]["messages"][1]["content"])
        check_session = self.Session()
        refreshed = SqlAlchemyMemoryRepository(check_session).get(memory.id)
        check_session.close()
        self.assertIsNotNone(refreshed.last_used_at)

    def test_review_reminder_with_spacing_is_not_duplicated(self):
        from app.domain.entities.memory import Memory
        from app.domain.value_objects.memory_type import ConfirmationStatus, MemoryType
        from app.infrastructure.llm.adapter import LLMResult, ToolCall
        from app.infrastructure.repositories.sqlalchemy_memory_repository import SqlAlchemyMemoryRepository
        memory_session = self.Session()
        memory = Memory(
            user_id="spaced-review-user", memory_type=MemoryType.REVIEW_SCHEDULE,
            course="数据结构与算法", task_type="study", knowledge_point="BFS",
            content="每2天复习一次", confirmation_status=ConfirmationStatus.CONFIRMED,
            created_at=datetime.now(timezone.utc) - timedelta(days=3),
        )
        SqlAlchemyMemoryRepository(memory_session).add(memory)
        memory_session.close()

        class SpacedReminderLLM(_PlanLLM):
            def chat(self, messages, *, tools=None, tool_choice="auto", response_format=None):
                result = super().chat(messages, tools=tools, tool_choice=tool_choice, response_format=response_format)
                if len(self.calls) == 2:
                    return LLMResult(
                        text='{"explanation":"复习提醒：根据你设置的每 2 天复习一次，当前已到复习时间"}',
                        model=self.model,
                    )
                return result

        llm = SpacedReminderLLM()
        app.dependency_overrides[get_llm] = lambda: llm
        try:
            response = self.client.post("/agent/plan", json={
                "user_id": "spaced-review-user", "course": "数据结构与算法",
                "goal": "复习BFS", "available_minutes": 25,
                "task_type": "study", "knowledge_point": "BFS",
            })
        finally:
            app.dependency_overrides.pop(get_llm, None)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["explanation"].count("复习提醒"), 1)

    def test_pending_or_not_due_review_schedule_does_not_change_plan(self):
        from app.domain.entities.memory import Memory
        from app.domain.value_objects.memory_type import ConfirmationStatus, MemoryType
        from app.infrastructure.repositories.sqlalchemy_memory_repository import SqlAlchemyMemoryRepository
        memory_session = self.Session()
        memory = Memory(
            user_id="not-due-review-user", memory_type=MemoryType.REVIEW_SCHEDULE,
            course="数据结构与算法", task_type="study", knowledge_point="BFS",
            content="每2天复习一次", confirmation_status=ConfirmationStatus.CONFIRMED,
            created_at=datetime.now(timezone.utc),
        )
        SqlAlchemyMemoryRepository(memory_session).add(memory)
        memory_session.close()
        llm = _PlanLLM()
        app.dependency_overrides[get_llm] = lambda: llm
        try:
            response = self.client.post("/agent/plan", json={
                "user_id": "not-due-review-user", "course": "数据结构与算法",
                "goal": "复习BFS", "available_minutes": 25,
                "task_type": "study", "knowledge_point": "BFS",
            })
        finally:
            app.dependency_overrides.pop(get_llm, None)
        self.assertEqual(response.status_code, 200)
        self.assertIn(memory.id, response.json()["retrieved_memory_ids"])
        self.assertNotIn(memory.id, response.json()["used_memory_ids"])
        self.assertNotIn("复习提醒", response.json()["explanation"])

    def test_pending_review_schedule_is_candidate_only(self):
        from app.domain.entities.memory import Memory
        from app.domain.value_objects.memory_type import ConfirmationStatus, MemoryType
        from app.infrastructure.repositories.sqlalchemy_memory_repository import SqlAlchemyMemoryRepository
        memory_session = self.Session()
        memory = Memory(
            user_id="pending-review-user", memory_type=MemoryType.REVIEW_SCHEDULE,
            course="数据结构与算法", task_type="study", knowledge_point="BFS",
            content="每2天复习一次", confirmation_status=ConfirmationStatus.PENDING,
            created_at=datetime.now(timezone.utc) - timedelta(days=3),
        )
        SqlAlchemyMemoryRepository(memory_session).add(memory)
        memory_session.close()
        llm = _PlanLLM()
        app.dependency_overrides[get_llm] = lambda: llm
        try:
            response = self.client.post("/agent/plan", json={
                "user_id": "pending-review-user", "course": "数据结构与算法",
                "goal": "复习BFS", "available_minutes": 25,
                "task_type": "study", "knowledge_point": "BFS",
            })
        finally:
            app.dependency_overrides.pop(get_llm, None)
        self.assertEqual(response.status_code, 200)
        self.assertIn(memory.id, response.json()["retrieved_memory_ids"])
        self.assertIn(memory.id, response.json()["candidate_memory_ids"])
        self.assertNotIn(memory.id, response.json()["used_memory_ids"])
        self.assertNotIn("复习提醒", response.json()["explanation"])


if __name__ == "__main__":
    unittest.main()
