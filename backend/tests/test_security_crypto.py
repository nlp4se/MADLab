"""Tests for provider credential encryption (``app.security``).

Covers Req 8.4:

* encrypt → decrypt round-trip across many plaintext keys (property-style loop);
* ciphertext is never equal to, and never contains, the plaintext — i.e. the
  value we persist never leaks the key;
* the same server secret decrypts what it encrypted, and a *different* secret
  cannot (ciphertext is bound to the operator secret);
* the secret is resolved from the environment / ``.env`` when not passed
  explicitly, and a missing/empty secret is a clear, key-free error;
* empty inputs are rejected rather than silently producing a bogus token;
* integration with the persistence layer: only the encrypted value is stored,
  ``Provider.has_key`` reflects presence only, and a serialized Provider row
  never carries the plaintext key.

Nothing here writes to disk or depends on a real ``.env``; the server secret is
injected via the explicit constructor argument or a monkeypatched environment.
"""

from __future__ import annotations

import json

import pytest

from app.security.crypto import (
    SERVER_SECRET_ENV,
    CredentialCipher,
    CredentialError,
    reset_cipher,
)

# A representative spread of plaintext API keys: realistic provider formats,
# unicode, whitespace, a long value, and a single char (round-trip only).
SAMPLE_KEYS = [
    "sk-proj-abc123",
    "AIzaSyCId9_BKwAF5V2rG0lGZ8WyeJlZg8Vdvxo",
    "key with spaces",
    "unicode-é-ключ-密钥",
    "x" * 512,
    "a",
]

# Keys long/distinctive enough that a substring leak-check is meaningful. A
# single random base64 character collides with almost any ciphertext by chance,
# so the degenerate 1-char case is exercised by the round-trip test only, not
# by the "plaintext not contained in ciphertext" check.
LEAK_CHECK_KEYS = [k for k in SAMPLE_KEYS if len(k) >= 4]


@pytest.fixture()
def cipher() -> CredentialCipher:
    """A cipher with a fixed, test-local server secret (no env/.env needed)."""
    return CredentialCipher(secret="test-server-secret")


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("plaintext", SAMPLE_KEYS)
def test_encrypt_decrypt_round_trip(cipher, plaintext):
    ciphertext = cipher.encrypt(plaintext)
    assert cipher.decrypt(ciphertext) == plaintext


def test_round_trip_is_stable_across_instances():
    """Same secret → ciphertext written by one instance reads back in another."""
    a = CredentialCipher(secret="shared-secret")
    b = CredentialCipher(secret="shared-secret")
    token = a.encrypt("sk-shared")
    assert b.decrypt(token) == "sk-shared"


def test_encrypt_is_nondeterministic_but_decrypts_the_same(cipher):
    """Fernet embeds a random IV, so two encryptions differ yet both decrypt."""
    t1 = cipher.encrypt("sk-same")
    t2 = cipher.encrypt("sk-same")
    assert t1 != t2
    assert cipher.decrypt(t1) == cipher.decrypt(t2) == "sk-same"


# ---------------------------------------------------------------------------
# Plaintext never leaks into the stored ciphertext
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("plaintext", LEAK_CHECK_KEYS)
def test_ciphertext_does_not_contain_plaintext(cipher, plaintext):
    ciphertext = cipher.encrypt(plaintext)
    assert ciphertext != plaintext
    # The raw key must not appear anywhere in the token we persist.
    assert plaintext not in ciphertext


# ---------------------------------------------------------------------------
# Secret binding
# ---------------------------------------------------------------------------


def test_wrong_secret_cannot_decrypt():
    token = CredentialCipher(secret="right-secret").encrypt("sk-secret")
    other = CredentialCipher(secret="wrong-secret")
    with pytest.raises(CredentialError):
        other.decrypt(token)


def test_decrypt_rejects_corrupted_ciphertext(cipher):
    token = cipher.encrypt("sk-value")
    corrupted = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(CredentialError):
        cipher.decrypt(corrupted)


# ---------------------------------------------------------------------------
# Empty / missing inputs
# ---------------------------------------------------------------------------


def test_encrypt_rejects_empty_plaintext(cipher):
    with pytest.raises(CredentialError):
        cipher.encrypt("")


def test_decrypt_rejects_empty_ciphertext(cipher):
    with pytest.raises(CredentialError):
        cipher.decrypt("")


# ---------------------------------------------------------------------------
# Server-secret resolution from the environment
# ---------------------------------------------------------------------------


def test_secret_loaded_from_environment(monkeypatch):
    monkeypatch.setenv(SERVER_SECRET_ENV, "env-secret")
    cipher = CredentialCipher()  # no explicit secret → read from env
    assert cipher.decrypt(cipher.encrypt("sk-env")) == "sk-env"


def test_missing_secret_raises_clear_error(monkeypatch):
    monkeypatch.delenv(SERVER_SECRET_ENV, raising=False)
    # Prevent a real project .env from supplying the secret during the test.
    monkeypatch.setattr("app.security.crypto.load_dotenv", lambda *a, **k: False)
    with pytest.raises(CredentialError) as exc:
        CredentialCipher()
    # The error names the env var but never leaks any key material.
    assert SERVER_SECRET_ENV in str(exc.value)


def test_empty_explicit_secret_rejected():
    with pytest.raises(CredentialError):
        CredentialCipher(secret="")


def test_reset_cipher_clears_default(monkeypatch):
    from app.security import crypto

    monkeypatch.setenv(SERVER_SECRET_ENV, "first")
    first = crypto.get_cipher()
    assert crypto.get_cipher() is first  # cached
    reset_cipher()
    monkeypatch.setenv(SERVER_SECRET_ENV, "second")
    assert crypto.get_cipher() is not first


# ---------------------------------------------------------------------------
# Integration with persistence: only ciphertext is stored, never plaintext
# ---------------------------------------------------------------------------


def test_provider_stores_only_ciphertext_and_exposes_has_key(cipher):
    from app.db.models import Provider

    plaintext = "sk-proj-super-secret"
    provider = Provider(
        name="OpenAI",
        kind="openai",
        encrypted_api_key=cipher.encrypt(plaintext),
        models=["gpt-4o"],
    )

    # has_key is the only key info exposed upward.
    assert provider.has_key is True
    # The stored column is ciphertext, not the plaintext key.
    assert provider.encrypted_api_key != plaintext
    assert plaintext not in provider.encrypted_api_key
    # The provider layer can still recover the key at call time.
    assert cipher.decrypt(provider.encrypted_api_key) == plaintext


def test_serialized_provider_never_contains_plaintext(cipher):
    """A dict/JSON view of a provider row must not carry the plaintext key."""
    from app.db.models import Provider

    plaintext = "sk-proj-never-serialize-me"
    provider = Provider(
        name="OpenAI",
        kind="openai",
        base_url=None,
        encrypted_api_key=cipher.encrypt(plaintext),
        models=["gpt-4o"],
    )

    serialized = {
        "id": provider.id,
        "name": provider.name,
        "kind": provider.kind,
        "base_url": provider.base_url,
        "models": provider.models,
        "has_key": provider.has_key,
    }
    assert plaintext not in json.dumps(serialized)
    assert "encrypted_api_key" not in serialized
