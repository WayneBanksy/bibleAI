"""
P1-04 IAP verification — integration tests.
"""
import uuid

import pytest
from httpx import AsyncClient


def _verify_payload(**overrides) -> dict:
    base = {
        "platform": "appstore",
        "product_type": "subscription",
        "product_id": "plus_monthly",
        "transaction_id": str(uuid.uuid4()),
        "original_transaction_id": None,
        "environment": "Sandbox",
        "signed_transaction_jws": "stub-jws-payload",
        "signed_renewal_info_jws": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# POST /v1/iap/verify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_subscription_200(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/iap/verify",
        headers=auth_headers,
        json=_verify_payload(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is True
    ent = body["entitlements"]
    assert ent["subscription_tier"] == "plus"
    assert ent["subscription_status"] == "active"
    assert ent["wwjd_enabled"] is True


@pytest.mark.asyncio
async def test_verify_idempotent(client: AsyncClient, auth_headers: dict):
    txn_id = str(uuid.uuid4())
    payload = _verify_payload(transaction_id=txn_id)

    resp1 = await client.post("/v1/iap/verify", headers=auth_headers, json=payload)
    assert resp1.status_code == 200

    resp2 = await client.post("/v1/iap/verify", headers=auth_headers, json=payload)
    assert resp2.status_code == 200
    assert resp2.json()["verified"] is True


@pytest.mark.asyncio
async def test_verify_consumable_200(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/iap/verify",
        headers=auth_headers,
        json=_verify_payload(product_type="consumable", product_id="credits_10"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is True
    # Consumable does not upgrade subscription
    assert body["entitlements"]["subscription_tier"] == "free"


@pytest.mark.asyncio
async def test_verify_unauthenticated(client: AsyncClient):
    resp = await client.post("/v1/iap/verify", json=_verify_payload())
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_verify_invalid_product_type(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/v1/iap/verify",
        headers=auth_headers,
        json=_verify_payload(product_type="invalid_type"),
    )
    assert resp.status_code == 422  # Pydantic validation


@pytest.mark.asyncio
async def test_verify_multiple_subscriptions_same_user(client: AsyncClient, auth_headers: dict):
    """Multiple different transactions for the same user should all succeed."""
    resp1 = await client.post(
        "/v1/iap/verify",
        headers=auth_headers,
        json=_verify_payload(product_id="plus_monthly"),
    )
    assert resp1.status_code == 200

    resp2 = await client.post(
        "/v1/iap/verify",
        headers=auth_headers,
        json=_verify_payload(product_id="plus_annual"),
    )
    assert resp2.status_code == 200
    assert resp2.json()["entitlements"]["subscription_tier"] == "plus"
