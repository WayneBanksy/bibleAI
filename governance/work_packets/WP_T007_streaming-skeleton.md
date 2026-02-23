# Work Packet: T007 — Backend Streaming Skeleton

## Goal

Wire the real message-processing pipeline end-to-end in the backend, replacing the
`publish_demo_stream` stub. The pipeline must implement the full execution path defined
in INTERFACES.md and SAFETY_POLICY.md — including the deterministic crisis bypass — but
with stubs in place of the real LLM call and the real ML safety classifier. Citation
validation is delegated to `app/citation.py` (T010); this packet calls it but does not
implement it (stub fallback only).

**B002 compliance:** The `risk.interrupt` message text MUST use
`CRISIS_TEMPLATE_PLACEHOLDER` (see §below). The crisis mechanics (LLM bypass, SSE event
emission, `requires_acknowledgment=true`, resource list) must be fully implemented.
Only the human-reviewed copy is blocked pending T012.

## Owner

Backend Engineer

## Branch / Worktree Name

`agent/backend/T007-streaming-skeleton`

## Scope (files allowed to change)

```
backend/app/
  pipeline.py          # NEW — orchestrates: pre_check → llm_stub → post_check → citation_stub → emit
  safety.py            # NEW — SafetyClassifier stub (keyword-based for dev; real ML deferred to T015)
  streaming.py         # MODIFY — replace publish_demo_stream with publish_real_stream; keep _sse helper
  routers/messages.py  # MODIFY — call pipeline.run() instead of publish_demo_stream

backend/tests/
  test_streaming.py    # NEW — unit + integration tests for the pipeline
```

## Do Not Touch

- `governance/INTERFACES.md`
- `governance/DECISIONS.md`
- `governance/SAFETY_POLICY.md`
- `governance/TASKS.md`
- `governance/DEPENDENCIES.md`
- `backend/app/citation.py`  (T010 owns this file)
- Any file under `/ios/`

## Dependencies

- T003 backend scaffold — Done ✅ (DB, models, routers, schemas in place)
- INTERFACES.md §5 SSE event schemas — LOCKED ✅
- INTERFACES.md §7 LLM structured output schema — LOCKED ✅
- INTERFACES.md §8 SafetyCheckResult schema — LOCKED ✅
- SAFETY_POLICY.md §1 action mapping table — LOCKED ✅
- SAFETY_POLICY.md §2 deterministic bypass requirements — LOCKED ✅
- **B002 (open):** Crisis template v1 text is a PLACEHOLDER in this packet. T012 (Mental Health Advisor signoff) must be resolved before ship-ready label. See compliance note below.
- **T010 (parallel):** `citation.py` is created by T010. This packet uses a stub fallback (`_citation_stub`) if the module is not yet merged.

## B002 Compliance — Crisis Template Placeholder

```python
# backend/app/pipeline.py

# ⚠️ PLACEHOLDER — DO NOT SHIP without T012 (Mental Health Advisor) signoff.
# Replace with reviewed copy from SAFETY_POLICY.md §2.3 after T012 is resolved.
CRISIS_TEMPLATE_PLACEHOLDER = (
    "[CRISIS RESPONSE COPY PENDING CLINICAL REVIEW — T012 REQUIRED BEFORE SHIP]"
)

CRISIS_RESOURCES = [
    {"label": "988 Suicide & Crisis Lifeline", "contact": "Call or text 988"},
    {"label": "Crisis Text Line", "contact": "Text HOME to 741741"},
    {"label": "Emergency Services", "contact": "Call 911"},
]
```

The `risk.interrupt` event MUST be emitted with this placeholder and the `CRISIS_RESOURCES`
list. The structure must be exactly as defined in INTERFACES.md §5 (`risk.interrupt`).

## Pipeline Contract

`pipeline.py` must implement the following stages **in order**:

```
1. pre_check(text: str) → SafetyCheckResult
   - If action == "escalate":
       → emit risk.interrupt (with CRISIS_TEMPLATE_PLACEHOLDER)
       → log safety_event (check_stage="pre", action="escalate")
       → RETURN immediately — do NOT invoke LLM
   - If action == "refuse":
       → emit stream.error(code="refused", message="...", retryable=False)
       → log safety_event
       → RETURN
   - If action in ("allow", "caution"):
       → continue to step 2

2. llm_stub(text: str, context: dict) → LLMRawOutput
   - Stub: return a hard-coded valid JSON response (matches INTERFACES.md §7.1 schema)
   - Real LLM call deferred to post-T007 (will replace this stub)

3. validate_llm_output(raw: str) → dict
   - Parse JSON; if invalid, emit stream.error and return
   - Validate against §7.1 schema (reflection required, etc.)

4. citation_gate(verse_block: list, db: AsyncSession) → list[CitationResult]
   - Try: from app.citation import validate_citations; return await validate_citations(...)
   - Except ImportError: fallback to _citation_stub() which returns all citations stripped
   - Log citation_integrity safety_event for any stripped citation

5. post_check(reflection: str) → SafetyCheckResult
   - Runs on the LLM-generated reflection text
   - If action in ("refuse", "escalate"): emit risk.interrupt or stream.error; return
   - Otherwise: continue

6. emit_stream(message_id, session_id, full_text, structured, citations, risk)
   - Emit token.delta events (split full_text into ~word chunks)
   - Emit message.final with all fields per INTERFACES.md §5
```

