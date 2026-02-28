"""Tests for pipeline with LLM provider abstraction.

These tests verify the pipeline correctly delegates to the provider
and handles error scenarios.
"""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.errors import (
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.llm.provider import LLMResponse
from app.llm.stub_provider import StubProvider


def _make_queue():
    return asyncio.Queue()


def _drain_queue(queue: asyncio.Queue) -> list[str]:
    """Drain all items from queue synchronously."""
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def _parse_sse_events(items: list[str]) -> list[tuple[str, dict]]:
    """Parse SSE event strings into (event_type, data) tuples."""
    parsed = []
    for item in items:
        lines = item.strip().split("\n")
        event_type = None
        data = None
        for line in lines:
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event_type and data is not None:
            parsed.append((event_type, data))
    return parsed


# ---------------------------------------------------------------------------
# Pipeline with StubProvider (regression)
# ---------------------------------------------------------------------------

class TestPipelineWithStub:
    """Verify the pipeline still works end-to-end with StubProvider."""

    @pytest.mark.asyncio
    async def test_stub_produces_token_deltas_and_final(self):
        """Pipeline with stub should emit token.delta events and message.final."""
        queue = _make_queue()

        # Mock DB session and crypto
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.execute = AsyncMock()

        session_id = uuid.uuid4()
        user_id = uuid.uuid4()
        user_msg_id = uuid.uuid4()
        asst_msg_id = uuid.uuid4()

        with (
            patch("app.pipeline.message_crypto") as mock_crypto,
            patch("app.pipeline.validate_citations", new_callable=AsyncMock, return_value=[]),
            patch("app.pipeline.get_llm_provider", return_value=StubProvider()),
        ):
            mock_crypto.encrypt.return_value = b"encrypted"

            from app.pipeline import run_pipeline

            await run_pipeline(
                session_id=session_id,
                user_id=user_id,
                user_message_id=user_msg_id,
                assistant_message_id=asst_msg_id,
                text="I feel lost",
                db=mock_db,
                queue=queue,
            )

        events = _drain_queue(queue)
        parsed = _parse_sse_events(events)

        # Should have token.delta events followed by message.final
        event_types = [e[0] for e in parsed]
        assert "token.delta" in event_types
        assert event_types[-1] == "message.final"

        # message.final should have required fields
        final_data = parsed[-1][1]
        assert "text" in final_data
        assert "structured" in final_data
        assert "citations" in final_data
        assert "risk" in final_data
        assert "model_version" in final_data
        assert final_data["model_version"] == "stub-v1"


# ---------------------------------------------------------------------------
# Pipeline error handling
# ---------------------------------------------------------------------------


class TestPipelineErrorHandling:
    """Verify pipeline correctly handles LLM provider errors."""

    async def _run_with_error(self, error_to_raise):
        queue = _make_queue()
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.execute = AsyncMock()

        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(side_effect=error_to_raise)

        with (
            patch("app.pipeline.message_crypto") as mock_crypto,
            patch("app.pipeline.get_llm_provider", return_value=mock_provider),
        ):
            mock_crypto.encrypt.return_value = b"encrypted"

            from app.pipeline import run_pipeline

            await run_pipeline(
                session_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                user_message_id=uuid.uuid4(),
                assistant_message_id=uuid.uuid4(),
                text="test message",
                db=mock_db,
                queue=queue,
            )

        return _drain_queue(queue)

    @pytest.mark.asyncio
    async def test_timeout_emits_retryable_error(self):
        events = await self._run_with_error(LLMTimeoutError())
        parsed = _parse_sse_events(events)

        assert len(parsed) == 1
        event_type, data = parsed[0]
        assert event_type == "stream.error"
        assert data["code"] == "llm_timeout"
        assert data["retryable"] is True

    @pytest.mark.asyncio
    async def test_rate_limit_emits_retryable_error(self):
        events = await self._run_with_error(LLMRateLimitError())
        parsed = _parse_sse_events(events)

        assert len(parsed) == 1
        event_type, data = parsed[0]
        assert event_type == "stream.error"
        assert data["code"] == "llm_rate_limit"
        assert data["retryable"] is True

    @pytest.mark.asyncio
    async def test_output_error_emits_retryable_error(self):
        events = await self._run_with_error(LLMOutputError())
        parsed = _parse_sse_events(events)

        assert len(parsed) == 1
        event_type, data = parsed[0]
        assert event_type == "stream.error"
        assert data["code"] == "llm_output_invalid"
        assert data["retryable"] is True

    @pytest.mark.asyncio
    async def test_provider_error_emits_non_retryable_error(self):
        events = await self._run_with_error(
            LLMProviderError("auth failure", status_code=401)
        )
        parsed = _parse_sse_events(events)

        assert len(parsed) == 1
        event_type, data = parsed[0]
        assert event_type == "stream.error"
        assert data["code"] == "llm_error"
        assert data["retryable"] is False

    @pytest.mark.asyncio
    async def test_model_version_propagates_to_final(self):
        """When LLM succeeds, model_version from response appears in message.final."""
        queue = _make_queue()
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.execute = AsyncMock()

        custom_version = "anthropic:claude-sonnet-4-20250514"
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(
            return_value=LLMResponse(
                raw_json=json.dumps({
                    "reflection": "Test reflection",
                    "verse_block": [],
                    "prayer": None,
                    "next_step": None,
                    "reflection_question": None,
                }),
                model_version=custom_version,
                input_tokens=100,
                output_tokens=50,
            )
        )

        with (
            patch("app.pipeline.message_crypto") as mock_crypto,
            patch("app.pipeline.validate_citations", new_callable=AsyncMock, return_value=[]),
            patch("app.pipeline.get_llm_provider", return_value=mock_provider),
        ):
            mock_crypto.encrypt.return_value = b"encrypted"

            from app.pipeline import run_pipeline

            await run_pipeline(
                session_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                user_message_id=uuid.uuid4(),
                assistant_message_id=uuid.uuid4(),
                text="test",
                db=mock_db,
                queue=queue,
            )

        events = _drain_queue(queue)
        parsed = _parse_sse_events(events)
        final_events = [e for e in parsed if e[0] == "message.final"]
        assert len(final_events) == 1
        assert final_events[0][1]["model_version"] == custom_version
