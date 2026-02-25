# Work Packet: P1-01 — Subscription & Entitlements (Backend)

## Goal
Implement server-side entitlements that unify:
- free-tier session quota
- subscription tier access (Plus)
- WWJD entitlement flag (derived from subscription tier)
- credit balance (from P1-02)

Expose a single "entitlement snapshot" the iOS app can rely on for gating UI and requests.

## Owner
Backend Engineer

## Branch / Worktree Name
agent/backend/P1-01-subscription-entitlements

## Dependencies
- Auth must exist and provide user identity (user_id from JWT).
- DB migrations (Alembic) working.
- P1-02 adds credits_balance + ledger; this WP must integrate cleanly but can proceed with credits_balance default 0.

## Scope (files allowed to change)
- backend/app/models/user.py (or equivalent)
- backend/app/services/entitlements.py (new)
- backend/app/routers/entitlements.py (new)
- backend/app/routers/auth.py (modify only as needed)
- backend/app/routers/sessions.py (modify only for returning entitlements)
- backend/app/routers/messages.py (modify only for returning entitlements)
- backend/alembic/versions/* (new migrations)
- backend/tests/test_entitlements.py (new)
- governance/TASKS.md (status line update only)

## Do Not Touch
- governance/INTERFACES.md (Orchestrator-only)
- governance/DECISIONS.md (Orchestrator-only)
- governance/SAFETY_POLICY.md
- backend/app/citation.py
- backend/app/crypto.py

## Data model
Add to users table:
- subscription_tier TEXT NOT NULL DEFAULT 'free'  # 'free' | 'plus'
- subscription_source TEXT NULL                   # 'appstore'
- subscription_status TEXT NOT NULL DEFAULT 'inactive'  # 'inactive' | 'active' | 'grace' | 'billing_retry'
- subscription_expires_at TIMESTAMPTZ NULL
- free_quota_window_start TIMESTAMPTZ NOT NULL DEFAULT now()
- free_sessions_used INT NOT NULL DEFAULT 0

Notes:
- quota resets weekly for free users: 7-day rolling window based on free_quota_window_start.
- Plus users have higher limits (see "Limits").

## Limits (must be configurable)
Read from environment (with defaults):
- FREE_SESSIONS_PER_WEEK=3
- PLUS_SESSIONS_PER_DAY=2
- PLUS_SESSIONS_PER_WEEK=10
- QUOTA_RESET_DAYS=7

Define logic:
- free tier: max FREE_SESSIONS_PER_WEEK within rolling 7-day window
- plus tier: enforce PLUS_SESSIONS_PER_DAY and/or PLUS_SESSIONS_PER_WEEK (both apply; whichever hits first blocks)

Tracking fields:
- For MVP, implement plus usage using existing sessions table counts in time windows
  - sessions created "today" (local day boundary UTC is acceptable for MVP)
  - sessions created in last 7 days
If sessions table is not available for querying, add:
- plus_quota_window_start, plus_sessions_used (optional)
Prefer query-based approach for simplicity.

## Entitlement snapshot (canonical server response object)
Implement in backend/app/services/entitlements.py:

get_entitlements(user, now) -> dict:
```json
{
  "subscription_tier": "free | plus",
  "subscription_status": "inactive | active | grace | billing_retry",
  "subscription_expires_at": "ISO8601|null",
  "wwjd_enabled": true,
  "credits_balance": 0,
  "free_sessions_remaining": 2,
  "plus_sessions_remaining_today": null,
  "plus_sessions_remaining_week": null,
  "can_start_session_now": true,
  "next_reset_at": "ISO8601",
  "blocking_reason": null
}
```

blocking_reason values: `"FREE_QUOTA_EXCEEDED"` | `"PLUS_DAILY_QUOTA_EXCEEDED"` | `"PLUS_WEEKLY_QUOTA_EXCEEDED"` | `null`

wwjd_enabled: `true` if tier == plus AND status in (active, grace)

## API: New endpoint
### GET /v1/entitlements
Returns:
```json
{
  "entitlements": "<snapshot>"
}
```

Auth required.

## API: Sessions/Messages must include entitlements snapshot
- POST /v1/sessions response includes entitlements
- POST /v1/sessions/{id}/messages response includes entitlements

This prevents extra entitlements calls for UI refresh.

## Enforcement points
This WP does NOT implement credits consumption (P1-02 does).
But it MUST implement quota enforcement helpers used by messages/session creation:
- assert_can_start_session(user, now) -> either ok or raise structured error with 402

Structured error (HTTP 402):
```json
{
  "error": {
    "code": "PAYWALL_REQUIRED",
    "reason": "<blocking_reason>",
    "message": "Upgrade or use credits to continue.",
    "entitlements": "<snapshot>"
  }
}
```

## Tests
backend/tests/test_entitlements.py must cover:
- free user remaining sessions decreases as free_sessions_used increases
- window reset: if now > window_start + 7 days -> resets used to 0 and moves window_start
- plus user: wwjd_enabled true when active and not expired
- plus user: blocking_reason set appropriately when daily/weekly limits exceeded (query sessions or stub)
- GET /v1/entitlements returns snapshot

Test command:
```
uv run pytest tests/test_entitlements.py -v
```

## Acceptance Criteria
- [ ] Entitlements snapshot is stable and returned consistently.
- [ ] Free tier quota + reset works deterministically.
- [ ] Subscription tier derived WWJD entitlement is correct.
- [ ] API returns 402 with machine-readable reason when blocked.

## PR Title
feat(backend): P1-01 entitlements snapshot + quota enforcement + /v1/entitlements

## Notes / Risks
- credits_balance will be 0 until P1-02 is integrated. Do not block on it.
- Plus subscription fields will be populated by P1-04 (receipt verification). Until then, only manual/test updates.
