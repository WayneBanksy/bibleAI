"""Claude (Anthropic) LLM provider implementation."""

from __future__ import annotations

import json
import time

import structlog

from app.llm.errors import (
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.llm.provider import LLMProvider, LLMResponse, RAGContext

log = structlog.get_logger()


class ClaudeProvider(LLMProvider):
    """Calls the Anthropic Messages API via the official SDK."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        rag_context: RAGContext | None = None,
        timeout_seconds: float = 30.0,
        max_output_tokens: int = 2048,
    ) -> LLMResponse:
        import anthropic

        # Build user message with optional RAG context
        user_content = user_prompt
        if rag_context and rag_context.verses:
            user_content = f"{rag_context.to_xml()}\n\n{user_prompt}"

        start = time.monotonic()

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=max_output_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
                timeout=timeout_seconds,
            )
        except anthropic.APITimeoutError as exc:
            raise LLMTimeoutError(
                f"Anthropic API timed out after {timeout_seconds}s"
            ) from exc
        except anthropic.RateLimitError as exc:
            raise LLMRateLimitError(
                "Anthropic rate limit exceeded"
            ) from exc
        except anthropic.APIStatusError as exc:
            raise LLMProviderError(
                f"Anthropic API error: {exc.message}",
                status_code=exc.status_code,
            ) from exc

        latency_ms = (time.monotonic() - start) * 1000

        # Extract text content from response
        raw_text = ""
        for block in response.content:
            if block.type == "text":
                raw_text += block.text

        # Validate that the response is parseable JSON
        try:
            json.loads(raw_text)
        except json.JSONDecodeError as exc:
            log.warning(
                "llm.output_not_json",
                model=self._model,
                raw_text_prefix=raw_text[:200],
            )
            raise LLMOutputError(
                f"Claude response is not valid JSON: {exc}"
            ) from exc

        # Log token usage for cost monitoring
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        log.info(
            "llm.generate",
            provider="anthropic",
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=round(latency_ms, 1),
        )

        return LLMResponse(
            raw_json=raw_text,
            model_version=f"anthropic:{self._model}",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
