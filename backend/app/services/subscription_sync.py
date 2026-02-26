"""
Subscription sync service — P1-04.

Deterministic updates to user subscription fields based on verified IAP data.
Handles expiry enforcement on read (MVP approach).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.models import User


def sync_subscription_from_transaction(
    user: User,
    expires_at: datetime | None,
    revocation_date: datetime | None = None,
) -> None:
    """
    Update user subscription fields from a verified transaction.

    Must be called within a transaction with the user row locked (SELECT FOR UPDATE).
    """
    now = datetime.now(timezone.utc)

    if revocation_date is not None:
        # Subscription was revoked
        user.subscription_tier = "free"
        user.subscription_status = "inactive"
        user.subscription_expires_at = None
        user.subscription_source = None
        return

    user.subscription_source = "appstore"
    user.subscription_tier = "plus"
    user.subscription_expires_at = expires_at

    if expires_at is not None and expires_at > now:
        user.subscription_status = "active"
    else:
        user.subscription_status = "inactive"
        user.subscription_tier = "free"


def enforce_subscription_expiry(user: User) -> bool:
    """
    Check if the user's subscription has expired and downgrade if needed.

    Called on read (entitlements check, sync). Returns True if downgraded.
    This is the MVP approach; a periodic background job is post-MVP.
    """
    if user.subscription_tier != "plus":
        return False

    if user.subscription_status not in ("active", "grace"):
        return False

    now = datetime.now(timezone.utc)

    if user.subscription_expires_at is None:
        return False

    if user.subscription_expires_at <= now:
        user.subscription_tier = "free"
        user.subscription_status = "inactive"
        return True

    return False
