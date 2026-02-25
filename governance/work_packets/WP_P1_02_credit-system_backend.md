# Work Packet: P1-02 — Credit System (Backend)

## Goal
Implement consumable credits to fund LLM sessions for:
- free users who exceed free quota
- plus users who exceed plus quota (optional behavior; enabled by default)
Credits must be auditable and idempotent on purchase redemption.

## Owner
Backend Engineer

## Branch / Worktree Name
agent/backend/P1-02-credits

## Dependencies
- P1-01 entitlements snapshot exists OR this WP must implement a minimal entitlements getter to include credits_balance.
- Auth must exist.
- No real receipt validation required in this WP (P1-03/P1-04 cover it), but redeem must be idempotent.

## Scope (files allowed to change)
- backend/app/models/user.py (or equivalent)
- backend/app/models/credit_ledger.py (new)
- backend/app/services/credits.py (new)
- backend/app/routers/credits.py (new)
- backend/app/routers/messages.py (modify only for consumption hook)
- backend/alembic/versions/* (new migration)
- backend/tests/test_credits.py (new)
- governance/TASKS.md (status line update only)

## Do Not Touch
- governance/INTERFACES.md, governance/DECISIONS.md (Orchestrator-only)
- backend/app/crypto.py
- backend/app/citation.py
- backend/app/safety.py

## Data model
### users
- credits_balance INT NOT NULL DEFAULT 0

### credit_ledger (new)
Columns:
- id UUID PK
- user_id UUID FK(users.id) NOT NULL
- delta INT NOT NULL
- reason TEXT NOT NULL  # 'iap_redeem' | 'session_consume' | 'admin_adjust'
- idempotency_key TEXT NULL
- product_id TEXT NULL
- related_session_id UUID NULL
- created_at TIMESTAMPTZ NOT NULL DEFAULT now()

Constraints:
- UNIQUE(user_id, idempotency_key) WHERE idempotency_key IS NOT NULL

## Products mapping (server-side)
Define mapping in code/config:
- credits_5  -> 5
- credits_10 -> 10
- credits_30 -> 30
- credits_50 -> 50

## API: POST /v1/credits/redeem
Request:
```json
{
  "idempotency_key": "string",
  "product_id": "credits_10",
  "purchase_token": "string",
  "purchased_at": "ISO8601"
}
```

Behavior:
- Auth required.
- Validate product_id is allowed.
- Quantity inferred from product_id (do not trust client quantity).
- Insert ledger row with idempotency_key; if unique violation:
  - return 409 with current balance, added=0
- Otherwise:
  - user.credits_balance += quantity
  - commit
  - return 200 with added=quantity and new balance

Responses:

200:
```json
{ "credits_balance": 27, "added": 10 }
```

409:
```json
{ "credits_balance": 27, "added": 0 }
```

400:
```json
{ "error": { "code": "INVALID_PURCHASE", "message": "..." } }
```

## Credit consumption hook
In the LLM-backed message flow (messages router/pipeline call site), implement:

consume_credit_if_needed(user, session_id) -> bool consumed

Rule:
- If user has credits_balance > 0:
  - decrement by 1 (atomic transaction)
  - insert ledger delta=-1 reason='session_consume' related_session_id=session_id
  - return true
- If credits_balance == 0:
  - return false (caller enforces quota via entitlements)

Concurrency:
- Must be safe under two simultaneous requests.
- Use SELECT ... FOR UPDATE on user row or an atomic UPDATE with check.

## Responses include entitlements snapshot
If entitlements service exists (P1-01), include updated credits_balance in snapshot in relevant responses.

## Tests
backend/tests/test_credits.py:
- redeem adds correct quantity for product_id
- redeem idempotency returns 409 and does not double-add
- consume decrements and creates ledger entry
- concurrent consume simulation: second call fails to consume when balance was 1
- invalid product_id returns 400

Test command:
```
uv run pytest tests/test_credits.py -v
```

## Acceptance Criteria
- [ ] Credits redeem is idempotent and auditable.
- [ ] Credit consumption is atomic and consistent.
- [ ] API returns correct balances after redeem/consume.

## PR Title
feat(backend): P1-02 credits redeem + ledger + atomic consumption

## Notes / Risks
- Concurrent consumption must use row-level locking (SELECT FOR UPDATE or atomic UPDATE ... WHERE credits_balance > 0).
- Product mapping is server-authoritative; never trust client-supplied quantity.
- Real receipt validation is out of scope (P1-04 handles it).
