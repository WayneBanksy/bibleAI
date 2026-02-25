# Work Packet: P2-02 — WWJD Entitlement Gate (Backend)

## Goal
Enforce that WWJD mode is premium (Plus subscription).
If a user requests WWJD without entitlement:
- Do NOT return the full WWJD content in plaintext response fields.
- Return a locked response with a blurred preview mechanism.
- Provide a path to unlock after subscription purchase.

## Owner
Backend Engineer

## Branch / Worktree Name
agent/backend/P2-02-wwjd-gate

## Dependencies
- P1-01 entitlements provides wwjd_enabled boolean.
- P2-01 defines WWJD structured output.
- Orchestrator updates INTERFACES.md for locked response fields if not already present.

## Scope (files allowed to change)
- backend/app/services/entitlements.py (use)
- backend/app/services/wwjd_lock.py (new)
- backend/app/models/locked_content.py (new)
- backend/app/routers/messages.py (modify)
- backend/app/routers/locked_content.py (new)
- backend/alembic/versions/* (new migration)
- backend/tests/test_wwjd_lock.py (new)
- governance/TASKS.md (status line update only)

## Do Not Touch
- governance/INTERFACES.md, governance/DECISIONS.md (Orchestrator-only)
- backend/app/citation.py
- backend/app/crypto.py
- crisis template content (B002)

## Data model
Create locked_content table:
- id UUID PK
- user_id UUID FK(users.id) NOT NULL
- session_id UUID NULL
- mode TEXT NOT NULL  # 'wwjd'
- preview_text TEXT NOT NULL  # short excerpt only
- payload_encrypted BYTEA NOT NULL  # encrypt full JSON output (use existing crypto if available; else use server key)
- created_at TIMESTAMPTZ NOT NULL DEFAULT now()
- expires_at TIMESTAMPTZ NOT NULL  # e.g., now + 24h

## Locked response behavior
When request.mode == "wwjd":
- If entitlements.wwjd_enabled == true:
  - proceed normally, return full WWJD response
- Else:
  1. Generate WWJD output (server-side) to ensure preview is legitimate.
  2. Store full output encrypted in locked_content.
  3. Return a "locked" message.final payload that contains:
     - locked=true
     - locked_content_id
     - preview_text (e.g., first 80–120 chars)
     - paywall_reason="WWJD_PREMIUM"

  IMPORTANT: Do not include full action_steps or full reflection in any plaintext field.

## API: New endpoint to unlock content
### GET /v1/locked/{locked_content_id}
Auth required. Behavior:
- If user not entitled (wwjd_enabled false): return 402 with paywall error.
- If user entitled: decrypt and return full payload (the WWJD JSON).

Response 200:
```json
{ "payload": "<full WWJD structured JSON>" }
```

Response 404 if not found or not owned by user.
Response 410 if expired.

## INTERFACES CHANGE REQUEST (Orchestrator)
If schemas don't exist, Orchestrator must update INTERFACES.md:
- message.final payload add:
  - mode
  - locked (bool)
  - locked_content_id (nullable)
  - preview_text (nullable)
  - paywall_reason (nullable)

## Tests
backend/tests/test_wwjd_lock.py:
- non-entitled user requesting wwjd:
  - response locked=true
  - response contains preview_text but NOT full content
  - locked_content row exists
- entitled user requesting wwjd:
  - locked=false
  - full output returned
- unlock endpoint:
  - 402 if not entitled
  - 200 returns decrypted payload if entitled
  - 404 for wrong user
  - 410 for expired

Command:
```
uv run pytest tests/test_wwjd_lock.py -v
```

## Acceptance Criteria
- [ ] WWJD output never leaks in plaintext when locked.
- [ ] Unlock flow works immediately after subscription purchase.
- [ ] Locked content expires and is cleaned up safely (TTL optional for MVP).

## PR Title
feat(backend): P2-02 WWJD premium gate + locked content unlock endpoint

## Notes / Risks
- Full WWJD content must NEVER appear in any plaintext response field when locked. Only preview_text (80–120 chars) is exposed.
- Encryption of payload should reuse existing crypto module (T016) if available; otherwise use a server-level symmetric key.
- Expiry cleanup can be a scheduled task or lazy deletion on access — lazy is acceptable for MVP.
- The generate-then-lock pattern means the LLM call still happens for non-entitled users. This is intentional to provide a real preview, but has cost implications to monitor.
