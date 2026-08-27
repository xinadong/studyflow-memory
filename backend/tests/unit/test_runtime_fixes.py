import unittest
import os
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text

from app.infrastructure.database import _upgrade_agent_runs_schema
from app.infrastructure.repositories.in_memory_memory_repository import InMemoryMemoryRepository
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.llm.adapter import LLMCallError, get_llm_adapter
from app.core.config import get_settings
from app.core.config import Settings
from app.agents.tools.split_learning_task import split_learning_task
from app.agents.tools.adjust_learning_plan import adjust_learning_plan
from app.agents.tool_registry import AdjustPlanArgs


class RuntimeFixTests(unittest.TestCase):
    def test_in_memory_repository_touch_increments_usage(self):
        repository = InMemoryMemoryRepository()
        memory = repository.add(Memory(
            user_id="u1",
            memory_type=MemoryType.TASK_PREFERENCE,
            course="数据结构与算法",
            content="20分钟",
        ))

        self.assertTrue(repository.touch(memory.id))
        touched = repository.get(memory.id)
        self.assertEqual(touched.use_count, 1)
        self.assertIsNotNone(touched.last_used_at)

    def test_agent_runs_upgrade_adds_trace_columns_to_existing_table(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE agent_runs (
                    id VARCHAR(32) PRIMARY KEY,
                    user_id VARCHAR(128),
                    operation VARCHAR(64),
                    input_tokens INTEGER DEFAULT 0,
                    memory_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    retrieval_latency_ms INTEGER DEFAULT 0,
                    model_latency_ms INTEGER DEFAULT 0,
                    retrieved_memory_ids JSON,
                    used_memory_ids JSON,
                    created_at DATETIME
                )
            """))
            _upgrade_agent_runs_schema(connection)

        columns = {column["name"] for column in inspect(engine).get_columns("agent_runs")}
        self.assertTrue({
            "model", "status", "tool_calls", "retry_count", "format_repair_count",
            "error_code", "error_message", "user_acceptance", "candidate_memory_ids",
        }.issubset(columns))
        with engine.begin() as connection:
            _upgrade_agent_runs_schema(connection)

    def test_split_task_never_exceeds_available_minutes_below_five(self):
        task = split_learning_task(goal="快速回顾", available_minutes=3)
        self.assertEqual(task["duration_minutes"], 3)

    def test_split_task_clamps_preference_to_available_minutes(self):
        task = split_learning_task(
            goal="复习BFS", available_minutes=20, preferred_minutes=30,
        )
        self.assertEqual(task["duration_minutes"], 20)

    def test_adjust_plan_never_exceeds_available_minutes_below_five(self):
        task = {"title": "快速回顾", "duration_minutes": 10}
        adjusted = adjust_learning_plan(
            task, available_minutes=3, preferred_minutes=3,
        )
        self.assertEqual(adjusted["duration_minutes"], 3)

    def test_adjust_plan_arguments_accept_sub_five_minute_preference(self):
        arguments = AdjustPlanArgs.model_validate({
            "task": {"title": "快速回顾", "duration_minutes": 3},
            "available_minutes": 3,
            "preferred_minutes": 3,
        })
        self.assertEqual(arguments.preferred_minutes, 3)

    def test_unconfigured_adapter_reports_failure_when_chat_is_called(self):
        with patch.dict(os.environ, {"LLM_BASE_URL": "", "LLM_API_KEY": ""}, clear=False):
            get_settings.cache_clear()
            try:
                adapter = get_llm_adapter()
                with self.assertRaises(LLMCallError) as caught:
                    adapter.chat([{"role": "user", "content": "test"}])
                self.assertEqual(caught.exception.code, "model_not_configured")
            finally:
                get_settings.cache_clear()

    def test_default_model_timeout_covers_slow_tool_calling_provider(self):
        settings = Settings(_env_file=None)
        self.assertGreaterEqual(settings.request_timeout_seconds, 90.0)

    def test_backend_container_installs_dependencies_and_persists_data(self):
        root = Path(__file__).resolve().parents[3]
        dockerfile = (root / "infra" / "Dockerfile.backend").read_text(encoding="utf-8")
        compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("pip install --no-cache-dir .", dockerfile)
        self.assertIn("pip install --no-cache-dir .", dockerfile)
        self.assertIn("./data:/app/data", compose)
        self.assertIn("sqlite:////app/data/studyflow.db", compose)
        self.assertIn("name: studyflow-memory", compose)


if __name__ == "__main__":
    unittest.main()
