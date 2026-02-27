# Decisions (ADR-lite)

<!-- All decisions: record options + rationale + implications. Status: Provisional → LOCKED after signoff. -->

---

## D001 — Streaming Protocol for Chat

- **Status:** LOCKED
- **Owner:** Backend Engineer
- **Options considered:** SSE vs WebSocket
- **Decision:** SSE (`text/event-stream`)
- **Rationale:** Simpler infrastructure, unidirectional server push is sufficient for token streaming, easier horizontal scaling, no full-duplex requirement identified for MVP. iOS can use `URLSession` streaming data tasks in lieu of a native `EventSource`.
- **Implications:**
  - Backend exposes `GET /v1/sessions/{id}/events` as SSE endpoint.
  - iOS must implement its own SSE parser (no native `EventSource` on iOS); reconnect on disconnect using `last_event_id` query param.
  - If future UX requires bidirectional real-time features (e.g., voice interruption), revisit WebSocket in a separate decision.
- **Revisit trigger:** iOS engineer identifies a UX requirement that SSE cannot fulfill.

---

## D002 — Scripture Source of Truth

- **Status:** LOCKED
- **Owner:** Backend Engineer + ML Engineer
- **Decision:** Canonical `bible_verses` table in PostgreSQL. All citations must resolve to a row in this table before being returned to the client.
- **Rationale:** Prevents LLM hallucination of verses, enables auditable citation logs, supports multiple translations cleanly.
- **Implications:**
  - Bible corpus must be ingested and loaded before any RAG or citation feature can work.
  - `verse_citations` table stores FK references (`verse_id_list`) to validated rows.
  - Citation validation gate is synchronous; failure = strip citation + log event (never block the full response due to a citation miss).

---

## D003 — SSE Implementation Specifics

- **Status:** LOCKED
- **Owner:** Backend Engineer

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Heartbeat interval | 15 seconds | Prevents proxy/load-balancer timeout; iOS detects stale connections |
| Reconnect window | 60 seconds | Server buffers events for reconnect within this window using `last_event_id` |
| Max stream duration | 5 minutes | After 5 min, server closes gracefully; client reconnects if needed |
| Event ID format | `{session_id}:{message_id}:{sequence}` | Enables precise resume without ambiguity |
| Keep-alive comment | `: keep-alive\n\n` | SSE comment syntax; ignored by parsers but prevents timeout |

- **iOS reconnect protocol:**
  1. On connection drop, client waits 1s then reconnects with `?last_event_id=<last_seen_id>`.
  2. Server replays events after `last_event_id` if within the 60s window.
  3. After 60s window, server returns a `stream.error` with `retryable: false`; client must re-POST the message using the original `client_message_id` (idempotency handles dedup).

---

## D004 — Idempotency Strategy

- **Status:** LOCKED
- **Owner:** Backend Engineer
- **Decision:** Client-generated `client_message_id` (UUID v4) with a unique constraint on `(session_id, client_message_id)` in the `messages` table.
- **Rationale:** Allows iOS to safely retry on network failure without duplicate processing.
- **Behavior on duplicate:** HTTP 409 returned with `original_message_id`. No re-processing. iOS uses `original_message_id` to reconnect to SSE.
- **Scope:** Idempotency is per-session.
- **Implications:** iOS must generate and persist `client_message_id` locally before sending so it survives app restarts.

---

## D005 — Allowed Bible Translations

- **Status:** LOCKED
- **Owner:** Theology Advisor

| Translation ID | Full Name | Notes |
|---------------|-----------|-------|
| `ESV` | English Standard Version | Default; widely used in evangelical contexts |
| `NIV` | New International Version (2011) | Broad readership; accessible |
| `KJV` | King James Version | Public domain; traditional preference |
| `NKJV` | New King James Version | Modern KJV; accessible |
| `NLT` | New Living Translation | Paraphrase-adjacent; readable |
| `CSB` | Christian Standard Bible | Balance of readability and accuracy |

- **Default translation:** `NIV` when user has not set a preference.
- **Rationale:** Primary translations used in English-language Protestant and broadly Christian contexts. Catholic-specific translations (NABRE, RSV-CE) deferred to post-MVP.
- **Revisit trigger:** User research shows demand for NASB, MSG, AMP, or NABRE.

---

## D006 — Paraphrase Policy

- **Status:** LOCKED
- **Owner:** Theology Advisor + ML Engineer
- **Decision:**
  - Direct quotes from validated `bible_verses` rows: allowed; returned in `verse_block` and `citations`.
  - Paraphrases: NOT permitted in `verse_block`/`citations`. If used in `reflection` prose, must be labeled inline: *"Paraphrase of [Book Chapter:Verse]"*.
  - LLM must not present a paraphrase as a direct quote (enforced via system prompt).
  - Fallback: if uncertain about exact verse text, omit the citation and reflect without quoting.
- **Rationale:** Presenting paraphrases as direct quotes is a citation integrity failure and a theological harm risk.

---

