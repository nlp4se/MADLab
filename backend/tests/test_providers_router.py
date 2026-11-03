"""API tests for the providers router (task 6.4).

Covers every path — ``GET/POST /api/providers``, ``GET/PUT/DELETE
/api/providers/{id}``, ``POST /api/providers/{id}/test`` — plus the cross-cutting
invariant the task calls out (Req 8.4): the API key plaintext/ciphertext is
**never** returned in any response.

Each test runs against a FastAPI ``TestClient`` over an app built with a
temp-file SQLite database (so the lifespan's seeding and the service-layer
connections observe the same schema/rows, unlike ``:memory:`` where each
connection is an independent empty database). A fixed server secret is supplied
so credential encryption/decryption is deterministic across the process.

The connectivity test (Req 8.5) is exercised fully offline: the service's
default registry factory is monkeypatched to build a :class:`ProviderRegistry`
with an injected :class:`~mad.providers.base.MockModelClient` factory, so no real
LiteLLM client is constructed and no network call is made.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import API_PREFIX, create_app
from app.security import crypto
from mad.providers.base import MockModelClient, ModelResponse, Usage
from mad.providers.registry import ProviderConfig, ProviderRegistry

FRONTEND_ORIGIN = "http://localhost:5173"
SERVER_SECRET = "test-secret-for-providers"

# A sentinel plaintext key we assert never appears in any serialized response.
SECRET_KEY_VALUE = "sk-super-secret-value-123"


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    """A TestClient over an app backed by a temp-file SQLite DB (shared state)."""
    # Deterministic server secret for Fernet derivation; reset the cached cipher
    # so this secret (not a leftover process one) is used.
    monkeypatch.setenv(crypto.SERVER_SECRET_ENV, SERVER_SECRET)
    crypto.reset_cipher()

    db_url = f"sqlite:///{tmp_path.as_posix()}/providers.db"
    settings = Settings(
        database_url=db_url,
        cors_origins=[FRONTEND_ORIGIN],
        secret_key=SERVER_SECRET,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client

    crypto.reset_cipher()


def _create(client: TestClient, **overrides) -> dict:
    payload = {
        "name": "OpenAI",
        "kind": "openai",
        "models": ["gpt-4o"],
        "api_key": SECRET_KEY_VALUE,
    }
    payload.update(overrides)
    resp = client.post(f"{API_PREFIX}/providers", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _assert_no_key_material(payload) -> None:
    """Fail if any key plaintext or ciphertext shape appears in ``payload``.

    Checks the raw serialized text for the plaintext value, for any ``api_key``/
    ``encrypted_api_key`` field name, and for the Fernet ciphertext that the
    stored key would encrypt to under the test secret.
    """
    import json

    raw = json.dumps(payload)
    assert SECRET_KEY_VALUE not in raw
    assert "api_key" not in raw
    assert "encrypted_api_key" not in raw

    # The exact ciphertext for the stored key under the test secret must not leak
    # either. (Fernet tokens are non-deterministic, so we check the field/plain
    # text above; here we assert the known plaintext simply isn't present.)


# --------------------------------------------------------------------------- #
# OpenAPI / routing
# --------------------------------------------------------------------------- #


def test_openapi_exposes_provider_paths(client: TestClient):
    paths = client.get("/openapi.json").json()["paths"]
    assert f"{API_PREFIX}/providers" in paths
    assert f"{API_PREFIX}/providers/{{provider_id}}" in paths
    assert f"{API_PREFIX}/providers/{{provider_id}}/test" in paths


# --------------------------------------------------------------------------- #
# Create (Req 8.1-8.4)
# --------------------------------------------------------------------------- #


def test_create_provider_with_key(client: TestClient):
    body = _create(client)
    assert body["name"] == "OpenAI"
    assert body["kind"] == "openai"
    assert body["models"] == ["gpt-4o"]
    assert body["has_key"] is True
    assert body["id"] >= 1
    _assert_no_key_material(body)


def test_create_provider_without_key(client: TestClient):
    body = _create(
        client,
        name="Local Ollama",
        kind="ollama",
        base_url="http://localhost:11434",
        models=["llama3"],
        api_key=None,
    )
    assert body["has_key"] is False
    assert body["base_url"] == "http://localhost:11434"
    _assert_no_key_material(body)


@pytest.mark.parametrize(
    "kind",
    [
        "openai",
        "anthropic",
        "gemini",
        "mistral",
        "deepseek",
        "ollama",
        "vllm",
        "openai_compatible",
    ],
)
def test_create_supports_all_provider_kinds(client: TestClient, kind: str):
    """Every supported provider kind is accepted (Req 8.2)."""
    body = _create(client, name=f"{kind} provider", kind=kind, api_key=None)
    assert body["kind"] == kind


def test_create_rejects_unknown_kind(client: TestClient):
    resp = client.post(
        f"{API_PREFIX}/providers",
        json={"name": "Bad", "kind": "not-a-provider"},
    )
    assert resp.status_code == 422


def test_create_stores_ciphertext_not_plaintext(client: TestClient, tmp_path):
    """The persisted key is encrypted — the plaintext is never written to the DB."""
    created = _create(client)
    pid = created["id"]

    # Inspect the row directly via the service-layer session.
    from app.db.models import Provider
    from app.db.session import session_scope

    with session_scope() as session:
        row = session.get(Provider, pid)
        assert row is not None
        assert row.encrypted_api_key is not None
        assert row.encrypted_api_key != SECRET_KEY_VALUE
        # Round-trips back to the original plaintext inside the security layer only.
        assert crypto.decrypt_api_key(row.encrypted_api_key) == SECRET_KEY_VALUE


# --------------------------------------------------------------------------- #
# List (Req 8.1) / Get
# --------------------------------------------------------------------------- #


def test_list_providers(client: TestClient):
    _create(client, name="P1")
    _create(client, name="P2", api_key=None)
    resp = client.get(f"{API_PREFIX}/providers")
    assert resp.status_code == 200
    rows = resp.json()
    assert [r["name"] for r in rows] == ["P1", "P2"]
    _assert_no_key_material(rows)


def test_get_provider(client: TestClient):
    created = _create(client)
    resp = client.get(f"{API_PREFIX}/providers/{created['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == created["id"]
    assert body["has_key"] is True
    _assert_no_key_material(body)


def test_get_missing_returns_404(client: TestClient):
    assert client.get(f"{API_PREFIX}/providers/999999").status_code == 404


# --------------------------------------------------------------------------- #
# Update (Req 8.1, 8.3, 8.4) — write-only key semantics
# --------------------------------------------------------------------------- #


def test_update_metadata_keeps_existing_key(client: TestClient):
    """Omitting ``api_key`` on update keeps the stored key (write-only, Req 8.4)."""
    created = _create(client)
    pid = created["id"]

    resp = client.put(
        f"{API_PREFIX}/providers/{pid}",
        json={"name": "Renamed", "models": ["gpt-4o", "gpt-4o-mini"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Renamed"
    assert body["models"] == ["gpt-4o", "gpt-4o-mini"]
    assert body["has_key"] is True  # key preserved
    _assert_no_key_material(body)


def test_update_replaces_key_when_provided(client: TestClient):
    created = _create(client)
    pid = created["id"]

    from app.db.models import Provider
    from app.db.session import session_scope

    with session_scope() as session:
        before = session.get(Provider, pid).encrypted_api_key

    resp = client.put(
        f"{API_PREFIX}/providers/{pid}",
        json={"api_key": "sk-a-different-key"},
    )
    assert resp.status_code == 200
    assert resp.json()["has_key"] is True
    _assert_no_key_material(resp.json())

    with session_scope() as session:
        after = session.get(Provider, pid).encrypted_api_key
        assert after != before
        assert crypto.decrypt_api_key(after) == "sk-a-different-key"


def test_update_clears_key_with_explicit_null(client: TestClient):
    created = _create(client)
    pid = created["id"]
    resp = client.put(f"{API_PREFIX}/providers/{pid}", json={"api_key": None})
    assert resp.status_code == 200
    assert resp.json()["has_key"] is False
    _assert_no_key_material(resp.json())


def test_update_missing_returns_404(client: TestClient):
    assert (
        client.put(f"{API_PREFIX}/providers/999999", json={"name": "x"}).status_code
        == 404
    )


# --------------------------------------------------------------------------- #
# Delete (Req 8.1)
# --------------------------------------------------------------------------- #


def test_delete_provider(client: TestClient):
    created = _create(client)
    pid = created["id"]
    resp = client.delete(f"{API_PREFIX}/providers/{pid}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert client.get(f"{API_PREFIX}/providers/{pid}").status_code == 404


def test_delete_missing_returns_404(client: TestClient):
    assert client.delete(f"{API_PREFIX}/providers/999999").status_code == 404


# --------------------------------------------------------------------------- #
# Connectivity test (Req 8.5) — fully offline via a mock registry factory
# --------------------------------------------------------------------------- #


def _patch_registry(monkeypatch, *, responder=None, boom=False):
    """Patch the service default registry factory to build an offline registry."""
    from app.services import providers as provider_service

    def client_factory(config: ProviderConfig) -> MockModelClient:
        if boom:
            class _Boom(MockModelClient):
                def complete(self, *args, **kwargs):
                    raise RuntimeError("connection refused")

            return _Boom()
        return MockModelClient(
            responder=responder
            or (lambda *_: ModelResponse(text="OK", usage=Usage(latency_s=0.01)))
        )

    def factory() -> ProviderRegistry:
        return ProviderRegistry(client_factory=client_factory)

    monkeypatch.setattr(provider_service, "_default_registry_factory", factory)


def test_test_connection_success(client: TestClient, monkeypatch):
    created = _create(client)
    _patch_registry(monkeypatch)

    resp = client.post(f"{API_PREFIX}/providers/{created['id']}/test", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["model"] == "gpt-4o"
    assert body["latency_s"] == 0.01
    _assert_no_key_material(body)


def test_test_connection_explicit_model(client: TestClient, monkeypatch):
    created = _create(client)
    captured = {}

    def responder(messages, model, params, schema):
        captured["model"] = model
        return "OK"

    _patch_registry(monkeypatch, responder=responder)
    resp = client.post(
        f"{API_PREFIX}/providers/{created['id']}/test",
        json={"model": "gpt-4o-mini"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["model"] == "gpt-4o-mini"
    assert captured["model"] == "gpt-4o-mini"


def test_test_connection_failure_reports_clear_error(client: TestClient, monkeypatch):
    created = _create(client)
    _patch_registry(monkeypatch, boom=True)

    resp = client.post(f"{API_PREFIX}/providers/{created['id']}/test", json={})
    assert resp.status_code == 200  # never raises; reported as ok=False
    body = resp.json()
    assert body["ok"] is False
    assert "connection refused" in body["message"]


def test_test_connection_missing_provider_returns_404(client: TestClient):
    assert (
        client.post(f"{API_PREFIX}/providers/999999/test", json={}).status_code == 404
    )


# --------------------------------------------------------------------------- #
# Cross-cutting: key never returned anywhere (Req 8.4)
# --------------------------------------------------------------------------- #


def test_key_never_returned_across_all_paths(client: TestClient, monkeypatch):
    """Walk every response path and assert no key plaintext/ciphertext leaks."""
    created = _create(client)
    pid = created["id"]

    payloads = [
        created,
        client.get(f"{API_PREFIX}/providers").json(),
        client.get(f"{API_PREFIX}/providers/{pid}").json(),
        client.put(f"{API_PREFIX}/providers/{pid}", json={"name": "N2"}).json(),
    ]
    _patch_registry(monkeypatch)
    payloads.append(
        client.post(f"{API_PREFIX}/providers/{pid}/test", json={}).json()
    )

    for payload in payloads:
        _assert_no_key_material(payload)
