# Work Packet: P1-04 — App Store Receipt Verification & Subscription Sync (Backend)

## Goal
Harden premium entitlements so the backend does not trust the client for subscription state.
Implement a receipt/transaction verification path for StoreKit 2 purchases that:
- validates subscription transactions server-side (or via Apple server API where appropriate),
- updates user subscription fields deterministically,
- supports restore/sync from iOS,
- is idempotent and auditable.

This packet is required to prevent entitlement spoofing and to keep subscription status correct over time.

## Owner
Backend Engineer

## Branch / Worktree Name
agent/backend/P1-04-appstore-verify

## Dependencies
- P1-01 entitlements snapshot + subscription fields exist (subscription_tier/status/expires_at).
- Auth exists (user identified via JWT).
- If P1-03 is in progress, coordinate on payload format for verify endpoint (transaction_id, product_id, signed payloads).

## Scope (files allowed to change)
- backend/app/services/iap_verification.py (new)
- backend/app/services/subscription_sync.py (new)
- backend/app/routers/iap.py (new)
- backend/app/models/iap_transaction.py (new)
- backend/app/models/user.py (modify)
- backend/alembic/versions/* (new migration)
- backend/tests/test_iap_verify.py (new)
- backend/tests/test_subscription_sync.py (new)
- governance/TASKS.md (status update only)

## Do Not Touch
- governance/INTERFACES.md / governance/DECISIONS.md (Orchestrator-only)
- governance/SAFETY_POLICY.md
- backend/app/crypto.py
- backend/app/citation.py
- backend/app/pipeline.py / routers/messages.py (unless strictly required to add entitlements snapshot fields)

## Data model

### iap_transactions (new)
Persist verified transactions for audit + idempotency.

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK(users.id) NOT NULL |
| platform | TEXT | NOT NULL DEFAULT 'appstore' |
| transaction_id | TEXT | NOT NULL |
| original_transaction_id | TEXT | NULL |
| product_id | TEXT | NOT NULL |
| product_type | TEXT | NOT NULL # 'subscription' \| 'consumable' |
| signed_transaction_jws | TEXT | NULL |
| signed_renewal_info_jws | TEXT | NULL |
| verified_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| expires_at | TIMESTAMPTZ | NULL # subscriptions only |
| revocation_date | TIMESTAMPTZ | NULL # if provided |
| environment | TEXT | NOT NULL DEFAULT 'Sandbox' # 'Sandbox' \| 'Production' |
| raw_payload | JSONB | NULL # optional; must not include secrets |

Constraints:
- UNIQUE(platform, transaction_id)

### users (ensure fields exist from P1-01; if not, add)
- subscription_tier TEXT NOT NULL DEFAULT 'free'
- subscription_status TEXT NOT NULL DEFAULT 'inactive'  # inactive | active | grace | billing_retry
- subscription_expires_at TIMESTAMPTZ NULL
- subscription_source TEXT NULL DEFAULT 'appstore'

## Verification architecture (pluggable)
Implement interface:

```python
class IAPVerifier:
    async def verify_subscription(self, signed_transaction_jws: str, signed_renewal_info_jws: str | None) -> VerifiedSubscription
    async def verify_consumable(self, signed_transaction_jws: str) -> VerifiedConsumable
```

Provide implementations:
1. **DevStubVerifier** (ENV=development):
   - accepts payloads without cryptographic verification
   - used only for local dev to unblock iOS iteration
2. **ProductionVerifier**:
   Choose ONE of these approaches (preferred first):
   - **A)** Use Apple App Store Server API to fetch transaction info by transaction_id and trust Apple response.
   - **B)** Verify StoreKit 2 signedTransaction JWS using Apple's public keys (JWKS) and validate claims.

MVP recommendation: **A** (server API) because test fixtures for JWS verification are painful.
If A is not feasible in your environment, implement B with JWKS caching.

## API: POST /v1/iap/verify
Purpose: iOS sends StoreKit 2 transaction info after purchase/restore.

Request JSON:
```json
{
  "platform": "appstore",
  "product_type": "subscription | consumable",
  "product_id": "string",
  "transaction_id": "string",
  "original_transaction_id": "string|null",
  "environment": "Sandbox | Production",
  "signed_transaction_jws": "string|null",
  "signed_renewal_info_jws": "string|null"
}
```

Behavior:
- Auth required.
- Idempotent by (platform, transaction_id):
  - If already recorded, return 200 with current entitlements snapshot.
- Verify using verifier service:
  - If verification fails: return 400 INVALID_RECEIPT
- Record into iap_transactions.
- If product_type == subscription:
  - Update user subscription fields:
    - subscription_source='appstore'
    - subscription_tier='plus'
    - subscription_status='active' (or map to grace/billing_retry if verifier provides)
    - subscription_expires_at set from verified expires_at
  - Return entitlements snapshot (P1-01)
- If product_type == consumable:
  - Do NOT add credits here (P1-02 redeem endpoint remains canonical).
  - Return 200 OK with entitlements snapshot (credits handled separately).

Response 200:
```json
{
  "entitlements": "<P1-01 snapshot>",
  "verified": true
}
```

Response 400:
```json
{
  "error": { "code": "INVALID_RECEIPT", "message": "Receipt/transaction verification failed." }
}
```

## API: POST /v1/iap/sync
Purpose: called on app launch / restore purchases; iOS provides latest subscription transaction and server re-validates.
Request: same shape as /verify (subscription only).
Response: entitlements snapshot.

## Subscription expiry enforcement
In entitlements service (or sync service), ensure:
- If now > subscription_expires_at and no grace: set subscription_status='inactive' and tier='free' on read (or via periodic sync).
This prevents stale "plus" state.

## Logging & privacy constraints
- Never log full signed JWS.
- Do not store raw user chat content in iap payload tables.
- Only store minimal fields for audit.

## Tests
Add tests that:
- /verify is idempotent for same transaction_id
- invalid payload returns 400
- subscription verify updates user tier/status/expires_at and entitlements reflects wwjd_enabled true
- sync downgrades when expired (simulate now > expires_at)
Use DevStubVerifier in tests (mock verifier) — do not call Apple services in unit tests.

Commands:
```
uv run pytest tests/test_iap_verify.py -v
uv run pytest tests/test_subscription_sync.py -v
```

## Acceptance Criteria
- [ ] Backend no longer relies purely on client-side subscription state.
- [ ] Verified subscription updates entitlements deterministically.
- [ ] Restore/sync works (no double writes, no downgrades when active).
- [ ] Tests pass.

## PR Title
feat(backend): P1-04 App Store transaction verification + subscription sync

## Notes / Risks
- DevStubVerifier must NEVER be active in production. Gate behind ENV check with a loud startup warning.
- Apple's App Store Server API requires an API key + issuer ID + key ID — these must be provisioned before production verification works.
- JWS signed payloads from StoreKit 2 differ from legacy receipt data — do not mix StoreKit 1 and 2 flows.
- Subscription expiry enforcement on read is acceptable for MVP; a periodic background sync job is a post-MVP enhancement.
