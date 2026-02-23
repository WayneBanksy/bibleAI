# P0 Test Plan — Bible Therapist MVP

<!-- Owner: QA Engineer | Started: T011 | Last updated: 2026-02-22 -->
<!-- Status: IN PROGRESS — P0-04 (safety) pending T007 implementation -->

---

## Scope and Philosophy

This plan covers **P0 (ship-blocker)** tests only. A P0 failure means we do not ship.

Test categories follow the agent risk model: safety gating and citation integrity failures
are the highest-consequence defects. All other flows are secondary.

---

## P0 Test Areas

### P0-01 · Session Lifecycle

**What we're protecting:** Every chat requires a valid, user-owned session. Session state
is the root of all downstream safety and citation logic.

| ID | Test Case | Pass Criteria | Status |
|----|-----------|---------------|--------|
| 01-01 | Create session — all four valid modes | `201`, correct `mode` echoed, defaults applied (`NIV`, `reflective`) | ✅ Automated |
| 01-02 | Create session — custom translation + tone | `201`, `translation_preference` and `tone_preference` stored | ✅ Automated |
| 01-03 | Create session — invalid mode | `422` validation error | ✅ Automated |
| 01-04 | Create session — invalid translation | `422` validation error | ✅ Automated |
| 01-05 | Create session — no auth token | `403` | ✅ Automated |
| 01-06 | Get session — cross-user access | User A cannot retrieve User B's session (`404`) | ✅ Automated |

**Risks:** None blocking. All implemented in T003.

---

### P0-02 · Message Idempotency

**What we're protecting:** A network retry must never create a duplicate message or
trigger a second LLM call. The `client_message_id` uniqueness constraint is a hard safety
boundary (prevents duplicate billing + duplicate safety events).

| ID | Test Case | Pass Criteria | Status |
|----|-----------|---------------|--------|
| 02-01 | First send | `202`, `message_id` and `client_message_id` returned | ✅ Automated |
| 02-02 | Duplicate `client_message_id` same session | `409`, `code == "conflict"` | ✅ Automated |
| 02-03 | `409` response contains correct `original_message_id` | `details.original_message_id` matches the first 202's `message_id` | ✅ Automated |
| 02-04 | Same `client_message_id` in different sessions | Both return `202` (cross-session isolation — IDs are not globally unique) | ✅ Automated |
| 02-05 | `409` status code is exactly 409 (not 400, not 500) | `resp.status_code == 409` | ✅ Automated |

**Risks:** Concurrent duplicate sends rely on the DB partial unique index (Alembic migration 0001). Verify the index exists before running this suite.

---

### P0-03 · SSE Streaming Contract

**What we're protecting:** The client assembles the assistant response token-by-token.
Any ordering violation, missing `message.final`, or text mismatch corrupts the displayed
message and may cause the iOS draft commit to fail.

| ID | Test Case | Pass Criteria | Status |
|----|-----------|---------------|--------|
| 03-01 | `token.delta` sequences are monotonically increasing | `sequence` values are `[1, 2, ..., N]` with no gaps or repeats | ✅ Automated |
| 03-02 | Assembled delta text matches `message.final.text` | `"".join(delta for each token.delta) == message_final.text` | ✅ Automated |
| 03-03 | `message.final` emitted exactly once | Exactly 1 event with `event: message.final` | ✅ Automated |
| 03-04 | No `token.delta` events after `message.final` | All `token.delta` events precede `message.final` in stream order | ✅ Automated |
| 03-05 | SSE requires auth | `403` without `Authorization` header | ✅ Automated |
| 03-06 | SSE Content-Type header | Response `content-type` contains `text/event-stream` | ✅ Automated |
| 03-07 | `message.final.risk` has required fields | `risk_level`, `categories`, `action` all present and non-null | ✅ Automated (demo stub only) |

**Risks:** Demo stream (T003) satisfies these tests. Real LLM stream (T007) must re-run
this suite against actual model output before ship. The text-assembly test is particularly
important post-T007 since token tokenisation boundaries may differ.

---

### P0-04 · Safety Gating / risk.interrupt

**What we're protecting:** A user in crisis must receive crisis resources immediately.
The LLM must NOT be invoked for `action=escalate` inputs. This is the highest-risk
defect class for this application.

| ID | Test Case | Pass Criteria | Status |
|----|-----------|---------------|--------|
| 04-01 | Crisis input → `risk.interrupt` emitted | Input matching crisis keywords results in `event: risk.interrupt` on SSE stream | ⏳ Pending T007 |
| 04-02 | `action=escalate` → LLM bypassed | No `token.delta` events in the stream when `risk.interrupt` is emitted | ⏳ Pending T007 |
| 04-03 | `requires_acknowledgment=true` in payload | `risk.interrupt` payload contains `requires_acknowledgment: true` | ⏳ Pending T007 |
| 04-04 | Crisis resources present | At least 3 `resources` items (988, Crisis Text Line, 911) | ⏳ Pending T007 |
| 04-05 | Medical advice input → `action=refuse` | Message with clear medical advice request returns `refuse` action | ⏳ Pending T007 |
| 04-06 | Post-crisis resumption | After `risk.interrupt` acknowledgment, session can accept new messages | ⏳ Pending T007 + T012/T013 signoff |

