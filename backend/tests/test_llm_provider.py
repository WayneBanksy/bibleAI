"""Tests for the LLM provider abstraction layer."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.errors import (
    LLMError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.llm.provider import LLMResponse, RAGContext
from app.llm.stub_provider import StubProvider


# ---------------------------------------------------------------------------
# RAGContext
# ---------------------------------------------------------------------------


class TestRAGContext:
    def test_empty_verses_returns_empty_string(self):
        ctx = RAGContext(verses=[])
        assert ctx.to_xml() == ""

    def test_single_verse_xml(self):
        ctx = RAGContext(
            verses=[
                {
                    "book": "Psalms",
                    "chapter": 23,
                    "verse_start": 1,
                    "verse_end": 3,
                    "translation_id": "NIV",
                    "quote": "The Lord is my shepherd...",
                }
            ]
        )
        xml = ctx.to_xml()
        assert "<retrieved_verses>" in xml
        assert 'ref="Psalms 23:1-3"' in xml
        assert 'translation="NIV"' in xml
        assert "The Lord is my shepherd..." in xml
        assert "</retrieved_verses>" in xml

    def test_multiple_verses(self):
        ctx = RAGContext(
            verses=[
                {"book": "Psalms", "chapter": 23, "verse_start": 1, "verse_end": 1, "quote": "v1"},
                {"book": "Psalms", "chapter": 23, "verse_start": 4, "verse_end": 4, "quote": "v4"},
            ]
        )
        xml = ctx.to_xml()
        assert xml.count("<verse ") == 2


# ---------------------------------------------------------------------------
# StubProvider
# ---------------------------------------------------------------------------


class TestStubProvider:
    @pytest.mark.asyncio
    async def test_returns_valid_json(self):
        provider = StubProvider()
        resp = await provider.generate(
            system_prompt="test",
            user_prompt="test",
        )
        assert isinstance(resp, LLMResponse)
        data = json.loads(resp.raw_json)
        assert "reflection" in data
        assert isinstance(data["reflection"], str)
        assert len(data["reflection"]) > 0

    @pytest.mark.asyncio
    async def test_stub_json_matches_schema(self):
        provider = StubProvider()
        resp = await provider.generate("sys", "usr")
        data = json.loads(resp.raw_json)

        # Required field
        assert isinstance(data["reflection"], str)

        # Optional fields
        assert "verse_block" in data
        assert isinstance(data["verse_block"], list)
        for verse in data["verse_block"]:
            assert "translation_id" in verse
            assert "book" in verse
            assert "chapter" in verse
            assert "verse_start" in verse

        # Other optional fields
        assert "prayer" in data
        assert "next_step" in data
        assert "reflection_question" in data

    @pytest.mark.asyncio
    async def test_model_version(self):
        provider = StubProvider()
        resp = await provider.generate("sys", "usr")
        assert resp.model_version == "stub-v1"

    @pytest.mark.asyncio
    async def test_zero_token_usage(self):
        provider = StubProvider()
        resp = await provider.generate("sys", "usr")
        assert resp.input_tokens == 0
        assert resp.output_tokens == 0


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class TestErrors:
    def test_timeout_is_retryable(self):
        err = LLMTimeoutError()
        assert err.retryable is True
        assert isinstance(err, LLMError)

    def test_rate_limit_is_retryable(self):
        err = LLMRateLimitError()
        assert err.retryable is True

    def test_provider_error_not_retryable(self):
        err = LLMProviderError("bad request", status_code=400)
        assert err.retryable is False
        assert err.status_code == 400

    def test_output_error_is_retryable(self):
        err = LLMOutputError()
        assert err.retryable is True

    def test_base_error_default_not_retryable(self):
        err = LLMError("generic")
        assert err.retryable is False


# ---------------------------------------------------------------------------
# ClaudeProvider (unit tests with mocked SDK)
# ---------------------------------------------------------------------------


def _make_claude_provider(mock_client):
    """Create a ClaudeProvider with a pre-injected mock client."""
    from app.llm.claude_provider import ClaudeProvider

    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider._client = mock_client
    provider._model = "claude-sonnet-4-20250514"
    return provider


def _mock_anthropic_response(text: str, input_tokens: int = 100, output_tokens: int = 50):
    """Build a mock Anthropic Messages API response."""
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = text

    mock_usage = MagicMock()
    mock_usage.input_tokens = input_tokens
    mock_usage.output_tokens = output_tokens

    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage = mock_usage
    return mock_response


class TestClaudeProvider:
    @pytest.mark.asyncio
    async def test_builds_user_message_without_rag(self):
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_anthropic_response(json.dumps({"reflection": "test"}))
        )

        provider = _make_claude_provider(mock_client)
        await provider.generate("system", "hello user")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "hello user"

    @pytest.mark.asyncio
    async def test_builds_user_message_with_rag(self):
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_anthropic_response(json.dumps({"reflection": "with rag"}))
        )

        provider = _make_claude_provider(mock_client)
        rag = RAGContext(
            verses=[{"book": "Psalms", "chapter": 23, "verse_start": 1, "verse_end": 1, "quote": "The Lord..."}]
        )
        await provider.generate("system", "hello", rag_context=rag)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert "<retrieved_verses>" in user_content
        assert "hello" in user_content

    @pytest.mark.asyncio
    async def test_handles_timeout(self):
        import anthropic

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            side_effect=anthropic.APITimeoutError(request=MagicMock())
        )

        provider = _make_claude_provider(mock_client)
        with pytest.raises(LLMTimeoutError):
            await provider.generate("sys", "usr")

    @pytest.mark.asyncio
    async def test_handles_invalid_json_response(self):
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_anthropic_response("This is not JSON at all")
        )

        provider = _make_claude_provider(mock_client)
        with pytest.raises(LLMOutputError):
            await provider.generate("sys", "usr")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestFactory:
    def test_stub_provider_by_default(self):
        from app.llm.factory import get_llm_provider

        get_llm_provider.cache_clear()
        provider = get_llm_provider()
        assert isinstance(provider, StubProvider)
        get_llm_provider.cache_clear()

    def test_anthropic_requires_api_key(self):
        from app.llm.factory import get_llm_provider

        get_llm_provider.cache_clear()
        with patch("app.config.settings") as mock_settings:
            mock_settings.llm_provider = "anthropic"
            mock_settings.anthropic_api_key = ""
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                get_llm_provider()
        get_llm_provider.cache_clear()

    def test_unknown_provider_raises(self):
        from app.llm.factory import get_llm_provider

        get_llm_provider.cache_clear()
        with patch("app.config.settings") as mock_settings:
            mock_settings.llm_provider = "gpt-4"
            with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
                get_llm_provider()
        get_llm_provider.cache_clear()
