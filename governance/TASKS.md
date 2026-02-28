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

- [ ] T009-tune RAG retrieval parameter tuning — Owner: ML Engineer
  - Deferred to post-MVP (after eval harness is running).
  - Items to tune: `top_k_verses` (5–12), `top_k_devotionals` (3–8), rerank weights, `ef_search` (default 60), embedding model upgrade if quality insufficient.
  - Gate: ML Engineer eval harness (T015) must show recall metrics before changing defaults.

- [x] T010 Implement citation validation gate — Owner: **Backend Engineer**
  - Work packet: `governance/work_packets/WP_T010_citation-gate.md`
  - Branch: `agent/backend/T010-citation-gate`
  - `backend/app/citation.py`: `CitationResult` dataclass + `validate_citations(verse_block, db) -> list[CitationResult]`. Five-step validation: guard → range check → DB lookup → not-found → SHA-256 hash check (all-or-nothing per citation). Never raises.
  - `backend/tests/test_citation.py`: 15 tests covering all acceptance criteria (empty list, happy-path single/range, not-found, range-invalid, hash-mismatch, mixed batch, malformed input, verse_end default).
  - `backend/tests/fixtures/bible_verses_seed.sql`: KJV seed rows (Genesis 1:1–2, John 3:16, Psalm 23:1) + corrupted-hash row for manual dev loading.
  - Public interface stable. T007 can now import `from app.citation import validate_citations` without the try/except stub fallback.
  - Definition of done: **Integrated** ✅
  - **Merged to main: 2026-02-23 — SHA b021917 (Orchestrator merge run)**

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
  - Definition of done: **Integrated** ✅

---

## Pending Advisor Signoffs (ship blockers)

- [x] T012 Crisis template v1 signoff — Owner: Project Owner (2026-02-28)
  - Unblocks: T007 (crisis path implementation), ship-ready label.
  - Signoff recorded: Project Owner approved SAFETY_POLICY.md §2.3 crisis template.
  - Template includes: acknowledgment of pain, not-a-substitute statement, 3 crisis resources (988, Crisis Text Line, 911), encouragement to seek help, safety check option.

- [ ] T013 Mental Health Advisor: written signoff on post-crisis resumption template — Owner: Mental Health Advisor
  - Unblocks: ship-ready label.

- [ ] T014 Theology Advisor + Mental Health Advisor: review + approve sensitive-topic devotional snippets — Owner: Both
  - Unblocks: T009 (RAG corpus ready for sensitive topics).

- [ ] T015 ML Engineer: deliver eval harness (100–200 gold examples + CI gates) — Owner: ML Engineer
  - Unblocks: QA signoff, ship-ready label.
  - **Implementation merged to main: 2026-02-23 — SHA 8e6fe8e (Orchestrator merge run)**. Live-mode CI gate activation blocked on B004 (needs T007+T009).

- [ ] T016 Backend Engineer: encryption key management strategy reviewed — Owner: Backend + Security Review
  - Unblocks: ship-ready label (D008 extension). Also unblocks T007 Integrated status.
  - **Implementation merged to main: 2026-02-23 — SHA 4ff5840 (Orchestrator merge run)**. Awaiting Security Review signoff (B003) before task can be marked done.

---

## Next Sprint — Monetization + WWJD Premium + Analytics

### Batch A (parallel — no inter-dependencies)

- [ ] P1-01 Subscription & Entitlements — Owner: **Backend Engineer**
  - Work packet: `governance/work_packets/WP_P1_01_subscription-entitlements_backend.md`
  - Branch: `agent/backend/P1-01-subscription-entitlements`
  - Deliverables: entitlements snapshot service, GET /v1/entitlements, quota enforcement (402 PAYWALL_REQUIRED), Alembic migration (subscription fields on users).
  - Dependencies: Auth (exists), Alembic (exists). P1-02 integrates later (credits_balance default 0).
  - Definition of done: **Pending**

- [ ] P1-02 Credit System — Owner: **Backend Engineer**
  - Work packet: `governance/work_packets/WP_P1_02_credit-system_backend.md`
  - Branch: `agent/backend/P1-02-credits`
  - Deliverables: credit_ledger table, POST /v1/credits/redeem (idempotent), atomic consume_credit_if_needed hook, Alembic migration.
  - Dependencies: Auth (exists). P1-01 optional (credits_balance field added here if needed).
  - Definition of done: **Pending**

- [ ] P2-01 WWJD Mode — Owner: **ML Engineer**
  - Work packet: `governance/work_packets/WP_P2_01_wwjd-mode_ml.md`
  - Branch: `agent/ml/P2-01-wwjd-mode`
  - Deliverables: WWJD system prompt, structured output schema (devotional + verse_block + action_steps), safety override logic, tests.
  - Dependencies: Safety taxonomy (exists), citation gate T010 (exists).
  - Definition of done: **Pending**

