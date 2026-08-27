import unittest
from datetime import datetime, timezone
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


if __name__ == "__main__":
    unittest.main()
