"""
Analytics event service — P1-05.

Allowlisted event ingestion + dev-only summary.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalyticsEvent

ALLOWED_EVENTS: frozenset[str] = frozenset({
    # Funnel / Paywall
    "paywall_shown",
    "paywall_cta_tapped",
    "purchase_started",
    "purchase_success",
    "purchase_failed",
    "restore_started",
    "restore_success",
    "restore_failed",
    # Credits
    "credits_pack_viewed",
    "credits_purchase_success",
    "credits_redeem_success",
    "credits_balance_low",
    # WWJD
    "wwjd_toggle_selected",
    "wwjd_locked_shown",
    "wwjd_unlock_purchase_started",
    "wwjd_unlocked",
    # Quota / errors
    "quota_blocked",
    "sse_stream_error",
    "api_error",
})

FORBIDDEN_PROPERTY_KEYS: frozenset[str] = frozenset({
    "message", "text", "user_message", "raw", "content", "verse_text",
})

MAX_PROPERTIES_SIZE = 8192  # 8 KB


async def record_event(
    user_id: uuid.UUID,
    event_name: str,
    session_id: uuid.UUID | None,
    properties: dict,
    db: AsyncSession,
) -> AnalyticsEvent:
    """Validate and persist an analytics event."""
    if event_name not in ALLOWED_EVENTS:
        raise ValueError(f"Event '{event_name}' not in allowlist")

    if len(json.dumps(properties)) > MAX_PROPERTIES_SIZE:
        raise ValueError("Properties exceed 8KB limit")

    forbidden = FORBIDDEN_PROPERTY_KEYS & set(properties.keys())
    if forbidden:
        raise ValueError(f"Forbidden property keys: {forbidden}")

    event = AnalyticsEvent(
        user_id=user_id,
        event_name=event_name,
        session_id=session_id,
        properties=properties,
    )
    db.add(event)
    await db.flush()
    return event


async def get_summary(db: AsyncSession, window_days: int = 7) -> dict:
    """Get event counts for the last N days. Dev-only."""
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    rows = (
        await db.execute(
            select(AnalyticsEvent.event_name, func.count())
            .where(AnalyticsEvent.created_at >= since)
            .group_by(AnalyticsEvent.event_name)
        )
    ).all()
    return {
        "window_days": window_days,
        "counts": {name: count for name, count in rows},
    }
