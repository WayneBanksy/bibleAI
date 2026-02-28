"""LLM provider abstraction layer.

Supports hybrid strategy: Claude (Anthropic) for MVP, swappable to
self-hosted Llama via config change.
"""

from app.llm.errors import (
    LLMError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.llm.factory import get_llm_provider
from app.llm.provider import LLMProvider, LLMResponse, RAGContext

__all__ = [
    "LLMError",
    "LLMOutputError",
    "LLMProvider",
    "LLMProviderError",
    "LLMRateLimitError",
    "LLMResponse",
    "LLMTimeoutError",
    "RAGContext",
    "get_llm_provider",
]
