"""
P1-01 Entitlements — unit + integration tests.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock

from app.config import Settings
from app.services.entitlements import assert_can_start_session, get_entitlements


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(**overrides):
    """Create a mock User object with entitlement defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "subscription_tier": "free",
        "subscription_status": "inactive",
        "subscription_source": None,
        "subscription_expires_at": None,
        "free_quota_window_start": datetime.now(timezone.utc),
        "free_sessions_used": 0,
        "credits_balance": 0,
    }
    defaults.update(overrides)
    user = MagicMock()
    for k, v in defaults.items():
        setattr(user, k, v)
    return user


def _make_settings(**overrides):
    defaults = {
        "free_sessions_per_week": 3,
        "plus_sessions_per_day": 2,
        "plus_sessions_per_week": 10,
        "quota_reset_days": 7,
    }
    defaults.update(overrides)
    s = MagicMock(spec=Settings)
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


# ---------------------------------------------------------------------------
# Unit tests — get_entitlements
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_free_user_default_entitlements():
    user = _make_user()
    db = AsyncMock()
    settings = _make_settings()
    snap = await get_entitlements(user, db, settings)

    assert snap["subscription_tier"] == "free"
    assert snap["free_sessions_remaining"] == 3
    assert snap["can_start_session_now"] is True
    assert snap["blocking_reason"] is None
    assert snap["wwjd_enabled"] is False


@pytest.mark.asyncio
async def test_free_user_sessions_decrease():
    user = _make_user(free_sessions_used=2)
    db = AsyncMock()
    settings = _make_settings()
    snap = await get_entitlements(user, db, settings)

    assert snap["free_sessions_remaining"] == 1
    assert snap["can_start_session_now"] is True


@pytest.mark.asyncio
async def test_free_user_quota_exceeded():
    user = _make_user(free_sessions_used=3)
    db = AsyncMock()
    settings = _make_settings()
    snap = await get_entitlements(user, db, settings)

    assert snap["free_sessions_remaining"] == 0
    assert snap["can_start_session_now"] is False
    assert snap["blocking_reason"] == "FREE_QUOTA_EXCEEDED"


@pytest.mark.asyncio
async def test_free_user_quota_exceeded_with_credits():
    user = _make_user(free_sessions_used=3, credits_balance=5)
    db = AsyncMock()
    settings = _make_settings()
    snap = await get_entitlements(user, db, settings)

    assert snap["can_start_session_now"] is True
    assert snap["blocking_reason"] is None


@pytest.mark.asyncio
async def test_free_user_window_reset():
    old_start = datetime.now(timezone.utc) - timedelta(days=8)
    user = _make_user(free_sessions_used=3, free_quota_window_start=old_start)
    db = AsyncMock()
    settings = _make_settings()

    snap = await get_entitlements(user, db, settings)

    assert user.free_sessions_used == 0
    assert snap["free_sessions_remaining"] == 3
    assert snap["can_start_session_now"] is True


@pytest.mark.asyncio
async def test_plus_user_wwjd_enabled():
    user = _make_user(subscription_tier="plus", subscription_status="active")
    db = AsyncMock()
    # Mock DB session count queries
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 0
    db.execute = AsyncMock(return_value=mock_result)
    settings = _make_settings()

    snap = await get_entitlements(user, db, settings)

    assert snap["wwjd_enabled"] is True
    assert snap["subscription_tier"] == "plus"


@pytest.mark.asyncio
async def test_plus_user_wwjd_disabled_inactive():
    user = _make_user(subscription_tier="plus", subscription_status="inactive")
    db = AsyncMock()
    settings = _make_settings()
    snap = await get_entitlements(user, db, settings)

    assert snap["wwjd_enabled"] is False


@pytest.mark.asyncio
async def test_assert_can_start_session_raises_402():
    from fastapi import HTTPException

    user = _make_user(free_sessions_used=3)
    db = AsyncMock()
    settings = _make_settings()

    with pytest.raises(HTTPException) as exc_info:
        await assert_can_start_session(user, db, settings)
    assert exc_info.value.status_code == 402
    assert "PAYWALL_REQUIRED" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# Integration tests — endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_entitlements_endpoint(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/v1/entitlements", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "entitlements" in body
    snap = body["entitlements"]
    assert "subscription_tier" in snap
    assert "can_start_session_now" in snap


@pytest.mark.asyncio
async def test_get_entitlements_unauthenticated(client: AsyncClient):
    resp = await client.get("/v1/entitlements")
    assert resp.status_code in (401, 403)
