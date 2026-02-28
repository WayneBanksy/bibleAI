"""
Citation validation module — T010.

Public interface:
    validate_citations(verse_block, db) -> list[CitationResult]

Called by the T007 pipeline after LLM response to validate every
verse_block entry against the bible_verses table before returning
citations to the client.

Rules (INTERFACES.md §7.2 + SAFETY_POLICY.md §5):
  1. Range check: verse_end < verse_start → strip, "range_invalid"
  2. DB lookup: SELECT rows WHERE verse IN [verse_start..verse_end]
  3. Not found: if verse_start absent in results → strip, "not_found"
  4. Hash check: SHA-256(row.text) must equal row.text_hash (all-or-nothing)
  5. Validated: all checks pass → verse_id_list + verbatim quote

Never raises — all failures returned as stripped CitationResult entries.

Dependency direction: pipeline → citation (never the reverse).
This module does NOT import from pipeline.py, streaming.py, or routers/.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BibleVerse


@dataclass
class CitationResult:
    """Validation outcome for a single verse_block entry."""

    verse_block_entry: dict
    validated: bool
    verse_id_list: list[UUID] = field(default_factory=list)
    quote: str = ""
    # None when validated=True; "not_found" | "hash_mismatch" | "range_invalid" otherwise
    strip_reason: str | None = None


async def validate_citations(
    verse_block: list[dict],
    db: AsyncSession,
) -> list[CitationResult]:
    """
    Validate each entry in verse_block against the bible_verses table.

    Returns a CitationResult for each input entry in the same order.
    Strips (validated=False) any entry that fails any check per
    INTERFACES.md §7.2 and SAFETY_POLICY.md §5.

    Does not raise; all failures are returned as stripped results.
    """
    results: list[CitationResult] = []
    for entry in verse_block:
        results.append(await _validate_entry(entry, db))
    return results


async def _validate_entry(entry: dict, db: AsyncSession) -> CitationResult:
    """Validate a single verse_block entry. Never raises."""

    # 0. Guard: malformed entries (None, missing keys, wrong type, etc.)
    try:
        translation_id: str = entry["translation_id"]
        book: str = entry["book"]
        chapter: int = entry["chapter"]
        verse_start: int = entry["verse_start"]
        verse_end: int = entry.get("verse_end", verse_start)
    except (KeyError, TypeError, AttributeError):
        return CitationResult(
            verse_block_entry=entry,
            validated=False,
            strip_reason="not_found",
        )

    # 1. Range check — no DB hit required
    if verse_end < verse_start:
        return CitationResult(
            verse_block_entry=entry,
            validated=False,
            strip_reason="range_invalid",
        )

    # 2. DB lookup — all verses in [verse_start, verse_end] ordered by verse number
    try:
        stmt = (
            select(BibleVerse)
            .where(
                and_(
                    BibleVerse.translation_id == translation_id,
                    BibleVerse.book == book,
                    BibleVerse.chapter == chapter,
                    BibleVerse.verse >= verse_start,
                    BibleVerse.verse <= verse_end,
                )
            )
            .order_by(BibleVerse.verse)
        )
        result = await db.execute(stmt)
        rows: list[BibleVerse] = list(result.scalars().all())
    except Exception:
        return CitationResult(
            verse_block_entry=entry,
            validated=False,
            strip_reason="not_found",
        )

    # 3. Not found: verse_start must be present as the first returned row
    if not rows or rows[0].verse != verse_start:
        return CitationResult(
            verse_block_entry=entry,
            validated=False,
            strip_reason="not_found",
        )

    # 4. Hash check — all-or-nothing: any single row mismatch strips the citation
    for row in rows:
        expected_hash = hashlib.sha256(row.text.encode()).hexdigest()
        if row.text_hash != expected_hash:
            return CitationResult(
                verse_block_entry=entry,
                validated=False,
                strip_reason="hash_mismatch",
            )

    # 5. All checks passed
    return CitationResult(
        verse_block_entry=entry,
        validated=True,
        verse_id_list=[row.id for row in rows],
        quote=" ".join(row.text for row in rows),
    )
