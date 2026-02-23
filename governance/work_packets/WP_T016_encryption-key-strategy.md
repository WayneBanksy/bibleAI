# Work Packet: T016 — Encryption Key Management Strategy

## Goal

Design, document, and implement the per-user AES-256-GCM encryption key management
strategy for message content storage (DECISIONS.md D008). This is a pre-ship security
review requirement.

Deliverables:
1. A written key management design document (decision record for D008 extension).
2. A concrete implementation in `backend/app/crypto.py` that the message write path
   (T007) can import directly.
3. A key rotation runbook stub.

This packet is code + design. It does NOT require T007 to be merged, but it must land
before T007 can be marked "Integrated" (T007 calls `crypto.encrypt()` for message
storage).

## Owner

Backend Engineer

## Branch / Worktree Name

`agent/backend/T016-encryption-keys`

## Scope (files allowed to change)

```
backend/
  app/
    crypto.py                 # NEW — encrypt/decrypt, key derivation, nonce management
  tests/
    test_crypto.py            # NEW — unit tests for encrypt/decrypt round-trip, key derivation
  docs/
    KEY_MANAGEMENT.md         # NEW — design document + rotation runbook stub
  app/config.py               # MODIFY — add MASTER_KEY_SECRET env var + key derivation config
```

## Do Not Touch

- `governance/INTERFACES.md`
- `governance/DECISIONS.md` — the design decision lives in `docs/KEY_MANAGEMENT.md`;
  the Orchestrator will record a summary back into DECISIONS.md D008 after this PR is reviewed.
- `governance/SAFETY_POLICY.md`
- `governance/TASKS.md`
- `governance/DEPENDENCIES.md`
- `backend/app/routers/**`   (T007 scope)
- `backend/app/pipeline.py`  (T007 scope)
- Any file under `/ios/`

## Dependencies

- DECISIONS.md D008 — encryption policy (LOCKED ✅):
  - Algorithm: AES-256-GCM
  - Scope: per-user key
  - What's stored: `content_encrypted` (BYTEA), `text_hash` (SHA-256 hex)
  - What is NOT stored: raw plaintext
- T003 backend scaffold — Done ✅ (`messages` table has `content_encrypted BYTEA` + `text_hash TEXT`)
- Python `cryptography` library — add to `pyproject.toml` if not already present

## Design Constraints

The chosen approach must satisfy ALL of the following:

1. **Per-user keys:** Each user's messages are encrypted with a distinct key. Compromise
   of one user's key does not expose other users' content.
