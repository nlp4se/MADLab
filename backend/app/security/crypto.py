"""Symmetric credential encryption (Fernet) for provider API keys.

Provider API keys are stored **encrypted at rest** and never returned to the
frontend in plaintext (Req 8.4). This module is the single place that turns a
plaintext key into ciphertext (on save) and back (only inside the provider
layer, at call time). Everything above the persistence layer sees nothing but
the ciphertext column and the :pyattr:`~app.db.models.Provider.has_key` boolean.

Design (see *Provider Abstraction & Credentials*):

* Keys are encrypted with **Fernet** (AES-128-CBC + HMAC authentication), a
  symmetric scheme from the ``cryptography`` library.
* The Fernet key is **derived from a server secret** read from the environment
  (``.env`` via ``python-dotenv``). The secret is operator-controlled and lives
  outside the database, so a leaked database file is not enough to recover keys.
* Derivation is deterministic (same secret → same Fernet key) so ciphertext
  written in one process can be read back in another, as long as the server
  secret is unchanged.

The module keeps **no plaintext** in any persistent form: it only ever returns
ciphertext strings for storage, and plaintext is produced transiently inside
:func:`decrypt` for immediate use by the caller.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

# Name of the environment variable holding the operator's server secret. The
# value can be any non-empty string; it is *derived* into a Fernet key below, so
# it does not itself need to be 32 url-safe base64 bytes.
SERVER_SECRET_ENV = "MAD_SECRET_KEY"


class CredentialError(Exception):
    """Raised for credential-encryption configuration or decryption failures.

    Covers a missing/empty server secret and ciphertext that cannot be
    decrypted with the current secret (wrong secret, corrupted/forged token).
    The message never contains key material.
    """


def _load_server_secret(secret: str | None = None) -> str:
    """Resolve the server secret, loading ``.env`` into the environment first.

    Resolution order:

    1. an explicit ``secret`` argument (used by tests and callers that manage
       the secret themselves);
    2. the :data:`SERVER_SECRET_ENV` environment variable, after
       ``load_dotenv()`` has populated it from a project ``.env`` file.

    :raises CredentialError: if no non-empty secret can be found.
    """
    if secret is not None:
        if not secret:
            raise CredentialError("Server secret must not be empty.")
        return secret

    # ``load_dotenv`` is idempotent and does not override already-set process
    # environment variables, so an explicitly exported secret still wins.
    load_dotenv()
    value = os.environ.get(SERVER_SECRET_ENV)
    if not value:
        raise CredentialError(
            f"No server secret configured: set {SERVER_SECRET_ENV} in the "
            "environment or the project .env file."
        )
    return value


def _derive_fernet_key(secret: str) -> bytes:
    """Deterministically derive a 32-byte url-safe base64 Fernet key from ``secret``.

    Fernet requires exactly 32 bytes, url-safe-base64 encoded. We hash the
    operator secret with SHA-256 (always 32 bytes) and base64-encode the digest,
    so any non-empty secret string yields a valid key and the same secret always
    maps to the same key (required for cross-process decryption).
    """
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


class CredentialCipher:
    """Encrypt / decrypt provider API keys with a secret-derived Fernet key.

    Instances are cheap and hold only the derived Fernet primitive — never the
    plaintext of any credential. Construct one per process (or reuse the
    module-level helpers, which build a default instance lazily).
    """

    def __init__(self, secret: str | None = None) -> None:
        resolved = _load_server_secret(secret)
        self._fernet = Fernet(_derive_fernet_key(resolved))

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext API key, returning url-safe ciphertext for storage.

        :raises CredentialError: if ``plaintext`` is empty (an empty key means
            "no key" and must not be stored as ciphertext — leave the column
            NULL instead).
        """
        if not plaintext:
            raise CredentialError("Cannot encrypt an empty API key.")
        token = self._fernet.encrypt(plaintext.encode("utf-8"))
        return token.decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt stored ciphertext back to the plaintext API key.

        Intended for use **only** inside the provider layer at call time.

        :raises CredentialError: if ``ciphertext`` is empty, or cannot be
            authenticated/decrypted with the current server secret.
        """
        if not ciphertext:
            raise CredentialError("Cannot decrypt an empty value.")
        try:
            plaintext = self._fernet.decrypt(ciphertext.encode("ascii"))
        except (InvalidToken, ValueError) as exc:
            # Do not leak the token or any key material in the error.
            raise CredentialError(
                "Failed to decrypt credential: the server secret is wrong or "
                "the stored value is corrupted."
            ) from exc
        return plaintext.decode("utf-8")


# ---------------------------------------------------------------------------
# Module-level convenience API (lazy default cipher)
# ---------------------------------------------------------------------------

_default_cipher: CredentialCipher | None = None


def get_cipher() -> CredentialCipher:
    """Return a process-wide :class:`CredentialCipher`, built lazily on first use.

    The default cipher reads the server secret from the environment / ``.env``.
    Tests that need a specific secret should construct :class:`CredentialCipher`
    directly or call :func:`reset_cipher` after setting the environment.
    """
    global _default_cipher
    if _default_cipher is None:
        _default_cipher = CredentialCipher()
    return _default_cipher


def reset_cipher() -> None:
    """Drop the cached default cipher (e.g. after the server secret changes)."""
    global _default_cipher
    _default_cipher = None


def encrypt_api_key(plaintext: str) -> str:
    """Encrypt ``plaintext`` with the default cipher. See :meth:`CredentialCipher.encrypt`."""
    return get_cipher().encrypt(plaintext)


def decrypt_api_key(ciphertext: str) -> str:
    """Decrypt ``ciphertext`` with the default cipher. See :meth:`CredentialCipher.decrypt`."""
    return get_cipher().decrypt(ciphertext)


__all__ = [
    "SERVER_SECRET_ENV",
    "CredentialError",
    "CredentialCipher",
    "get_cipher",
    "reset_cipher",
    "encrypt_api_key",
    "decrypt_api_key",
]