- [ ] P1-05 Analytics Events (Backend portion) — Owner: **Backend Engineer**
  - Work packet: `governance/work_packets/WP_P1_05_analytics-events_backend_ios.md`
  - Branch: `agent/backend/P1-05-analytics`
  - Deliverables: analytics_events table, POST /v1/analytics/event (allowlisted), GET /v1/analytics/summary (dev-only), Alembic migration, tests.
  - Dependencies: Auth (exists).
  - Definition of done: **Pending**

### Batch B (after P1-01 endpoints exist)

- [x] P1-04 App Store Receipt Verification — Owner: **Backend Engineer**
  - Work packet: `governance/work_packets/WP_P1_04_appstore-receipt-verification_backend.md`
  - Branch: `main` (direct commit)
  - Deliverables:
    - Alembic migration `0005_iap_transactions.py`: iap_transactions table with UNIQUE(platform, transaction_id), check constraints on product_type and environment.
    - `backend/app/services/iap_verification.py`: pluggable `IAPVerifier` interface with `DevStubVerifier` (dev) and `ProductionVerifier` (Apple API placeholder); `verify_and_record()` with idempotency on (platform, transaction_id).
    - `backend/app/services/subscription_sync.py`: `sync_subscription_from_transaction()` (deterministic tier/status/expires_at update), `enforce_subscription_expiry()` (MVP on-read downgrade).
    - `backend/app/routers/iap.py`: POST /v1/iap/verify + POST /v1/iap/sync (expiry enforcement on sync).
    - ORM: IAPTransaction model + User.iap_transactions relationship.
    - `backend/app/schemas.py`: IAPVerifyRequest, IAPVerifyResponse.
    - Tests: **7/7 unit tests passing** (subscription activation, expiry, revocation, enforce expiry scenarios). 8 integration tests written (require Postgres): verify sub/consumable, idempotency, unauthenticated, invalid type, multiple subs, sync endpoint, sync unauth.
  - ⚠️ ProductionVerifier raises NotImplementedError — requires Apple API credentials (B005-adjacent). DevStubVerifier must NEVER be active in production (gated behind `is_dev`).
  - Definition of done: **Draft** ✅ — Integration tests require Postgres. ProductionVerifier requires Apple API key provisioning.
  - **Commit: 8aa5aa4 on main (2026-02-25)**

- [x] P1-03 StoreKit Integration — Owner: **iOS Engineer**
  - Work packet: `governance/work_packets/WP_P1_03_storekit-integration_ios.md`
  - Branch: `main` (direct commit)
  - Deliverables:
    - `ios/Sources/BibleTherapistCore/Store/ProductIDs.swift`: centralized product IDs (2 subscriptions: plus_monthly, plus_annual; 4 credit packs: credits_5/10/30/50).
    - `ios/Sources/BibleTherapistCore/Store/StoreKitManager.swift`: StoreKit 2 `Product.purchase()`, transaction listener (`Transaction.updates`), restore via `AppStore.sync()` + `Transaction.currentEntitlements`, backend sync for subscriptions (verifyIAP) and credits (redeemCredits). Credit restores do NOT re-redeem (per spec).
    - `ios/Sources/BibleTherapistCore/Store/EntitlementsStore.swift`: `@MainActor ObservableObject` with `refresh()` → GET /v1/entitlements; derived state: `isPlusActive`, `wwjdEnabled`, `creditsBalance`, `canStartSession`, `blockingReason`.
    - `ios/Sources/BibleTherapistCore/Views/PaywallView.swift`: feature comparison (Free vs Plus), subscription CTAs, credit pack CTAs, restore button, blocking reason display.
    - `ios/Sources/BibleTherapistCore/Models/AppModels.swift`: added `EntitlementsSnapshot`, `EntitlementsResponse`, `RedeemCreditsResponse`, `IAPVerifyResponse`.
    - `ios/Sources/BibleTherapistCore/Networking/APIClient.swift`: added `paywallRequired` error case + 402 handling, generic GET helper, `getEntitlements()`, `redeemCredits()`, `verifyIAP()`, `syncIAP()`.
    - Tests: **5/5 unit tests passing** (derived state defaults, product IDs, snapshot/credits/IAP response decoding). All **29/29 iOS tests pass** (10 ChatViewModel + 5 EntitlementsStore + 14 SSEParser).
  - Dependencies met: P1-01 (GET /v1/entitlements), P1-02 (POST /v1/credits/redeem), P1-04 (POST /v1/iap/verify + /sync).
  - Definition of done: **Integrated** ✅ — all unit tests pass, swift build + swift test green.
  - **Commit: 8aa5aa4 on main (2026-02-25)**

