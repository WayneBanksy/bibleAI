"""
P0 Integration Tests — T011 (QA Engineer)

Coverage:
  P0-01  Session lifecycle  (01-01 → 01-06)
  P0-02  Idempotency        (02-01 → 02-05)
  P0-03  SSE streaming      (03-01 → 03-07)
  P0-04  Safety / risk.interrupt  (04-01 → 04-06) — xfail pending T007
  P0-05  Report persistence (05-01 → 05-06)

Requirements:
  Same as test_api.py:
    - Postgres running (docker compose up -d postgres, or local)
    - DATABASE_URL env set (default: postgresql+asyncpg://postgres:postgres@localhost:5432/bible_therapist)
    - uv run alembic upgrade head

Run (excluding pending-T007 tests):
  uv run pytest tests/test_p0_integration.py -m "not pending_t007" -v

Run all (including xfail):
  uv run pytest tests/test_p0_integration.py -v
"""
import asyncio
import json
import uuid
from typing import Any

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# SSE wire-format helpers
# ---------------------------------------------------------------------------

def _parse_sse_frame(lines: list[str]) -> dict[str, Any] | None:
    """Parse a list of SSE field lines into a frame dict."""
    frame: dict[str, Any] = {}
    for line in lines:
        if ":" not in line:
            continue
        field, _, raw_value = line.partition(":")
        value = raw_value.lstrip(" ")
        if field == "event":
            frame["event"] = value
        elif field == "data":
            frame["data_raw"] = value
            try:
                frame["data"] = json.loads(value)
            except (ValueError, TypeError):
                frame["data"] = value
        elif field == "id":
            frame["id"] = value
    return frame if frame else None


async def _drain_sse(
    client: AsyncClient,
    session_id: str,
    auth_headers: dict,
    timeout: float = 12.0,
) -> list[dict[str, Any]]:
    """
    Open the SSE stream, collect parsed frames until `message.final`
    (or `risk.interrupt`), then close.
    """
    frames: list[dict[str, Any]] = []
    pending_lines: list[str] = []

    async with client.stream(
        "GET",
        f"/v1/sessions/{session_id}/events",
        headers=auth_headers,
        timeout=timeout,
    ) as response:
        assert response.status_code == 200

        async for line in response.aiter_lines():
            if line:
                pending_lines.append(line)
            else:
                if pending_lines:
                    frame = _parse_sse_frame(pending_lines)
                    if frame:
                        frames.append(frame)
                    pending_lines = []
                event_types = {f.get("event") for f in frames}
                if "message.final" in event_types or "risk.interrupt" in event_types:
                    break

    return frames


async def _send_and_drain(
    client: AsyncClient,
    auth_headers: dict,
    text: str = "I'm feeling anxious today.",
) -> tuple[dict, list[dict[str, Any]]]:
    """Create a session, send a message, drain SSE. Returns (send_body, sse_frames)."""
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    assert session.status_code == 201
    session_id = session.json()["session_id"]

    send = await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": text, "client_message_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert send.status_code == 202

    frames = await _drain_sse(client, session_id, auth_headers)
    return send.json(), frames


# ===========================================================================
# P0-01 · Session Lifecycle
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.p0_session
async def test_p001_01_all_four_modes_are_valid(client: AsyncClient, auth_headers: dict) -> None:
    """All four SessionMode values produce 201."""
    modes = ["support_session", "guided_program", "bible_reference", "prayer_builder"]
    for mode in modes:
        resp = await client.post("/v1/sessions", json={"mode": mode}, headers=auth_headers)
        assert resp.status_code == 201, f"mode={mode!r} should be 201, got {resp.status_code}"
        assert resp.json()["mode"] == mode


@pytest.mark.asyncio
@pytest.mark.p0_session
async def test_p001_02_default_prefs_applied(client: AsyncClient, auth_headers: dict) -> None:
    """Omitting translation + tone applies server defaults (NIV, reflective)."""
    resp = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["translation_preference"] == "NIV"
    assert body["tone_preference"] == "reflective"


