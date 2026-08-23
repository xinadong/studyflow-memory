import unittest

import httpx

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
