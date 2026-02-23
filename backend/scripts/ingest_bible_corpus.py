#!/usr/bin/env python3
"""
Bible corpus ingestion script — T009.

Loads a translation source JSON into bible_verses and optionally generates
text-embedding-3-small embeddings into verse_embeddings.

Usage:
    # KJV (no embeddings — fast, no API key needed):
    uv run python scripts/ingest_bible_corpus.py \\
        --translation KJV \\
        --source scripts/data/kjv_public_domain.json \\
        --no-embeddings

    # With embeddings (requires OPENAI_API_KEY):
    uv run python scripts/ingest_bible_corpus.py \\
        --translation KJV \\
        --source scripts/data/kjv_public_domain.json \\
        --batch-size 100

    # Missing source file — exits cleanly with a warning:
    uv run python scripts/ingest_bible_corpus.py \\
        --translation ESV \\
        --source scripts/data/esv.json

The script is idempotent: safe to re-run on an already-populated DB.
"""

import argparse
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path bootstrap: allow running from the backend/ directory without installing
# the package.  Add backend/ to sys.path so `app.*` imports resolve.
# ---------------------------------------------------------------------------
BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

import asyncio  # noqa: E402 (after sys.path tweak)

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
ALLOWED_TRANSLATIONS = {"ESV", "NIV", "KJV", "NKJV", "NLT", "CSB"}


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest a Bible translation corpus into bible_verses + verse_embeddings."
    )
    parser.add_argument(
        "--translation",
        required=True,
        choices=sorted(ALLOWED_TRANSLATIONS),
        help="Translation identifier (e.g. KJV, ESV).",
    )
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Path to the source JSON file (relative to CWD or absolute).",
    )
    parser.add_argument(
        "--no-embeddings",
        action="store_true",
        default=False,
        help="Skip embedding generation entirely (no OPENAI_API_KEY required).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of verses per OpenAI embedding API call (default: 100).",
    )
    parser.add_argument(
        "--delay-ms",
        type=int,
        default=0,
        help="Optional delay in milliseconds between embedding batches (for rate-limit control).",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "Override DATABASE_URL. Defaults to the DATABASE_URL environment variable "
            "or the value in backend/.env."
        ),
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Database URL resolution
# ---------------------------------------------------------------------------

def resolve_database_url(override: str | None) -> str:
    if override:
        return override
    # Try env var first
    env_val = os.environ.get("DATABASE_URL")
    if env_val:
        return env_val
    # Try loading from .env file next to this script's backend root
    dotenv_path = BACKEND_ROOT / ".env"
    if dotenv_path.exists():
        for line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(
        "No DATABASE_URL found. Set the DATABASE_URL environment variable, "
        "create backend/.env, or pass --database-url."
    )


# ---------------------------------------------------------------------------
# Source file loading + validation
# ---------------------------------------------------------------------------