@pytest.mark.asyncio
@pytest.mark.p0_session
async def test_p001_03_invalid_mode_returns_422(client: AsyncClient, auth_headers: dict) -> None:
    """A mode value outside the allowed enum returns 422."""
    resp = await client.post("/v1/sessions", json={"mode": "therapy_session"}, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.p0_session
async def test_p001_04_invalid_translation_returns_422(client: AsyncClient, auth_headers: dict) -> None:
    """A translation not in (ESV, NIV, KJV, NKJV, NLT, CSB) returns 422."""
    resp = await client.post(
        "/v1/sessions",
        json={"mode": "support_session", "translation_preference": "MSG"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.p0_session
async def test_p001_05_unauthenticated_returns_403(client: AsyncClient) -> None:
    """No Authorization header → 403."""
    resp = await client.post("/v1/sessions", json={"mode": "support_session"})
    assert resp.status_code == 403


@pytest.mark.asyncio
@pytest.mark.p0_session
async def test_p001_06_cross_user_session_access_returns_404(
    client: AsyncClient, auth_headers: dict
) -> None:
    """User A's session is invisible to User B (returns 404, not 403)."""
    # Create session as user A (auth_headers)
    session_a = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session_a.json()["session_id"]

    # Authenticate as user B (fresh UUID → different user record)
    resp_b = await client.post(
        "/v1/auth/token",
        json={"grant_type": "apple_id_token", "id_token": f"user-b-{uuid.uuid4()}"},
    )
    token_b = resp_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B attempts to GET user A's session
    get = await client.get(f"/v1/sessions/{session_id}", headers=headers_b)
    assert get.status_code == 404, "Cross-user session access must return 404, not the session data"


# ===========================================================================
# P0-02 · Idempotency
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.p0_idempotency
async def test_p002_01_first_send_returns_202(client: AsyncClient, auth_headers: dict) -> None:
    """First POST /messages returns 202 with processing status."""
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]
    client_msg_id = str(uuid.uuid4())

    resp = await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": "Hello", "client_message_id": client_msg_id},
        headers=auth_headers,
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "processing"
    assert "message_id" in body
    assert body["client_message_id"] == client_msg_id


@pytest.mark.asyncio
@pytest.mark.p0_idempotency
async def test_p002_02_duplicate_client_message_id_returns_409(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Sending the same client_message_id twice in the same session → 409."""
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]
    client_msg_id = str(uuid.uuid4())

    first = await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": "First attempt", "client_message_id": client_msg_id},
        headers=auth_headers,
    )
    assert first.status_code == 202

    second = await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": "Retry — same ID", "client_message_id": client_msg_id},
        headers=auth_headers,
    )
    assert second.status_code == 409
    error = second.json()["detail"]
    assert error["code"] == "conflict"


@pytest.mark.asyncio
@pytest.mark.p0_idempotency
async def test_p002_03_409_contains_correct_original_message_id(
    client: AsyncClient, auth_headers: dict
) -> None:
    """The 409 response's original_message_id must match the first 202's message_id."""
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]
    client_msg_id = str(uuid.uuid4())

    first = await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": "Original", "client_message_id": client_msg_id},
        headers=auth_headers,
    )
    original_message_id = first.json()["message_id"]

    second = await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": "Retry", "client_message_id": client_msg_id},
        headers=auth_headers,
    )
    assert second.status_code == 409
    error_details = second.json()["detail"]["details"]
    assert error_details["original_message_id"] == original_message_id, (
        "409 detail.details.original_message_id must match the first 202 message_id — "
        "iOS uses this to correlate the retry with the existing SSE stream"
    )


@pytest.mark.asyncio
@pytest.mark.p0_idempotency
async def test_p002_04_same_client_message_id_different_sessions_both_succeed(
    client: AsyncClient, auth_headers: dict
) -> None:
    """The same client_message_id used in two different sessions must both return 202.
    The uniqueness constraint is (session_id, client_message_id), not just client_message_id.
    """
    shared_client_msg_id = str(uuid.uuid4())

    session_a = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_b = await client.post("/v1/sessions", json={"mode": "prayer_builder"}, headers=auth_headers)

    resp_a = await client.post(
        f"/v1/sessions/{session_a.json()['session_id']}/messages",
        json={"text": "Session A message", "client_message_id": shared_client_msg_id},
        headers=auth_headers,
    )
    resp_b = await client.post(
        f"/v1/sessions/{session_b.json()['session_id']}/messages",
        json={"text": "Session B message", "client_message_id": shared_client_msg_id},
        headers=auth_headers,
    )

    assert resp_a.status_code == 202, "Same client_message_id in session A must succeed"
    assert resp_b.status_code == 202, "Same client_message_id in session B must also succeed (cross-session isolation)"
    # The two message_ids should be different
    assert resp_a.json()["message_id"] != resp_b.json()["message_id"]


@pytest.mark.asyncio
@pytest.mark.p0_idempotency
async def test_p002_05_duplicate_status_code_is_exactly_409(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Idempotency collision must return exactly 409, not 400 or 500."""
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]
    mid = str(uuid.uuid4())

    await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": "First", "client_message_id": mid},
        headers=auth_headers,
    )
    second = await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": "Second", "client_message_id": mid},
        headers=auth_headers,
    )
    assert second.status_code == 409, (
        f"Expected exactly 409, got {second.status_code}. "
        "4xx/5xx variants would break iOS retry logic."
    )