### Batch C (after P1-01 + P2-01)

- [ ] P2-02 WWJD Entitlement Gate — Owner: **Backend Engineer**
  - Work packet: `governance/work_packets/WP_P2_02_wwjd-entitlement-gate_backend.md`
  - Branch: `agent/backend/P2-02-wwjd-gate`
  - Deliverables: locked_content table, locked response behavior, GET /v1/locked/{id} unlock endpoint, tests.
  - Dependencies: P1-01 (wwjd_enabled), P2-01 (WWJD structured output schema).
  - Definition of done: **Pending**

### Batch D (after P1-03 + P2-02)

- [ ] P2-03 WWJD Blur Overlay — Owner: **iOS Engineer**
  - Work packet: `governance/work_packets/WP_P2_03_wwjd-blur-overlay_ios.md`
  - Branch: `agent/ios/P2-03-wwjd-overlay`
  - Deliverables: mode toggle (Default | WWJD), blurred preview bubble, paywall overlay, unlock fetch + render, tests.
  - Dependencies: P1-03 (paywall exists), P2-02 (locked response + /v1/locked/{id}).
  - Definition of done: **Pending**

- [ ] P1-05 Analytics Events (iOS portion) — Owner: **iOS Engineer**
  - Work packet: `governance/work_packets/WP_P1_05_analytics-events_backend_ios.md`
  - Branch: `agent/ios/P1-05-analytics`
  - Deliverables: AnalyticsClient, fire-and-forget event hooks (paywall, credits, WWJD, quota), integration with PaywallView + ChatViewModel + StoreKitManager.
  - Dependencies: P1-05 backend (POST /v1/analytics/event), P1-03 (paywall views), P2-03 (WWJD views).
  - Definition of done: **Pending**

---

## In Progress

- [x] T007 Implement message send + streaming events — Owner: **Backend Engineer**
  - Work packet: `governance/work_packets/WP_T007_streaming-skeleton.md`
  - Branch: `agent/backend/T007-streaming-skeleton`
  - Deliverables: `backend/app/safety.py` (KeywordSafetyClassifier + SafetyClassifier protocol), `backend/app/pipeline.py` (7-stage run_pipeline), `backend/app/streaming.py` (publish_real_stream wired), `backend/app/routers/messages.py` (background task → real pipeline), `backend/tests/test_streaming.py` (12 tests, all passing).
  - ⚠️ B002 compliant: crisis mechanics fully implemented; `message` field uses `CRISIS_TEMPLATE_PLACEHOLDER`. Do NOT replace with real copy until T012 signoff is recorded here.
  - Definition of done: **Integrated** ✅
  - **Merged to main: 2026-02-23 — SHA c61ff09 (Orchestrator T007 re-dispatch)**

- [x] T009 Implement RAG retrieval (pgvector) — Owner: **ML Engineer** (Phase B: corpus ingestion)
  - Work packet: `governance/work_packets/WP_T009_corpus-ingestion.md`
  - Phase B complete ✅: KJV corpus (31,100 verses, 66 books) → `bible_verses` + SHA-256 hashes; `text-embedding-3-small` embedding pipeline → `verse_embeddings`; `verify_corpus.py` sanity-check; `README_corpus.md`; `data/.gitignore`.
  - RAG retrieval query implementation deferred to Phase C (after eval harness T015 is running).
  - ⚠️ Embedding generation requires `OPENAI_API_KEY` in deployment env (B005); corpus load works without it (`--no-embeddings`).
  - Definition of done: **Integrated** ✅
  - **Merged to main: 2026-02-23 — SHA 3c14355 (Orchestrator merge run)**

- [x] T015 ML Engineer: deliver eval harness — Owner: **ML Engineer**
  - Work packet: `governance/work_packets/WP_T015_eval-harness.md`
  - 120 gold examples (all WP minimums met), runner + metrics + CI gate implemented. Stub baseline in eval/README_eval.md.
  - CI gate runs in `--mode stub` (B004). Switches to `--mode live` after T007+T009 merge.
  - Does NOT require T012 (B002) — tests classifier behaviour, not crisis copy wording.
  - Definition of done: **Integrated** ✅
  - **Merged to main: 2026-02-23 — SHA 8e6fe8e (Orchestrator merge run)**

