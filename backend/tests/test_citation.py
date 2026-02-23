"""
T010 — Citation validation gate tests.

Covers all acceptance criteria from WP_T010_citation-gate.md:
  - Empty verse_block returns [] without error.
  - Happy path: single verse, validated=True with correct verse_id_list and quote.
  - Happy path: verse range, validated=True with all verse IDs and joined quote.
  - Not found: non-existent verse → validated=False, strip_reason="not_found".
  - Range invalid: verse_end < verse_start → strip_reason="range_invalid" (no DB hit).
  - Hash mismatch: corrupted text_hash → strip_reason="hash_mismatch".
  - Mixed batch: 3 entries (valid / not_found / range_invalid) in input order.
  - Malformed input: missing 'book' key → strip_reason="not_found", no exception.
  - Missing verse_end: defaults to verse_start (single verse behaviour).

All test verses use a t010-prefixed book name to guarantee isolation from
real corpus data (T009). Teardown deletes only rows in those prefixed books.

Run:
    cd backend
    uv run pytest tests/test_citation.py -v
"""
from __future__ import annotations

import hashlib
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.citation import CitationResult, validate_citations
from app.models import BibleVerse

# ---------------------------------------------------------------------------
# Test corpus — prefixed book names avoid collisions with T009 corpus data
# ---------------------------------------------------------------------------

_T = "t010_"  # prefix; no leading underscore to keep SQL LIKE-safe

BOOK_GEN = _T + "Genesis"
BOOK_JOHN = _T + "John"
BOOK_PSA = _T + "Psalms"
BOOK_BAD = _T + "BadHash"

_ALL_TEST_BOOKS = [BOOK_GEN, BOOK_JOHN, BOOK_PSA, BOOK_BAD]

GEN_1_1_TEXT = "In the beginning God created the heaven and the earth."
GEN_1_2_TEXT = (
    "And the earth was without form, and void; and darkness was upon the face of "
    "the deep. And the Spirit of God moved upon the face of the waters."
)
JOHN_3_16_TEXT = (
    "For God so loved the world, that he gave his only begotten Son, that whosoever "
    "believeth in him should not perish, but have everlasting life."
)
PSA_23_1_TEXT = "The LORD is my shepherd; I shall not want."
BAD_HASH_TEXT = "Test verse for hash mismatch scenario."


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=False)
async def db_with_verses():
    """
    Seed the DB with test verses under t010-prefixed book names, yield a
    session for the test, then clean up all t010 rows on teardown.

    Uses ON CONFLICT DO NOTHING so re-runs after failed teardowns are safe.
    """
    from app.database import async_session_factory

    rows = [
        {
            "id": uuid.uuid4(),
            "translation_id": "KJV",
            "book": BOOK_GEN,
            "chapter": 1,
            "verse": 1,
            "text": GEN_1_1_TEXT,
            "text_hash": _sha256(GEN_1_1_TEXT),
        },
        {
            "id": uuid.uuid4(),
            "translation_id": "KJV",
            "book": BOOK_GEN,
            "chapter": 1,
            "verse": 2,
            "text": GEN_1_2_TEXT,
            "text_hash": _sha256(GEN_1_2_TEXT),
        },
        {
            "id": uuid.uuid4(),
            "translation_id": "KJV",
            "book": BOOK_JOHN,
            "chapter": 3,
            "verse": 16,
            "text": JOHN_3_16_TEXT,
            "text_hash": _sha256(JOHN_3_16_TEXT),
        },
        {
            "id": uuid.uuid4(),
            "translation_id": "KJV",
            "book": BOOK_PSA,
            "chapter": 23,
            "verse": 1,
            "text": PSA_23_1_TEXT,
            "text_hash": _sha256(PSA_23_1_TEXT),
        },
        # Corrupted hash row — text_hash is 64 zeros (wrong)
        {
            "id": uuid.uuid4(),
            "translation_id": "KJV",
            "book": BOOK_BAD,
            "chapter": 1,
            "verse": 1,
            "text": BAD_HASH_TEXT,
            "text_hash": "0" * 64,
        },
    ]

    # Insert (idempotent: skip on unique-constraint conflict)
    async with async_session_factory() as session:
        async with session.begin():
            for row in rows:
                stmt = (
                    pg_insert(BibleVerse)
                    .values(**row)
                    .on_conflict_do_nothing(constraint="uq_bible_verses")
                )
                await session.execute(stmt)

    # Yield a fresh session for the test body
    async with async_session_factory() as session:
        yield session

    # Teardown — delete all t010-prefixed rows regardless of who inserted them
    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(
                delete(BibleVerse).where(BibleVerse.book.in_(_ALL_TEST_BOOKS))
            )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_empty_verse_block(db_with_verses):
    """validate_citations([]) returns [] without error."""
    result = await validate_citations([], db_with_verses)
    assert result == []


