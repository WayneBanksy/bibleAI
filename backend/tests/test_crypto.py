"""
Unit tests for backend/app/crypto.py (T016).

These tests are self-contained: they instantiate MessageCrypto with a
fixed test secret rather than importing the module-level singleton so
tests are hermetic and do not depend on env vars.
"""

import uuid

import pytest
from cryptography.exceptions import InvalidTag

from app.crypto import MessageCrypto

_TEST_SECRET = b"test-master-secret-32-bytes-abcd"  # 32 bytes for test clarity
_USER_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_USER_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture()
def crypto() -> MessageCrypto:
    return MessageCrypto(master_key_secret=_TEST_SECRET)


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_roundtrip_basic(crypto: MessageCrypto) -> None:
    """decrypt(encrypt(text)) == text for a normal message."""
    text = "What does the Bible say about anxiety?"
    blob = crypto.encrypt(_USER_A, text)
    assert crypto.decrypt(_USER_A, blob) == text


def test_roundtrip_empty_string(crypto: MessageCrypto) -> None:
    """Empty string round-trips correctly."""
    blob = crypto.encrypt(_USER_A, "")
    assert crypto.decrypt(_USER_A, blob) == ""


def test_roundtrip_unicode(crypto: MessageCrypto) -> None:
    """Unicode characters round-trip without data loss."""
    text = "Dios te ama. \U0001f54a\ufe0f"
    blob = crypto.encrypt(_USER_A, text)
    assert crypto.decrypt(_USER_A, blob) == text


def test_roundtrip_long_message(crypto: MessageCrypto) -> None:
    """A 2000-char message (max allowed) round-trips correctly."""
    text = "A" * 2000
    blob = crypto.encrypt(_USER_A, text)
    assert crypto.decrypt(_USER_A, blob) == text


# ---------------------------------------------------------------------------
# Nonce uniqueness — two encryptions of the same plaintext must differ
# ---------------------------------------------------------------------------


def test_nonce_uniqueness(crypto: MessageCrypto) -> None:
    """Two encryptions of the same (user_id, text) must produce distinct blobs."""
    text = "same plaintext"
    blob1 = crypto.encrypt(_USER_A, text)
    blob2 = crypto.encrypt(_USER_A, text)
    assert blob1 != blob2, "Random nonce must make ciphertext non-deterministic"


def test_nonce_uniqueness_many(crypto: MessageCrypto) -> None:
    """50 encryptions all produce unique blobs."""
    text = "repeated message"
    blobs = {crypto.encrypt(_USER_A, text) for _ in range(50)}
    assert len(blobs) == 50, "Expected 50 distinct blobs from 50 encryptions"


# ---------------------------------------------------------------------------
# Tamper detection
# ---------------------------------------------------------------------------


def test_tamper_ciphertext_raises(crypto: MessageCrypto) -> None:
    """Flipping a bit in the ciphertext body must raise ValueError."""
    blob = crypto.encrypt(_USER_A, "sensitive content")
    # Flip a byte in the ciphertext (byte 12 is the first ciphertext byte after the nonce)
    tampered = bytearray(blob)
    tampered[12] ^= 0xFF
    with pytest.raises(ValueError):
        crypto.decrypt(_USER_A, bytes(tampered))


def test_tamper_nonce_raises(crypto: MessageCrypto) -> None:
    """Flipping a byte in the nonce must raise ValueError (auth tag check fails)."""
    blob = crypto.encrypt(_USER_A, "sensitive content")
    tampered = bytearray(blob)
    tampered[0] ^= 0x01
    with pytest.raises(ValueError):
        crypto.decrypt(_USER_A, bytes(tampered))


def test_tamper_auth_tag_raises(crypto: MessageCrypto) -> None:
    """Flipping a byte in the auth tag (last 16 bytes) must raise ValueError."""
    blob = crypto.encrypt(_USER_A, "sensitive content")
    tampered = bytearray(blob)
    tampered[-1] ^= 0x01
    with pytest.raises(ValueError):
        crypto.decrypt(_USER_A, bytes(tampered))


def test_blob_too_short_raises(crypto: MessageCrypto) -> None:
    """A blob shorter than nonce + auth_tag must raise ValueError immediately."""
    with pytest.raises(ValueError, match="too short"):
        crypto.decrypt(_USER_A, b"\x00" * 10)


# ---------------------------------------------------------------------------
# Cross-user key isolation
# ---------------------------------------------------------------------------


def test_cross_user_cannot_decrypt(crypto: MessageCrypto) -> None:
    """User B cannot decrypt a blob encrypted for User A."""
    blob = crypto.encrypt(_USER_A, "user A private message")
    with pytest.raises(ValueError):
        crypto.decrypt(_USER_B, blob)


def test_different_users_different_blobs(crypto: MessageCrypto) -> None:
    """Same plaintext encrypted for two different users produces different blobs."""
    text = "shared message text"
    blob_a = crypto.encrypt(_USER_A, text)
    blob_b = crypto.encrypt(_USER_B, text)
    assert blob_a != blob_b


# ---------------------------------------------------------------------------
# Key derivation determinism and isolation
# ---------------------------------------------------------------------------


def test_derive_key_deterministic(crypto: MessageCrypto) -> None:
    """derive_key is deterministic: same (master_secret, user_id) → same key."""
    key1 = crypto.derive_key(_USER_A)
    key2 = crypto.derive_key(_USER_A)
    assert key1 == key2


def test_derive_key_32_bytes(crypto: MessageCrypto) -> None:
    """Derived key is exactly 32 bytes (256 bits)."""
    key = crypto.derive_key(_USER_A)
    assert len(key) == 32


def test_derive_key_different_users_differ(crypto: MessageCrypto) -> None:
    """Different user IDs yield different keys."""
    key_a = crypto.derive_key(_USER_A)
    key_b = crypto.derive_key(_USER_B)
    assert key_a != key_b


def test_derive_key_different_master_secrets_differ() -> None:
    """Different master secrets yield different keys for the same user."""
    crypto1 = MessageCrypto(master_key_secret=b"secret-one-padded-to-thirtytwo-!")
    crypto2 = MessageCrypto(master_key_secret=b"secret-two-padded-to-thirtytwo-!")
    key1 = crypto1.derive_key(_USER_A)
    key2 = crypto2.derive_key(_USER_A)
    assert key1 != key2


# ---------------------------------------------------------------------------
# Constructor guard
# ---------------------------------------------------------------------------


def test_empty_master_key_raises() -> None:
    """MessageCrypto must refuse to instantiate with an empty master key."""
    with pytest.raises(ValueError):
        MessageCrypto(master_key_secret=b"")
