"""API tests for the executions router + async job runner (task 6.6).

Covers the execution lifecycle end-to-end over a FastAPI ``TestClient`` with a
temp-file SQLite database and a temp dataset storage dir, fully offline and
deterministic:

* **single-run lifecycle** — launch a single ad-hoc run, it completes, the
  detail carries a transcript + decision, and list/export reflect it;
* **batch progress** — launch a batch over a small CSV, every row produces an
  instance, progress reaches 1.0, and aggregate metrics appear when a
  ground-truth column is mapped;
* **failure isolation** — one instance's provider failure is isolated: the other
  instances still complete and the run ends ``partial`` (Req 10.6);
* **under-development pre-run gating** — a config selecting a non-executable
  value is rejected at launch with 409 and no row is created (Req 7.5);
* **delete / export / 404s** (Req 11.4).

Determinism: the ``get_registry`` dependency is overridden with a registry whose
client factory returns a :class:`~mad.providers.base.MockModelClient` (no
network), and ``get_launcher`` is overridden with a synchronous launcher so the
background job finishes before assertions run.

Validates: Requirements 10.4, 10.5, 10.6, 11.1, 11.2, 11.3, 11.4, 7.5
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import API_PREFIX, create_app
from app.routers import executions as executions_router
from app.services.executions import make_sync_launcher
from mad.providers.base import MockModelClient, ModelResponse
from mad.providers.registry import ProviderConfig, ProviderRegistry

FRONTEND_ORIGIN = "http://localhost:5173"

# Provider id the test configs bind their nodes to. The mock registry registers
# a ProviderConfig under this id so resolution succeeds offline.
PROVIDER_ID = "test-provider"
MODEL_KEY = "mock-model"


# --------------------------------------------------------------------------- #
# Config artifact builders
# --------------------------------------------------------------------------- #


def _node(node_id: str, label: str, roles=None) -> dict:
    return {
        "id": node_id,
        "label": label,
        "roles": roles or ["debater"],
        "base_model": {
            "provider_id": PROVIDER_ID,
            "model_key": MODEL_KEY,
            "family": "open_weight",
            "temperature": 0.0,
        },
        "system_prompt": f"You are {label}.",
    }


def _executable_artifact(name: str, *, template: str) -> dict:
    """A minimal fully-executable two-debater config (collective/majority)."""
    return {
        "schema_version": "1.0",
        "name": name,
        "participants": {
            "nodes": [_node("alice", "Alice"), _node("bob", "Bob")],
        },
        "interaction": {
            "topology": {"adaptability": "static", "structure": "fully_connected"},
            "protocol": {
                "mechanism": "sequential",
                "max_rounds": 1,
                "ordering": "fixed",
                "order": ["alice", "bob"],
            },
            "format": {"syntax": "natural_language", "memory": "short_term"},
        },
        "agreement": {"authority": "collective", "resolution": "majority_vote"},
        "input_spec": {"template": template, "placeholders": ["topic"]},
    }


# --------------------------------------------------------------------------- #
# Mock registry / client
# --------------------------------------------------------------------------- #


def _make_mock_registry(responder=None) -> ProviderRegistry:
    """A registry whose only provider resolves to a MockModelClient (offline)."""

    def _factory(_config: ProviderConfig) -> MockModelClient:
        return MockModelClient(responder=responder)

    registry = ProviderRegistry(client_factory=_factory)
    registry.add(
        ProviderConfig(
            id=PROVIDER_ID,
            name="Test provider",
            kind="openai_compatible",
            models=[MODEL_KEY],
        )
    )
    return registry


# --------------------------------------------------------------------------- #
# App / client fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture()
def nfr_csv(tmp_path) -> Path:
    """A tiny 3-row CSV with a requirement column + ground-truth type column."""
    csv = tmp_path / "mini.csv"
    csv.write_text(
        "requirement,type\n"
        "The system shall respond in 1s,F\n"
        "The UI shall be accessible,NF\n"
        "The system shall log events,F\n",
        encoding="utf-8",
    )
    return csv


def _build_client(tmp_path, *, responder=None) -> TestClient:
    db_url = f"sqlite:///{tmp_path.as_posix()}/exec.db"
    storage = tmp_path / "storage"
    settings = Settings(
        database_url=db_url,
        cors_origins=[FRONTEND_ORIGIN],
        dataset_storage_path=str(storage),
    )
    app = create_app(settings)

    registry = _make_mock_registry(responder=responder)
    # Override the registry + launcher seams for offline, synchronous runs.
    app.dependency_overrides[executions_router.get_registry] = lambda: registry
    app.dependency_overrides[executions_router.get_launcher] = (
        lambda: make_sync_launcher(sleep=lambda _s: None)
    )

    client = TestClient(app)
    client.storage_dir = storage  # type: ignore[attr-defined]
    return client


@pytest.fixture()
def client(tmp_path) -> TestClient:
    with _build_client(tmp_path) as test_client:
        yield test_client


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _create_config(client: TestClient, artifact: dict) -> dict:
    resp = client.post(f"{API_PREFIX}/configs/import", json={"artifact": artifact})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _upload_dataset(client: TestClient, csv_path: Path) -> dict:
    resp = client.post(
        f"{API_PREFIX}/datasets",
        files={"file": (csv_path.name, csv_path.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --------------------------------------------------------------------------- #
# OpenAPI / routing
# --------------------------------------------------------------------------- #


def test_openapi_exposes_execution_paths(client: TestClient):
    paths = client.get("/openapi.json").json()["paths"]
    assert f"{API_PREFIX}/executions" in paths
    assert f"{API_PREFIX}/executions/{{execution_id}}" in paths
    assert f"{API_PREFIX}/executions/{{execution_id}}/stream" in paths
    assert f"{API_PREFIX}/executions/{{execution_id}}/export" in paths


# --------------------------------------------------------------------------- #
# Single-run lifecycle (Req 10.4, 11.1, 11.2, 11.3)
# --------------------------------------------------------------------------- #


def test_single_run_lifecycle(client: TestClient):
    config = _create_config(
        client, _executable_artifact("Single run", template="Debate: {{topic}}")
    )

    resp = client.post(
        f"{API_PREFIX}/executions",
        json={"config_id": config["id"], "input": {"topic": "cats vs dogs"}},
    )
    assert resp.status_code == 201, resp.text
    detail = resp.json()

    # Synchronous launcher => finished by the time the response returns.
    assert detail["input_mode"] == "single"
    assert detail["status"] == "completed"
    assert detail["progress"] == 1.0
    assert detail["instance_count"] == 1
    assert detail["error_count"] == 0

    # Immutable snapshot captured (Req 11.3).
    assert detail["config_snapshot"]["name"] == "Single run"

    # Per-instance transcript + decision present (Req 11.2).
    inst = detail["instances"][0]
    assert inst["instance_index"] == 0
    assert inst["resolved_input"] == {"topic": "cats vs dogs"}
    assert inst["transcript"] is not None
    assert inst["transcript"]["resolved_input"].startswith("Debate: cats vs dogs")
    assert len(inst["transcript"]["messages"]) >= 1
    assert inst["final_decision"] is not None
    assert inst["error"] is None


def test_single_run_appears_in_list_and_get(client: TestClient):
    config = _create_config(
        client, _executable_artifact("Listed run", template="{{topic}}")
    )
    created = client.post(
        f"{API_PREFIX}/executions",
        json={"config_id": config["id"], "input": {"topic": "x"}},
    ).json()

    listing = client.get(f"{API_PREFIX}/executions").json()
    assert any(e["id"] == created["id"] for e in listing)
    summary = next(e for e in listing if e["id"] == created["id"])
    assert summary["status"] == "completed"
    assert summary["config_name"] == "Listed run"

    got = client.get(f"{API_PREFIX}/executions/{created['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == created["id"]


def test_snapshot_is_immutable_against_config_edits(client: TestClient):
    config = _create_config(
        client, _executable_artifact("Original", template="{{topic}}")
    )
    created = client.post(
        f"{API_PREFIX}/executions",
        json={"config_id": config["id"], "input": {"topic": "x"}},
    ).json()

    # Rename the source config; the execution snapshot must not change (Req 11.3).
    detail = client.get(f"{API_PREFIX}/configs/{config['id']}").json()
    artifact = {**detail["artifact"], "name": "Renamed"}
    client.put(f"{API_PREFIX}/configs/{config['id']}", json={"artifact": artifact})

    after = client.get(f"{API_PREFIX}/executions/{created['id']}").json()
    assert after["config_snapshot"]["name"] == "Original"


# --------------------------------------------------------------------------- #
# Batch progress + aggregate metrics (Req 10.4, 10.7, 11.5)
# --------------------------------------------------------------------------- #


def test_batch_run_progress_and_instances(client: TestClient, nfr_csv: Path):
    dataset = _upload_dataset(client, nfr_csv)
    config = _create_config(
        client, _executable_artifact("Batch run", template="Classify: {{req}}")
    )

    resp = client.post(
        f"{API_PREFIX}/executions",
        json={
            "config_id": config["id"],
            "batch": {
                "dataset_id": dataset["id"],
                "mapping": {"requirement": "req"},
            },
        },
    )
    assert resp.status_code == 201, resp.text
    detail = resp.json()

    assert detail["input_mode"] == "batch"
    assert detail["status"] == "completed"
    assert detail["progress"] == 1.0
    assert detail["instance_count"] == 3
    # One instance per CSV row, in order.
    indices = sorted(i["instance_index"] for i in detail["instances"])
    assert indices == [0, 1, 2]


def test_batch_run_computes_aggregate_metrics_with_ground_truth(
    client: TestClient, nfr_csv: Path
):
    dataset = _upload_dataset(client, nfr_csv)
    # Make the collective decision deterministic: every debater "votes" F so the
    # majority decision is F, which matches 2 of the 3 ground-truth rows.
    config = _create_config(
        client, _executable_artifact("GT batch", template="{{req}}")
    )

    resp = client.post(
        f"{API_PREFIX}/executions",
        json={
            "config_id": config["id"],
            "batch": {
                "dataset_id": dataset["id"],
                "mapping": {"requirement": "req"},
                "ground_truth_column": "type",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    detail = resp.json()
    assert detail["status"] == "completed"
    # Aggregate metrics present when a ground-truth column is mapped (Req 11.5).
    assert detail["metrics"] is not None
    assert "overall" in detail["metrics"]
    assert detail["metrics"]["scored_count"] == 3
    # Per-instance ground truth is persisted.
    assert all(i["ground_truth"] in ("F", "NF") for i in detail["instances"])


# --------------------------------------------------------------------------- #
# Failure isolation (Req 10.6)
# --------------------------------------------------------------------------- #


def test_failure_isolation_marks_partial(tmp_path, nfr_csv: Path):
    # A responder that raises for the second row's topic but succeeds otherwise.
    def responder(messages, model, params, response_schema):
        text = " ".join(m.content for m in messages)
        if "accessible" in text:
            raise RuntimeError("simulated provider outage")
        return ModelResponse(text="ok")

    with _build_client(tmp_path, responder=responder) as client:
        dataset = _upload_dataset(client, nfr_csv)
        config = _create_config(
            client, _executable_artifact("Isolation", template="Classify: {{req}}")
        )
        resp = client.post(
            f"{API_PREFIX}/executions",
            json={
                "config_id": config["id"],
                "batch": {
                    "dataset_id": dataset["id"],
                    "mapping": {"requirement": "req"},
                },
            },
        )
        assert resp.status_code == 201, resp.text
        detail = resp.json()

        # One row failed, the other two completed -> partial (Req 10.6).
        assert detail["status"] == "partial"
        assert detail["instance_count"] == 3
        assert detail["error_count"] == 1
        errored = [i for i in detail["instances"] if i["error"] is not None]
        assert len(errored) == 1
        # The failing row's instance carries an isolated error string.
        assert errored[0]["error"]
        # The failure did not abort the run: the other rows have transcripts.
        ok = [i for i in detail["instances"] if i["error"] is None]
        assert len(ok) == 2
        assert all(i["transcript"] is not None for i in ok)


# --------------------------------------------------------------------------- #
# Under-development pre-run gating (Req 7.5)
# --------------------------------------------------------------------------- #


def test_under_development_config_is_gated_at_launch(client: TestClient):
    # 'coordinator' ordering is a non-executable (under-development) value.
    artifact = _executable_artifact("Gated", template="{{topic}}")
    artifact["interaction"]["protocol"]["ordering"] = "coordinator"
    config = _create_config(client, artifact)

    resp = client.post(
        f"{API_PREFIX}/executions",
        json={"config_id": config["id"], "input": {"topic": "x"}},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"] == "UnderDevelopment"

    # No execution row should have been created for a gated launch.
    assert client.get(f"{API_PREFIX}/executions").json() == []


# --------------------------------------------------------------------------- #
# Input validation (Req 10.2)
# --------------------------------------------------------------------------- #


def test_single_missing_placeholder_is_422(client: TestClient):
    config = _create_config(
        client, _executable_artifact("Missing field", template="{{topic}}")
    )
    resp = client.post(
        f"{API_PREFIX}/executions",
        json={"config_id": config["id"], "input": {"wrong": "x"}},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "TemplateError"


def test_requires_exactly_one_input_mode(client: TestClient):
    config = _create_config(
        client, _executable_artifact("One mode", template="{{topic}}")
    )
    # Neither input nor batch.
    resp = client.post(
        f"{API_PREFIX}/executions", json={"config_id": config["id"]}
    )
    assert resp.status_code == 422


def test_missing_config_returns_404(client: TestClient):
    resp = client.post(
        f"{API_PREFIX}/executions",
        json={"config_id": 999999, "input": {"topic": "x"}},
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Delete / export / 404s (Req 11.4)
# --------------------------------------------------------------------------- #


def test_delete_execution(client: TestClient):
    config = _create_config(
        client, _executable_artifact("To delete", template="{{topic}}")
    )
    created = client.post(
        f"{API_PREFIX}/executions",
        json={"config_id": config["id"], "input": {"topic": "x"}},
    ).json()

    resp = client.delete(f"{API_PREFIX}/executions/{created['id']}")
    assert resp.status_code == 200
    assert resp.json() == {"id": created["id"], "deleted": True}
    assert client.get(f"{API_PREFIX}/executions/{created['id']}").status_code == 404


def test_export_execution(client: TestClient):
    config = _create_config(
        client, _executable_artifact("To export", template="{{topic}}")
    )
    created = client.post(
        f"{API_PREFIX}/executions",
        json={"config_id": config["id"], "input": {"topic": "x"}},
    ).json()

    resp = client.get(f"{API_PREFIX}/executions/{created['id']}/export")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == created["id"]
    assert body["config_snapshot"]["name"] == "To export"
    assert len(body["instances"]) == 1


# --------------------------------------------------------------------------- #
# SSE progress stream (Req 10.5)
# --------------------------------------------------------------------------- #


def test_stream_emits_terminal_progress(client: TestClient):
    config = _create_config(
        client, _executable_artifact("Streamed", template="{{topic}}")
    )
    created = client.post(
        f"{API_PREFIX}/executions",
        json={"config_id": config["id"], "input": {"topic": "x"}},
    ).json()

    # The sync launcher already finished the run, so the stream emits the
    # terminal event and closes.
    resp = client.get(f"{API_PREFIX}/executions/{created['id']}/stream")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    assert "data:" in body
    assert '"status": "completed"' in body
    assert '"progress": 1.0' in body


def test_stream_missing_execution_emits_not_found(client: TestClient):
    resp = client.get(f"{API_PREFIX}/executions/999999/stream")
    assert resp.status_code == 200
    assert "not_found" in resp.text


def test_get_missing_returns_404(client: TestClient):
    assert client.get(f"{API_PREFIX}/executions/999999").status_code == 404


def test_export_missing_returns_404(client: TestClient):
    assert client.get(f"{API_PREFIX}/executions/999999/export").status_code == 404


def test_delete_missing_returns_404(client: TestClient):
    assert client.delete(f"{API_PREFIX}/executions/999999").status_code == 404
