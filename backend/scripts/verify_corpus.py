#!/usr/bin/env python3
"""
Corpus verification / sanity-check script — T009.

Outputs a human-readable report covering:
  - Row counts per translation in bible_verses
  - Spot-check: SHA-256 hash validation for 10 random rows
  - Embedding dimension check (should be 1536 for text-embedding-3-small)
  - HNSW index existence check on verse_embeddings

Usage:
    uv run python scripts/verify_corpus.py
    uv run python scripts/verify_corpus.py --translation KJV
"""

import argparse
import hashlib
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

import asyncio  # noqa: E402

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

EMBEDDING_MODEL = "text-embedding-3-small"
EXPECTED_DIM = 1536
SPOT_CHECK_COUNT = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify bible corpus integrity.")
    parser.add_argument(
        "--translation",
        default=None,
        help="Limit spot-check and embedding check to this translation (optional).",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override DATABASE_URL.",
    )
    return parser.parse_args()


def resolve_database_url(override: str | None) -> str:
    if override:
        return override
    env_val = os.environ.get("DATABASE_URL")
    if env_val:
        return env_val
    dotenv_path = BACKEND_ROOT / ".env"
    if dotenv_path.exists():
        for line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("No DATABASE_URL found. Set DATABASE_URL or create backend/.env.")


def sha256_hex(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Report sections
# ---------------------------------------------------------------------------

async def check_verse_counts(session: AsyncSession) -> bool:
    print("\n── Verse counts per translation ─────────────────────────")
    result = await session.execute(
        text(
            "SELECT translation_id, COUNT(*) AS cnt "
            "FROM bible_verses GROUP BY translation_id ORDER BY translation_id"
        )
    )
    rows = result.fetchall()
    if not rows:
        print("  [WARN] bible_verses table is empty.")
        return False

    ok = True
    for translation_id, cnt in rows:
        flag = ""
        if translation_id == "KJV" and cnt < 31000:
            flag = "  ← [WARN] KJV count low; expected ~31,100"
            ok = False
        print(f"  {translation_id:6s}: {cnt:>7,} verses{flag}")
    return ok


async def check_hashes(session: AsyncSession, translation: str | None) -> bool:
    print(f"\n── SHA-256 spot-check ({SPOT_CHECK_COUNT} random rows) ─────────────────")

    where_clause = "WHERE translation_id = :t" if translation else ""
    params: dict = {"t": translation} if translation else {}

    result = await session.execute(
        text(
            f"SELECT id, text, text_hash FROM bible_verses {where_clause} "  # noqa: S608
            f"ORDER BY RANDOM() LIMIT {SPOT_CHECK_COUNT}"
        ),
        params,
    )
    rows = result.fetchall()

    if not rows:
        print("  [WARN] No rows found to spot-check.")
        return False

    all_ok = True
    for row in rows:
        verse_id, stored_text, stored_hash = row[0], row[1], row[2]
        expected_hash = sha256_hex(stored_text)
        status = "OK" if expected_hash == stored_hash else "FAIL"
        if status == "FAIL":
            all_ok = False
        print(f"  {status}  verse_id={verse_id}  hash={stored_hash[:16]}...")

    if all_ok:
        print(f"  All {len(rows)} spot-checked hashes are correct.")
    else:
        print(f"  [ERROR] Hash mismatch detected — corpus integrity compromised.")
    return all_ok


async def check_embedding_dim(session: AsyncSession, translation: str | None) -> bool:
    print(f"\n── Embedding dimension check ({EMBEDDING_MODEL}) ─────────────────")

    join_clause = (
        "JOIN bible_verses bv ON bv.id = ve.verse_id "
        "WHERE bv.translation_id = :t AND ve.embedding_model = :model"
        if translation
        else "WHERE ve.embedding_model = :model"
    )
    params: dict = {"model": EMBEDDING_MODEL}
    if translation:
        params["t"] = translation

    # Count embeddings
    count_result = await session.execute(
        text(
            f"SELECT COUNT(*) FROM verse_embeddings ve {join_clause}"  # noqa: S608
        ),
        params,
    )
    count = count_result.scalar()
    print(f"  Embedding rows ({translation or 'all'}): {count:,}")

    if count == 0:
        print("  [INFO] No embeddings found (run without --no-embeddings to generate).")
        return True  # Not a failure; embeddings may not have been generated yet

    # Check dimension via array_length on a sample
    dim_result = await session.execute(
        text(
            f"SELECT array_length(embedding::real[], 1) "  # noqa: S608
            f"FROM verse_embeddings ve {join_clause} LIMIT 1"
        ),
        params,
    )
    dim = dim_result.scalar()

    if dim is None:
        print("  [WARN] Could not determine embedding dimension.")
        return False
    if dim != EXPECTED_DIM:
        print(f"  [ERROR] Embedding dimension={dim}, expected {EXPECTED_DIM}.")
        return False

    print(f"  Embedding dimension: {dim} ✓")
    return True


async def check_hnsw_index(session: AsyncSession) -> bool:
    print("\n── HNSW index existence check ─────────────────────────")
    result = await session.execute(
        text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'verse_embeddings'
              AND indexdef ILIKE '%hnsw%'
            """
        )
    )
    rows = result.fetchall()
    if rows:
        for indexname, indexdef in rows:
            print(f"  FOUND: {indexname}")
            print(f"         {indexdef[:120]}...")
        return True
    else:
        print(
            "  [WARN] No HNSW index found on verse_embeddings. "
            "Run Alembic migrations (alembic upgrade head)."
        )
        return False


async def main() -> None:
    args = parse_args()
    db_url = resolve_database_url(args.database_url)

    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    print("=== Bible Corpus Verification Report ===")
    if args.translation:
        print(f"  Scoped to translation: {args.translation}")

    results: list[bool] = []

    async with session_factory() as session:
        results.append(await check_verse_counts(session))
        results.append(await check_hashes(session, args.translation))
        results.append(await check_embedding_dim(session, args.translation))
        results.append(await check_hnsw_index(session))

    await engine.dispose()

    passed = sum(results)
    total = len(results)
    print(f"\n=== Summary: {passed}/{total} checks passed ===")
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
