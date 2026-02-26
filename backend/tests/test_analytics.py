"""
P1-05 Analytics — unit + integration tests.
"""
import json
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Integration tests — endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_valid_event(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/analytics/event",
        headers=auth_headers,
        json={
            "event_name": "paywall_shown",
            "timestamp": "2026-02-25T12:00:00Z",
            "properties": {"screen": "main"},
        },
    )
    assert resp.status_code == 202
    assert resp.json()["accepted"] is True


@pytest.mark.asyncio
async def test_ingest_unknown_event_name(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/analytics/event",
        headers=auth_headers,
        json={
            "event_name": "totally_fake_event",
            "timestamp": "2026-02-25T12:00:00Z",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_forbidden_property_key(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/analytics/event",
        headers=auth_headers,
        json={
            "event_name": "paywall_shown",
            "timestamp": "2026-02-25T12:00:00Z",
            "properties": {"message": "secret text"},
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_properties_too_large(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/analytics/event",
        headers=auth_headers,
        json={
            "event_name": "paywall_shown",
            "timestamp": "2026-02-25T12:00:00Z",
            "properties": {"big": "x" * 9000},
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_with_session_id(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/analytics/event",
        headers=auth_headers,
        json={
            "event_name": "quota_blocked",
            "timestamp": "2026-02-25T12:00:00Z",
            "session_id": str(uuid.uuid4()),
            "properties": {"blocking_reason": "FREE_QUOTA_EXCEEDED"},
        },
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_ingest_without_session_id(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/analytics/event",
        headers=auth_headers,
        json={
            "event_name": "purchase_started",
            "timestamp": "2026-02-25T12:00:00Z",
        },
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_ingest_unauthenticated(client: AsyncClient):
    resp = await client.post(
        "/v1/analytics/event",
        json={
            "event_name": "paywall_shown",
            "timestamp": "2026-02-25T12:00:00Z",
        },
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_summary_dev_mode(client: AsyncClient, auth_headers: dict):
    # Ingest an event first
    await client.post(
        "/v1/analytics/event",
        headers=auth_headers,
        json={"event_name": "paywall_shown", "timestamp": "2026-02-25T12:00:00Z"},
    )

    resp = await client.get("/v1/analytics/summary", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "window_days" in body
    assert "counts" in body
