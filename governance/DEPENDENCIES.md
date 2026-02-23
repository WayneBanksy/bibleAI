# Dependencies / Blockers

---

## Active Blockers

### ~~B001 — pgvector embedding spec not yet defined~~ — RESOLVED

- **ID:** B001
- **status:** resolved
- **resolved_by:** Orchestrator (MVP defaults adopted — D010 LOCKED)
- **resolution:** ML Engineer did not specify within the contract lock run. Orchestrator adopted MVP defaults per standing fallback protocol:
  - Model: `text-embedding-3-small`, 1536 dims, cosine distance, HNSW (m=16, ef_construction=64, ef_search=60)
- **artifacts produced:**
  - DECISIONS.md D010 — pgvector spec, LOCKED
  - INTERFACES.md §9 — `verse_embeddings` table schema + HNSW index DDL
- **override path:** ML Engineer must file a task in TASKS.md to change model, dimensions, or index params. A schema migration and full re-embed will be required.
- **converted to tuning task:** T009-tune (see TASKS.md backlog — RAG retrieval param tuning: top_k, rerank weights, ef_search — deferred to post-MVP eval harness)

---

### B002 — Crisis template v1 lacks written Mental Health Advisor signoff

- **ID:** B002
- **blocked_task:** T007 crisis path implementation; ship-ready label
- **blocked_owner:** Backend Engineer
- **blocked_by:** Mental Health Advisor
- **needed_artifact:** Written approval of crisis template v1 copy (SAFETY_POLICY.md §2.3). Record approval in TASKS.md T012 and DECISIONS.md D009.
- **why_blocked:** Crisis response copy in `risk.interrupt` events must be clinically reviewed before production. This is a non-negotiable safety gate.
- **fallback_assumption:** None. No acceptable fallback. Ship is blocked until resolved.
- **deadline:** Before ship-ready label is applied.
- **status:** open

---

### B003 — Security review signoff required for T016 key management design

- **ID:** B003
- **blocked_task:** T016 (ship-ready label); DECISIONS.md D008 final LOCKED status
- **blocked_owner:** Backend Engineer
- **blocked_by:** Security Reviewer
- **needed_artifact:** Reviewer name + date recorded in `backend/docs/KEY_MANAGEMENT.md §6` (Security Review Signoff table). Summary note added to DECISIONS.md D008.
- **why_blocked:** Per D008 policy, the AES-256-GCM key management design (HKDF derivation scheme, nonce management, rotation runbook) requires explicit security reviewer approval before the ship-ready label can be applied. Implementation is complete (PR #2); review is the only remaining gate.
- **fallback_assumption:** None. No acceptable fallback. Ship is blocked until resolved.
- **deadline:** Before ship-ready label is applied.
- **status:** open

---

## Resolved Blockers

(none yet)

---

## Template (copy/paste)

- ID: BXXX
  blocked_task: T00X
  blocked_owner: role
  blocked_by: role
  needed_artifact: exact file + section
  why_blocked: 1-2 sentences
  fallback_assumption: what we assume if not provided, or "none"
  deadline: date or milestone
  status: open|resolved
