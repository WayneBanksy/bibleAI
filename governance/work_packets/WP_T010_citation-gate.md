# Work Packet: T010 — Citation Validation Gate

## Goal

Implement `backend/app/citation.py`: the citation validation module that resolves
LLM-proposed `verse_block` entries against the `bible_verses` database table, strips
unvalidatable citations, and logs `citation_integrity` safety events. This module is
consumed by the T007 pipeline but is implemented independently in its own file.

The DB schema and validation rules are already fully specified in INTERFACES.md §7.2
and SAFETY_POLICY.md §5. No governance changes are needed.

## Owner

Backend Engineer

## Branch / Worktree Name

`agent/backend/T010-citation-gate`

## Scope (files allowed to change)

```
backend/app/
  citation.py            # NEW — citation validation module (primary deliverable)

backend/tests/
  test_citation.py       # NEW — unit tests + DB integration tests for citation.py
  fixtures/
    bible_verses_seed.sql  # NEW — minimal KJV verse rows for test fixtures
```

> **No other files.** In particular, do NOT modify `routers/messages.py`
> (T007's scope) or `streaming.py`. T007 imports `citation.py` via:
> `from app.citation import validate_citations`

## Do Not Touch

- `governance/INTERFACES.md`
- `governance/DECISIONS.md`
- `governance/SAFETY_POLICY.md`
- `governance/TASKS.md`
- `governance/DEPENDENCIES.md`
- `backend/app/routers/messages.py`  (T007 owns this)
- `backend/app/pipeline.py`          (T007 owns this)
- `backend/app/streaming.py`         (T007 owns this)
- Any file under `/ios/`

## Dependencies

- T003 backend scaffold — Done ✅ (DB, models, Alembic migration, `bible_verses` table in schema)
- INTERFACES.md §7.2 — validation rules — LOCKED ✅
- INTERFACES.md §9 — `bible_verses` table schema — LOCKED ✅
- SAFETY_POLICY.md §5 — citation integrity rules — LOCKED ✅
- **Bible corpus:** The `bible_verses` table may be empty in dev (T009 handles ingestion). The test fixture file (`bible_verses_seed.sql`) must provide enough rows to test happy path and mismatch cases without requiring a full corpus load.
- **T007 (parallel):** T007 imports `validate_citations` from this module. The function signature must be stable before T007 merges. Signature is defined here.

## Public Interface Contract

This is the **only** public function. Do not change its signature after T007 begins.

```python
# backend/app/citation.py

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

class CitationResult:
    verse_block_entry: dict        # the original verse_block item from the LLM
    validated: bool
    verse_id_list: list[UUID]      # populated if validated=True; empty if stripped
    quote: str                     # verbatim text from DB if validated; "" if stripped
    strip_reason: str | None       # None if validated; one of: "not_found", "hash_mismatch", "range_invalid"

async def validate_citations(
    verse_block: list[dict],
    db: AsyncSession,
) -> list[CitationResult]:
    """
    Validate each entry in verse_block against the bible_verses table.
    Returns a CitationResult for each input entry.
    Strips (validated=False) any entry that fails any check in §7.2.
    Does not raise; all failures are returned as stripped results.
    """
    ...
```

## Validation Logic (from INTERFACES.md §7.2 + SAFETY_POLICY.md §5)

For each `verse_block` entry:

1. **Range check:** if `verse_end < verse_start` → strip, `strip_reason="range_invalid"`.
2. **DB lookup:** query `bible_verses` WHERE `(translation_id, book, chapter, verse)` in `[verse_start..verse_end]`. Collect all matching rows.
3. **Not found:** if zero rows match for `verse_start` → strip, `strip_reason="not_found"`.
4. **Hash check (per row):** compute `SHA-256(row.text)` and compare to `row.text_hash`. If mismatch → strip that citation, `strip_reason="hash_mismatch"`.
5. **Validated:** if all rows found and hashes match → `validated=True`; set `verse_id_list` to `[row.id for row in rows]`; set `quote` to the concatenated verse text (verses joined with a space separator).

**Note on partial ranges:** If a range covers 5 verses and 4 pass but 1 fails the hash check, strip the entire citation (not just the failing verse). All-or-nothing per citation.

## Acceptance Criteria

- [ ] `validate_citations(verse_block=[], db=...)` returns an empty list without error.
- [ ] Happy path: a verse_block entry with valid `(translation_id, book, chapter, verse_start, verse_end)` present in the DB returns `CitationResult(validated=True)` with correct `verse_id_list` and verbatim `quote`.
- [ ] Not found: a verse_block entry referencing a non-existent book/chapter/verse returns `CitationResult(validated=False, strip_reason="not_found")`.
- [ ] Range invalid: `verse_end < verse_start` returns `CitationResult(validated=False, strip_reason="range_invalid")` without querying the DB.
- [ ] Hash mismatch: a verse_block entry where the stored `text_hash` does not match `SHA-256(text)` returns `CitationResult(validated=False, strip_reason="hash_mismatch")`. (Simulate via test fixture with a corrupted `text_hash`.)
- [ ] Mixed batch: a verse_block with 3 entries (1 valid, 1 not_found, 1 range_invalid) returns 3 results in the same order as input, each with the correct `validated` flag.
- [ ] The function never raises an exception for malformed verse_block input (e.g., missing `book` key) — returns `strip_reason="not_found"` for any lookup failure.
- [ ] `test_citation.py` covers all cases above using the `bible_verses_seed.sql` fixture.
- [ ] The `bible_verses_seed.sql` fixture loads at least: Genesis 1:1 (KJV), John 3:16 (KJV), Psalm 23:1 (KJV) — enough to test range queries and happy-path validation.
- [ ] All existing `test_api.py` tests continue to pass.
- [ ] `citation.py` does not import from `pipeline.py`, `streaming.py`, or `routers/` (dependency direction: pipeline → citation, not the reverse).

## Test / Run Commands

```bash
cd backend

# Run citation-specific tests (uses test DB via conftest.py)
uv run pytest tests/test_citation.py -v

# Load the test fixture manually (optional, for ad-hoc inspection)
docker-compose up -d db
docker exec -i <pg_container> psql -U postgres -d bible_therapist \
  < tests/fixtures/bible_verses_seed.sql

# Run full suite to confirm no regressions
uv run pytest tests/ -v
```

## Notes / Risks

- **Bible corpus availability:** The `bible_verses` table will be empty in a freshly migrated dev DB until T009 (corpus ingestion) is run. The test fixture (`bible_verses_seed.sql`) provides the minimum rows needed for citation tests. Do NOT rely on T009 being merged first.
- **Translations with hash:** The `text_hash` column in `bible_verses` is `SHA-256(text)` stored as a hex string (64 chars). Make sure the fixture rows use `encode(sha256(text::bytea), 'hex')` or Python `hashlib.sha256(text.encode()).hexdigest()` consistently.
- **Parallel merge with T007:** T007 imports this module via `try/except ImportError`. Once this PR is merged, T007's stub fallback will no longer be used. Coordinate merge order with Backend Engineer on T007 if they share a review cycle.
- **No `messages.py` changes:** All DB write side effects (inserting `verse_citations` rows) are done in `pipeline.py` (T007), not in `citation.py`. `citation.py` is read-only with respect to the DB (it queries `bible_verses`; it does not insert).
- **PR title suggestion:** `feat(backend): T010 citation validation gate — DB lookup, hash check, strip-and-log`