2. **Key derivation (not key storage):** Do NOT store per-user keys in the DB. Derive
   them deterministically from a `MASTER_KEY_SECRET` (env var, never committed) +
   a user-stable salt (the user's `id` UUID from the `users` table).
3. **Algorithm:** AES-256-GCM. 256-bit key, 96-bit (12-byte) random nonce per
   encryption operation. Authentication tag included (GCM provides integrity + confidentiality).
4. **Nonce:** Random per encryption, prepended to ciphertext in the stored BYTEA blob.
   Format: `nonce (12 bytes) || ciphertext || auth_tag (16 bytes)`.
5. **Key derivation function:** HKDF-SHA256. Input: `MASTER_KEY_SECRET` as IKM,
   `user_id` (bytes) as salt, `b"bible_therapist_message_v1"` as info. Output: 32-byte key.
6. **No key in logs:** The derived key must never appear in structured logs or tracebacks.
7. **Rotation path:** Design must support key rotation (re-encryption of all user messages
   with a new master key) without downtime. Document the rotation runbook.

## Public Interface Contract

```python
# backend/app/crypto.py

from uuid import UUID

class MessageCrypto:
    """
    Encrypts/decrypts message content using per-user AES-256-GCM keys
    derived from a master secret. Keys are derived; never stored.
    """

    def __init__(self, master_key_secret: bytes): ...

    def encrypt(self, user_id: UUID, plaintext: str) -> bytes:
        """
        Returns nonce (12 bytes) || ciphertext || auth_tag (16 bytes).
        Never returns the same bytes for the same input (nonce is random).
        """
        ...

    def decrypt(self, user_id: UUID, blob: bytes) -> str:
        """
        Decrypts a blob produced by encrypt(). Raises ValueError on
        authentication failure (tampered ciphertext).
        """
        ...

    def derive_key(self, user_id: UUID) -> bytes:
        """
        Returns the 32-byte AES key for this user. Used internally.
        Exposed for testing ONLY — never log this value.
        """
        ...
```

A module-level singleton is initialised from config:

```python
# backend/app/crypto.py
from app.config import settings
message_crypto = MessageCrypto(master_key_secret=settings.master_key_secret.encode())
```

`app/config.py` must add:
```python
master_key_secret: str = Field(default=..., env="MASTER_KEY_SECRET")
# No default value — must be set in env. Application fails to start if missing.
```

## KEY_MANAGEMENT.md Required Sections

1. **Algorithm choice rationale** — why AES-256-GCM (authenticated encryption, NIST standard, GCM provides integrity without separate HMAC, wide library support).
2. **Key derivation design** — HKDF-SHA256 diagram: `MASTER_KEY_SECRET` → `HKDF` → per-user 256-bit key. Why HKDF: standard KDF, deterministic, no key storage needed.
3. **Nonce management** — why random 12-byte nonce per operation; collision probability analysis for MVP message volumes.
4. **MASTER_KEY_SECRET management** — how it must be set in production (environment variable via secret manager; NOT in code or `.env` committed to git); recommended value generation (`openssl rand -base64 32`).
5. **Rotation runbook (stub)** — steps to rotate the master key:
   - Generate `MASTER_KEY_SECRET_NEW`.
   - Run re-encryption migration: for each message, decrypt with old key, re-encrypt with new key, write new `content_encrypted`.
   - Swap `MASTER_KEY_SECRET` → `MASTER_KEY_SECRET_NEW` in secret manager.
   - Verify: spot-check a sample of messages decrypt correctly.
   - Revoke old key.
   - Note: This is a stub; a full re-encryption migration script is post-MVP.
6. **Security review signoff line** — placeholder for reviewer name + date.

## Acceptance Criteria

- [ ] `crypto.py` implements `MessageCrypto.encrypt()` and `MessageCrypto.decrypt()` using AES-256-GCM via the `cryptography` library (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`).
- [ ] Round-trip test: `decrypt(user_id, encrypt(user_id, text)) == text` for arbitrary inputs.
- [ ] Two calls to `encrypt()` with the same inputs produce different bytes (random nonce).
- [ ] `decrypt()` raises `ValueError` (or `cryptography.exceptions.InvalidTag`) when the blob is tampered.
- [ ] `derive_key()` is deterministic: same `(master_key_secret, user_id)` always returns the same 32 bytes.
- [ ] Different `user_id` values produce different derived keys (per-user isolation).
- [ ] `MASTER_KEY_SECRET` env var is required; application startup fails with a clear error if not set.
- [ ] `MASTER_KEY_SECRET` never appears in logs, test output, or error messages.
- [ ] `test_crypto.py` covers: round-trip, nonce uniqueness, tamper detection, cross-user key isolation, deterministic derivation.
- [ ] `docs/KEY_MANAGEMENT.md` covers all 6 required sections.
- [ ] `docker-compose.yml` is updated with a placeholder `MASTER_KEY_SECRET=dev-insecure-local-only` for local dev (clearly labelled as insecure).
- [ ] All existing `test_api.py` tests continue to pass (no regressions from `config.py` changes — `MASTER_KEY_SECRET` should have a dev-only default when `ENV=development`).

## Test / Run Commands

```bash
cd backend

# Install deps (cryptography should already be in pyproject.toml; verify)
uv sync

# Run crypto-specific tests
uv run pytest tests/test_crypto.py -v

# Run full suite (no regressions)
uv run pytest tests/ -v

# Verify startup fails without MASTER_KEY_SECRET in production mode
MASTER_KEY_SECRET="" ENV=production uv run python -c "from app.config import settings" 2>&1
# Expected: ValidationError or similar — must not silently use an empty key

# Verify startup succeeds in development mode (uses dev default)
ENV=development uv run python -c "from app.crypto import message_crypto; print('OK')"
```

## Notes / Risks

- **`cryptography` library:** Use `cryptography.hazmat.primitives.ciphers.aead.AESGCM` for AES-256-GCM. This is the standard Python cryptography library (not `pycryptodome`). Add to `pyproject.toml` dependencies if not already present.
- **Dev default for `MASTER_KEY_SECRET`:** When `ENV=development`, allow a weak default (`"dev-insecure-do-not-use-in-production"`) so the existing test suite doesn't break. In production, no default is allowed — fail fast. Document this clearly in `config.py` comments.
- **`docker-compose.yml` change:** Adding `MASTER_KEY_SECRET=dev-insecure-local-only` to `docker-compose.yml` is allowed in this packet (it is a dev environment file, not a governance file). Add a comment: `# INSECURE: dev only. Never use this value in production.`
- **T007 integration note:** T007 will call `from app.crypto import message_crypto` and `message_crypto.encrypt(user_id, text)` before writing to the DB. Coordinate with T007 engineer to confirm the import path before T007 merges.
- **What this packet does NOT cover:** Key storage in HSM/KMS, secret rotation automation, or audit logging of key access events — these are post-MVP security hardening items.
- **PR title suggestion:** `feat(backend): T016 AES-256-GCM per-user message encryption + key management design`
