import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_db
from app.infrastructure.database import Base
from app.infrastructure.models.auth import AuthSessionRecord, UserRecord
from app.infrastructure.models.task import TaskRecord
from app.main import app


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp.name).as_posix()}/auth.db",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)

        def db():
            with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = db

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.temp.cleanup()

    def client(self) -> TestClient:
        return TestClient(app)

    def register(self, client: TestClient, email: str) -> dict:
        response = client.post(
            "/auth/register",
            json={"email": email, "password": "correct horse battery staple"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_register_sets_session_and_returns_current_user(self):
        client = self.client()
        try:
            user = self.register(client, "Alice@Example.com")

            self.assertEqual(user["email"], "alice@example.com")
            self.assertTrue(client.cookies.get("studyflow_session"))
            self.assertEqual(client.get("/auth/me").json()["id"], user["id"])
        finally:
            client.close()

    def test_duplicate_email_and_invalid_credentials_are_rejected(self):
        client = self.client()
        try:
            self.register(client, "alice@example.com")
            duplicate = client.post(
                "/auth/register",
                json={"email": "ALICE@example.com", "password": "another password"},
            )
            self.assertEqual(duplicate.status_code, 409)
            self.assertEqual(duplicate.json()["detail"]["code"], "email_already_registered")

            invalid = client.post(
                "/auth/login",
                json={"email": "alice@example.com", "password": "wrong password"},
            )
            self.assertEqual(invalid.status_code, 401)
            self.assertEqual(invalid.json()["detail"]["code"], "invalid_credentials")
        finally:
            client.close()

    def test_logout_revokes_session(self):
        client = self.client()
        try:
            self.register(client, "alice@example.com")
            session_token = client.cookies.get("studyflow_session")
            self.assertEqual(client.post("/auth/logout").status_code, 204)
            self.assertEqual(client.get("/auth/me").status_code, 401)
            with self.sessions() as session:
                stored = session.scalar(select(AuthSessionRecord))
                self.assertIsNotNone(stored)
                self.assertTrue(stored.revoked_at)
            self.assertNotEqual(client.cookies.get("studyflow_session"), session_token)
        finally:
            client.close()

    def test_business_endpoints_require_authentication(self):
        client = self.client()
        try:
            self.assertEqual(client.get("/tasks").status_code, 401)
            self.assertEqual(client.get("/memories").status_code, 401)
        finally:
            client.close()

    def test_tasks_are_isolated_by_server_side_account_identity(self):
        alice = self.client()
        bob = self.client()
        try:
            alice_user = self.register(alice, "alice@example.com")
            self.register(bob, "bob@example.com")
            created = alice.post(
                "/tasks",
                json={
                    "id": "alice-task",
                    "course": "Algorithms",
                    "title": "BFS",
                    "description": "Review BFS",
                    "duration_minutes": 15,
                    "task_type": "study",
                    "knowledge_point": "BFS",
                },
            )
            self.assertEqual(created.status_code, 200, created.text)
            self.assertEqual(created.json()["course"], "Algorithms")
            self.assertEqual(alice.get("/tasks").json()["items"][0]["id"], "alice-task")
            self.assertEqual(bob.get("/tasks").json()["items"], [])
            with self.sessions() as session:
                task_owner = session.scalar(
                    select(TaskRecord.user_id).where(TaskRecord.id == "alice-task")
                )
            self.assertEqual(task_owner, alice_user["id"])
        finally:
            alice.close()
            bob.close()


if __name__ == "__main__":
    unittest.main()
