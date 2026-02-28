"""LLM provider factory — returns the configured provider instance."""

from __future__ import annotations

import functools

from app.llm.provider import LLMProvider


@functools.lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    """Return the LLM provider configured in settings.

    Uses lru_cache so the provider (and its HTTP client) is created once
    per process.  For tests, call ``get_llm_provider.cache_clear()``
    before overriding settings.
    """
    from app.config import settings

    provider_name = settings.llm_provider.lower()

    if provider_name == "anthropic":
        from app.llm.claude_provider import ClaudeProvider

        if not settings.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY must be set when LLM_PROVIDER=anthropic"
            )
        return ClaudeProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )

    if provider_name == "stub":
        from app.llm.stub_provider import StubProvider

        return StubProvider()

    raise ValueError(
        f"Unknown LLM_PROVIDER: {settings.llm_provider!r}. "
        "Valid options: 'anthropic', 'stub'"
    )
