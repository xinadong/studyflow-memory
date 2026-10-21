import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_db, get_llm
from app.infrastructure.database import Base, _upgrade_memory_scope
from app.infrastructure.llm.adapter import LLMResult, ToolCall
from app.infrastructure.models.memory import MemoryRecord
from app.infrastructure.models.feedback import FeedbackRecord
from app.main import app


class PreferenceLLM:
    model = "test-only"

    def __init__(self, tool="split_learning_task"):
        self.tool = tool
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(messages)
        if len(self.calls) == 1:
            return LLMResult(text=None, tool_calls=[ToolCall("test-call", self.tool, {})], model=self.model)
        return LLMResult(text='{"explanation":"Plan ready"}', model=self.model)


class PreferenceScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.temp.name).as_posix()}/scope.db",
                                    connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)

        def db():
            with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = db
        self.llm = PreferenceLLM()
        app.dependency_overrides[get_llm] = lambda: self.llm
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()
        self.temp.cleanup()

    def save(self, scope, content="每次学习15分钟", **kwargs):
        response = self.client.post("/feedback", json={
            "user_id": "alice", "feedback_type": "task_preference", "explicit": True,
            "scope": scope, "content": content, **kwargs,
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["memories"][0]

    def plan(self, course="Algorithms", point="BFS", **kwargs):
        self.llm = PreferenceLLM()
        response = self.client.post("/agent/plan", json={
            "user_id": "alice", "course": course, "knowledge_point": point,
            "goal": "Practice", "available_minutes": 60, **kwargs,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_global_preference_crosses_courses_but_never_users(self):
        memory = self.save("global", course="ignored", knowledge_point="ignored")
        self.assertEqual((memory["scope"], memory["course"], memory["knowledge_point"]), ("global", "", None))
        self.assertEqual(self.plan(course="Calculus")["used_memory_ids"], [memory["id"]])
        self.llm = PreferenceLLM()
        response = self.client.post("/agent/plan", json={
            "user_id": "bob", "course": "Calculus", "goal": "Practice", "available_minutes": 60,
        })
        self.assertEqual(response.json()["used_memory_ids"], [])

    def test_specific_scope_overrides_global_without_crossing_boundaries(self):
        global_memory = self.save("global", "每次学习40分钟")
        course_memory = self.save("course", "每次学习20分钟", course="Algorithms", knowledge_point="ignored")
        point_memory = self.save("knowledge_point", "每次学习10分钟", course="Algorithms", knowledge_point="BFS")
        for course, point, expected, minutes in [
            ("Algorithms", "BFS", point_memory, 10),
            ("Algorithms", "DFS", course_memory, 20),
            ("Calculus", "BFS", global_memory, 40),
        ]:
            result = self.plan(course, point)
            self.assertEqual(result["used_memory_ids"], [expected["id"]])
            self.assertEqual(result["tasks"][0]["duration_minutes"], minutes)

    def test_temporary_preference_does_not_write_or_modify_long_term_memory(self):
        memory = self.save("global", "每次学习40分钟")
        result = self.plan(temporary_preference="本次只学15分钟")
        self.assertEqual(result["tasks"][0]["duration_minutes"], 15)
        self.assertEqual(result["used_memory_ids"], [])
        with self.sessions() as session:
            rows = session.scalars(select(MemoryRecord)).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].content, "每次学习40分钟")
            self.assertEqual(rows[0].use_count, 0)
            self.assertEqual(len(session.scalars(select(FeedbackRecord)).all()), 1)
        following = self.plan()
        self.assertEqual(following["tasks"][0]["duration_minutes"], 40)
        self.assertEqual(following["used_memory_ids"], [memory["id"]])

    def test_unconfirmed_scoped_memory_is_not_applied(self):
        self.save("global", explicit=False)
        result = self.plan()
        self.assertEqual(result["used_memory_ids"], [])
        self.assertEqual(len(result["candidate_memory_ids"]), 1)

    def test_invalid_scopes_and_missing_context_are_rejected(self):
        for fields in [{"scope": "wrong"}, {"scope": "course", "course": " "},
                       {"scope": "knowledge_point", "course": "Algorithms"}]:
            response = self.client.post("/feedback", json={
                "user_id": "alice", "content": "15 minutes", "feedback_type": "task_preference", **fields,
            })
            self.assertEqual(response.status_code, 422)

    def test_current_hint_overrides_persistent_style_without_new_preference(self):
        memory = self.save("global", "先看例子，再讲定义", feedback_type="explanation_preference")
        self.llm = PreferenceLLM("generate_understanding_question")
        response = self.client.post("/agent/check", json={
            "user_id": "alice", "course": "Algorithms", "knowledge_point": "BFS", "hint_preference": "definition",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["used_memory_ids"], [])
        payload = json.loads(self.llm.calls[0][1]["content"])
        self.assertEqual(payload["confirmed_memories"], [])
        with self.sessions() as session:
            self.assertEqual(len(session.scalars(select(MemoryRecord)).all()), 1)
        self.llm = PreferenceLLM("generate_understanding_question")
        following = self.client.post("/agent/check", json={
            "user_id": "alice", "course": "Another course", "knowledge_point": "Limit",
        })
        self.assertEqual(following.json()["used_memory_ids"], [memory["id"]])

    def test_old_scopes_upgrade_without_becoming_global(self):
        engine = create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql("CREATE TABLE memories (id TEXT, knowledge_point TEXT)")
                connection.exec_driver_sql("INSERT INTO memories VALUES ('course', NULL), ('point', 'BFS')")
                _upgrade_memory_scope(connection)
                _upgrade_memory_scope(connection)
                self.assertEqual(connection.exec_driver_sql("SELECT scope FROM memories ORDER BY id").all(),
                                 [("course",), ("knowledge_point",)])
        finally:
            engine.dispose()
