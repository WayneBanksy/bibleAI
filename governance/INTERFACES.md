# Interfaces / Contracts (v0)

<!-- Owner: Backend Engineer | Contributors: ML Engineer
     Last updated: 2026-02-22 | Status: LOCKED (contract phase) -->

---

## 1. Global Conventions

### 1.1 Auth
All protected endpoints require:
```
Authorization: Bearer <jwt>
```
JWT claims:
- `sub`: user_id (opaque UUID)
- `exp`: expiry timestamp (1-hour window)
- `iat`: issued at

### 1.2 Request Tracing
```
X-Request-ID: <uuid>   # client-generated; propagated through all logs
```
If omitted, server generates one and echoes it in the response header.

### 1.3 Content-Type
- Requests: `Content-Type: application/json`
- SSE stream: server responds with `Content-Type: text/event-stream; charset=utf-8`

### 1.4 Error Schema (all endpoints)
```json
{
  "error": {
    "code": "string",         // machine-readable, snake_case (see table below)
    "message": "string",      // human-readable
    "request_id": "uuid",
    "details": {}             // optional, endpoint-specific structured data
  }
}
```

| code | HTTP Status | Meaning |
|------|-------------|---------|
| `unauthenticated` | 401 | Missing or invalid JWT |
| `forbidden` | 403 | Valid JWT, insufficient scope |
| `not_found` | 404 | Resource does not exist |
| `conflict` | 409 | Idempotency key collision (duplicate `client_message_id`) |
| `validation_error` | 422 | Request body failed schema validation |
| `rate_limited` | 429 | Too many requests; include `Retry-After` header |
| `internal_error` | 500 | Server-side fault |

---

## 2. Auth Endpoints

### POST /v1/auth/token
Exchange an Apple ID token for a server-issued JWT.
In development, a `password` grant may be enabled behind a feature flag.

**Request:**
```json
{
  "grant_type": "apple_id_token",
  "id_token": "string"
}
```

