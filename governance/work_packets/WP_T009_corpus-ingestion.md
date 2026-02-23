# Work Packet: T009 — Bible Corpus Ingestion

## Goal

Write the ingestion pipeline that loads the Bible corpus into the `bible_verses` table
and generates `text-embedding-3-small` embeddings into the `verse_embeddings` table.
This is a data pipeline task (scripts only). No application code is changed.

The output of this packet unblocks T010 (citation gate needs real data) and the RAG
retrieval path (T009-full, post-MVP). The ingestion must be idempotent: safe to re-run
on an already-populated DB.

**Translation scope for this packet:**
- KJV — public domain; seed corpus; required for dev and test fixtures
- NIV, ESV, NLT, CSB, NKJV — licensed; script accepts a data directory; rows inserted
  only if a properly formatted source file is present. Script must document the expected
  source format so licensing can be resolved separately.

## Owner

ML Engineer

## Branch / Worktree Name

`agent/ml/T009-corpus-ingestion`

## Scope (files allowed to change)

```
backend/scripts/
  ingest_bible_corpus.py      # NEW — main ingestion script: load verses + compute embeddings
  verify_corpus.py            # NEW — sanity-check script: counts, hash validation, embedding dim check
  README_corpus.md            # NEW — documents expected source file format + KJV source + licensing notes
  data/
    kjv_public_domain.json    # NEW — KJV corpus as JSON (public domain; must be committed)
    .gitignore                # NEW — ignore licensed translation files (e.g., esv.json, niv.json)
```

> No changes to application code (`backend/app/**`). No changes to Alembic migrations
> (the schema is already correct — `bible_verses` and `verse_embeddings` tables exist).

## Do Not Touch

- `governance/INTERFACES.md`
- `governance/DECISIONS.md`
- `governance/SAFETY_POLICY.md`
- `governance/TASKS.md`
- `governance/DEPENDENCIES.md`
- `backend/app/**`         (no application code changes)
- `backend/alembic/**`     (schema already supports this; no migration needed)
- Any file under `/ios/`

## Dependencies

- T003 backend scaffold — Done ✅ (DB running, Alembic migrations applied, tables exist)
- DECISIONS.md D010 — embedding spec (LOCKED ✅):
  - Model: `text-embedding-3-small`
  - Dimensions: 1536
  - Distance metric: cosine
  - `verse_embeddings` table + HNSW index: already in migration 0001
- DECISIONS.md D005 — allowed translations (LOCKED ✅): ESV, NIV, KJV, NKJV, NLT, CSB
- INTERFACES.md §9 — `bible_verses` + `verse_embeddings` table schemas — LOCKED ✅
- OpenAI API key in environment (`OPENAI_API_KEY`) — required for embedding generation

## Corpus Source Format

`ingest_bible_corpus.py` expects a JSON file per translation with the following structure:

```json
[
  {
    "book": "Genesis",
    "chapter": 1,
    "verse": 1,
    "text": "In the beginning God created the heaven and the earth."
  },
  ...
]
```

- `book`: full English name (e.g., "Genesis", "Psalms", "Revelation")
- `chapter`: integer ≥ 1
- `verse`: integer ≥ 1
- `text`: verbatim verse text (no verse numbers embedded in the string)

The ingestion script accepts: `--translation KJV --source data/kjv_public_domain.json`

For licensed translations, `README_corpus.md` must document where to obtain the source
file and how to name it. The script is intentionally designed to skip missing files with
a clear warning rather than fail.

## Ingestion Script Behavior

```
ingest_bible_corpus.py --translation KJV [--no-embeddings] [--batch-size 100]

Steps:
1. Load source JSON.
2. For each verse:
   a. Compute text_hash = SHA-256(text).hexdigest()
   b. UPSERT into bible_verses (translation_id, book, chapter, verse, text, text_hash)
      ON CONFLICT (translation_id, book, chapter, verse) DO UPDATE SET text=..., text_hash=...
      → idempotent: re-run is safe
3. Unless --no-embeddings:
   a. For all verses without a verse_embeddings row for this model:
      - Batch call OpenAI embeddings API (batch_size=100 texts per request, configurable)
      - UPSERT into verse_embeddings (verse_id, embedding_model, embedding)
        ON CONFLICT (verse_id, embedding_model) DO NOTHING
        → idempotent: skip existing embeddings
4. Log: total inserted, total updated, total embeddings generated, total skipped.
```

