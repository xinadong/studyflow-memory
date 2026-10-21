import json
import unittest

import httpx

from app.agents.orchestrator import _explanation_style, _json_object
from app.api.routes.feedback import _correct_memory_type_from_explicit_cue
from app.domain.value_objects.memory_type import MemoryType
from app.agents.tool_registry import RECOVERY_TOOL_NAMES, tool_definitions
from app.infrastructure.llm.adapter import LLMCallError
from app.infrastructure.llm.client import OpenAICompatibleClient


PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "split_learning_task",
        "description": "拆分学习任务",
        "parameters": {
            "type": "object",
            "properties": {"goal": {"type": "string"}},
            "required": ["goal"],
            "additionalProperties": False,
        },
    },
}


class LLMToolCallingTests(unittest.TestCase):
    def test_recovery_tool_schema_inlines_local_enum_references(self):
        schema = tool_definitions(RECOVERY_TOOL_NAMES)[1]["function"]["parameters"]
        encoded = json.dumps(schema, ensure_ascii=False)

        self.assertNotIn("$ref", encoded)
        self.assertNotIn("$defs", encoded)
        self.assertIn('"too_hard"', encoded)

    def test_explicit_diagram_preference_wins_over_concept_word(self):
        self.assertEqual(
            _explanation_style("以后请先给我看图示或流程图，再解释概念"),
            "diagram_first",
        )

    def test_ambiguous_feedback_cues_do_not_force_one_memory_type(self):
        self.assertEqual(
            _correct_memory_type_from_explicit_cue(
                "任务控制20分钟，同时先看一个例子",
                MemoryType.TASK_PREFERENCE,
            ),
            MemoryType.TASK_PREFERENCE,
        )

    def test_too_hard_recovery_action_has_progressive_steps(self):
        from app.agents.tools.generate_recovery_action import generate_recovery_action
        from app.domain.value_objects.memory_type import BlockType

        result = generate_recovery_action(
            block_type=BlockType.TOO_HARD,
            context="队列作用不理解",
            knowledge_point="BFS",
        )
        self.assertIn("定位难点", result["action"])
        self.assertIn("回顾前置", result["action"])
        self.assertIn("基础练习", result["action"])
        self.assertIn("返回原题", result["action"])
        self.assertIn("BFS", result["action"])

    def test_old_simple_recovery_action_is_nested_once_as_basic_practice(self):
        from app.agents.tools.generate_recovery_action import generate_recovery_action
        from app.domain.value_objects.memory_type import BlockType

        result = generate_recovery_action(
            block_type=BlockType.TOO_HARD,
            context="队列作用不理解",
            knowledge_point="BFS",
            preferred_action="先看一个遍历示例，再完成一道小题。",
        )
        self.assertEqual(result["action"].count("定位难点"), 1)
        self.assertEqual(result["action"].count("基础练习"), 1)
        self.assertIn("基础练习：先看一个遍历示例，再完成一道小题。", result["action"])

    def test_final_json_parser_accepts_a_fenced_json_object(self):
        self.assertEqual(
            _json_object("```json\n{\"explanation\":\"已生成任务\"}\n```"),
            {"explanation": "已生成任务"},
        )

    def test_final_json_parser_extracts_one_embedded_object(self):
        self.assertEqual(
            _json_object('结果如下：\n{"explanation":"已生成任务"}\n请查收。'),
            {"explanation": "已生成任务"},
        )

    def test_client_sends_response_format_when_requested(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={
                "choices": [{"message": {
                    "role": "assistant",
                    "content": '{"explanation":"ok"}',
                }}],
            })

        client = OpenAICompatibleClient(
            "https://example.test/v1", "secret", "gpt-5.6-terra",
            transport=httpx.MockTransport(handler), max_retries=0,
        )
        client.chat(
            [{"role": "user", "content": "返回JSON"}],
            response_format={"type": "json_object"},
        )

        payload = __import__("json").loads(requests[0].content)
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_client_sends_tools_and_parses_tool_calls_and_usage(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "split_learning_task",
                                    "arguments": '{"goal":"学习BFS"}',
                                },
                            }],
                        },
                        "finish_reason": "tool_calls",
                    }],
                    "usage": {"prompt_tokens": 21, "completion_tokens": 7},
                },
            )

        client = OpenAICompatibleClient(
            "https://example.test/v1", "secret", "gpt-5.6-terra",
            transport=httpx.MockTransport(handler), max_retries=2,
        )
        result = client.chat(
            [{"role": "user", "content": "帮我学习BFS"}],
            tools=[PLAN_TOOL],
            tool_choice="required",
        )

        self.assertEqual(result.tool_calls[0].name, "split_learning_task")
        self.assertEqual(result.tool_calls[0].arguments, {"goal": "学习BFS"})
        self.assertEqual(result.input_tokens, 21)
        self.assertEqual(result.output_tokens, 7)
        self.assertEqual(result.retry_count, 0)
        self.assertEqual(requests[0].url.path, "/v1/chat/completions")
        payload = __import__("json").loads(requests[0].content)
        self.assertEqual(payload["model"], "gpt-5.6-terra")
        self.assertEqual(payload["tool_choice"], "required")
        self.assertEqual(payload["tools"][0]["function"]["name"], "split_learning_task")

    def test_client_retries_transient_errors_twice_then_returns_failure(self):
        attempts = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(503, json={"error": {"message": "busy"}})

        client = OpenAICompatibleClient(
            "https://example.test/v1", "secret", "gpt-5.6-terra",
            transport=httpx.MockTransport(handler), max_retries=2,
        )

        with self.assertRaises(LLMCallError) as caught:
            client.chat([{"role": "user", "content": "test"}], tools=[PLAN_TOOL])

        self.assertEqual(attempts, 3)
        self.assertEqual(caught.exception.code, "provider_unavailable")
        self.assertEqual(caught.exception.retry_count, 2)
        self.assertEqual(caught.exception.model, "gpt-5.6-terra")
        self.assertGreater(caught.exception.input_tokens, 0)
        self.assertGreaterEqual(caught.exception.model_latency_ms, 0)

    def test_client_rejects_invalid_tool_arguments(self):
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "choices": [{"message": {"role": "assistant", "tool_calls": [{
                    "id": "call-1", "type": "function",
                    "function": {"name": "split_learning_task", "arguments": "not-json"},
                }]}}],
            })

        client = OpenAICompatibleClient(
            "https://example.test/v1", "secret", "gpt-5.6-terra",
            transport=httpx.MockTransport(handler), max_retries=0,
        )

        with self.assertRaises(LLMCallError) as caught:
            client.chat([{"role": "user", "content": "test"}], tools=[PLAN_TOOL])

        self.assertEqual(caught.exception.code, "invalid_tool_arguments")


if __name__ == "__main__":
    unittest.main()