**Response 200:**
```json
{
  "access_token": "string",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

---

## 3. Session Endpoints

### POST /v1/sessions
Create a new chat session.

**Request:**
```json
{
  "mode": "support_session | guided_program | bible_reference | prayer_builder",
  "translation_preference": "ESV | NIV | KJV | NKJV | NLT | CSB",
  "tone_preference": "reflective | encouraging | neutral"
}
```
`mode` is required. `translation_preference` and `tone_preference` are optional; server defaults apply if omitted.

**Response 201:**
```json
{
  "session_id": "uuid",
  "mode": "support_session",
  "translation_preference": "NIV",
  "tone_preference": "reflective",
  "created_at": "ISO 8601"
}
```

---

### GET /v1/sessions/{session_id}
Retrieve session metadata.

**Response 200:**
```json
{
  "session_id": "uuid",
  "mode": "string",
  "status": "active | ended",
  "message_count": 12,
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601"
}
```

---

## 4. Message Endpoints

### POST /v1/sessions/{session_id}/messages
Send a user message. Server persists the message, runs the safety pre-check, and triggers
a streaming response over the SSE channel. Returns immediately (202) while processing continues.

**Headers:**
```
Authorization: Bearer <jwt>
Idempotency-Key: <client_message_id>   # same UUID as body field; duplicated for HTTP-level deduplication
```

**Request:**
```json
{
  "text": "string",              // required; max 2000 chars
  "client_message_id": "uuid",  // client-generated; unique per session (idempotency key)
  "input_mode": "text | voice_transcript"
}
```

**Response 202 (accepted; stream begins on SSE channel):**
```json
{
  "message_id": "uuid",
  "client_message_id": "uuid",
  "session_id": "uuid",
  "status": "processing"
}
```

**Response 409 (duplicate `client_message_id`):**
```json
{
  "error": {
    "code": "conflict",
    "message": "Duplicate client_message_id for this session.",
    "request_id": "uuid",
    "details": {
      "original_message_id": "uuid",
      "client_message_id": "uuid"
    }
  }
}
```

**Idempotency Rules:**
- `(session_id, client_message_id)` is unique-constrained in the DB.
- On duplicate: return 409 with the original `message_id`. Do NOT re-process.
- iOS client should use the 409 response to reconnect to the SSE channel if the stream was dropped.
- A successful 202 response is NOT a guarantee the message was processed; the SSE stream carries the actual result.

---

## 5. Stream Events (SSE)

### GET /v1/sessions/{session_id}/events

**Headers:**
```
Authorization: Bearer <jwt>
Accept: text/event-stream
Cache-Control: no-cache
```

**Query Params:**
- `last_event_id` (optional, string): Resume from this event ID. Server replays missed events
  within a 60-second window. After that window, the client must re-fetch.

**SSE Wire Format:**
```
id: <event_id>
event: <event_type>
data: <json_payload>
\n\n
```

---

### Event: `heartbeat`
Sent every 15 seconds to keep the connection alive. iOS must not parse as data.

```json
{}
```

---

### Event: `token.delta`
A single streaming text chunk of the assistant response. Emitted sequentially.

```json
{
  "message_id": "uuid",
  "delta": "string",
  "sequence": 42
}
```
- `sequence` is monotonically increasing per message (starts at 1).
- Client assembles `delta` chunks in order to reconstruct the full text.

---

### Event: `message.final`
Emitted once, after all `token.delta` events for a message. Contains the complete structured payload.
The assembled text in `text` must match the concatenated `delta` values.

```json
{
  "message_id": "uuid",
  "session_id": "uuid",
  "text": "string",
  "structured": {
    "reflection": "string",
    "prayer": "string | null",
    "next_step": "string | null",
    "reflection_question": "string | null"
  },
  "citations": [
    {
      "translation_id": "ESV | NIV | KJV | NKJV | NLT | CSB",
      "book": "string",
      "chapter": 1,
      "verse_start": 1,
      "verse_end": 3,
      "verse_id_list": ["uuid", "uuid"],
      "quote": "string"
    }
  ],
  "risk": {
    "risk_level": "none | low | medium | high",
    "categories": [],
    "action": "allow | caution | refuse | escalate"
  },
  "model_version": "string",
  "created_at": "ISO 8601"
}
```

**Citation field rules:**
- `verse_id_list`: FK references to `bible_verses.id`; populated only after backend validation.
- `quote`: validated verbatim text from the DB; NEVER LLM-generated.
- If a citation fails validation, it is stripped before `message.final` is emitted; client never sees unvalidated citations.

---

### Event: `risk.interrupt`
Emitted **instead of** `token.delta` / `message.final` when `action=escalate`. LLM is NOT invoked.
This event must be the only event emitted for a crisis turn (no tokens, no final message).

```json
{
  "risk_level": "high",
  "action": "escalate",
  "categories": ["self_harm"],
  "message": "string",
  "resources": [
    { "label": "988 Suicide & Crisis Lifeline", "contact": "Call or text 988" },
    { "label": "Crisis Text Line", "contact": "Text HOME to 741741" },
    { "label": "Emergency Services", "contact": "Call 911" }
  ],
  "requires_acknowledgment": true
}
```

- `message`: comes from a pre-approved deterministic template (see SAFETY_POLICY.md §2.3).
- `requires_acknowledgment`: when `true`, iOS MUST show a blocking acknowledgment screen before the user can type again.
- After acknowledgment, iOS may resume the SSE connection; server decides if chat can continue.

---

### Event: `stream.error`
Emitted when server-side processing fails after the stream has begun (i.e., after 202 was returned).

```json
{
  "code": "string",
  "message": "string",
  "retryable": true
}
```

---

## 6. Safety Report Endpoint

### POST /v1/safety/report
User-submitted report on an assistant message.

**Request:**
```json
{
  "session_id": "uuid",
  "message_id": "uuid",
  "reason": "inappropriate | incorrect_scripture | harmful | other",
  "details": "string | null"
}
```
`details` max 500 chars; optional.

**Response 200:**
```json
{
  "ok": true,
  "report_id": "uuid"
}
```

---

## 7. Assistant Structured Output

<!-- Owner: ML Engineer | Backend enforces validation before streaming -->

The LLM is instructed via the system prompt to return **strict JSON only**. Backend validates
the JSON before streaming tokens to the client.

### 7.1 LLM Output JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["reflection"],
  "additionalProperties": false,
  "properties": {
    "reflection": {
      "type": "string",
      "minLength": 1,
      "maxLength": 1500,
      "description": "Primary reflective response. Must not contain diagnosis, treatment advice, or coercive religious language."
    },
    "verse_block": {
      "type": "array",
      "maxItems": 5,
      "items": {
        "type": "object",
        "required": ["translation_id", "book", "chapter", "verse_start"],
        "additionalProperties": false,
        "properties": {
          "translation_id": {
            "type": "string",
            "enum": ["ESV", "NIV", "KJV", "NKJV", "NLT", "CSB"]
          },
          "book": { "type": "string" },
          "chapter": { "type": "integer", "minimum": 1 },
          "verse_start": { "type": "integer", "minimum": 1 },
          "verse_end": { "type": "integer", "minimum": 1 }
        }
      },
      "description": "Scripture citations. Each must be validated against bible_verses table. If uncertain, omit rather than guess."
    },
    "prayer": {
      "type": ["string", "null"],
      "maxLength": 800
    },
    "next_step": {
      "type": ["string", "null"],
      "maxLength": 400,
      "description": "Suggested non-clinical action (e.g., journaling, talking to a trusted person)."
    },
    "reflection_question": {
      "type": ["string", "null"],
      "maxLength": 300
    }
  }
}
```

