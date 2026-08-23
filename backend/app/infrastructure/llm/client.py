"""OpenAI-compatible Chat Completions client with validated tool calls."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any

import httpx

from app.infrastructure.llm.adapter import LLMCallError, LLMResult, ToolCall
from app.infrastructure.telemetry.token_tracker import estimate_tokens


class OpenAICompatibleClient:
    RETRYABLE_STATUS = {429, 502, 503, 504}

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 20.0,
        *,
        max_retries: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        normalized = base_url.rstrip("/")
        self.base_url = normalized if normalized.endswith("/v1") else f"{normalized}/v1"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.transport = transport

    def _annotate_failure(
        self,
        error: LLMCallError,
        *,
        messages: list[dict[str, Any]],
        started: float,
        retry_count: int,
    ) -> LLMCallError:
        """Attach provider-independent telemetry to a failed call."""
        error.model = self.model
        error.input_tokens = estimate_tokens(json.dumps(messages, ensure_ascii=False))
        error.output_tokens = 0
        error.model_latency_ms = int((perf_counter() - started) * 1000)
        error.retry_count = retry_count
        return error

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> LLMResult:
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload.update({"tools": tools, "tool_choice": tool_choice})

        started = perf_counter()
        retry_count = 0
        response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
                    response = client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                    )
                if response.status_code in self.RETRYABLE_STATUS and attempt < self.max_retries:
                    retry_count += 1
                    continue
                response.raise_for_status()
                break
            except (httpx.TimeoutException, httpx.TransportError) as cause:
                if attempt < self.max_retries:
                    retry_count += 1
                    continue
                code = "provider_timeout" if isinstance(cause, httpx.TimeoutException) else "provider_unavailable"
                error = LLMCallError(
                    code,
                    status_code=504 if code == "provider_timeout" else 502,
                )
                raise self._annotate_failure(
                    error,
                    messages=messages,
                    started=started,
                    retry_count=retry_count,
                ) from cause
            except httpx.HTTPStatusError as error:
                code = "provider_rejected" if error.response.status_code < 500 else "provider_unavailable"
                failure = LLMCallError(code)
                raise self._annotate_failure(
                    failure,
                    messages=messages,
                    started=started,
                    retry_count=retry_count,
                ) from error

        if response is None or response.status_code in self.RETRYABLE_STATUS:
            failure = LLMCallError("provider_unavailable")
            raise self._annotate_failure(
                failure,
                messages=messages,
                started=started,
                retry_count=retry_count,
            )

        try:
            data = response.json()
            message = data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            failure = LLMCallError("invalid_provider_response")
            raise self._annotate_failure(
                failure,
                messages=messages,
                started=started,
                retry_count=retry_count,
            ) from error

        parsed_calls: list[ToolCall] = []
        for raw_call in message.get("tool_calls") or []:
            try:
                arguments = json.loads(raw_call["function"]["arguments"])
                if not isinstance(arguments, dict):
                    raise TypeError("tool arguments must be an object")
                parsed_calls.append(ToolCall(
                    id=raw_call["id"],
                    name=raw_call["function"]["name"],
                    arguments=arguments,
                ))
            except (ValueError, KeyError, TypeError) as error:
                failure = LLMCallError("invalid_tool_arguments")
                raise self._annotate_failure(
                    failure,
                    messages=messages,
                    started=started,
                    retry_count=retry_count,
                ) from error

        usage = data.get("usage") or {}
        prompt_text = json.dumps(messages, ensure_ascii=False)
        output_text = message.get("content") or json.dumps(message.get("tool_calls") or [], ensure_ascii=False)
        return LLMResult(
            text=message.get("content"),
            tool_calls=parsed_calls,
            input_tokens=int(usage.get("prompt_tokens", estimate_tokens(prompt_text))),
            output_tokens=int(usage.get("completion_tokens", estimate_tokens(output_text))),
            latency_ms=int((perf_counter() - started) * 1000),
            model=data.get("model", self.model),
            retry_count=retry_count,
        )