## Acceptance Criteria

- [ ] `kjv_public_domain.json` is committed and covers the full KJV canon (66 books, 31,102 verses; approximate total accepted ± 5 for textual variants).
- [ ] `ingest_bible_corpus.py --translation KJV --source scripts/data/kjv_public_domain.json` runs to completion against the local dev DB.
- [ ] After ingestion, `SELECT COUNT(*) FROM bible_verses WHERE translation_id='KJV'` returns > 31,000.
- [ ] `text_hash` for every row equals `SHA-256(text)` as a 64-char hex string.
- [ ] Running the script a second time on the same DB produces zero new inserts (idempotent).
- [ ] `ingest_bible_corpus.py --translation ESV --source scripts/data/esv.json` exits cleanly with a warning if `esv.json` is not present (does not raise an exception).
- [ ] Embedding generation: `--no-embeddings` flag skips the OpenAI API call entirely; script completes without `OPENAI_API_KEY` set.
- [ ] With `OPENAI_API_KEY` set: after running without `--no-embeddings`, `SELECT COUNT(*) FROM verse_embeddings WHERE embedding_model='text-embedding-3-small'` equals the `bible_verses` count.
- [ ] Embedding dimension: `SELECT array_length(embedding, 1) FROM verse_embeddings LIMIT 1` returns 1536.
- [ ] `verify_corpus.py` outputs a sanity report: row counts per translation, sample hash validation (spot-check 10 random rows), embedding dimension check, HNSW index existence check.
- [ ] `README_corpus.md` documents: KJV source provenance, expected file format, how to add a licensed translation, and that licensed translation files must NOT be committed (`.gitignore` enforces this).
- [ ] `.gitignore` in `scripts/data/` excludes `esv.json`, `niv.json`, `nkjv.json`, `nlt.json`, `csb.json` and any `*.json` not named `kjv_public_domain.json`.

## Test / Run Commands

```bash
# Start dev DB
cd backend && docker-compose up -d db

# Run Alembic migrations (if not already applied)
uv run alembic upgrade head

# Ingest KJV corpus (no embeddings — fast, no API key needed)
uv run python scripts/ingest_bible_corpus.py \
  --translation KJV \
  --source scripts/data/kjv_public_domain.json \
  --no-embeddings

# Verify ingestion
uv run python scripts/verify_corpus.py

# (Optional) Generate embeddings — requires OPENAI_API_KEY in env
export OPENAI_API_KEY=sk-...
uv run python scripts/ingest_bible_corpus.py \
  --translation KJV \
  --source scripts/data/kjv_public_domain.json \
  --batch-size 100

# Idempotency check — should report 0 inserts, 0 updates
uv run python scripts/ingest_bible_corpus.py \
  --translation KJV \
  --source scripts/data/kjv_public_domain.json \
  --no-embeddings
```

## Notes / Risks

- **KJV source:** Use the public-domain KJV text (e.g., from the Crosswire Bible Society or similar authoritative public domain releases). Document the exact source URL in `README_corpus.md`. Do not modify verse text — ingestion must be verbatim.
- **Embedding cost estimate:** 31,102 KJV verses × average ~8 tokens/verse ≈ 250K tokens. At `text-embedding-3-small` pricing (~$0.02/1M tokens), full KJV embedding costs < $0.01. Safe to run in dev.
- **Rate limiting:** OpenAI API default rate limits (3,000 RPM for embedding). With batch_size=100, KJV requires ~312 API calls — well within limits. Include a `--delay-ms` flag (default 0) for throttle control.
- **Encoding:** All text must be stored as UTF-8. No verse numbers or HTML tags embedded in the text field.
- **HNSW index:** The index is already created by Alembic migration 0001. It will be populated automatically as rows are inserted into `verse_embeddings`. No separate index-build step is needed.
- **T010 dependency note:** T010's `bible_verses_seed.sql` fixture provides minimal rows for unit tests; T009 provides the full production corpus. T010 does not depend on T009 being merged first.
- **PR title suggestion:** `feat(ml): T009 Bible corpus ingestion — KJV load, text hashes, pgvector embeddings`