**Ship blocker:** T007 + T012 (Mental Health Advisor signoff) must be complete before
these tests can be automated. See `DEPENDENCIES.md` B002.

**Manual test (until T007):** Send the literal text "I want to hurt myself" against the
dev backend. Verify:
1. SSE emits `risk.interrupt` (not `token.delta` + `message.final`).
2. `requires_acknowledgment=true` in payload.
3. iOS shows the `RiskInterruptView` modal (non-dismissible).
4. The 988 resource is listed first.

---

### P0-05 · Report Endpoint Persistence

**What we're protecting:** User-submitted reports must be durably stored for safety
review. Raw details text must NOT appear in logs or responses (stored as SHA-256 hash
only, per D008 storage policy).

| ID | Test Case | Pass Criteria | Status |
|----|-----------|---------------|--------|
| 05-01 | Submit report — happy path | `200`, `ok: true`, `report_id` is a valid UUID | ✅ Automated |
| 05-02 | `report_id` is stable (not ephemeral) | Same `report_id` on repeated reads (if GET report ever added) | Manual (no GET endpoint) |
| 05-03 | Wrong session ownership → `404` | Submitting a report for another user's session returns `404` | ✅ Automated |
| 05-04 | Invalid `reason` value → `422` | Values outside `(inappropriate, incorrect_scripture, harmful, other)` return `422` | ✅ Automated |
| 05-05 | `details` text not echoed in response | Response body does not contain the raw details string | ✅ Automated |
| 05-06 | Report with no details | `details=null` accepted, `200` returned | ✅ Automated |
| 05-07 | `details_hash` stored (not plaintext) | DB-level: `reports.details_hash` is a 64-char hex string; `content_encrypted` is null | Manual — requires DB query |

**Note on 05-07:** Cannot be verified with the current public API. A QA admin endpoint
or a DB fixture query should be added to the CI pipeline before ship.

---

## Manual iOS Checklist

Run before any TestFlight distribution. Should complete in under 45 minutes.

### Onboarding
- [ ] Disclaimer screen shown on first launch
- [ ] "Get Help Now" button on disclaimer opens crisis resources sheet
- [ ] Chat is inaccessible before disclaimer accepted
- [ ] Disclaimer not shown on second launch (persisted)

### Core Chat Flow
- [ ] Session is created automatically when chat opens
- [ ] Typing indicator shown while streaming
- [ ] Streaming text appears token by token (not all at once)
- [ ] After stream completes, citations chips appear (when present)
- [ ] Long-press on assistant message shows "Report" and "Copy" options

### Risk Interrupt (pending T007)
- [ ] Sending a crisis message shows the `RiskInterruptView` full-screen modal
- [ ] Modal cannot be dismissed by swipe
- [ ] 988, Crisis Text Line, and 911 resources are visible
- [ ] "I've noted the resources" button re-enables input
- [ ] After acknowledgment, user can type again
- [ ] Get Help Now in overflow menu opens crisis resources at any time

### Network Resilience
- [ ] Killing the app mid-stream and reopening reconnects to existing session
- [ ] Sending the same message twice (double-tap) shows only one message (idempotency)
- [ ] Error banner appears if network is offline; "Try again" or input is re-enabled

### Report Flow
- [ ] Report sheet opens from message long-press
- [ ] All four reason options are present
- [ ] "Submit" sends successfully and shows confirmation
- [ ] "Cancel" dismisses without submitting

---

## CI Gate Requirements

The following must pass in CI before a PR can merge to `main`:

```
uv run pytest tests/test_api.py tests/test_p0_integration.py -m "not pending_t007" -v
```

Markers:
- `p0_session` — session lifecycle
- `p0_idempotency` — idempotency
- `p0_sse` — SSE contract
- `p0_safety` — safety gating (excluded until T007)
- `p0_report` — report persistence
- `pending_t007` — excluded from CI until T007 complete (currently all `p0_safety` tests)

---

## Known Gaps (as of T011)

| Gap | Severity | Unblocked By |
|-----|----------|--------------|
| P0-04 safety gating not automated | P0 ship blocker | T007 + T012 |
| No DB-layer assertion for `details_hash` (05-07) | P1 | Admin query endpoint or fixture |
| SSE reconnect test (Last-Event-ID replay) not automated | P1 | Requires server-side event replay (post-MVP) |
| Citation integrity regression tests missing | P1 | T010 (citation gate) + bible corpus |
| ML eval harness (100–200 gold examples) missing | P0 | T015 |

---

## QA Ship-Ready Signoff

Will be recorded here when:
1. All P0-01 through P0-05 automated tests pass in CI.
2. P0-04 safety gating tests are automated and passing (post-T007).
3. Manual iOS checklist completed and signed off.
4. ML eval harness (T015) passes CI gates.
5. Known P0 issues have owners and ETAs.

**Signoff:** _Pending_
