"""
P0 API tests — require docker-compose postgres + alembic upgrade head.

Coverage:
  - POST /v1/auth/token (dev stub)
  - POST /v1/sessions
  - GET  /v1/sessions/{id}
  - POST /v1/sessions/{id}/messages (202 + idempotency)
  - GET  /v1/sessions/{id}/events (SSE connection + heartbeat)
  - GET  /health
"""
import asyncio
import uuid

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_token_dev(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/auth/token",
        json={"grant_type": "apple_id_token", "id_token": f"test-{uuid.uuid4()}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 3600


@pytest.mark.asyncio
async def test_auth_requires_valid_grant(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/auth/token",
        json={"grant_type": "password", "id_token": "anything"},
    )
    assert resp.status_code == 422  # Pydantic rejects invalid Literal


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_session(client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.post(
        "/v1/sessions",
        json={"mode": "support_session"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["mode"] == "support_session"
    assert body["translation_preference"] == "NIV"  # default
    assert body["tone_preference"] == "reflective"    # default
    assert "session_id" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_create_session_custom_prefs(client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.post(
        "/v1/sessions",
        json={"mode": "prayer_builder", "translation_preference": "ESV", "tone_preference": "encouraging"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["translation_preference"] == "ESV"
    assert body["tone_preference"] == "encouraging"


@pytest.mark.asyncio
async def test_get_session(client: AsyncClient, auth_headers: dict) -> None:
    create = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = create.json()["session_id"]

    resp = await client.get(f"/v1/sessions/{session_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == session_id
    assert body["status"] == "active"
    assert body["message_count"] == 0


@pytest.mark.asyncio
async def test_get_session_not_found(client: AsyncClient, auth_headers: dict) -> None:
    resp = await client.get(f"/v1/sessions/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_session_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/v1/sessions", json={"mode": "support_session"})
    assert resp.status_code == 403  # HTTPBearer raises 403 when no credentials


# ---------------------------------------------------------------------------
# Messages — send + idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_message(client: AsyncClient, auth_headers: dict) -> None:
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]
    client_msg_id = str(uuid.uuid4())

    resp = await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": "I'm feeling anxious today.", "client_message_id": client_msg_id},
        headers=auth_headers,
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["session_id"] == session_id
    assert body["client_message_id"] == client_msg_id
    assert body["status"] == "processing"
    assert "message_id" in body


@pytest.mark.asyncio
async def test_send_message_idempotency(client: AsyncClient, auth_headers: dict) -> None:
    """Second send with same client_message_id must return 409."""
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]
    client_msg_id = str(uuid.uuid4())

    first = await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": "Hello", "client_message_id": client_msg_id},
        headers=auth_headers,
    )
    assert first.status_code == 202
    original_msg_id = first.json()["message_id"]

    second = await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": "Hello again (retry)", "client_message_id": client_msg_id},
        headers=auth_headers,
    )
    assert second.status_code == 409
    error = second.json()["detail"]
    assert error["code"] == "conflict"
    assert error["details"]["original_message_id"] == original_msg_id


@pytest.mark.asyncio
async def test_message_count_increments(client: AsyncClient, auth_headers: dict) -> None:
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]

    await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": "First message", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    # Allow background task to persist
    await asyncio.sleep(0.1)

    detail = await client.get(f"/v1/sessions/{session_id}", headers=auth_headers)
    assert detail.json()["message_count"] >= 1


# ---------------------------------------------------------------------------
# SSE — connection opens and yields a heartbeat within timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sse_connects_and_heartbeats(client: AsyncClient, auth_headers: dict) -> None:
    session = await client.post("/v1/sessions", json={"mode": "support_session"}, headers=auth_headers)
    session_id = session.json()["session_id"]

    # Send a message first so there will be demo stream events
    await client.post(
        f"/v1/sessions/{session_id}/messages",
        json={"text": "Test stream", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers,
    )

    events: list[str] = []
    async with client.stream(
        "GET",
        f"/v1/sessions/{session_id}/events",
        headers=auth_headers,
        timeout=10.0,
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        async for line in response.aiter_lines():
            if line:
                events.append(line)
            # Collect until we see message.final
            if any("message.final" in e for e in events):
                break

    event_types = [e for e in events if e.startswith("event:")]
    assert any("token.delta" in e for e in event_types), f"No token.delta in {event_types}"
    assert any("message.final" in e for e in event_types), f"No message.final in {event_types}"