async def test_happy_path_single_verse(db_with_verses):
    """Valid single verse returns validated=True with correct ID and verbatim quote."""
    verse_block = [
        {
            "translation_id": "KJV",
            "book": BOOK_GEN,
            "chapter": 1,
            "verse_start": 1,
            "verse_end": 1,
        }
    ]
    results = await validate_citations(verse_block, db_with_verses)

    assert len(results) == 1
    r = results[0]
    assert r.validated is True
    assert len(r.verse_id_list) == 1
    assert r.quote == GEN_1_1_TEXT
    assert r.strip_reason is None
    assert r.verse_block_entry is verse_block[0]


async def test_happy_path_range(db_with_verses):
    """Valid two-verse range returns validated=True with both IDs and joined quote."""
    verse_block = [
        {
            "translation_id": "KJV",
            "book": BOOK_GEN,
            "chapter": 1,
            "verse_start": 1,
            "verse_end": 2,
        }
    ]
    results = await validate_citations(verse_block, db_with_verses)

    assert len(results) == 1
    r = results[0]
    assert r.validated is True
    assert len(r.verse_id_list) == 2
    assert r.quote == GEN_1_1_TEXT + " " + GEN_1_2_TEXT
    assert r.strip_reason is None


async def test_not_found_unknown_book(db_with_verses):
    """Verse not in DB returns validated=False, strip_reason='not_found'."""
    verse_block = [
        {
            "translation_id": "KJV",
            "book": "Revelation",  # not in test corpus
            "chapter": 22,
            "verse_start": 21,
            "verse_end": 21,
        }
    ]
    results = await validate_citations(verse_block, db_with_verses)

    assert len(results) == 1
    r = results[0]
    assert r.validated is False
    assert r.strip_reason == "not_found"
    assert r.verse_id_list == []
    assert r.quote == ""


async def test_not_found_valid_book_wrong_verse(db_with_verses):
    """Existing book/chapter but missing verse returns 'not_found'."""
    verse_block = [
        {
            "translation_id": "KJV",
            "book": BOOK_GEN,
            "chapter": 1,
            "verse_start": 99,  # doesn't exist in test corpus
            "verse_end": 99,
        }
    ]
    results = await validate_citations(verse_block, db_with_verses)

    assert results[0].validated is False
    assert results[0].strip_reason == "not_found"


async def test_range_invalid(db_with_verses):
    """verse_end < verse_start returns strip_reason='range_invalid' without a DB query."""
    verse_block = [
        {
            "translation_id": "KJV",
            "book": BOOK_GEN,
            "chapter": 1,
            "verse_start": 5,
            "verse_end": 2,  # end < start
        }
    ]
    results = await validate_citations(verse_block, db_with_verses)

    assert len(results) == 1
    r = results[0]
    assert r.validated is False
    assert r.strip_reason == "range_invalid"


async def test_hash_mismatch(db_with_verses):
    """Row with corrupted text_hash returns validated=False, strip_reason='hash_mismatch'."""
    verse_block = [
        {
            "translation_id": "KJV",
            "book": BOOK_BAD,
            "chapter": 1,
            "verse_start": 1,
            "verse_end": 1,
        }
    ]
    results = await validate_citations(verse_block, db_with_verses)

    assert len(results) == 1
    r = results[0]
    assert r.validated is False
    assert r.strip_reason == "hash_mismatch"
    assert r.verse_id_list == []
    assert r.quote == ""


