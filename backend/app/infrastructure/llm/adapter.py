"""Provider-neutral contracts for OpenAI-compatible tool calling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMCallError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str = "模型调用失败",
        *,
        retry_count: int = 0,
        status_code: int = 502,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_count = retry_count
        self.status_code = status_code
        # Optional audit metadata populated by the provider adapter. Keeping
        # it on the typed error lets routes persist complete failure traces
        # without coupling the domain layer to httpx.
        self.model: str | None = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.model_latency_ms = 0


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMResult:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    model: str = ""
    retry_count: int = 0


class LLMAdapter(Protocol):
    model: str

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> LLMResult: ...


class UnconfiguredLLMAdapter:
    """An explicit failing adapter used when no provider credentials exist.

    Returning an adapter instead of failing in FastAPI dependency resolution
    lets the Agent service persist a failed run with the requesting user and
    operation before the API returns the structured error response.
    """

    def __init__(self, model: str) -> None:
        self.model = model

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> LLMResult:
        raise LLMCallError(
            "model_not_configured",
            "模型调用失败：未配置模型 API",
            status_code=503,
        )


def get_llm_adapter() -> LLMAdapter:
    from app.core.config import get_settings
    from app.infrastructure.llm.client import OpenAICompatibleClient

    settings = get_settings()
    if not settings.llm_base_url or not settings.llm_api_key:
        return UnconfiguredLLMAdapter(settings.llm_model)
    return OpenAICompatibleClient(
        settings.llm_base_url,
        settings.llm_api_key,
        settings.llm_model,
        timeout=settings.request_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
