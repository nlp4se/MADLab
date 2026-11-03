"""Credential encryption (Fernet) for provider API keys.

Provider API keys are encrypted at rest with Fernet, keyed from a server secret
read from the environment / ``.env`` (Req 8.4). Plaintext is never persisted and
never returned upward; only ciphertext and the ``has_key`` boolean cross the
persistence boundary. Decryption happens solely inside the provider layer at
call time.

See :mod:`app.security.crypto` for the implementation.
"""

from app.security.crypto import (
    SERVER_SECRET_ENV,
    CredentialCipher,
    CredentialError,
    decrypt_api_key,
    encrypt_api_key,
    get_cipher,
    reset_cipher,
)

__all__ = [
    "SERVER_SECRET_ENV",
    "CredentialError",
    "CredentialCipher",
    "get_cipher",
    "reset_cipher",
    "encrypt_api_key",
    "decrypt_api_key",
]