## D007 — Authentication Strategy

- **Status:** LOCKED
- **Owner:** Backend Engineer
- **Decision:** Apple Sign-In as primary auth for iOS MVP. Server exchanges Apple ID token for a short-lived server-issued JWT (1-hour expiry). No refresh token in MVP.
- **JWT claims:** `sub` (internal user UUID), `exp`, `iat`.
- **Rationale:** Apple Sign-In required for iOS apps offering social login. Minimizes credential management liability.
- **Implications:**
  - Backend validates Apple ID token against Apple's public keys on each auth call.
  - A dev-only password grant may exist behind a feature flag for local testing only.
  - Refresh tokens deferred to post-MVP.

---

## D008 — Message Content Storage Policy

- **Status:** LOCKED
- **Owner:** Backend Engineer
- **Decision:** Raw user message text is NOT stored in plaintext. Stored encrypted (AES-256-GCM, per-user key).
- **Options rejected:**
  - Hash-only: prevents audit/support use cases.
  - Plaintext: privacy and regulatory risk.
- **What IS stored unencrypted:** `text_hash` (SHA-256), `metadata` JSONB (non-sensitive fields only), all `safety_events` fields (risk level, categories, action, rationale codes — no raw text).
- **Implications:** Key management strategy (derivation, rotation) is a pre-ship security review blocker.

---

## D009 — Crisis Template Governance

- **Status:** PROVISIONAL — requires Mental Health Advisor signoff before ship
- **Owner:** Mental Health Advisor (content) + Backend Engineer (delivery)
- **Decision:** Crisis response copy is stored as versioned server-side templates, not hardcoded in client or generated by LLM.
- **Rationale:** Allows copy updates without app releases. Ensures deterministic, clinically reviewed content in the highest-risk path.
- **Template fields:** `message` (main copy), `resources` array (label + contact), `requires_acknowledgment` flag.
- **Versioning:** Template version logged in `safety_events` for each escalation event.

---

## D010 — pgvector Embedding Spec (RAG)

- **Status:** LOCKED (MVP defaults — ML Engineer may override via task before T009 begins)
- **Owner:** ML Engineer (spec) + Backend Engineer (implementation)
- **Resolved blocker:** B001

### Decision Process
ML Engineer was asked to provide the embedding spec within the contract lock phase. No specification was received in this run. MVP defaults adopted per Orchestrator standing protocol (see B001 fallback assumption in DEPENDENCIES.md).

### Adopted Spec

| Parameter | Value | Notes |
|-----------|-------|-------|
| Embedding model | `text-embedding-3-small` (OpenAI) | 1536-dim; cost-effective for MVP corpus size |
| Vector dimensions | 1536 | Must match model output exactly; changing model requires full re-embed + migration |
| Distance metric | Cosine | Standard for semantic text similarity |
| pgvector operator class | `vector_cosine_ops` | Matches cosine distance metric |
| Index type | HNSW | Better query-time performance than IVFFlat at this scale; no training step required |
| HNSW `m` | 16 | Connections per layer; default balance of recall vs. index size |
| HNSW `ef_construction` | 64 | Build-time accuracy; higher = slower build, better recall |
| HNSW `ef_search` | 60 | Query-time accuracy; set as session param `SET hnsw.ef_search = 60` |

### Table Design
Separate `verse_embeddings` table (not a column on `bible_verses`) to allow multiple models/versions coexist without schema migrations when the model changes. See INTERFACES.md §9.

### Override Protocol
If ML Engineer determines different model, dimensions, or index params are needed:
1. File a task in TASKS.md with the proposed change and rationale.
2. Update this decision to REVISED status.
3. Backend must run a migration to drop + recreate the embedding column and index.
4. Full re-embed of the bible corpus is required on model/dimension change.

### RAG Retrieval Parameters (from ML Engineer agent spec)
- `top_k_verses`: 5–12 (exact value tunable post-MVP via eval harness)
- `top_k_devotionals`: 3–8 (exact value tunable post-MVP)
- Optional rerank: semantic score + theology tags (implementation details deferred to T009)

---

## D015 — iOS Build Guardian Role & Automated Pre-Merge Gate

- **Date:** 2026-02-27
- **Status:** LOCKED
- **Owner:** iOS Engineer (Lead)
- **Decision:** The iOS Engineer (Lead) is permanently assigned as Build Guardian. All PRs touching `ios/` must pass `scripts/verify_ios_build.sh` (exit code 0) before merge. Failures trigger a defined escalation protocol (see `governance/ORCHESTRATOR_POLICY_build_guardian.md`).
- **Rationale:** Repeated build failures from directory duplication and cross-agent changes demonstrated the need for automated enforcement and clear ownership of build integrity.
- **Implications:**
  - Orchestrator must run the gate script before merging any PR that modifies `ios/`.
  - iOS Engineer has authority to block any PR that fails the gate.
  - Escalation protocol: Level 1 (self-fix) → Level 2 (cross-agent blocking task) → Level 3 (Project Owner).
