"""Stub LLM provider — returns hard-coded JSON for tests and CI."""

from __future__ import annotations

import json

from app.llm.provider import LLMProvider, LLMResponse, RAGContext

_STUB_JSON = json.dumps({
    "reflection": (
        "You are not alone in what you're feeling. "
        "Scripture reminds us that God is close to the brokenhearted and "
        "saves those who are crushed in spirit. "
        "Whatever you are carrying right now, you are seen and valued."
    ),
    "verse_block": [
        {
            "translation_id": "NIV",
            "book": "Psalms",
            "chapter": 34,
            "verse_start": 18,
            "verse_end": 18,
        }
    ],
    "prayer": (
        "Lord, draw near to those who are hurting. "
        "May they feel your presence and find rest in you."
    ),
    "next_step": "Consider sharing what you're carrying with a trusted friend or pastor.",
    "reflection_question": "What would it feel like to let yourself be fully known and loved?",
})


class StubProvider(LLMProvider):
    """Returns a fixed JSON response. Used for tests and CI."""

    MODEL_VERSION = "stub-v1"

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        rag_context: RAGContext | None = None,
        timeout_seconds: float = 30.0,
        max_output_tokens: int = 2048,
    ) -> LLMResponse:
        return LLMResponse(
            raw_json=_STUB_JSON,
            model_version=self.MODEL_VERSION,
            input_tokens=0,
            output_tokens=0,
            latency_ms=0.0,
        )
