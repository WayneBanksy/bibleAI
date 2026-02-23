# Tasks (MVP)

---

## Done

- [x] T001 Decide streaming protocol (SSE vs WebSocket) — Owner: Backend + iOS
  - Decision: SSE. LOCKED in DECISIONS.md D001 + D003.

- [x] T002 Define v0 API contract (sessions/messages/events/report) — Owner: Backend
  - Full contract written in INTERFACES.md §1–§6. Auth (§2), Sessions (§3), Messages (§4), SSE events (§5), Report (§6).

- [x] T003-pre DB schema proposal — Owner: Backend
  - DB Schema Proposal written in INTERFACES.md §9 (tables: users, consents, sessions, messages, bible_verses, verse_citations, safety_events, reports).

- [x] T003 Scaffold FastAPI backend + Postgres + Alembic — Owner: Backend
  - Tool choice: uv (documented in pyproject.toml).
  - SQLAlchemy 2.0 async ORM models: /backend/app/models.py (all 8 tables + verse_embeddings).
  - Alembic migration: /backend/alembic/versions/0001_initial.py (pgvector extension + all tables + HNSW index).
  - JWT middleware (Apple exchange stubbed in dev): /backend/app/auth.py.
  - Structured logging with request_id: /backend/app/logger.py + middleware in main.py.
  - Endpoints implemented with working persistence (no LLM):
    - POST /v1/auth/token
    - POST /v1/sessions
    - GET  /v1/sessions/{id}
    - POST /v1/sessions/{id}/messages (202 + idempotency via partial unique index D004)
    - GET  /v1/sessions/{id}/events (SSE: heartbeat every 15s + demo token.delta stream + message.final)
    - POST /v1/safety/report
  - SSE demo: background task emits token.delta tokens then message.final.
  - Idempotency: (session_id, client_message_id) partial unique index; 409 on duplicate.
  - docker-compose.yml: pgvector/pgvector:pg16 + api service.
  - Pytest scaffold: /backend/tests/conftest.py + /backend/tests/test_api.py (7 test cases).
  - Definition of done: Draft. Integrated after T007 (real LLM pipeline) + T010 (citation gate).

- [x] T005 Define safety taxonomy + crisis mapping — Owner: ML + Mental Health Advisor
  - Safety taxonomy (risk levels, categories, action mapping) written in SAFETY_POLICY.md §1.
  - Crisis definitions + deterministic bypass requirements in SAFETY_POLICY.md §2.
  - Prohibited clinical language in SAFETY_POLICY.md §3.
  - SafetyCheckResult JSON schema in INTERFACES.md §8.

- [x] T006 Define citation integrity rules + translation policy — Owner: ML + Theology Advisor
  - Translation policy: 6 allowed translations (ESV, NIV, KJV, NKJV, NLT, CSB). LOCKED in DECISIONS.md D005.
  - Paraphrase policy: LOCKED in DECISIONS.md D006.
  - Citation integrity rules in SAFETY_POLICY.md §5.
  - LLM structured output schema (verse_block validation rules) in INTERFACES.md §7.
  - Spiritual coercion prohibited patterns + reframes in SAFETY_POLICY.md §4.

- [x] T004 Create iOS SwiftUI scaffold + chat UI shell — Owner: iOS
  - Swift Package at /ios/ (BibleTherapistCore library + BibleTherapistCoreTests).
  - MVVM with @MainActor ChatViewModel (ObservableObject).
  - Session create: POST /v1/sessions → startSSEStream().
  - Message send: POST /v1/sessions/{id}/messages with client_message_id (UUID per send, idempotency).
  - 409 recovery: reconnect to SSE stream per INTERFACES.md §4.
  - SwiftUI app (App/ dir, add to Xcode project):
    - DisclaimerView (gate with GetHelpNowButton + CrisisResourcesSheet).
    - ChatView (ScrollView + auto-scroll + overflow menu with Get Help Now).
    - MessageBubble (user/assistant, streaming TypingIndicator, citation chips, Report context menu).
    - InputBar (multiline, disabled while streaming or inputBlocked).
    - RiskInterruptView (full-screen, non-dismissible, crisis resources + ack button).

