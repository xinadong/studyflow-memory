import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_db
from app.agents.tools.get_learning_state import get_learning_state
from app.infrastructure.database import Base, _upgrade_tasks_schema
from app.infrastructure.models.task import TaskRecord
from app.main import app


class TaskPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp.name).as_posix()}/tasks.db",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)

        def db():
            with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = db
        self.client = TestClient(app)
        self.payload = dict(id="test-task", user_id="alice", course="Algorithms",
                            title="BFS", description="Review BFS", duration_minutes=15,
                            task_type="study", knowledge_point="BFS")

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.temp.cleanup()

    def test_completed_task_survives_new_connection_and_reaches_learning_state(self):
        self.assertEqual(self.client.post("/tasks", json=self.payload).status_code, 200)
        response = self.client.patch("/tasks/test-task?user_id=alice", json={"status": "completed"})
        self.assertEqual(response.status_code, 200)
        # A different client/session represents reopening the page.
        reopened = TestClient(app)
        try:
            items = reopened.get("/tasks?user_id=alice").json()["items"]
            self.assertEqual(items[0]["status"], "completed")
        finally:
            reopened.close()
        with self.sessions() as session:
            state = get_learning_state(session, user_id="alice", course="Algorithms")
            self.assertEqual(state["tasks"][0]["status"], "completed")

    def test_confirmed_review_is_persistent_idempotent_and_keeps_timezone(self):
        payload = {**self.payload, "task_type": "review", "due_at": "2027-01-02T19:30:00+08:00"}
        for _ in range(2):
            response = self.client.post("/tasks", json=payload)
            self.assertEqual(response.status_code, 200, response.text)
        with self.sessions() as session:
            self.assertEqual(len(session.scalars(select(TaskRecord)).all()), 1)
        client = TestClient(app)
        try:
            items = client.get("/tasks?user_id=alice").json()["items"]
        finally:
            client.close()
        self.assertEqual(len(items), 1)
        self.assertEqual(datetime.fromisoformat(items[0]["due_at"]),
                         datetime(2027, 1, 2, 11, 30, tzinfo=timezone.utc))

    def test_owner_filter_and_id_conflict(self):
        self.client.post("/tasks", json=self.payload)
        self.assertEqual(self.client.get("/tasks?user_id=bob").json()["items"], [])
        for method in ["patch", "delete"]:
            kwargs = {"json": {"status": "completed"}} if method == "patch" else {}
            response = getattr(self.client, method)("/tasks/test-task?user_id=bob", **kwargs)
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.post("/tasks", json={**self.payload, "user_id": "bob"}).status_code, 409)
        self.assertEqual(self.client.get("/tasks").status_code, 422)

    def test_deleted_tasks_do_not_reappear_or_reach_agent(self):
        self.client.post("/tasks", json=self.payload)
        self.assertEqual(self.client.delete("/tasks/test-task?user_id=alice").status_code, 204)
        self.assertEqual(self.client.get("/tasks?user_id=alice").json()["items"], [])
        with self.sessions() as session:
            self.assertEqual(get_learning_state(session, user_id="alice", course="Algorithms")["tasks"], [])

    def test_invalid_status_and_review_date_are_rejected(self):
        self.assertEqual(self.client.post("/tasks", json={**self.payload, "task_type": "review"}).status_code, 422)
        self.assertEqual(self.client.post("/tasks", json={**self.payload, "due_at": "2027-01-02T19:30:00"}).status_code, 422)
        self.client.post("/tasks", json=self.payload)
        self.assertEqual(self.client.patch("/tasks/test-task?user_id=alice", json={"status": "invalid"}).status_code, 422)

    def test_old_database_upgrade_preserves_rows_and_is_repeatable(self):
        old_engine = create_engine("sqlite://")
        try:
            with old_engine.begin() as connection:
                connection.exec_driver_sql("CREATE TABLE tasks (id VARCHAR(32) PRIMARY KEY, title TEXT)")
                connection.exec_driver_sql("INSERT INTO tasks (id, title) VALUES ('old', 'Keep me')")
                _upgrade_tasks_schema(connection)
                _upgrade_tasks_schema(connection)
                self.assertIn("due_at", {c["name"] for c in inspect(connection).get_columns("tasks")})
                self.assertEqual(connection.exec_driver_sql("SELECT title, due_at FROM tasks").one(), ("Keep me", None))
        finally:
            old_engine.dispose()
