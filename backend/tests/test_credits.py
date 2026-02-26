"""
P1-02 Credits — unit + integration tests.
"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Integration tests — endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_redeem_endpoint_200(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/credits/redeem",
        headers=auth_headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "product_id": "credits_10",
            "purchase_token": "tok_test",
            "purchased_at": "2026-02-25T00:00:00Z",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == 10
    assert body["credits_balance"] == 10


@pytest.mark.asyncio
async def test_redeem_idempotency_409(client: AsyncClient, auth_headers: dict):
    key = str(uuid.uuid4())
    payload = {
        "idempotency_key": key,
        "product_id": "credits_5",
        "purchase_token": "tok_test",
        "purchased_at": "2026-02-25T00:00:00Z",
    }
    resp1 = await client.post("/v1/credits/redeem", headers=auth_headers, json=payload)
    assert resp1.status_code == 200
    assert resp1.json()["added"] == 5

    resp2 = await client.post("/v1/credits/redeem", headers=auth_headers, json=payload)
    assert resp2.status_code == 409
    assert resp2.json()["detail"]["added"] == 0


@pytest.mark.asyncio
async def test_redeem_invalid_product_400(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/credits/redeem",
        headers=auth_headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "product_id": "credits_999",
            "purchase_token": "tok_test",
            "purchased_at": "2026-02-25T00:00:00Z",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_redeem_unauthenticated(client: AsyncClient):
    resp = await client.post(
        "/v1/credits/redeem",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "product_id": "credits_10",
            "purchase_token": "tok_test",
            "purchased_at": "2026-02-25T00:00:00Z",
        },
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_redeem_multiple_products(client: AsyncClient, auth_headers: dict):
    """Redeem different products and verify cumulative balance."""
    r1 = await client.post(
        "/v1/credits/redeem",
        headers=auth_headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "product_id": "credits_5",
            "purchase_token": "tok1",
            "purchased_at": "2026-02-25T00:00:00Z",
        },
    )
    assert r1.status_code == 200

    r2 = await client.post(
        "/v1/credits/redeem",
        headers=auth_headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "product_id": "credits_30",
            "purchase_token": "tok2",
            "purchased_at": "2026-02-25T00:00:00Z",
        },
    )
    assert r2.status_code == 200
    assert r2.json()["credits_balance"] == 35
