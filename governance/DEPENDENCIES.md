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

### B004 — T015 CI gate cannot activate live-mode or citation metrics

- **ID:** B004
- **blocked_task:** T015 — CI gate passing P0 thresholds in `--mode live`; citation hit-rate metric
- **blocked_owner:** ML Engineer (eval harness)
- **blocked_by:** Backend Engineer (T007, T010), ML Engineer (T009)
- **needed_artifacts:**
  - T007 merged → switch CI gate from `--mode stub` to `--mode live`; escalate_recall ≥ 0.97 threshold only testable against real LLM classifier
  - T010 merged → citation validation gate available; drop `SKIP_CITATION_METRICS=true` in CI
  - T009 merged → Bible corpus + embeddings populated; required for citation hit-rate to be non-trivially testable
- **why_blocked:** Keyword stub (pre-T007) achieves escalate_recall=0.744, well below the 0.97 P0 threshold. The threshold is only achievable with a real LLM classifier. Citation metrics require the full corpus + validation pipeline.
- **fallback_assumption:** CI runs `--mode stub` with `SKIP_CITATION_METRICS=true` until all three tasks merge. Stub failures are expected and documented in `eval/README_eval.md`.
- **deadline:** Before ship-ready label is applied.
- **status:** open

---

### B005 — OPENAI_API_KEY must be provisioned in deployment environment before embedding generation

- **ID:** B005
- **blocked_task:** T009 embedding generation phase (verse_embeddings population)
- **blocked_owner:** ML Engineer (script ready; awaiting key)
- **blocked_by:** Backend Engineer / DevOps (key management)
- **needed_artifact:** `OPENAI_API_KEY` set in the server environment (or secrets manager entry documented in T016 key management strategy). Backend Engineer to confirm where API keys are managed alongside T016 encryption key strategy.
- **why_blocked:** `ingest_bible_corpus.py` without `--no-embeddings` calls the OpenAI API. Corpus load (`--no-embeddings`) and citation validation (T010) are NOT blocked — they work with the committed KJV JSON alone. Only the pgvector similarity-search path requires embeddings.
- **fallback_assumption:** Run ingestion with `--no-embeddings` for all CI/dev work; defer embedding generation to staging/prod environment where key is available. RAG retrieval (Phase C) is already deferred to post-MVP.
- **deadline:** Before Phase C (RAG retrieval query) is implemented; not a blocker for T010 or current MVP scope.
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