## Acceptance Criteria

- [ ] `POST /v1/sessions/{id}/messages` triggers the real pipeline (not the demo stub).
- [ ] **CRITICAL:** When pre_check returns `action=escalate`, the LLM is NOT called. The SSE channel emits exactly one `risk.interrupt` event; no `token.delta` or `message.final` events follow.
- [ ] `risk.interrupt` payload matches INTERFACES.md §5 schema: `risk_level`, `action`, `categories`, `message` (placeholder text), `resources` (all 3 entries), `requires_acknowledgment: true`.
- [ ] When pre_check returns `action=refuse`, the SSE channel emits `stream.error` with `retryable: false` and no `token.delta` events.
- [ ] When pre_check returns `action=allow` or `action=caution`, the LLM stub is called, tokens are emitted via `token.delta`, and `message.final` is emitted last.
- [ ] `message.final.text` equals the concatenated `delta` values from all preceding `token.delta` events (invariant from INTERFACES.md §5).
- [ ] `message.final.risk` contains the SafetyCheckResult from the pre-check stage.
- [ ] A `safety_event` row is inserted in the DB for every pre-check result (even `action=allow` if `risk_level != "none"`).
- [ ] A `safety_event` row is inserted for every post-check result that triggers action.
- [ ] Citation validation uses `citation.validate_citations()` if available; falls back to `_citation_stub()` (strips all citations) if T010 is not yet merged. Either path must NOT raise an exception.
- [ ] The keyword-based safety stub (`safety.py`) correctly classifies these test inputs:
  - `"I want to kill myself"` → `action=escalate, categories=["self_harm"]`
  - `"I want to hurt someone"` → `action=escalate, categories=["violence"]`
  - `"What medication should I take?"` → `action=refuse, categories=["medical_advice"]`
  - `"I feel sad today"` → `action=allow, risk_level="low"`
  - `"Hello"` → `action=allow, risk_level="none"`
- [ ] `test_streaming.py` covers: escalate path (no LLM invoked), refuse path, allow path (delta + final sequence invariant), citation stub fallback.
- [ ] All existing tests in `test_api.py` continue to pass.

## Test / Run Commands

```bash
cd backend

# Run the full test suite (existing + new)
uv run pytest tests/ -v

# Run only streaming tests
uv run pytest tests/test_streaming.py -v

# Smoke test against live server (requires docker-compose up)
docker-compose up -d
uv run uvicorn app.main:app --reload --port 8000 &

# Test escalate path (should emit risk.interrupt, no token.delta)
curl -s -N \
  -H "Authorization: Bearer dev-token-1" \
  -H "Accept: text/event-stream" \
  "http://localhost:8000/v1/sessions/<session_id>/events" &

curl -s -X POST \
  -H "Authorization: Bearer dev-token-1" \
  -H "Content-Type: application/json" \
  -d '{"text":"I want to kill myself","client_message_id":"<uuid>","input_mode":"text"}' \
  "http://localhost:8000/v1/sessions/<session_id>/messages"
# Expected: SSE yields exactly one event: risk.interrupt; no token.delta

# Test normal path
curl -s -X POST \
  -H "Authorization: Bearer dev-token-1" \
  -H "Content-Type: application/json" \
  -d '{"text":"I feel overwhelmed","client_message_id":"<uuid2>","input_mode":"text"}' \
  "http://localhost:8000/v1/sessions/<session_id>/messages"
# Expected: SSE yields token.delta (N events) then message.final
```

## Notes / Risks

- **Parallel merge order:** T010 (`citation.py`) may or may not be merged before this PR. The `try/except ImportError` stub pattern makes this order-independent. After T010 merges, remove the stub fallback and import directly.
- **LLM stub response:** The hard-coded JSON stub must validate against INTERFACES.md §7.1 schema. Keep it realistic (includes reflection, verse_block, prayer fields) so downstream tests are meaningful.
- **`safety.py` is keyword-based only:** It is not the production ML classifier (T015). It must be easy to swap out — define a `SafetyClassifier` abstract base class and inject a concrete implementation.
- **Event ordering:** The asyncio.Queue approach in `streaming.py` is single-instance only (documented in T003). This is acceptable for MVP. Do not change the architecture.
- **B002 reminder:** The `CRISIS_TEMPLATE_PLACEHOLDER` string MUST NOT be replaced with the real crisis copy until T012 signoff is recorded in TASKS.md. Leave a TODO comment pointing to T012.
- **PR title suggestion:** `feat(backend): T007 real message pipeline — safety gating, LLM stub, SSE stream [B002 placeholder]`