- [x] T008 Implement iOS streaming parser + message rendering — Owner: iOS
  - SSEClient: URLSession.bytes async stream, line-by-line SSE wire format parser.
  - SSEEventParser: pure static function (RawSSEFrame → SSEEvent); all 5 event types handled.
  - token.delta: appended to ChatMessage.text while isStreaming=true.
  - message.final: draft committed with authoritative text, citations, risk, structured payload.
  - risk.interrupt: draft removed, inputBlocked=true, riskInterrupt payload set → modal shown.
  - stream.error: draft removed, errorMessage set, reconnect if retryable=true.
  - heartbeat: no-op (keep-alive).
  - 24 unit tests pass (14 SSEParserTests + 10 ChatViewModelTests): swift test ✅.

---

## Backlog

- [ ] T007 Implement message send + streaming events — Owner: Backend
  - Pre-req: T003 complete (DONE). Wire real safety pre-check + LLM call + citation validation gate.

- [ ] T009 Implement RAG retrieval (pgvector) — Owner: ML + Backend
  - Pre-req: T003 scaffold complete. Bible corpus ingested.
  - Embedding spec: LOCKED in DECISIONS.md D010 (`text-embedding-3-small`, 1536 dims, HNSW cosine). B001 resolved.
  - Schema: `verse_embeddings` table + HNSW index DDL in INTERFACES.md §9.

- [ ] T009-tune RAG retrieval parameter tuning — Owner: ML Engineer
  - Deferred to post-MVP (after eval harness is running).
  - Items to tune: `top_k_verses` (5–12), `top_k_devotionals` (3–8), rerank weights, `ef_search` (default 60), embedding model upgrade if quality insufficient.
  - Gate: ML Engineer eval harness (T015) must show recall metrics before changing defaults.

- [ ] T010 Implement citation validation gate — Owner: Backend
  - Pre-req: T003 complete + bible_verses table populated. Rules in INTERFACES.md §7.2.

- [x] T011 Add P0 test plan + integration tests — Owner: QA
  - P0 test plan: /governance/TEST_PLAN.md (5 areas × test cases, manual iOS checklist, CI gate spec, known-gaps table).
  - Pytest integration skeleton: /backend/tests/test_p0_integration.py (30 tests, 0 failures on collection).
  - CI command: `uv run pytest tests/ -m "not pending_t007" -v`
  - P0 markers registered in pyproject.toml: p0_session, p0_idempotency, p0_sse, p0_safety, p0_report, pending_t007.
  - P0-01 Session: 6 tests (all modes, defaults, 422 on invalid mode/translation, 403 unauthenticated, 404 cross-user).
  - P0-02 Idempotency: 5 tests (202 happy path, 409 duplicate, original_message_id in 409, cross-session isolation, exact status code).
  - P0-03 SSE contract: 7 tests (sequence ordering, text assembly, message.final exactly once, no delta after final, auth gate, content-type, risk payload fields).
  - P0-04 Safety/risk.interrupt: 6 tests — xfail(pending_t007): crisis input, LLM bypass, requires_acknowledgment=true, resources, medical advice refuse, post-crisis resume.
  - P0-05 Report: 6 tests (happy path, wrong-session 404, invalid reason 422, raw details not echoed, null details, all 4 reasons).
  - Known gaps documented in TEST_PLAN.md: P0-04 unblocked by T007+T012, DB-layer hash assertion requires admin endpoint, citation regression requires T010.

---

## Pending Advisor Signoffs (ship blockers)

- [ ] T012 Mental Health Advisor: written signoff on crisis template v1 — Owner: Mental Health Advisor
  - Unblocks: T007 (crisis path implementation), ship-ready label.

- [ ] T013 Mental Health Advisor: written signoff on post-crisis resumption template — Owner: Mental Health Advisor
  - Unblocks: ship-ready label.

- [ ] T014 Theology Advisor + Mental Health Advisor: review + approve sensitive-topic devotional snippets — Owner: Both
  - Unblocks: T009 (RAG corpus ready for sensitive topics).

- [ ] T015 ML Engineer: deliver eval harness (100–200 gold examples + CI gates) — Owner: ML Engineer
  - Unblocks: QA signoff, ship-ready label.

- [ ] T016 Backend Engineer: encryption key management strategy reviewed — Owner: Backend + Security Review
  - Unblocks: ship-ready label.

## In Progress

(none)
