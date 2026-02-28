"""Abstract LLM provider interface and shared data types."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RAGContext:
    """Retrieved verses to inject into the user prompt."""

    verses: list[dict]  # Each dict matches verse_block schema from INTERFACES.md §7.1
    translation_id: str = "NIV"

    def to_xml(self) -> str:
        """Format verses as XML block for inclusion in user message."""
        if not self.verses:
            return ""
        lines = ["<retrieved_verses>"]
        for v in self.verses:
            book = v.get("book", "")
            ch = v.get("chapter", "")
            vs = v.get("verse_start", "")
            ve = v.get("verse_end", vs)
            tid = v.get("translation_id", self.translation_id)
            quote = v.get("quote", "")
            lines.append(
                f'  <verse ref="{book} {ch}:{vs}-{ve}" translation="{tid}">'
                f"{quote}</verse>"
            )
        lines.append("</retrieved_verses>")
        return "\n".join(lines)


@dataclass(frozen=True)
class LLMResponse:
    """Structured response from an LLM provider."""

    raw_json: str
    model_version: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    metadata: dict = field(default_factory=dict)


class LLMProvider(abc.ABC):
    """Abstract base for LLM providers (Claude, Llama, stub, etc.)."""

    @abc.abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        rag_context: RAGContext | None = None,
        timeout_seconds: float = 30.0,
        max_output_tokens: int = 2048,
    ) -> LLMResponse:
        """Generate a structured JSON response.

        Args:
            system_prompt: System instructions for the LLM.
            user_prompt: User message (may include RAG context).
            rag_context: Optional retrieved verses to include.
            timeout_seconds: Request timeout.
            max_output_tokens: Maximum tokens in the response.

        Returns:
            LLMResponse with raw JSON string and usage metadata.

        Raises:
            LLMTimeoutError: Request exceeded timeout.
            LLMRateLimitError: Provider rate limit hit.
            LLMOutputError: Response was not valid JSON.
            LLMProviderError: Other provider-level error.
        """
        ...