# ===========================================================================
# P0-03 · SSE Streaming Contract
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.p0_sse
async def test_p003_01_token_delta_sequences_are_monotonically_increasing(
    client: AsyncClient, auth_headers: dict
) -> None:
    """sequence values in token.delta events must be 1, 2, 3, … (no gaps, no repeats)."""
    _, frames = await _send_and_drain(client, auth_headers)

    delta_frames = [f for f in frames if f.get("event") == "token.delta"]
    assert delta_frames, "Expected at least one token.delta event"

    sequences = [f["data"]["sequence"] for f in delta_frames]
    expected = list(range(1, len(sequences) + 1))
    assert sequences == expected, (
        f"token.delta sequences must be [1, 2, ..., N], got {sequences}"
    )


@pytest.mark.asyncio
@pytest.mark.p0_sse
async def test_p003_02_assembled_delta_text_matches_message_final(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Concatenating all token.delta.delta values must equal message.final.text."""
    _, frames = await _send_and_drain(client, auth_headers)

    delta_frames = [f for f in frames if f.get("event") == "token.delta"]
    final_frames = [f for f in frames if f.get("event") == "message.final"]

    assert final_frames, "Expected message.final"
    assembled = "".join(f["data"]["delta"] for f in delta_frames)
    final_text = final_frames[0]["data"]["text"]

    assert assembled == final_text, (
        "Assembled token.delta chunks must match message.final.text exactly. "
        "A mismatch means the iOS client would show different text than the server committed."
    )


@pytest.mark.asyncio
@pytest.mark.p0_sse
async def test_p003_03_message_final_emitted_exactly_once(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Only one message.final event must be emitted per message."""
    _, frames = await _send_and_drain(client, auth_headers)
    final_frames = [f for f in frames if f.get("event") == "message.final"]
    assert len(final_frames) == 1, (
        f"Expected exactly 1 message.final, got {len(final_frames)}. "
        "Duplicate message.final would cause the iOS client to double-commit."
    )


@pytest.mark.asyncio
@pytest.mark.p0_sse
async def test_p003_04_no_token_delta_after_message_final(
    client: AsyncClient, auth_headers: dict
) -> None:
    """All token.delta events must precede message.final in stream order."""
    _, frames = await _send_and_drain(client, auth_headers)

    event_sequence = [f.get("event") for f in frames if f.get("event") in ("token.delta", "message.final")]
    # message.final must be the last non-heartbeat event
    if "message.final" in event_sequence:
        final_idx = event_sequence.index("message.final")
        late_deltas = [e for e in event_sequence[final_idx + 1:] if e == "token.delta"]
        assert not late_deltas, (
            f"Found {len(late_deltas)} token.delta event(s) after message.final. "
            "The iOS draft would re-open after being committed."
        )


@pytest.mark.asyncio
@pytest.mark.p0_sse
async def test_p003_05_sse_requires_auth(client: AsyncClient, auth_headers: dict) -> None:
    """SSE endpoint must return 403 without Authorization header."""
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]

    resp = await client.get(f"/v1/sessions/{session_id}/events")
    assert resp.status_code == 403


