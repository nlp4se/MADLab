"""API tests for the datasets router (task 6.5).

Covers every path — ``POST /api/datasets`` (CSV upload), ``GET
/api/datasets/{id}`` (metadata), ``POST /api/datasets/{id}/preview`` (resolved
template for a sample row) — against a FastAPI ``TestClient``.

Each test runs over an app built with a temp-file SQLite database (so the
lifespan's seeding and the service-layer connections observe the same schema and
rows) and a temp dataset storage directory supplied via settings, so uploads are
written under the test's control and never touch the real ``data/`` tree.

The real research dataset ``data/datasets/PROMISE/nfr-small.csv`` provides the
upload bytes, so columns (``requirement``, ``type``) and row_count are exercised
end-to-end (Req 10.1, 10.3).

Validates: Requirements 10.1, 10.3
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import API_PREFIX, create_app

FRONTEND_ORIGIN = "http://localhost:5173"

REPO_ROOT = Path(__file__).resolve().parents[2]
NFR_SMALL = REPO_ROOT / "data" / "datasets" / "PROMISE" / "nfr-small.csv"


@pytest.fixture()
def nfr_bytes() -> bytes:
    assert NFR_SMALL.exists(), f"fixture dataset missing: {NFR_SMALL}"
    return NFR_SMALL.read_bytes()


@pytest.fixture()
def client(tmp_path) -> TestClient:
    """A TestClient over an app backed by temp DB + temp dataset storage."""
    db_url = f"sqlite:///{tmp_path.as_posix()}/datasets.db"
    storage = tmp_path / "storage"
    settings = Settings(
        database_url=db_url,
        cors_origins=[FRONTEND_ORIGIN],
        dataset_storage_path=str(storage),
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        test_client.storage_dir = storage  # type: ignore[attr-defined]
        yield test_client


def _upload(client: TestClient, content: bytes, *, filename="nfr-small.csv", name=None):
    data = {"name": name} if name is not None else {}
    resp = client.post(
        f"{API_PREFIX}/datasets",
        files={"file": (filename, content, "text/csv")},
        data=data,
    )
    return resp


# --------------------------------------------------------------------------- #
# OpenAPI / routing
# --------------------------------------------------------------------------- #


def test_openapi_exposes_dataset_paths(client: TestClient):
    paths = client.get("/openapi.json").json()["paths"]
    assert f"{API_PREFIX}/datasets" in paths
    assert f"{API_PREFIX}/datasets/{{dataset_id}}" in paths
    assert f"{API_PREFIX}/datasets/{{dataset_id}}/preview" in paths


# --------------------------------------------------------------------------- #
# Upload (Req 10.1)
# --------------------------------------------------------------------------- #


def test_upload_captures_columns_and_row_count(client: TestClient, nfr_bytes: bytes):
    resp = _upload(client, nfr_bytes)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] >= 1
    assert body["original_filename"] == "nfr-small.csv"
    assert body["name"] == "nfr-small"
    assert body["columns"] == ["requirement", "type"]
    assert body["row_count"] == 2


def test_upload_writes_file_to_storage_dir(client: TestClient, nfr_bytes: bytes):
    _upload(client, nfr_bytes)
    stored = list(Path(client.storage_dir).glob("*.csv"))  # type: ignore[attr-defined]
    assert len(stored) == 1
    assert stored[0].read_bytes() == nfr_bytes


def test_upload_respects_explicit_name(client: TestClient, nfr_bytes: bytes):
    body = _upload(client, nfr_bytes, name="My NFR set").json()
    assert body["name"] == "My NFR set"


def test_upload_rejects_unparseable_csv(client: TestClient):
    # An empty file cannot be parsed as a CSV with a header → storage error.
    resp = _upload(client, b"", filename="empty.csv")
    assert resp.status_code == 500
    assert resp.json()["error"] == "DatasetStorageError"


def test_two_uploads_same_name_do_not_collide(client: TestClient, nfr_bytes: bytes):
    first = _upload(client, nfr_bytes).json()
    second = _upload(client, nfr_bytes).json()
    assert first["id"] != second["id"]
    stored = list(Path(client.storage_dir).glob("*.csv"))  # type: ignore[attr-defined]
    assert len(stored) == 2


# --------------------------------------------------------------------------- #
# Get (Req 10.1)
# --------------------------------------------------------------------------- #


def test_get_dataset(client: TestClient, nfr_bytes: bytes):
    created = _upload(client, nfr_bytes).json()
    resp = client.get(f"{API_PREFIX}/datasets/{created['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == created["id"]
    assert body["columns"] == ["requirement", "type"]
    assert body["row_count"] == 2


def test_get_missing_returns_404(client: TestClient):
    assert client.get(f"{API_PREFIX}/datasets/999999").status_code == 404


# --------------------------------------------------------------------------- #
# Preview (Req 10.3) — inline template
# --------------------------------------------------------------------------- #


def test_preview_with_inline_template(client: TestClient, nfr_bytes: bytes):
    created = _upload(client, nfr_bytes).json()
    resp = client.post(
        f"{API_PREFIX}/datasets/{created['id']}/preview",
        json={
            "mapping": {"requirement": "requirement"},
            "template": "Classify: {{requirement}}",
            "row_index": 0,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["row_index"] == 0
    assert body["resolved_input"].startswith("Classify: The system shall have a MDI")
    assert body["instance"]["requirement"].startswith("The system shall have a MDI")


def test_preview_selects_sample_row(client: TestClient, nfr_bytes: bytes):
    created = _upload(client, nfr_bytes).json()
    resp = client.post(
        f"{API_PREFIX}/datasets/{created['id']}/preview",
        json={
            "mapping": {"requirement": "requirement"},
            "template": "{{requirement}}",
            "row_index": 1,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["resolved_input"].startswith(
        "The system shall display Events"
    )


# --------------------------------------------------------------------------- #
# Preview (Req 10.3) — resolve template from a referenced configuration
# --------------------------------------------------------------------------- #


def _create_config_with_template(client: TestClient, template: str) -> dict:
    """Create a config, then PUT an artifact whose input_spec.template is set."""
    created = client.post(
        f"{API_PREFIX}/configs",
        json={"name": "Preview config"},
    ).json()
    detail = client.get(f"{API_PREFIX}/configs/{created['id']}").json()
    artifact = detail["artifact"]
    artifact["input_spec"] = {**artifact.get("input_spec", {}), "template": template}
    updated = client.put(
        f"{API_PREFIX}/configs/{created['id']}",
        json={"artifact": artifact},
    )
    assert updated.status_code == 200, updated.text
    return updated.json()


def test_preview_with_config_template(client: TestClient, nfr_bytes: bytes):
    created = _upload(client, nfr_bytes).json()
    config = _create_config_with_template(
        client, "Requirement under review: {{requirement}}"
    )
    resp = client.post(
        f"{API_PREFIX}/datasets/{created['id']}/preview",
        json={
            "mapping": {"requirement": "requirement"},
            "config_id": config["id"],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["resolved_input"].startswith(
        "Requirement under review: The system shall have a MDI"
    )


def test_preview_missing_config_returns_404(client: TestClient, nfr_bytes: bytes):
    created = _upload(client, nfr_bytes).json()
    resp = client.post(
        f"{API_PREFIX}/datasets/{created['id']}/preview",
        json={"mapping": {"requirement": "requirement"}, "config_id": 999999},
    )
    assert resp.status_code == 404


def test_preview_missing_dataset_returns_404(client: TestClient):
    resp = client.post(
        f"{API_PREFIX}/datasets/999999/preview",
        json={"mapping": {"requirement": "requirement"}, "template": "{{requirement}}"},
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Preview validation errors (Req 10.3)
# --------------------------------------------------------------------------- #


def test_preview_requires_a_template_source(client: TestClient, nfr_bytes: bytes):
    created = _upload(client, nfr_bytes).json()
    resp = client.post(
        f"{API_PREFIX}/datasets/{created['id']}/preview",
        json={"mapping": {"requirement": "requirement"}},
    )
    assert resp.status_code == 422


def test_preview_rejects_both_template_sources(client: TestClient, nfr_bytes: bytes):
    created = _upload(client, nfr_bytes).json()
    resp = client.post(
        f"{API_PREFIX}/datasets/{created['id']}/preview",
        json={
            "mapping": {"requirement": "requirement"},
            "template": "{{requirement}}",
            "config_id": 1,
        },
    )
    assert resp.status_code == 422


def test_preview_unmapped_placeholder_is_422(client: TestClient, nfr_bytes: bytes):
    created = _upload(client, nfr_bytes).json()
    resp = client.post(
        f"{API_PREFIX}/datasets/{created['id']}/preview",
        json={
            "mapping": {"requirement": "requirement"},
            "template": "{{missing}}",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "TemplateError"


def test_preview_row_index_out_of_range_is_422(client: TestClient, nfr_bytes: bytes):
    created = _upload(client, nfr_bytes).json()
    resp = client.post(
        f"{API_PREFIX}/datasets/{created['id']}/preview",
        json={
            "mapping": {"requirement": "requirement"},
            "template": "{{requirement}}",
            "row_index": 99,
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "TemplateError"
