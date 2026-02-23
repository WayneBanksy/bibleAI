"""
Per-user AES-256-GCM message encryption.

Keys are derived (never stored) using HKDF-SHA256:
    IKM  = MASTER_KEY_SECRET (env var)
    salt = user_id bytes
    info = b"bible_therapist_message_v1"

Blob format stored in messages.content_encrypted (BYTEA):
    nonce (12 bytes) || ciphertext || auth_tag (16 bytes)

See docs/KEY_MANAGEMENT.md for full design rationale and rotation runbook.
"""

import os
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_NONCE_BYTES = 12  # 96-bit nonce; GCM recommendation
_KEY_BYTES = 32    # 256-bit AES key
_HKDF_INFO = b"bible_therapist_message_v1"


class MessageCrypto:
    """
    Encrypts/decrypts message content using per-user AES-256-GCM keys
    derived from a master secret. Keys are derived; never stored.
    """

    def __init__(self, master_key_secret: bytes) -> None:
        if not master_key_secret:
            raise ValueError("master_key_secret must not be empty")
        # Store as bytes internally; attribute is not logged by structlog
        # because it is not included in any log record.
        self._master_key_secret = master_key_secret

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def encrypt(self, user_id: UUID, plaintext: str) -> bytes:
        """
        Encrypt *plaintext* for *user_id*.

        Returns nonce (12 bytes) || ciphertext || auth_tag (16 bytes).
        Each call produces distinct bytes because the nonce is random.
        """
        key = self.derive_key(user_id)
        nonce = os.urandom(_NONCE_BYTES)
        aesgcm = AESGCM(key)
        # AESGCM.encrypt returns ciphertext + appended 16-byte auth tag.
        ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return nonce + ciphertext_with_tag

    def decrypt(self, user_id: UUID, blob: bytes) -> str:
        """
        Decrypt a blob produced by encrypt().

        Raises ValueError on authentication failure (tampered ciphertext or
        wrong key). The underlying InvalidTag exception is re-raised as
        ValueError so callers need not import cryptography internals.
        """
        if len(blob) < _NONCE_BYTES + 16:
            raise ValueError("Blob too short to be a valid encrypted message")
        nonce = blob[:_NONCE_BYTES]
        ciphertext_with_tag = blob[_NONCE_BYTES:]
        key = self.derive_key(user_id)
        aesgcm = AESGCM(key)
        try:
            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
        except InvalidTag as exc:
            raise ValueError("Decryption failed: authentication tag mismatch") from exc
        return plaintext_bytes.decode("utf-8")

    def derive_key(self, user_id: UUID) -> bytes:
        """
        Derive the 32-byte AES-256 key for *user_id* deterministically.

        Exposed for testing ONLY — never log this value.
        Uses HKDF-SHA256 with:
            IKM  = self._master_key_secret
            salt = user_id bytes (16 bytes, stable per user)
            info = b"bible_therapist_message_v1"
        """
        hkdf = HKDF(
            algorithm=SHA256(),
            length=_KEY_BYTES,
            salt=user_id.bytes,
            info=_HKDF_INFO,
        )
        return hkdf.derive(self._master_key_secret)


# ---------------------------------------------------------------------------
# Module-level singleton — import and use in the message write path:
#   from app.crypto import message_crypto
#   blob = message_crypto.encrypt(user_id, text)
# ---------------------------------------------------------------------------

from app.config import settings  # noqa: E402 — imported after class definition

message_crypto = MessageCrypto(
    master_key_secret=settings.master_key_secret.encode("utf-8")
)