- [x] T016 Backend Engineer: encryption key management strategy — Owner: **Backend Engineer**
  - Work packet: `governance/work_packets/WP_T016_encryption-key-strategy.md`
  - Branch: `agent/backend/T016-encryption-keys`
  - Deliverables: `app/crypto.py` (AES-256-GCM + HKDF-SHA256), `tests/test_crypto.py` (17 passing), `docs/KEY_MANAGEMENT.md`, `config.py` production guard.
  - Definition of done: **Integrated** ✅ (code merged). Ship-ready blocked on B003 (Security Review signoff).
  - **Merged to main: 2026-02-23 — SHA 4ff5840 (Orchestrator merge run)**

- [x] T-BUILDFIX-001 Fix iOS build error + wire app entry point — Owner: **iOS Engineer (Lead)**
  - Work packet: `governance/work_packets/WP_IOS_BUILDFIX_001.md`
  - Branch: `main` (direct fix — blocking)
  - Fixes applied:
    - `BibleAIApp.swift`: wired `APIClient` → `AuthStore` → `ChatViewModel` → `ContentView` dependency chain + `.environmentObject(authStore)`.
    - `ChatViewModel.swift`: `service` visibility changed from `private` to `public` (cross-module access from `MessageBubble.ReportSheet`).
    - `ChatViewModel.swift`: `riskInterrupt` changed from `internal(set)` to `public` (cross-module `Binding` from `ChatView.$vm.riskInterrupt`).
    - `MessageBubble.swift`: added `import Combine` (required for `Timer.publish`).
    - `PaywallView.swift`: added `import BibleTherapistCore` (required for `StoreKitManager`/`EntitlementsStore`).
  - Verification: `./scripts/verify_ios_build.sh` → **BUILD SUCCEEDED** (exit 0). `swift test` → **29/29 passing**.
  - Definition of done: **Integrated** ✅

- [x] T-AC001 Restore deleted backend files — Owner: **Project Owner**
  - AC-001 critical: commit 8aa5aa4 deleted ~60 backend files.
  - Restored from 0eeeb17 (last known-good state). Preserved HEAD versions of main.py, models.py, schemas.py (contain Batch B IAP additions).
  - All 8 routers, alembic migrations 0001-0004, pyproject.toml, Docker config, tests, eval harness restored.
  - Definition of done: **Integrated** ✅
  - **Resolved: 2026-02-28**

- [x] T-LLM-001 Claude (Anthropic) LLM Integration — Owner: **Project Owner**
  - Decision: D016 (LOCKED)
  - Deliverables:
    - `backend/app/llm/` package: LLMProvider abstraction, ClaudeProvider, StubProvider, factory, error hierarchy.
    - `backend/app/config.py`: LLM settings (llm_provider, anthropic_api_key, anthropic_model, timeouts, RAG top_k).
    - `backend/app/pipeline.py`: stage 3 replaced with provider call (was hard-coded stub).
    - `backend/app/prompting/default_prompt.py`: enhanced system prompt for Claude (citation rules, safety, invitational tone).
    - `backend/pyproject.toml`: anthropic SDK dependency added.
    - `backend/tests/test_llm_provider.py`: provider tests (stub, Claude mock, factory, errors).
    - `backend/tests/test_pipeline_with_provider.py`: pipeline integration tests with error handling.
  - StubProvider (default) ensures all existing tests pass without API key.
  - To activate Claude: set `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY=sk-...` in env.
  - Definition of done: **Integrated** ✅
  - **Resolved: 2026-02-28**

- [x] T-IOS-DEVPREVIEW iOS Dev Preview Mode — Owner: **Project Owner**
  - Compile-time `DEV_PREVIEW` flag (Debug config only) + `#if DEBUG` mock types.
  - MockSessionService + MockSSEProvider in `ios/Sources/BibleTherapistCore/Mocks/`.
  - ChatViewModel `simulateStreamingResponse()` for word-by-word mock streaming.
  - BibleAIApp.swift: injects mocks and bypasses auth when DEV_PREVIEW is active.
  - ChatView.swift: welcome message + mock send intercept.
  - Triple guard: `#if DEBUG` on mocks, `#if DEV_PREVIEW` on wiring, Release build strips all.
  - Definition of done: **Integrated** ✅
  - **Resolved: 2026-02-28**

---

### T-BUILD-GUARDIAN: iOS Build Guardian Standing Assignment
- **Status:** ACTIVE (permanent)
- **Owner:** iOS Engineer (Lead)
- **Decision:** D015 (LOCKED)
- **Summary:** Ongoing responsibility to verify iOS build integrity on every PR touching `ios/`. Includes running pre-merge gate script, approving `ios/` merges, and escalating cross-agent build breaks per `governance/ORCHESTRATOR_POLICY_build_guardian.md`.