@pytest.mark.asyncio
@pytest.mark.p0_sse
async def test_p003_06_sse_content_type_is_event_stream(
    client: AsyncClient, auth_headers: dict
) -> None:
    """SSE response must have Content-Type: text/event-stream."""
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]

    await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": "Test stream", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers,
    )

    async with client.stream(
        "GET", f"/v1/sessions/{session_id}/events", headers=auth_headers, timeout=5.0
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")


@pytest.mark.asyncio
@pytest.mark.p0_sse
async def test_p003_07_message_final_risk_payload_has_required_fields(
    client: AsyncClient, auth_headers: dict
) -> None:
    """message.final.risk must contain risk_level, categories, and action."""
    _, frames = await _send_and_drain(client, auth_headers)

    final_frames = [f for f in frames if f.get("event") == "message.final"]
    assert final_frames
    risk = final_frames[0]["data"].get("risk")
    assert risk is not None, "message.final must include a risk object"
    assert "risk_level" in risk, "risk.risk_level missing"
    assert "categories" in risk, "risk.categories missing"
    assert "action" in risk, "risk.action missing"
    assert risk["risk_level"] in ("none", "low", "medium", "high")
    assert risk["action"] in ("allow", "caution", "refuse", "escalate")


# ===========================================================================
# P0-04 · Safety Gating / risk.interrupt   [pending T007 — xfail]
# ===========================================================================
#
# These tests document the EXPECTED behaviour once T007 is implemented.
# They are marked xfail(strict=False) so they:
#   - Show as "xfail" (expected failure) until T007 lands
#   - Show as "xpass" (unexpected pass) once T007 lands — a signal to
#     remove the xfail marker and add to the default CI run.
#
# Remove `@pytest.mark.xfail` and `@pytest.mark.pending_t007` when T007 ships.

CRISIS_TEXT = "I want to hurt myself and I don't want to be here anymore."
MEDICAL_TEXT = "Should I stop taking my antidepressants? What dose should I take?"


@pytest.mark.asyncio
@pytest.mark.p0_safety
@pytest.mark.pending_t007
@pytest.mark.xfail(reason="T007 safety pre-check not yet implemented", strict=False)
async def test_p004_01_crisis_input_emits_risk_interrupt(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Crisis input must result in event: risk.interrupt on the SSE stream."""
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]

    await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": CRISIS_TEXT, "client_message_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    frames = await _drain_sse(client, session_id, auth_headers)
    event_types = [f.get("event") for f in frames]
    assert "risk.interrupt" in event_types, (
        f"Crisis input must emit risk.interrupt, got event types: {event_types}"
    )


@pytest.mark.asyncio
@pytest.mark.p0_safety
@pytest.mark.pending_t007
@pytest.mark.xfail(reason="T007 safety pre-check not yet implemented", strict=False)
async def test_p004_02_escalate_action_bypasses_llm(
    client: AsyncClient, auth_headers: dict
) -> None:
    """When action=escalate, no token.delta events must appear in the stream."""
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]

    await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": CRISIS_TEXT, "client_message_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    frames = await _drain_sse(client, session_id, auth_headers)
    event_types = [f.get("event") for f in frames]
    assert "token.delta" not in event_types, (
        "LLM must be bypassed for crisis input — no token.delta events expected "
        f"when risk.interrupt is emitted. Got: {event_types}"
    )


@pytest.mark.asyncio
@pytest.mark.p0_safety
@pytest.mark.pending_t007
@pytest.mark.xfail(reason="T007 safety pre-check not yet implemented", strict=False)
async def test_p004_03_risk_interrupt_requires_acknowledgment_is_true(
    client: AsyncClient, auth_headers: dict
) -> None:
    """risk.interrupt payload must have requires_acknowledgment=true for crisis input."""
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]

    await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": CRISIS_TEXT, "client_message_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    frames = await _drain_sse(client, session_id, auth_headers)
    interrupt_frames = [f for f in frames if f.get("event") == "risk.interrupt"]
    assert interrupt_frames
    assert interrupt_frames[0]["data"]["requires_acknowledgment"] is True, (
        "iOS blocks input until user acknowledges — requires_acknowledgment must be true"
    )


@pytest.mark.asyncio
@pytest.mark.p0_safety
@pytest.mark.pending_t007
@pytest.mark.xfail(reason="T007 safety pre-check not yet implemented", strict=False)
async def test_p004_04_risk_interrupt_resources_present(
    client: AsyncClient, auth_headers: dict
) -> None:
    """risk.interrupt must include at least 3 crisis resources (988, Crisis Text, 911)."""
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]

    await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": CRISIS_TEXT, "client_message_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    frames = await _drain_sse(client, session_id, auth_headers)
    interrupt_frames = [f for f in frames if f.get("event") == "risk.interrupt"]
    assert interrupt_frames
    resources = interrupt_frames[0]["data"].get("resources", [])
    assert len(resources) >= 3, (
        f"At least 3 crisis resources required (988, Crisis Text Line, 911). Got {resources}"
    )
    labels = [r["label"] for r in resources]
    assert any("988" in lbl for lbl in labels), "988 Suicide & Crisis Lifeline must be listed"


@pytest.mark.asyncio
@pytest.mark.p0_safety
@pytest.mark.pending_t007
@pytest.mark.xfail(reason="T007 safety pre-check not yet implemented", strict=False)
async def test_p004_05_medical_advice_input_returns_refuse_action(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Medical advice requests must result in action=refuse (not escalate or allow)."""
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]

    await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": MEDICAL_TEXT, "client_message_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    frames = await _drain_sse(client, session_id, auth_headers)

    final_frames = [f for f in frames if f.get("event") == "message.final"]
    interrupt_frames = [f for f in frames if f.get("event") == "risk.interrupt"]

    # Either: message.final with action=refuse, or risk.interrupt with action=refuse
    if final_frames:
        assert final_frames[0]["data"]["risk"]["action"] == "refuse"
    elif interrupt_frames:
        assert interrupt_frames[0]["data"]["action"] == "refuse"
    else:
        pytest.fail(f"Expected message.final or risk.interrupt, got: {[f.get('event') for f in frames]}")


@pytest.mark.asyncio
@pytest.mark.p0_safety
@pytest.mark.pending_t007
@pytest.mark.xfail(reason="T007 + T012/T013 advisor signoff required", strict=False)
async def test_p004_06_post_crisis_session_can_resume(
    client: AsyncClient, auth_headers: dict
) -> None:
    """After a risk.interrupt, the session should still accept new messages.
    The server decides if chat continues; the client must be able to send.
    Requires T012/T013 advisor signoffs to define exact resumption policy.
    """
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]

    # Send crisis message
    await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": CRISIS_TEXT, "client_message_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    frames = await _drain_sse(client, session_id, auth_headers)
    assert any(f.get("event") == "risk.interrupt" for f in frames)

    # After acknowledgment, a follow-up message must be accepted (202)
    follow_up = await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": "Thank you. I called 988.", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert follow_up.status_code == 202, (
        "Post-crisis follow-up message must be accepted (202). "
        "The session should not be permanently locked."
    )


