import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy import delete
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_db, get_llm
from app.infrastructure.database import Base
from app.infrastructure.llm.adapter import UnconfiguredLLMAdapter
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
