"""
P1-04 Subscription sync — unit + integration tests.
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.services.subscription_sync import (
    enforce_subscription_expiry,
    sync_subscription_from_transaction,
)


# ---------------------------------------------------------------------------
# Unit tests — sync_subscription_from_transaction
# ---------------------------------------------------------------------------


def _make_user(**overrides):
    """Create a lightweight user-like object for unit testing (no DB/ORM required)."""
    defaults = {
        "id": uuid.uuid4(),
        "external_id": "test",
        "subscription_tier": "free",
        "subscription_status": "inactive",
        "subscription_expires_at": None,
        "subscription_source": None,
        "free_quota_window_start": datetime.now(timezone.utc),
        "free_sessions_used": 0,
        "credits_balance": 0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_sync_activates_subscription():
    user = _make_user()
    future = datetime.now(timezone.utc) + timedelta(days=30)
    sync_subscription_from_transaction(user, expires_at=future)
    assert user.subscription_tier == "plus"
    assert user.subscription_status == "active"
    assert user.subscription_source == "appstore"
    assert user.subscription_expires_at == future


def test_sync_expired_subscription_stays_free():
    user = _make_user()
    past = datetime.now(timezone.utc) - timedelta(days=1)
    sync_subscription_from_transaction(user, expires_at=past)
    assert user.subscription_tier == "free"
    assert user.subscription_status == "inactive"


def test_sync_revoked_subscription():
    user = _make_user(subscription_tier="plus", subscription_status="active")
    revoked = datetime.now(timezone.utc) - timedelta(days=5)
    sync_subscription_from_transaction(user, expires_at=None, revocation_date=revoked)
    assert user.subscription_tier == "free"
    assert user.subscription_status == "inactive"
    assert user.subscription_source is None


# ---------------------------------------------------------------------------
# Unit tests — enforce_subscription_expiry
# ---------------------------------------------------------------------------


def test_enforce_expiry_downgrades_expired():
    past = datetime.now(timezone.utc) - timedelta(days=1)
    user = _make_user(
        subscription_tier="plus",
        subscription_status="active",
        subscription_expires_at=past,
    )
    assert enforce_subscription_expiry(user) is True
    assert user.subscription_tier == "free"
    assert user.subscription_status == "inactive"


def test_enforce_expiry_noop_when_still_active():
    future = datetime.now(timezone.utc) + timedelta(days=30)
    user = _make_user(
        subscription_tier="plus",
        subscription_status="active",
        subscription_expires_at=future,
    )
    assert enforce_subscription_expiry(user) is False
    assert user.subscription_tier == "plus"


def test_enforce_expiry_noop_for_free_user():
    user = _make_user()
    assert enforce_subscription_expiry(user) is False


def test_enforce_expiry_noop_no_expiry_date():
    user = _make_user(subscription_tier="plus", subscription_status="active")
    assert enforce_subscription_expiry(user) is False


# ---------------------------------------------------------------------------
# Integration tests — POST /v1/iap/sync
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_endpoint_200(client: AsyncClient, auth_headers: dict):
    txn_id = str(uuid.uuid4())
    resp = await client.post(
        "/v1/iap/sync",
        headers=auth_headers,
        json={
            "platform": "appstore",
            "product_type": "subscription",
            "product_id": "plus_monthly",
            "transaction_id": txn_id,
            "environment": "Sandbox",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is True
    assert body["entitlements"]["subscription_tier"] == "plus"


@pytest.mark.asyncio
async def test_sync_unauthenticated(client: AsyncClient):
    resp = await client.post(
        "/v1/iap/sync",
        json={
            "platform": "appstore",
            "product_type": "subscription",
            "product_id": "plus_monthly",
            "transaction_id": str(uuid.uuid4()),
            "environment": "Sandbox",
        },
    )
    assert resp.status_code in (401, 403)