### 7.2 Validation Rules (Backend Enforcement)

| Check | Failure Action |
|-------|----------------|
| JSON not parseable | Emit `stream.error`; log `citation_integrity` safety event |
| `reflection` field missing | Emit `stream.error` |
| `verse_block` entry not found in `bible_verses` | Strip that citation; fallback to uncited reflection; log `citation_integrity` |
| `verse_block` text hash mismatch | Strip that citation; log `citation_integrity` |
| `reflection` contains prohibited phrase (SAFETY_POLICY.md §3, §4) | Post-check classifier flags; emit `risk.interrupt` or `refuse` action |
| `verse_end` < `verse_start` | Strip that citation; log `citation_integrity` |

### 7.3 Prompt Rules (enforced in system prompt, not code)
- The assistant must be reflective, not authoritative.
- Avoid shame, condemnation, or divine certainty claims.
- Never provide medical or clinical guidance.
- If uncertain about a verse, omit citations rather than guess.
- Output must be valid JSON with no surrounding prose or markdown.

---

## 8. SafetyCheckResult Schema

<!-- Owner: ML Engineer | Consumed by: Backend (pre-check and post-check pipeline stages) -->

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["risk_level", "categories", "action"],
  "additionalProperties": false,
  "properties": {
    "risk_level": {
      "type": "string",
      "enum": ["none", "low", "medium", "high"]
    },
    "categories": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": [
          "self_harm",
          "abuse",
          "medical_advice",
          "hate",
          "sexual",
          "violence",
          "spiritual_coercion",
          "citation_integrity"
        ]
      }
    },
    "action": {
      "type": "string",
      "enum": ["allow", "caution", "refuse", "escalate"]
    },
    "rationale_codes": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Short audit codes only. No raw user text included."
    }
  }
}
```

---

## 9. DB Schema Proposal

<!-- Owner: Backend Engineer | Status: Proposal — requires Alembic migration before implementation -->

### Table: `users`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK, `DEFAULT gen_random_uuid()` |
| `external_id` | TEXT | UNIQUE NOT NULL (Apple/Google `sub`) |
| `created_at` | TIMESTAMPTZ | NOT NULL, `DEFAULT now()` |
| `consent_accepted_at` | TIMESTAMPTZ | NULL |

---

### Table: `consents`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `user_id` | UUID | FK → `users.id`, NOT NULL |
| `disclaimer_version` | TEXT | NOT NULL |
| `accepted_at` | TIMESTAMPTZ | NOT NULL |
| `privacy_prefs` | JSONB | NULL |

---

### Table: `sessions`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `user_id` | UUID | FK → `users.id`, NOT NULL |
| `mode` | TEXT | NOT NULL, `CHECK (mode IN ('support_session','guided_program','bible_reference','prayer_builder'))` |
| `status` | TEXT | NOT NULL, `DEFAULT 'active'`, `CHECK (status IN ('active','ended'))` |
| `translation_preference` | TEXT | NULL, `CHECK (translation_preference IN ('ESV','NIV','KJV','NKJV','NLT','CSB'))` |
| `tone_preference` | TEXT | NULL, `CHECK (tone_preference IN ('reflective','encouraging','neutral'))` |
| `started_at` | TIMESTAMPTZ | NOT NULL, `DEFAULT now()` |
| `ended_at` | TIMESTAMPTZ | NULL |

---

### Table: `messages`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `session_id` | UUID | FK → `sessions.id`, NOT NULL |
| `role` | TEXT | NOT NULL, `CHECK (role IN ('user','assistant','system'))` |
| `text_hash` | TEXT | NULL (SHA-256 of raw text; stored for integrity checks) |
| `content_encrypted` | BYTEA | NULL (AES-256-GCM; keyed per user; raw text NOT stored in plaintext) |
| `metadata` | JSONB | NULL |
| `client_message_id` | UUID | NULL (only set for `role='user'`) |
| `model_version` | TEXT | NULL (only set for `role='assistant'`) |
| `created_at` | TIMESTAMPTZ | NOT NULL, `DEFAULT now()` |
| UNIQUE | | `(session_id, client_message_id) WHERE client_message_id IS NOT NULL` |

---

### Table: `bible_verses`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `translation_id` | TEXT | NOT NULL, `CHECK (translation_id IN ('ESV','NIV','KJV','NKJV','NLT','CSB'))` |
| `book` | TEXT | NOT NULL |
| `chapter` | INTEGER | NOT NULL |
| `verse` | INTEGER | NOT NULL |
| `text` | TEXT | NOT NULL |
| `text_hash` | TEXT | NOT NULL (SHA-256 of `text`) |
| UNIQUE | | `(translation_id, book, chapter, verse)` |

Index: `(translation_id, book, chapter, verse)` — used heavily by citation validation.

---

### Table: `verse_citations`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `message_id` | UUID | FK → `messages.id`, NOT NULL |
| `translation_id` | TEXT | NOT NULL |
| `book` | TEXT | NOT NULL |
| `chapter` | INTEGER | NOT NULL |
| `verse_start` | INTEGER | NOT NULL |
| `verse_end` | INTEGER | NOT NULL |
| `verse_id_list` | UUID[] | NOT NULL (FK references to `bible_verses.id`) |
| `validated` | BOOLEAN | NOT NULL, `DEFAULT false` |
| `created_at` | TIMESTAMPTZ | NOT NULL, `DEFAULT now()` |

---

### Table: `safety_events`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `message_id` | UUID | FK → `messages.id`, NOT NULL |
| `check_stage` | TEXT | NOT NULL, `CHECK (check_stage IN ('pre','post'))` |
| `risk_level` | TEXT | NOT NULL |
| `categories` | TEXT[] | NOT NULL |
| `action` | TEXT | NOT NULL |
| `rationale_codes` | TEXT[] | NULL |
| `model_version` | TEXT | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL, `DEFAULT now()` |

---

### Table: `reports`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `session_id` | UUID | FK → `sessions.id`, NOT NULL |
| `message_id` | UUID | FK → `messages.id`, NOT NULL |
| `user_id` | UUID | FK → `users.id`, NOT NULL |
| `reason` | TEXT | NOT NULL |
| `details_hash` | TEXT | NULL (SHA-256 of details text; raw details NOT stored in plaintext) |
| `status` | TEXT | NOT NULL, `DEFAULT 'open'`, `CHECK (status IN ('open','reviewed','closed'))` |
| `created_at` | TIMESTAMPTZ | NOT NULL, `DEFAULT now()` |

---

### Required Indexes (minimum)
| Table | Index |
|-------|-------|
| `messages` | `(session_id, created_at)` |
| `messages` | `(session_id, client_message_id) WHERE client_message_id IS NOT NULL` — UNIQUE |
| `bible_verses` | `(translation_id, book, chapter, verse)` — UNIQUE |
| `verse_citations` | `(message_id)` |
| `safety_events` | `(message_id)` |
| `sessions` | `(user_id, started_at)` |

### pgvector Extension

Required for RAG retrieval. Enable with `CREATE EXTENSION IF NOT EXISTS vector;` in migrations.

---

### Table: `verse_embeddings`

<!-- Owner: Backend Engineer | Spec: D010 (LOCKED) -->

Separate table (not a column on `bible_verses`) to allow multiple embedding models to coexist
without schema migrations when the model changes. See DECISIONS.md D010 for full spec rationale.

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK, `DEFAULT gen_random_uuid()` |
| `verse_id` | UUID | FK → `bible_verses.id`, NOT NULL |
| `embedding_model` | TEXT | NOT NULL (e.g., `'text-embedding-3-small'`) |
| `embedding` | `vector(1536)` | NOT NULL — dimensionality from D010; update if model changes |
| `created_at` | TIMESTAMPTZ | NOT NULL, `DEFAULT now()` |
| UNIQUE | | `(verse_id, embedding_model)` |

**HNSW Index DDL (from D010):**

```sql
CREATE INDEX verse_embeddings_hnsw_idx
  ON verse_embeddings
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

