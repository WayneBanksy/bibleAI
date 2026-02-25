# Work Packet: P1-05 — Analytics Events for Funnel + Monetization (Backend + iOS)

## Goal
Add a minimal analytics event pipeline to measure conversion and usage for:
- paywall impressions and purchase funnel
- credits purchases and redemptions
- WWJD locked → unlock conversion
- quota blocks (402 PAYWALL_REQUIRED)

This enables optimizing $0 → $5k–$10k MRR without guessing.

## Owners
Backend Engineer (event ingestion + storage)
iOS Engineer (event emission hooks)

## Branch / Worktree Names
Backend: agent/backend/P1-05-analytics
iOS:     agent/ios/P1-05-analytics

## Dependencies
- Auth exists (user identity for events).
- P1-01 entitlements endpoint exists (or will exist in sprint).
- P1-03 paywall exists (or will exist in sprint).
- P2-02 locked content exists (for wwjd_locked_shown / wwjd_unlocked events).

## Scope (files allowed to change)
Backend:
- backend/app/models/analytics_event.py (new)
- backend/app/routers/analytics.py (new)
- backend/app/services/analytics.py (new)
- backend/alembic/versions/* (new migration)
- backend/tests/test_analytics.py (new)

iOS:
- ios/** (add AnalyticsClient + hook points)
- ChatViewModel.swift (modify)
- PaywallView.swift / StoreKitManager.swift (modify)
- APIClient.swift (optional: expose a fire-and-forget event method)
- Unit tests optional

Governance:
- governance/TASKS.md (status update only)

## Do Not Touch
- governance/INTERFACES.md / governance/DECISIONS.md
- governance/SAFETY_POLICY.md
- backend/app/crypto.py
- backend/app/citation.py

## Event schema (canonical)
Event JSON sent from iOS to backend:

```json
{
  "event_name": "string",
  "timestamp": "ISO8601",
  "session_id": "uuid|null",
  "properties": { "k": "v" }
}
```

Hard constraints:
- properties MUST NOT contain raw user message text.
- properties MUST NOT contain verse text.
- properties may contain product_id, reason codes, counts, booleans, screen names.

## Required event names (minimum)

### Funnel / Paywall
- paywall_shown
- paywall_cta_tapped
- purchase_started
- purchase_success
- purchase_failed
- restore_started
- restore_success
- restore_failed

### Credits
- credits_pack_viewed
- credits_purchase_success
- credits_redeem_success
- credits_balance_low

### WWJD
- wwjd_toggle_selected
- wwjd_locked_shown
- wwjd_unlock_purchase_started
- wwjd_unlocked

### Quota / errors
- quota_blocked (include blocking_reason)
- sse_stream_error (include retryable)
- api_error (include endpoint + status)

## Backend storage
Create analytics_events table:

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK(users.id) NOT NULL |
| event_name | TEXT | NOT NULL |
| session_id | UUID | NULL |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| properties | JSONB | NOT NULL DEFAULT '{}' |

Indexes:
- (user_id, created_at DESC)
- (event_name, created_at DESC)

## Backend API

### POST /v1/analytics/event
Auth required.
Request: event schema above.
Behavior:
- Validate event_name is in allowlist OR accept any but enforce length <= 64 and prefix rules.
  MVP recommendation: allowlist the required events to avoid garbage.
- Validate properties JSON size <= 8KB.
- Reject if properties contains keys: ["message", "text", "user_message", "raw"] (defensive).
- Persist row.

Response 202 Accepted:
```json
{ "accepted": true }
```

### GET /v1/analytics/summary (dev-only)
For debugging during sprint:
- If ENV=development, allow returning simple counts for last 7 days by event_name.
- If not development: 404.

Response:
```json
{ "window_days": 7, "counts": { "paywall_shown": 12 } }
```

## iOS integration points (must implement)
Hook emissions:
- When PaywallView appears → paywall_shown
- When user taps subscribe button → paywall_cta_tapped + purchase_started
- On StoreKit purchase result → purchase_success / purchase_failed
- On restore → restore_started / restore_success / restore_failed
- When credits pack view shown → credits_pack_viewed
- When credits purchased → credits_purchase_success (product_id)
- When redeem returns 200 → credits_redeem_success (added, new_balance)
- When user selects WWJD toggle → wwjd_toggle_selected
- When locked WWJD bubble rendered → wwjd_locked_shown
- When unlock purchase begins → wwjd_unlock_purchase_started
- When unlock endpoint returns 200 → wwjd_unlocked
- When backend returns 402 PAYWALL_REQUIRED → quota_blocked (blocking_reason)

Implementation requirements:
- Fire-and-forget network call (don't block UI).
- Batch optional; not required.
- If event send fails, ignore (no retries in MVP).

## Tests
Backend:
- accepts valid event in allowlist
- rejects events with forbidden keys in properties
- enforces size limit
- dev-only summary endpoint gated by ENV

Command:
```
uv run pytest tests/test_analytics.py -v
```

## Acceptance Criteria
- [ ] iOS emits required events with correct properties.
- [ ] Backend stores events without leaking sensitive text.
- [ ] Dev summary endpoint helps validate instrumentation during sprint.
- [ ] Tests pass.

## PR Titles
Backend: feat(backend): P1-05 analytics event ingestion + storage
iOS:     feat(ios): P1-05 analytics hooks for paywall, credits, WWJD

## Notes / Risks
- Properties must NEVER contain raw user text or verse content — this is a privacy invariant.
- The allowlist approach prevents garbage event names from polluting the analytics table.
- Fire-and-forget on iOS means some events may be lost on poor connectivity. Acceptable for MVP; batch + retry queue is a post-MVP enhancement.
- Dev summary endpoint must be strictly gated — never expose in production.
