# Bible Corpus — Source Provenance & Ingestion Guide

## KJV — King James Version (Public Domain)

### Source

`data/kjv_public_domain.json` is derived from the public-domain KJV text
distributed by Thiago Bodruk at:

> **https://github.com/thiagobodruk/bible** — file `json/en_kjv.json`

The source file is published under the public domain and was normalized from
its original nested structure (books → chapters → verse arrays) into the flat
format used by this project (see §File Format below).

**No verse text was modified**. The text is verbatim KJV, including translator
insertion markers (`{word}`) which are part of the traditional KJV presentation.

**Verse count**: 31,100 verses across 66 canonical books (within the accepted
±5 tolerance for textual variants from the traditional count of 31,102).

---

## File Format

All source files must be JSON arrays with one object per verse:

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

| Field     | Type    | Requirement                                              |
|-----------|---------|----------------------------------------------------------|
| `book`    | string  | Full English name (e.g., "Genesis", "Psalms", "Revelation") |
| `chapter` | integer | ≥ 1                                                      |
| `verse`   | integer | ≥ 1                                                      |
| `text`    | string  | Verbatim verse text — no embedded verse numbers, no HTML |

Text must be UTF-8. The ingestion script computes `text_hash = SHA-256(text)`
and stores it in `bible_verses.text_hash` for downstream integrity validation.

---

## Adding a Licensed Translation

Licensed translations (NIV, ESV, NLT, CSB, NKJV) **must not be committed**
to this repository. The `data/.gitignore` enforces this.

To add a licensed translation:

1. Obtain a license from the copyright holder (e.g., Biblica for NIV, Crossway
   for ESV, Tyndale for NLT, Holman for CSB, Thomas Nelson for NKJV).
2. Obtain or convert the text into the file format described above.
3. Save the file to `scripts/data/<translation_id_lowercase>.json`
   (e.g., `scripts/data/esv.json`).
4. Run the ingestion script:
   ```bash
   uv run python scripts/ingest_bible_corpus.py \
     --translation ESV \
     --source scripts/data/esv.json \
     --no-embeddings
   ```
5. Verify:
   ```bash
   uv run python scripts/verify_corpus.py --translation ESV
   ```

The ingestion script exits cleanly with a warning if the source file is not
present — it does not fail the build.

---

## Running the Ingestion Pipeline

### Prerequisites

- Docker + docker-compose (for the local Postgres + pgvector DB)
- `uv` (https://docs.astral.sh/uv)
- Alembic migrations applied (`alembic upgrade head`)

### Step-by-step

```bash
# 1. Start the dev DB (if not already running)
cd backend && docker-compose up -d db

# 2. Apply migrations (if not already applied)
uv run alembic upgrade head

# 3. Ingest KJV — fast path (no embeddings, no API key needed)
uv run python scripts/ingest_bible_corpus.py \
  --translation KJV \
  --source scripts/data/kjv_public_domain.json \
  --no-embeddings

# 4. Verify ingestion
uv run python scripts/verify_corpus.py

# 5. (Optional) Generate embeddings — requires OPENAI_API_KEY
export OPENAI_API_KEY=sk-...
uv run python scripts/ingest_bible_corpus.py \
  --translation KJV \
  --source scripts/data/kjv_public_domain.json \
  --batch-size 100

# 6. Idempotency check — should report 0 inserts, 0 updates
uv run python scripts/ingest_bible_corpus.py \
  --translation KJV \
  --source scripts/data/kjv_public_domain.json \
  --no-embeddings
```

### Cost estimate

- **KJV**: 31,100 verses × ~8 tokens/verse ≈ 250K tokens
- `text-embedding-3-small` pricing: ~$0.02 / 1M tokens
- **Estimated cost: < $0.01 for full KJV**

### Rate limiting

With `--batch-size 100`, KJV requires ~312 API calls. This is well within
OpenAI's default embedding rate limits (3,000 RPM). Use `--delay-ms <N>` if
you need to throttle (default: 0).

---

## Encoding Requirements

- All text stored as UTF-8.
- No HTML tags or embedded verse numbers in the `text` field.
- `text_hash` = `SHA-256(text.encode("utf-8")).hexdigest()` (64-char hex string).

---

## Governance Notes

- Translation allowlist is locked in DECISIONS.md D005: ESV, NIV, KJV, NKJV, NLT, CSB.
- Embedding model is locked in DECISIONS.md D010: `text-embedding-3-small`, dim=1536.
- The `bible_verses` and `verse_embeddings` table schemas are locked in INTERFACES.md §9.
- Do not modify verse text — citation integrity (SAFETY_POLICY.md §5) depends on
  verbatim storage: the backend validates `text_hash` before returning any citation.
