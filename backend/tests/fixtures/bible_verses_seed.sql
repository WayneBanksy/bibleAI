-- bible_verses_seed.sql — minimal KJV seed for T010 citation validation tests
--
-- Load into dev DB (optional, for ad-hoc inspection):
--   docker-compose up -d db
--   docker exec -i <pg_container> psql -U postgres -d bible_therapist \
--     < tests/fixtures/bible_verses_seed.sql
--
-- text_hash is SHA-256(text) stored as a 64-char hex string.
-- PostgreSQL 11+ sha256() is used to compute the hash inline so this file
-- stays correct regardless of whitespace changes.
--
-- Automated pytest tests insert data via Python fixtures (test_citation.py)
-- using test-prefixed book names for isolation; this file uses real names
-- for dev readability.

-- Genesis 1:1 (KJV) — used for happy-path single-verse validation
INSERT INTO bible_verses (id, translation_id, book, chapter, verse, text, text_hash)
VALUES (
    gen_random_uuid(),
    'KJV',
    'Genesis',
    1,
    1,
    'In the beginning God created the heaven and the earth.',
    encode(sha256('In the beginning God created the heaven and the earth.'::bytea), 'hex')
) ON CONFLICT (translation_id, book, chapter, verse) DO NOTHING;

-- Genesis 1:2 (KJV) — used for range query validation (Genesis 1:1-2)
INSERT INTO bible_verses (id, translation_id, book, chapter, verse, text, text_hash)
VALUES (
    gen_random_uuid(),
    'KJV',
    'Genesis',
    1,
    2,
    'And the earth was without form, and void; and darkness was upon the face of the deep. And the Spirit of God moved upon the face of the waters.',
    encode(sha256('And the earth was without form, and void; and darkness was upon the face of the deep. And the Spirit of God moved upon the face of the waters.'::bytea), 'hex')
) ON CONFLICT (translation_id, book, chapter, verse) DO NOTHING;

-- John 3:16 (KJV) — used for mixed-batch happy-path entry
INSERT INTO bible_verses (id, translation_id, book, chapter, verse, text, text_hash)
VALUES (
    gen_random_uuid(),
    'KJV',
    'John',
    3,
    16,
    'For God so loved the world, that he gave his only begotten Son, that whosoever believeth in him should not perish, but have everlasting life.',
    encode(sha256('For God so loved the world, that he gave his only begotten Son, that whosoever believeth in him should not perish, but have everlasting life.'::bytea), 'hex')
) ON CONFLICT (translation_id, book, chapter, verse) DO NOTHING;

-- Psalms 23:1 (KJV) — used for verse_end-defaults-to-verse_start test
INSERT INTO bible_verses (id, translation_id, book, chapter, verse, text, text_hash)
VALUES (
    gen_random_uuid(),
    'KJV',
    'Psalms',
    23,
    1,
    'The LORD is my shepherd; I shall not want.',
    encode(sha256('The LORD is my shepherd; I shall not want.'::bytea), 'hex')
) ON CONFLICT (translation_id, book, chapter, verse) DO NOTHING;

-- Deliberately corrupted hash row — used for hash_mismatch test
-- Uses a fake book name to avoid conflicting with a real corpus row.
-- The text is real but text_hash is all-zeros (invalid).
INSERT INTO bible_verses (id, translation_id, book, chapter, verse, text, text_hash)
VALUES (
    gen_random_uuid(),
    'KJV',
    '_t010_BadHash',
    1,
    1,
    'Test verse for hash mismatch scenario.',
    '0000000000000000000000000000000000000000000000000000000000000000'
) ON CONFLICT (translation_id, book, chapter, verse) DO NOTHING;
