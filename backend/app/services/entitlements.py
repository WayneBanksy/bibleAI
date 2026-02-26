"""
Entitlements snapshot service — P1-01.

Canonical source of truth for subscription tier, quota, and session-start gating.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import Session as SessionModel
from app.models import User


async def get_entitlements(
    user: User,
    db: AsyncSession,
    settings: Settings,
    now: datetime | None = None,
) -> dict:
    """Build the canonical entitlement snapshot."""
    now = now or datetime.now(timezone.utc)

    # Reset free-tier window if expired
    window_age = now - user.free_quota_window_start
    if window_age >= timedelta(days=settings.quota_reset_days):
        user.free_quota_window_start = now
        user.free_sessions_used = 0

    tier = user.subscription_tier
    status = user.subscription_status
    is_plus_active = tier == "plus" and status in ("active", "grace")

    # Plus quota from DB session counts
    plus_today: int | None = None
    plus_week: int | None = None
    if is_plus_active:
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)

        plus_today_count = (
            await db.execute(
                select(func.count())
                .select_from(SessionModel)
                .where(SessionModel.user_id == user.id, SessionModel.started_at >= today_start)
            )
        ).scalar_one()

        plus_week_count = (
            await db.execute(
                select(func.count())
                .select_from(SessionModel)
                .where(SessionModel.user_id == user.id, SessionModel.started_at >= week_start)
            )
        ).scalar_one()

        plus_today = max(0, settings.plus_sessions_per_day - plus_today_count)
        plus_week = max(0, settings.plus_sessions_per_week - plus_week_count)

    # Blocking reason
    blocking_reason: str | None = None
    can_start = True

    if is_plus_active:
        if plus_today == 0:
            blocking_reason = "PLUS_DAILY_QUOTA_EXCEEDED"
            can_start = False
        elif plus_week == 0:
            blocking_reason = "PLUS_WEEKLY_QUOTA_EXCEEDED"
            can_start = False
    else:
        free_remaining = max(0, settings.free_sessions_per_week - user.free_sessions_used)
        if free_remaining == 0:
            if user.credits_balance > 0:
                can_start = True
            else:
                blocking_reason = "FREE_QUOTA_EXCEEDED"
                can_start = False

    free_remaining_val = (
        max(0, settings.free_sessions_per_week - user.free_sessions_used)
        if not is_plus_active
        else None
    )
    next_reset = (
        (user.free_quota_window_start + timedelta(days=settings.quota_reset_days)).isoformat()
        if not is_plus_active
        else None
    )

    return {
        "subscription_tier": tier,
        "subscription_status": status,
        "subscription_expires_at": (
            user.subscription_expires_at.isoformat() if user.subscription_expires_at else None
        ),
        "wwjd_enabled": is_plus_active,
        "credits_balance": user.credits_balance,
        "free_sessions_remaining": free_remaining_val,
        "plus_sessions_remaining_today": plus_today,
        "plus_sessions_remaining_week": plus_week,
        "can_start_session_now": can_start,
        "next_reset_at": next_reset,
        "blocking_reason": blocking_reason,
    }


async def assert_can_start_session(
    user: User,
    db: AsyncSession,
    settings: Settings,
) -> dict:
    """Check quota and raise HTTP 402 if blocked. Returns entitlements snapshot."""
    snapshot = await get_entitlements(user, db, settings)
    if not snapshot["can_start_session_now"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": {
                    "code": "PAYWALL_REQUIRED",
                    "reason": snapshot["blocking_reason"],
                    "message": "Upgrade or use credits to continue.",
                    "entitlements": snapshot,
                }
            },
        )
    return snapshot
