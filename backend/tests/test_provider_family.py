"""Base-model family derived from the provider (task 11.9).

Covers the kind -> family mapping, the idempotent ``providers.family`` column
migration on an old-schema database, the provider API accepting/rejecting a
family, and the normalization of ``base_model.family`` on configuration
save/import and in the execution snapshot.

Validates: Requirements 1.7, 1.8, 8.2, 8.6, 14.3
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.config import Settings
from app.db.models import Configuration, Provider
from app.db.session import (
    SCHEMA_VERSION,
    create_engine_for,
    get_schema_version,
    init_db,
)
from app.main import API_PREFIX, create_app
from app.provider_family import (
    FIXED_KIND_FAMILY,
    check_family_for_kind,
    default_family,
    effective_family,
    is_mixed_kind,
)
from app.schemas.executions import ExecutionCreateRequest
from app.schemas.providers import PROVIDER_KINDS
from app.security import crypto
from app.services import executions as executions_service
from mad.providers.registry import ProviderRegistry
from mad.taxonomy.schema import MADConfig
from sqlalchemy.orm import sessionmaker

SERVER_SECRET = "test-secret-for-family"


# --------------------------------------------------------------------------- #
# Mapping
# --------------------------------------------------------------------------- #


def test_every_kind_has_a_family():
    for kind in PROVIDER_KINDS:
        assert effective_family(kind, None) in ("open_weight", "closed_weight")


@pytest.mark.parametrize(
    "kind,family",
    [
        ("openai", "closed_weight"),
        ("anthropic", "closed_weight"),
        ("gemini", "closed_weight"),
        ("ollama", "open_weight"),
        ("vllm", "open_weight"),
        ("deepseek", "open_weight"),
    ],
)
def test_fixed_kinds_ignore_stored_value(kind, family):
    assert not is_mixed_kind(kind)
    other = "open_weight" if family == "closed_weight" else "closed_weight"
    assert effective_family(kind, None) == family
    assert effective_family(kind, other) == family
    # A matching value is a no-op; a contradicting one is rejected.
    assert check_family_for_kind(kind, family) is None
    with pytest.raises(ValueError):
        check_family_for_kind(kind, other)


def test_mixed_kinds_use_stored_value_with_defaults():
    assert default_family("mistral") == "closed_weight"
    assert default_family("openai_compatible") == "open_weight"
    for kind in ("mistral", "openai_compatible"):
        assert is_mixed_kind(kind)
        assert kind not in FIXED_KIND_FAMILY
        assert effective_family(kind, "open_weight") == "open_weight"
        assert effective_family(kind, "closed_weight") == "closed_weight"
        assert check_family_for_kind(kind, "open_weight") == "open_weight"
    assert effective_family("mistral", None) == "closed_weight"
    assert effective_family("openai_compatible", None) == "open_weight"


# --------------------------------------------------------------------------- #
# Migration on an old-schema database
# --------------------------------------------------------------------------- #


def _make_old_db(path) -> None:
    """Create a schema-version-1 database: providers without ``family``."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE providers (
            id INTEGER NOT NULL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            kind VARCHAR(64) NOT NULL,
            base_url VARCHAR(1024),
            encrypted_api_key TEXT,
            models JSON NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        );
        CREATE TABLE schema_meta (
            key VARCHAR(64) NOT NULL PRIMARY KEY,
            value VARCHAR(256) NOT NULL
        );
        INSERT INTO providers (id, name, kind, base_url, encrypted_api_key, models,
                               created_at, updated_at)
        VALUES (1, 'Local', 'ollama', 'http://localhost:11434', NULL, '["llama3"]',
                '2024-01-01 00:00:00', '2024-01-01 00:00:00'),
               (2, 'Gateway', 'openai_compatible', NULL, 'cipher', '["m"]',
                '2024-01-01 00:00:00', '2024-01-01 00:00:00');
        INSERT INTO schema_meta (key, value) VALUES ('schema_version', '1');
        """
    )
    conn.commit()
    conn.close()


def test_init_db_adds_family_column_to_old_db(tmp_path):
    db_path = tmp_path / "old.db"
    _make_old_db(db_path)
    engine = create_engine_for(f"sqlite:///{db_path.as_posix()}")

    assert init_db(engine) == SCHEMA_VERSION == "3"
    assert "family" in {c["name"] for c in inspect(engine).get_columns("providers")}
    # Idempotent: a second run neither fails nor changes the result.
    assert init_db(engine) == SCHEMA_VERSION
    assert get_schema_version(engine) == SCHEMA_VERSION

    with sessionmaker(bind=engine)() as session:
        rows = {p.id: p for p in session.query(Provider).all()}
    assert rows[1].name == "Local" and rows[1].models == ["llama3"]
    assert rows[2].encrypted_api_key == "cipher"
    assert rows[1].family is None and rows[2].family is None
    assert effective_family(rows[2].kind, rows[2].family) == "open_weight"
    # Other tables were created by create_all.
    assert "configurations" in inspect(engine).get_table_names()
    engine.dispose()


# --------------------------------------------------------------------------- #
# Provider API
# --------------------------------------------------------------------------- #


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv(crypto.SERVER_SECRET_ENV, SERVER_SECRET)
    crypto.reset_cipher()
    settings = Settings(
        database_url=f"sqlite:///{tmp_path.as_posix()}/family.db",
        cors_origins=["http://localhost:5173"],
        secret_key=SERVER_SECRET,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
    crypto.reset_cipher()


def _create(client, **payload):
    body = {"name": "P", "kind": "openai", "models": ["m"], **payload}
    return client.post(f"{API_PREFIX}/providers", json=body)


def test_provider_response_returns_effective_family(client):
    assert _create(client, kind="openai").json()["family"] == "closed_weight"
    assert _create(client, kind="ollama").json()["family"] == "open_weight"
    assert _create(client, kind="mistral").json()["family"] == "closed_weight"
    assert _create(client, kind="openai_compatible").json()["family"] == "open_weight"
    listed = client.get(f"{API_PREFIX}/providers").json()
    assert [p["family"] for p in listed] == [
        "closed_weight",
        "open_weight",
        "closed_weight",
        "open_weight",
    ]


def test_create_accepts_family_for_mixed_kind_and_matching_fixed(client):
    resp = _create(client, kind="mistral", family="open_weight")
    assert resp.status_code == 201, resp.text
    assert resp.json()["family"] == "open_weight"
    resp = _create(client, kind="anthropic", family="closed_weight")
    assert resp.status_code == 201, resp.text
    assert resp.json()["family"] == "closed_weight"


def test_create_rejects_contradicting_or_unknown_family(client):
    assert _create(client, kind="openai", family="open_weight").status_code == 422
    assert _create(client, kind="vllm", family="closed_weight").status_code == 422
    assert _create(client, kind="mistral", family="half_open").status_code == 422


def test_update_family_rules(client):
    pid = _create(client, kind="openai_compatible").json()["id"]
    url = f"{API_PREFIX}/providers/{pid}"

    resp = client.put(url, json={"family": "closed_weight"})
    assert resp.status_code == 200 and resp.json()["family"] == "closed_weight"
    # Omitting family keeps the stored choice.
    resp = client.put(url, json={"name": "Renamed"})
    assert resp.json()["family"] == "closed_weight"
    # Null resets to the kind default.
    resp = client.put(url, json={"family": None})
    assert resp.json()["family"] == "open_weight"

    # Contradicting a fixed kind (current or new) is rejected; row unchanged.
    resp = client.put(url, json={"kind": "openai", "family": "open_weight"})
    assert resp.status_code == 422
    assert client.get(url).json()["kind"] == "openai_compatible"

    # Changing kind without family re-derives from the new kind.
    client.put(url, json={"family": "closed_weight"})
    resp = client.put(url, json={"kind": "ollama"})
    assert resp.json()["family"] == "open_weight"
    resp = client.put(url, json={"kind": "openai_compatible"})
    assert resp.json()["family"] == "open_weight"  # stored choice was reset
    resp = client.put(url, json={"kind": "mistral"})
    assert resp.json()["family"] == "closed_weight"

    fixed = _create(client, kind="gemini").json()["id"]
    resp = client.put(f"{API_PREFIX}/providers/{fixed}", json={"family": "open_weight"})
    assert resp.status_code == 422
    resp = client.put(f"{API_PREFIX}/providers/{fixed}", json={"family": "closed_weight"})
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# Save / import / snapshot normalization
# --------------------------------------------------------------------------- #


def _artifact(bound_provider_id: str) -> dict:
    """Two nodes: one bound (stale family), one unbound (family kept)."""
    return {
        "schema_version": "1.0",
        "name": "Family test",
        "participants": {
            "base_model_heterogeneity": "heterogeneous",
            "nodes": [
                {
                    "id": "a",
                    "label": "A",
                    "base_model": {
                        "provider_id": bound_provider_id,
                        "model_key": "m",
                        "family": "closed_weight",
                    },
                },
                {
                    "id": "b",
                    "label": "B",
                    "base_model": {"provider_id": None, "family": "open_weight"},
                },
                {
                    "id": "c",
                    "label": "C",
                    "base_model": {"provider_id": "999", "family": "closed_weight"},
                },
            ],
        },
        "input_spec": {"template": "", "placeholders": []},
    }


def _families(artifact: dict) -> list[str]:
    return [n["base_model"]["family"] for n in artifact["participants"]["nodes"]]


def test_config_create_update_import_normalize_family(client):
    pid = str(_create(client, kind="ollama").json()["id"])
    expected = ["open_weight", "open_weight", "closed_weight"]

    resp = client.post(f"{API_PREFIX}/configs", json={"artifact": _artifact(pid)})
    assert resp.status_code == 201, resp.text
    assert _families(resp.json()["artifact"]) == expected

    cid = resp.json()["id"]
    resp = client.put(f"{API_PREFIX}/configs/{cid}", json={"artifact": _artifact(pid)})
    assert resp.status_code == 200, resp.text
    assert _families(resp.json()["artifact"]) == expected

    resp = client.post(f"{API_PREFIX}/configs/import", json={"artifact": _artifact(pid)})
    assert resp.status_code in (200, 201), resp.text
    assert _families(resp.json()["artifact"]) == expected


def test_execution_snapshot_normalizes_family(tmp_path):
    engine = create_engine_for(f"sqlite:///{tmp_path.as_posix()}/snap.db")
    init_db(engine)
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with maker() as session:
        provider = Provider(name="Mistral", kind="mistral", models=["m"], family="open_weight")
        session.add(provider)
        session.flush()
        pid = str(provider.id)
        # A stored artifact whose family went stale (e.g. provider edited later).
        artifact = MADConfig.model_validate(_artifact(pid)).model_dump(mode="json")
        row = Configuration(name="c", artifact=artifact, schema_version="1.0")
        session.add(row)
        session.commit()
        config_id = row.id

    with maker() as session:
        detail = executions_service.create_execution(
            session,
            ExecutionCreateRequest(config_id=config_id, input={}),
            launch=lambda _id, _registry: None,
            registry=ProviderRegistry(),
        )
        assert _families(detail.config_snapshot) == [
            "open_weight",
            "open_weight",
            "closed_weight",
        ]
        # The stored configuration itself is untouched by launching.
        stored = session.get(Configuration, config_id).artifact
        assert _families(stored)[0] == "closed_weight"
    engine.dispose()
