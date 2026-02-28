"""
Pipeline tests.

Tests the full message pipeline SSE output via direct calls to run_pipeline.
DB persistence helpers are patched to avoid triggering SQLAlchemy mapper
configuration in unit tests (the mapper's BibleVerse.citations relationship
uses a non-standard any() expression that errors on first init outside a real
connection). Integration-level DB tests live in test_p0_integration.py.

Coverage:
  1. escalate path  — risk.interrupt only; no token.delta; LLM NOT called
  2. refuse path    — stream.error only; no token.delta
  3. allow path     — N token.delta then exactly one message.final; invariants checked
  4. citation stub  — pipeline does not raise if validate_citations returns []
  5. safety classifier — required keyword → action/category mapping
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline import (
    CRISIS_TEMPLATE,
    CRISIS_RESOURCES,
    run_pipeline,
)
from app.safety import KeywordSafetyClassifier, SafetyCheckResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_sse_event(raw: str) -> dict[str, Any] | None:
    """Parse a single SSE event string → {event, data}. None for heartbeats."""
    lines = [ln for ln in raw.strip().split("\n") if ln]
    event_type = None
    data_str = None
    for line in lines:
        if line.startswith("event: "):
            event_type = line[len("event: "):]
        elif line.startswith("data: "):
            data_str = line[len("data: "):]
    if event_type and data_str:
        return {"event": event_type, "data": json.loads(data_str)}
    return None


async def _drain_queue(
    queue: asyncio.Queue, timeout: float = 3.0
) -> list[dict[str, Any]]:
    """Consume all items from the queue until empty (with timeout)."""
    events = []
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            raw = queue.get_nowait()
            parsed = _parse_sse_event(raw)
            if parsed:
                events.append(parsed)
        except asyncio.QueueEmpty:
            await asyncio.sleep(0.02)
            if queue.empty():
                break
    return events


# Patch context that stubs out all DB helpers so SQLAlchemy mapper never fires.
_DB_PATCHES = [
    patch("app.pipeline._log_safety_event", new_callable=AsyncMock),
    patch("app.pipeline._update_user_message", new_callable=AsyncMock),
    patch("app.pipeline._persist_assistant_message", new_callable=AsyncMock),
]


def _no_db_patches():
    """Stack all DB-stub patches for use with contextlib.ExitStack."""
    import contextlib
    stack = contextlib.ExitStack()
    for p in _DB_PATCHES:
        stack.enter_context(p)
    return stack


def _mock_llm_provider():
    """Create a mock LLM provider that returns a valid stub response."""
    from app.llm.provider import LLMResponse

    mock_json = json.dumps({
        "reflection": (
            "You are not alone in what you're feeling. "
            "Scripture reminds us that God is close to the brokenhearted."
        ),
        "verse_block": [],
        "prayer": "Lord, draw near to those who are hurting.",
        "next_step": "Consider sharing what you're carrying with a trusted friend.",
        "reflection_question": "What would it feel like to let yourself be fully known?",
    })

    mock_provider = MagicMock()
    mock_provider.generate = AsyncMock(
        return_value=LLMResponse(
            raw_json=mock_json,
            model_version="mock-v1",
        )
    )
    return mock_provider


# ---------------------------------------------------------------------------
# 1. Escalate path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escalate_path_no_llm():
    """
    pre_check action=escalate → exactly one risk.interrupt; LLM never called.
    """
    queue = asyncio.Queue()

    mock_provider = MagicMock()
    mock_provider.generate = AsyncMock(side_effect=AssertionError("LLM must not be called on escalate"))

    with _no_db_patches(), \
         patch("app.pipeline.get_llm_provider", return_value=mock_provider), \
         patch("app.pipeline.llm_classifier") as mock_llm_clf:
        mock_llm_clf.classify.return_value = SafetyCheckResult(
            risk_level="none", categories=[], action="allow"
        )
        await run_pipeline(
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            user_message_id=uuid.uuid4(),
            assistant_message_id=uuid.uuid4(),
            text="I want to kill myself",
            db=None,
            queue=queue,
        )

    events = await _drain_queue(queue)
    event_types = [e["event"] for e in events]
    assert event_types == ["risk.interrupt"], f"Expected only risk.interrupt, got: {event_types}"

    interrupt = events[0]["data"]
    assert interrupt["action"] == "escalate"
    assert interrupt["requires_acknowledgment"] is True
    assert interrupt["message"] == CRISIS_TEMPLATE
    assert len(interrupt["resources"]) == len(CRISIS_RESOURCES)
    assert "self_harm" in interrupt["categories"]


@pytest.mark.asyncio
async def test_escalate_violence_path():
    """Violence keyword also produces risk.interrupt with no LLM invocation."""
    queue = asyncio.Queue()

    mock_provider = MagicMock()
    mock_provider.generate = AsyncMock(side_effect=AssertionError("LLM must not be called"))

    with _no_db_patches(), \
         patch("app.pipeline.get_llm_provider", return_value=mock_provider), \
         patch("app.pipeline.llm_classifier") as mock_llm_clf:
        mock_llm_clf.classify.return_value = SafetyCheckResult(
            risk_level="none", categories=[], action="allow"
        )
        await run_pipeline(
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            user_message_id=uuid.uuid4(),
            assistant_message_id=uuid.uuid4(),
            text="I want to hurt someone",
            db=None,
            queue=queue,
        )

    events = await _drain_queue(queue)
    assert len(events) == 1
    assert events[0]["event"] == "risk.interrupt"
    assert "violence" in events[0]["data"]["categories"]


# ---------------------------------------------------------------------------
# 2. Refuse path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refuse_path_no_tokens():
    """
    pre_check action=refuse → stream.error with retryable=False; no token.delta.
    """
    queue = asyncio.Queue()

    with _no_db_patches():
        await run_pipeline(
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            user_message_id=uuid.uuid4(),
            assistant_message_id=uuid.uuid4(),
            text="What medication should I take?",
            db=None,
            queue=queue,
        )

    events = await _drain_queue(queue)
    event_types = [e["event"] for e in events]

    assert "token.delta" not in event_types
    assert "message.final" not in event_types
    assert "stream.error" in event_types

    error = next(e["data"] for e in events if e["event"] == "stream.error")
    assert error["retryable"] is False


# ---------------------------------------------------------------------------
# 3. Allow path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_allow_path_delta_then_final():
    """
    Normal allow path:
    - N token.delta (sequence 1..N)
    - Exactly one message.final AFTER all deltas
    - message.final.text == concatenated deltas
    - message.final.risk.action == "allow"
    """
    queue = asyncio.Queue()

    with _no_db_patches(), \
         patch("app.pipeline.get_llm_provider", return_value=_mock_llm_provider()), \
         patch("app.pipeline.validate_citations", new_callable=AsyncMock, return_value=[]), \
         patch("app.pipeline.llm_classifier") as mock_llm_clf:
        mock_llm_clf.classify.return_value = SafetyCheckResult(
            risk_level="none", categories=[], action="allow"
        )
        await run_pipeline(
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            user_message_id=uuid.uuid4(),
            assistant_message_id=uuid.uuid4(),
            text="I feel sad today",
            db=None,
            queue=queue,
        )

    events = await _drain_queue(queue)

    deltas = [e for e in events if e["event"] == "token.delta"]
    finals = [e for e in events if e["event"] == "message.final"]

    assert len(finals) == 1, "Exactly one message.final expected"
    assert len(deltas) > 0, "At least one token.delta expected"

    # Sequence invariant: 1..N
    sequences = [d["data"]["sequence"] for d in deltas]
    assert sequences == list(range(1, len(deltas) + 1)), f"Sequence not 1..N: {sequences}"

    # Text assembly invariant
    assembled = "".join(d["data"]["delta"] for d in deltas)
    assert assembled == finals[0]["data"]["text"], "Assembled deltas != message.final.text"

    # All deltas precede message.final
    delta_indices = [i for i, e in enumerate(events) if e["event"] == "token.delta"]
    final_index = next(i for i, e in enumerate(events) if e["event"] == "message.final")
    assert all(i < final_index for i in delta_indices)

    # Risk reflects pre-check result
    assert finals[0]["data"]["risk"]["action"] == "allow"


@pytest.mark.asyncio
async def test_allow_path_hello():
    """'Hello' → risk_level=none, action=allow."""
    queue = asyncio.Queue()

    with _no_db_patches(), \
         patch("app.pipeline.get_llm_provider", return_value=_mock_llm_provider()), \
         patch("app.pipeline.validate_citations", new_callable=AsyncMock, return_value=[]), \
         patch("app.pipeline.llm_classifier") as mock_llm_clf:
        mock_llm_clf.classify.return_value = SafetyCheckResult(
            risk_level="none", categories=[], action="allow"
        )
        await run_pipeline(
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            user_message_id=uuid.uuid4(),
            assistant_message_id=uuid.uuid4(),
            text="Hello",
            db=None,
            queue=queue,
        )

    events = await _drain_queue(queue)
    finals = [e for e in events if e["event"] == "message.final"]
    assert len(finals) == 1
    assert finals[0]["data"]["risk"]["risk_level"] == "none"
    assert finals[0]["data"]["risk"]["action"] == "allow"


# ---------------------------------------------------------------------------
# 4. Citation stub fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_citation_gate_error_does_not_raise():
    """
    If validate_citations raises (ImportError, DB error, etc.),
    pipeline does NOT raise and still emits message.final with empty citations.
    """
    queue = asyncio.Queue()

    with _no_db_patches(), \
         patch("app.pipeline.get_llm_provider", return_value=_mock_llm_provider()), \
         patch(
             "app.pipeline.validate_citations",
             new_callable=AsyncMock,
             side_effect=ImportError("citation module unavailable"),
         ), \
         patch("app.pipeline.llm_classifier") as mock_llm_clf:
        mock_llm_clf.classify.return_value = SafetyCheckResult(
            risk_level="none", categories=[], action="allow"
        )
        await run_pipeline(
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            user_message_id=uuid.uuid4(),
            assistant_message_id=uuid.uuid4(),
            text="I feel overwhelmed",
            db=None,
            queue=queue,
        )

    events = await _drain_queue(queue)
    finals = [e for e in events if e["event"] == "message.final"]
    assert len(finals) == 1
    assert finals[0]["data"]["citations"] == []


# ---------------------------------------------------------------------------
# 5. Safety classifier — required keyword → action/category mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected_action,expected_category", [
    ("I want to kill myself",           "escalate", "self_harm"),
    ("I want to hurt someone",          "escalate", "violence"),
    ("What medication should I take?",  "refuse",   "medical_advice"),
    ("I feel sad today",                "allow",    None),
    ("Hello",                           "allow",    None),
])
def test_keyword_classifier_required_cases(text, expected_action, expected_category):
    clf = KeywordSafetyClassifier()
    result = clf.classify(text)
    assert result.action == expected_action, (
        f"text={text!r}: expected action={expected_action!r}, got={result.action!r}"
    )
    if expected_category:
        assert expected_category in result.categories, (
            f"text={text!r}: expected {expected_category!r} in categories={result.categories}"
        )


def test_keyword_classifier_returns_safety_check_result():
    clf = KeywordSafetyClassifier()
    result = clf.classify("Hello")
    assert isinstance(result, SafetyCheckResult)
    assert result.risk_level in ("none", "low", "medium", "high")
    assert result.action in ("allow", "caution", "refuse", "escalate")
    assert isinstance(result.categories, list)
    assert isinstance(result.rationale_codes, list)