def load_source(source_path: Path, translation: str) -> list[dict[str, Any]]:
    """
    Load and validate the source JSON.  Returns the list of verse dicts.
    Exits cleanly with a warning if the file is missing (not an error — the
    calling workflow may simply not have the licensed file available).
    """
    if not source_path.exists():
        print(
            f"[WARN] Source file not found: {source_path}\n"
            f"       Skipping {translation} ingestion.  "
            "See README_corpus.md for instructions on obtaining licensed translations."
        )
        sys.exit(0)

    print(f"[INFO] Loading {source_path} ...")
    with open(source_path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print(f"[ERROR] Expected a JSON array; got {type(data).__name__}. Aborting.")
        sys.exit(1)

    required_keys = {"book", "chapter", "verse", "text"}
    errors: list[str] = []
    for i, entry in enumerate(data):
        missing = required_keys - set(entry.keys())
        if missing:
            errors.append(f"  Entry {i}: missing keys {sorted(missing)}")
        if errors and len(errors) > 5:
            errors.append("  ... (truncated after 5 errors)")
            break

    if errors:
        print("[ERROR] Source JSON validation failed:\n" + "\n".join(errors))
        sys.exit(1)

    print(f"[INFO] Loaded {len(data):,} verses for translation={translation}.")
    return data


# ---------------------------------------------------------------------------
# Hash helper
# ---------------------------------------------------------------------------

def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Verse ingestion (upsert)
# ---------------------------------------------------------------------------

async def ingest_verses(
    session: AsyncSession,
    translation: str,
    verses: list[dict[str, Any]],
) -> tuple[int, int, int]:
    """
    UPSERT each verse into bible_verses.

    Returns (inserted_count, updated_count, skipped_count).

    ON CONFLICT behaviour:
      - New row   → INSERT; is_insert=True.
      - Existing row, text changed → UPDATE SET text + text_hash.
      - Existing row, text unchanged → no-op (WHERE clause false); skipped.

    Idempotent: re-running with identical data produces inserted=0, updated=0.
    """
    inserted = 0
    updated = 0
    skipped = 0

    for v in verses:
        book = v["book"]
        chapter = int(v["chapter"])
        verse_num = int(v["verse"])
        raw_text = v["text"]
        text_hash_val = sha256_hex(raw_text)

        result = await session.execute(
            text(
                """
                INSERT INTO bible_verses (id, translation_id, book, chapter, verse, text, text_hash)
                VALUES (:id, :translation_id, :book, :chapter, :verse, :text, :text_hash)
                ON CONFLICT (translation_id, book, chapter, verse)
                DO UPDATE SET
                    text      = EXCLUDED.text,
                    text_hash = EXCLUDED.text_hash
                WHERE bible_verses.text_hash != EXCLUDED.text_hash
                RETURNING (xmax = 0) AS is_insert
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "translation_id": translation,
                "book": book,
                "chapter": chapter,
                "verse": verse_num,
                "text": raw_text,
                "text_hash": text_hash_val,
            },
        )
        row = result.fetchone()
        if row is None:
            # Conflict row existed but WHERE clause was false → no-op skip
            skipped += 1
        elif row[0]:
            inserted += 1
        else:
            updated += 1

    await session.commit()
    return inserted, updated, skipped


# ---------------------------------------------------------------------------
# Embedding generation
# ---------------------------------------------------------------------------

async def generate_embeddings(
    session: AsyncSession,
    translation: str,
    batch_size: int,
    delay_ms: int,
) -> int:
    """
    For all bible_verses rows (for this translation) that don't yet have a
    verse_embeddings row for EMBEDDING_MODEL, call the OpenAI embeddings API
    and upsert the results.

    Returns the count of new embeddings generated.
    """
    try:
        from openai import AsyncOpenAI  # noqa: PLC0415
    except ImportError:
        print(
            "[ERROR] openai package not installed.  "
            "Run: uv add openai  (or pip install openai)"
        )
        sys.exit(1)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[ERROR] OPENAI_API_KEY environment variable is not set. Cannot generate embeddings.")
        sys.exit(1)

    client = AsyncOpenAI(api_key=api_key)

    # Fetch verse IDs + texts that don't yet have embeddings for this model.
    result = await session.execute(
        text(
            """
            SELECT bv.id, bv.text
            FROM bible_verses bv
            WHERE bv.translation_id = :translation_id
              AND NOT EXISTS (
                  SELECT 1 FROM verse_embeddings ve
                  WHERE ve.verse_id = bv.id
                    AND ve.embedding_model = :model
              )
            ORDER BY bv.book, bv.chapter, bv.verse
            """
        ),
        {"translation_id": translation, "model": EMBEDDING_MODEL},
    )
    pending = result.fetchall()

    if not pending:
        print(f"[INFO] All {translation} verses already have embeddings for {EMBEDDING_MODEL}. Skipping.")
        return 0

    total = len(pending)
    print(f"[INFO] Generating embeddings for {total:,} verses (batch_size={batch_size}) ...")

    generated = 0
    for batch_start in range(0, total, batch_size):
        batch = pending[batch_start : batch_start + batch_size]
        verse_ids = [str(row[0]) for row in batch]
        texts = [row[1] for row in batch]

        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
        )

        for verse_id, emb_data in zip(verse_ids, response.data):
            vector = emb_data.embedding
            if len(vector) != EMBEDDING_DIM:
                print(
                    f"[WARN] Unexpected embedding dimension {len(vector)} "
                    f"(expected {EMBEDDING_DIM}) for verse_id={verse_id}. Skipping."
                )
                continue

            await session.execute(
                text(
                    """
                    INSERT INTO verse_embeddings (id, verse_id, embedding_model, embedding, created_at)
                    VALUES (:id, :verse_id, :model, :embedding::text::vector, NOW())
                    ON CONFLICT (verse_id, embedding_model) DO NOTHING
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "verse_id": verse_id,
                    "model": EMBEDDING_MODEL,
                    "embedding": str(vector),
                },
            )
            generated += 1

        await session.commit()
        progress = min(batch_start + batch_size, total)
        print(f"  [{progress:,}/{total:,}] embeddings committed")

        if delay_ms > 0 and batch_start + batch_size < total:
            await asyncio.sleep(delay_ms / 1000.0)

    return generated


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    args = parse_args()

    # Resolve source path relative to CWD
    source_path = args.source if args.source.is_absolute() else Path.cwd() / args.source

    # Load + validate source
    verses = load_source(source_path, args.translation)

    # Resolve DB URL
    db_url = resolve_database_url(args.database_url)

    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        # ---- Step 1: Upsert verses ----
        print(f"[INFO] Upserting {len(verses):,} verses into bible_verses ...")
        inserted, updated, skipped = await ingest_verses(session, args.translation, verses)
        print(
            f"[INFO] bible_verses: {inserted:,} inserted, {updated:,} updated, "
            f"{skipped:,} skipped (0 inserted + 0 updated = idempotent re-run)."
        )

        # ---- Step 2: Embeddings ----
        if args.no_embeddings:
            print("[INFO] --no-embeddings flag set. Skipping embedding generation.")
            embeddings_generated = 0
        else:
            embeddings_generated = await generate_embeddings(
                session,
                args.translation,
                batch_size=args.batch_size,
                delay_ms=args.delay_ms,
            )

    await engine.dispose()

    print(
        f"\n[DONE] Translation={args.translation} | "
        f"Inserted={inserted:,} | Updated={updated:,} | Skipped={skipped:,} | "
        f"Embeddings generated={embeddings_generated:,}"
    )


if __name__ == "__main__":
    asyncio.run(main())