**Query-time session parameter** (set per connection or per query in the RAG retrieval path):

```sql
SET hnsw.ef_search = 60;
```

**Similarity query pattern** (cosine distance; lower = more similar):

```sql
SELECT ve.verse_id, ve.embedding <=> $1 AS distance
FROM verse_embeddings ve
WHERE ve.embedding_model = 'text-embedding-3-small'
ORDER BY distance
LIMIT 12;
```

**Migration notes:**
- If `embedding_model` changes, the existing rows for the old model remain valid.
- A full re-embed is required only for the new model; insert new rows with the new `embedding_model` value.
- If vector `dimensions` change (i.e., a different model with different dim), the `vector(N)` column type must be altered and the index rebuilt. File a task before proceeding.

### Updated Required Indexes (minimum)

| Table | Index |
|-------|-------|
| `messages` | `(session_id, created_at)` |
| `messages` | `(session_id, client_message_id) WHERE client_message_id IS NOT NULL` — UNIQUE |
| `bible_verses` | `(translation_id, book, chapter, verse)` — UNIQUE |
| `verse_citations` | `(message_id)` |
| `safety_events` | `(message_id)` |
| `sessions` | `(user_id, started_at)` |
| `verse_embeddings` | HNSW index on `(embedding vector_cosine_ops)` — see DDL above |
| `verse_embeddings` | `(verse_id, embedding_model)` — UNIQUE |