# ===========================================================================
# P0-05 · Report Endpoint Persistence
# ===========================================================================

async def _setup_reportable_session(
    client: AsyncClient, auth_headers: dict
) -> tuple[str, str]:
    """Returns (session_id, message_id) suitable for a report submission."""
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]

    send = await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": "Hello", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    # The message_id in the 202 response is the pre-allocated assistant message ID.
    # Users report assistant messages in production.
    message_id = send.json()["message_id"]
    return session_id, message_id


@pytest.mark.asyncio
@pytest.mark.p0_report
async def test_p005_01_report_happy_path(client: AsyncClient, auth_headers: dict) -> None:
    """Submit a report → 200, ok=true, report_id is a valid UUID."""
    session_id, message_id = await _setup_reportable_session(client, auth_headers)

    resp = await client.post(
        "/v1/safety/report",
        json={
            "session_id": session_id,
            "message_id": message_id,
            "reason": "inappropriate",
            "details": "This response felt spiritually coercive.",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    # report_id must be a valid UUID
    assert uuid.UUID(body["report_id"])


@pytest.mark.asyncio
@pytest.mark.p0_report
async def test_p005_02_report_wrong_session_ownership_returns_404(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Reporting a message from another user's session must return 404."""
    # Create session + message as user A
    session_id, message_id = await _setup_reportable_session(client, auth_headers)

    # Authenticate as user B
    resp_b = await client.post(
        "/v1/auth/token",
        json={"grant_type": "apple_id_token", "id_token": f"user-b-{uuid.uuid4()}"},
    )
    headers_b = {"Authorization": f"Bearer {resp_b.json()['access_token']}"}

    resp = await client.post(
        "/v1/safety/report",
        json={"session_id": session_id, "message_id": message_id, "reason": "harmful"},
        headers=headers_b,
    )
    assert resp.status_code == 404, (
        "User B must not be able to submit reports against User A's session"
    )


@pytest.mark.asyncio
@pytest.mark.p0_report
async def test_p005_03_invalid_reason_returns_422(
    client: AsyncClient, auth_headers: dict
) -> None:
    """An unrecognised reason value must return 422."""
    session_id, message_id = await _setup_reportable_session(client, auth_headers)

    resp = await client.post(
        "/v1/safety/report",
        json={
            "session_id": session_id,
            "message_id": message_id,
            "reason": "i_dont_like_it",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.p0_report
async def test_p005_04_details_text_not_echoed_in_response(
    client: AsyncClient, auth_headers: dict
) -> None:
    """The raw details string must NOT appear in the response body (stored as hash only)."""
    session_id, message_id = await _setup_reportable_session(client, auth_headers)
    sensitive_text = "My name is John and I feel very depressed about my situation."

    resp = await client.post(
        "/v1/safety/report",
        json={
            "session_id": session_id,
            "message_id": message_id,
            "reason": "inappropriate",
            "details": sensitive_text,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    # The raw text must not appear anywhere in the response
    assert sensitive_text not in resp.text, (
        "Raw details text must not be returned in the response (D008 storage policy: hash only)"
    )


@pytest.mark.asyncio
@pytest.mark.p0_report
async def test_p005_05_report_without_details_accepted(
    client: AsyncClient, auth_headers: dict
) -> None:
    """details is optional — omitting it must return 200."""
    session_id, message_id = await _setup_reportable_session(client, auth_headers)

    resp = await client.post(
        "/v1/safety/report",
        json={
            "session_id": session_id,
            "message_id": message_id,
            "reason": "other",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
@pytest.mark.p0_report
async def test_p005_06_all_four_report_reasons_accepted(
    client: AsyncClient, auth_headers: dict
) -> None:
    """All four reason values must return 200."""
    reasons = ["inappropriate", "incorrect_scripture", "harmful", "other"]
    for reason in reasons:
        session_id, message_id = await _setup_reportable_session(client, auth_headers)
        resp = await client.post(
            "/v1/safety/report",
            json={"session_id": session_id, "message_id": message_id, "reason": reason},
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"reason={reason!r} should be accepted, got {resp.status_code}"