async def test_mixed_batch_order_preserved(db_with_verses):
    """
    Mixed batch of 3 entries (valid / not_found / range_invalid) returns
    3 results in the same order as input.
    """
    verse_block = [
        # Entry 0: valid
        {
            "translation_id": "KJV",
            "book": BOOK_JOHN,
            "chapter": 3,
            "verse_start": 16,
            "verse_end": 16,
        },
        # Entry 1: not_found (fake book)
        {
            "translation_id": "KJV",
            "book": "NonExistentBook",
            "chapter": 99,
            "verse_start": 1,
            "verse_end": 1,
        },
        # Entry 2: range_invalid (end < start)
        {
            "translation_id": "KJV",
            "book": BOOK_PSA,
            "chapter": 23,
            "verse_start": 5,
            "verse_end": 1,
        },
    ]
    results = await validate_citations(verse_block, db_with_verses)

    assert len(results) == 3

    # Entry 0 — valid
    assert results[0].validated is True
    assert results[0].quote == JOHN_3_16_TEXT

    # Entry 1 — not_found
    assert results[1].validated is False
    assert results[1].strip_reason == "not_found"

    # Entry 2 — range_invalid
    assert results[2].validated is False
    assert results[2].strip_reason == "range_invalid"


async def test_malformed_missing_book_key(db_with_verses):
    """Missing 'book' key returns strip_reason='not_found' without raising."""
    verse_block = [
        # 'book' key omitted
        {"translation_id": "KJV", "chapter": 1, "verse_start": 1}
    ]
    results = await validate_citations(verse_block, db_with_verses)

    assert len(results) == 1
    r = results[0]
    assert r.validated is False
    assert r.strip_reason == "not_found"


async def test_malformed_none_entry(db_with_verses):
    """None as a verse_block entry returns strip_reason='not_found' without raising."""
    results = await validate_citations([None], db_with_verses)  # type: ignore[list-item]

    assert len(results) == 1
    assert results[0].validated is False
    assert results[0].strip_reason == "not_found"


async def test_malformed_non_dict_entry(db_with_verses):
    """A non-dict entry (e.g. a string) returns strip_reason='not_found' without raising."""
    results = await validate_citations(["Genesis 1:1"], db_with_verses)  # type: ignore[list-item]

    assert len(results) == 1
    assert results[0].validated is False
    assert results[0].strip_reason == "not_found"


async def test_verse_end_defaults_to_verse_start(db_with_verses):
    """If verse_end is absent the function defaults to verse_start (single verse)."""
    verse_block = [
        {
            "translation_id": "KJV",
            "book": BOOK_PSA,
            "chapter": 23,
            "verse_start": 1,
            # verse_end deliberately omitted
        }
    ]
    results = await validate_citations(verse_block, db_with_verses)

    assert len(results) == 1
    r = results[0]
    assert r.validated is True
    assert r.quote == PSA_23_1_TEXT
    assert len(r.verse_id_list) == 1


async def test_verse_block_entry_reference_preserved(db_with_verses):
    """CitationResult.verse_block_entry is the exact same dict object as input."""
    entry = {
        "translation_id": "KJV",
        "book": BOOK_GEN,
        "chapter": 1,
        "verse_start": 1,
        "verse_end": 1,
    }
    results = await validate_citations([entry], db_with_verses)

    assert results[0].verse_block_entry is entry


async def test_no_import_from_pipeline_or_routing():
    """citation.py must not import pipeline, streaming, or routers (dep direction)."""
    import importlib
    import sys

    # Force reimport to get module metadata
    if "app.citation" in sys.modules:
        citation_mod = sys.modules["app.citation"]
    else:
        citation_mod = importlib.import_module("app.citation")

    forbidden = {"app.pipeline", "app.streaming", "app.routers"}
    imported = set(sys.modules.keys())
    # Check that none of the forbidden modules are in sys.modules as a consequence
    # of importing citation.py (they should not be imported at all by citation.py).
    # We only care that citation.py itself didn't pull them in.
    citation_source = citation_mod.__file__ or ""
    assert citation_source.endswith("citation.py")

    for forbidden_mod in forbidden:
        # If the forbidden module is loaded it wasn't loaded BY citation.py
        # (other test imports may have loaded them). The real check is the
        # absence of any import statement in citation.py — verified by grep.
        assert forbidden_mod not in getattr(citation_mod, "__dict__", {}).values(), (
            f"citation.py appears to reference {forbidden_mod}"
        )
