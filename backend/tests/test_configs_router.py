"""API tests for the configurations router (task 6.3).

Covers every path — ``GET/POST /api/configs``, ``GET/PUT/DELETE
/api/configs/{id}``, ``POST /configs/{id}/copy``, ``POST /configs/import``,
``GET /configs/{id}/export``, ``POST /configs/validate`` — plus the two
cross-cutting behaviours the task calls out: validation rejection with
actionable errors (Req 4.2, 7.3) and the built-in gold/template configs being
seeded on first run (Req 5.7).

Each test runs against a FastAPI ``TestClient`` over an app built with a
temp-file SQLite database (so the lifespan's seeding and the separate
service-layer connections observe the same schema/rows, unlike ``:memory:``
where each connection is an independent empty database).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import API_PREFIX, create_app
from mad.taxonomy import templates
from mad.taxonomy.version import export_config

FRONTEND_ORIGIN = "http://localhost:5173"


@pytest.fixture()
def client(tmp_path) -> TestClient:
    """A TestClient over an app backed by a temp-file SQLite DB (shared state)."""
    db_url = f"sqlite:///{tmp_path.as_posix()}/configs.db"
    settings = Settings(
        database_url=db_url,
        cors_origins=[FRONTEND_ORIGIN],
        secret_key="test-secret",
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _configs(client: TestClient) -> list[dict]:
    resp = client.get(f"{API_PREFIX}/configs")
    assert resp.status_code == 200
    return resp.json()


# --------------------------------------------------------------------------- #
# OpenAPI / routing
# --------------------------------------------------------------------------- #


def test_openapi_exposes_config_paths(client: TestClient):
    paths = client.get("/openapi.json").json()["paths"]
    assert f"{API_PREFIX}/configs" in paths
    assert f"{API_PREFIX}/configs/{{config_id}}" in paths
    assert f"{API_PREFIX}/configs/{{config_id}}/copy" in paths
    assert f"{API_PREFIX}/configs/import" in paths
    assert f"{API_PREFIX}/configs/{{config_id}}/export" in paths
    assert f"{API_PREFIX}/configs/validate" in paths


# --------------------------------------------------------------------------- #
# Seeding (Req 5.7)
# --------------------------------------------------------------------------- #


def test_builtin_gold_configs_seeded_on_first_run(client: TestClient):
    rows = _configs(client)
    names = {r["name"] for r in rows}
    expected = {templates.build_gold_case(k).name for k in (
        "re_binary_debate", "chateval_s1", "chateval_s2", "chateval_s3"
    )}
    assert expected <= names
    # Each gold config is flagged as a built-in.
    for row in rows:
        if row["name"] in expected:
            assert row["is_builtin"] is True


def test_seeding_is_idempotent_across_restarts(tmp_path):
    """Re-building the app over the same DB does not duplicate built-ins."""
    db_url = f"sqlite:///{tmp_path.as_posix()}/seed.db"
    settings = Settings(database_url=db_url, cors_origins=[FRONTEND_ORIGIN])

    with TestClient(create_app(settings)) as c1:
        first = _configs(c1)
    with TestClient(create_app(settings)) as c2:
        second = _configs(c2)

    assert len(first) == len(second)
    assert len(first) == 4  # exactly the four gold cases, once each


def test_seeded_summary_attributes(client: TestClient):
    rows = _configs(client)
    re_name = templates.build_gold_case("re_binary_debate").name
    re_row = next(r for r in rows if r["name"] == re_name)
    attrs = re_row["attributes"]
    assert attrs["participant_count"] == 3
    assert attrs["authority"] == "judge_based"
    assert attrs["resolution"] == "argument_evaluation"
    assert attrs["protocol_mechanism"] == "sequential"


# --------------------------------------------------------------------------- #
# Create (Req 5.2) / Get (Req 5.3)
# --------------------------------------------------------------------------- #


def test_create_with_defaults(client: TestClient):
    resp = client.post(f"{API_PREFIX}/configs", json={"name": "My config"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "My config"
    assert body["artifact"]["name"] == "My config"
    assert body["schema_version"]
    assert body["is_builtin"] is False
    # Defaults are immediately valid.
    assert "participants" in body["artifact"]


def test_create_from_artifact_and_get(client: TestClient):
    artifact = export_config(templates.build_gold_case("chateval_s1"))
    resp = client.post(
        f"{API_PREFIX}/configs",
        json={"name": "Imported S1", "artifact": artifact},
    )
    assert resp.status_code == 201
    created = resp.json()
    cid = created["id"]

    got = client.get(f"{API_PREFIX}/configs/{cid}")
    assert got.status_code == 200
    assert got.json()["name"] == "Imported S1"
    assert got.json()["artifact"]["participants"]["nodes"]


def test_get_missing_returns_404(client: TestClient):
    resp = client.get(f"{API_PREFIX}/configs/999999")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Update (Req 5.3)
# --------------------------------------------------------------------------- #


def test_update_name_only(client: TestClient):
    created = client.post(f"{API_PREFIX}/configs", json={"name": "Before"}).json()
    cid = created["id"]
    resp = client.put(f"{API_PREFIX}/configs/{cid}", json={"name": "After"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "After"
    assert body["artifact"]["name"] == "After"


def test_update_artifact_revalidated(client: TestClient):
    created = client.post(f"{API_PREFIX}/configs", json={"name": "Edit me"}).json()
    cid = created["id"]
    new_artifact = export_config(templates.build_gold_case("chateval_s2"))
    resp = client.put(
        f"{API_PREFIX}/configs/{cid}",
        json={"artifact": new_artifact},
    )
    assert resp.status_code == 200
    assert resp.json()["artifact"]["interaction"]["protocol"]["mechanism"] == "simultaneous"


def test_update_missing_returns_404(client: TestClient):
    resp = client.put(f"{API_PREFIX}/configs/999999", json={"name": "x"})
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Copy (Req 5.5)
# --------------------------------------------------------------------------- #


def test_copy_creates_independent_config(client: TestClient):
    created = client.post(f"{API_PREFIX}/configs", json={"name": "Original"}).json()
    cid = created["id"]
    resp = client.post(f"{API_PREFIX}/configs/{cid}/copy", json={})
    assert resp.status_code == 201
    copy = resp.json()
    assert copy["id"] != cid
    assert copy["name"] == "Copy of Original"
    # The copy has its own artifact identity.
    assert copy["artifact"]["id"] != created["artifact"]["id"]


def test_copy_with_custom_name(client: TestClient):
    created = client.post(f"{API_PREFIX}/configs", json={"name": "Src"}).json()
    resp = client.post(
        f"{API_PREFIX}/configs/{created['id']}/copy",
        json={"name": "My duplicate"},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "My duplicate"


def test_copy_missing_returns_404(client: TestClient):
    resp = client.post(f"{API_PREFIX}/configs/999999/copy", json={})
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Delete (Req 5.4)
# --------------------------------------------------------------------------- #


def test_delete_returns_reference_count_zero(client: TestClient):
    created = client.post(f"{API_PREFIX}/configs", json={"name": "Deletable"}).json()
    cid = created["id"]
    resp = client.delete(f"{API_PREFIX}/configs/{cid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] is True
    assert body["referencing_executions"] == 0
    # Gone afterwards.
    assert client.get(f"{API_PREFIX}/configs/{cid}").status_code == 404


def test_delete_missing_returns_404(client: TestClient):
    resp = client.delete(f"{API_PREFIX}/configs/999999")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Import (Req 4.2, 4.3) / Export (Req 4.3)
# --------------------------------------------------------------------------- #


def test_import_valid_artifact(client: TestClient):
    artifact = export_config(templates.build_gold_case("re_binary_debate"))
    resp = client.post(
        f"{API_PREFIX}/configs/import",
        json={"artifact": artifact, "name": "Imported RE"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Imported RE"
    assert body["artifact"]["agreement"]["authority"] == "judge_based"


def test_import_invalid_artifact_rejected_with_errors(client: TestClient):
    # Judge-based authority but no judge node -> semantic validation failure.
    bad = export_config(templates.build_gold_case("re_binary_debate"))
    for node in bad["participants"]["nodes"]:
        node["roles"] = ["debater"]  # strip the judge role
    resp = client.post(f"{API_PREFIX}/configs/import", json={"artifact": bad})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "ConfigValidationError"
    assert "judge" in body["detail"].lower()


def test_export_roundtrips_to_import(client: TestClient):
    rows = _configs(client)
    cid = rows[0]["id"]
    resp = client.get(f"{API_PREFIX}/configs/{cid}/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert "attachment" in resp.headers.get("content-disposition", "")
    artifact = resp.json()
    assert artifact["schema_version"]

    # Round-trip: the exported artifact imports cleanly.
    back = client.post(f"{API_PREFIX}/configs/import", json={"artifact": artifact})
    assert back.status_code == 201


def test_export_missing_returns_404(client: TestClient):
    resp = client.get(f"{API_PREFIX}/configs/999999/export")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Validate (Req 4.2, 7.3)
# --------------------------------------------------------------------------- #


def test_validate_valid_artifact(client: TestClient):
    artifact = export_config(templates.build_gold_case("chateval_s1"))
    resp = client.post(f"{API_PREFIX}/configs/validate", json={"artifact": artifact})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["errors"] == []


def test_validate_invalid_artifact_returns_structured_errors(client: TestClient):
    bad = export_config(templates.build_gold_case("re_binary_debate"))
    # Point an edge at a non-existent node -> semantic validation failure.
    bad["interaction"]["topology"]["edges"].append(
        {"source": "ghost", "target": "judge", "directed": True}
    )
    resp = client.post(f"{API_PREFIX}/configs/validate", json={"artifact": bad})
    assert resp.status_code == 200  # validate never 4xx's for a bad artifact
    body = resp.json()
    assert body["valid"] is False
    assert body["errors"]
    assert any("ghost" in e["message"] for e in body["errors"])


def test_validate_reports_under_development(client: TestClient):
    # 'dynamic' topology adaptability is a non-executable (under-dev) value.
    artifact = export_config(templates.build_gold_case("chateval_s1"))
    artifact["interaction"]["topology"]["adaptability"] = "dynamic"
    resp = client.post(f"{API_PREFIX}/configs/validate", json={"artifact": artifact})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert "dynamic" in body["under_development"]
