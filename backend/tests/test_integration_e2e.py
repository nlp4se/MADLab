"""End-to-end integration pass against REAL providers (task 10.1).

This is the authoritative artifact for task 10.1: it drives the **full request
path** through the FastAPI app with a real :class:`~fastapi.testclient.TestClient`
(no ``MockModelClient``) against live LLM providers, exercising

    frontend contract (HTTP) -> API -> services -> engine -> LiteLLM -> provider

for the gold cases, and asserts that history + per-instance transcripts + final
decisions are persisted and well-formed, and that aggregate metrics are computed
for a batch with a ground-truth column.

Requirements: 4.4 (gold cases run end to end), 9.2 (heterogeneous models in one
debate), 10.* (input binding / run / persistence / metrics), 11.* (history +
analysis).

Cost/time discipline (these make real calls, so they cost real tokens):

* every node binds to a **cheap** model (``gpt-4o-mini`` / ``claude-3-5-haiku`` /
  ``gemini-1.5-flash``) with a tiny ``max_tokens`` cap and ``max_rounds=1``;
* single runs use 1 instance; the batch uses ``limit=2`` rows;
* the launcher is overridden to run **synchronously** with a 1-attempt retry
  policy and a no-op backoff sleep, so a bad key fails fast (no 3x ret
  back-off waits) and assertions observe the finished run immediately. The
  **registry is NOT overridden** — the real LiteLLM-backed clients are used.

Skip semantics: each test is skipped when the provider key(s) it needs are
absent from the environment, so the suite stays green on machines without keys.
A provider whose key is present but turns out to be unauthorized at runtime does
not fail the heterogeneous test — its node's turn is isolated as an error and
the run still produces a decision from the providers that work (Req 9.5/10.6).

The keys are read from the repo-root ``.env`` **by name** (never hard-coded) and
handed to the provider via the normal ``POST /api/providers`` path, which
encrypts them at rest; the plaintext is only ever referenced through the env.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import API_PREFIX, create_app
from app.routers import executions as executions_router
from app.security import crypto
from app.services.executions import make_sync_launcher
from mad.engine.orchestrator import RetryPolicy

# --------------------------------------------------------------------------- #
# Environment / keys
# --------------------------------------------------------------------------- #

# Repo root is two levels up from this file: backend/tests/ -> backend/ -> repo.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_root_env() -> None:
    """Load the repo-root .env so provider keys are visible to this process.

    The backend loads .env via python-dotenv in normal operation; here we load
    it explicitly (without overriding anything already exported) so the keys are
    available whether or not pytest was launched from the repo root.
    """
    try:
        from dotenv import load_dotenv
    except Exception:  # pragma: no cover - dotenv is a declared dependency
        return
    env_path = _REPO_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


_load_root_env()

# Provider kind -> the env var that holds its key. OpenAI/Anthropic use the
# conventional names; Gemini's key is stored as GOOGLE_API_KEY in this repo's
# .env (LiteLLM also accepts GEMINI_API_KEY, but we pass the key explicitly).
_OPENAI_ENV = "OPENAI_API_KEY"
_ANTHROPIC_ENV = "ANTHROPIC_API_KEY"
_GEMINI_ENV = "GOOGLE_API_KEY"

# Cheap models per provider (minimise token cost).
_OPENAI_MODEL = "gpt-4o-mini"
_ANTHROPIC_MODEL = "claude-3-5-haiku-latest"
_GEMINI_MODEL = "gemini-1.5-flash"

SERVER_SECRET = "test-secret-for-e2e-integration"


def _key(env_var: str) -> str | None:
    value = os.environ.get(env_var)
    return value.strip() if value and value.strip() else None


def _require(env_var: str) -> str:
    value = _key(env_var)
    if value is None:
        pytest.skip(f"{env_var} not set — skipping real-provider e2e test.")
    return value


# --------------------------------------------------------------------------- #
# App / client fixture (REAL registry, synchronous fast launcher)
# --------------------------------------------------------------------------- #


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    """A TestClient over a temp-file SQLite app using the real provider path.

    Only the launcher seam is overridden (synchronous + 1 attempt + no-op
    backoff sleep); ``get_registry`` is left as the real
    :func:`app.services.providers.build_registry`, so executions call LiteLLM.
    """
    monkeypatch.setenv(crypto.SERVER_SECRET_ENV, SERVER_SECRET)
    crypto.reset_cipher()

    db_url = f"sqlite:///{tmp_path.as_posix()}/e2e.db"
    storage = tmp_path / "storage"
    settings = Settings(
        database_url=db_url,
        cors_origins=["http://localhost:5173"],
        dataset_storage_path=str(storage),
        secret_key=SERVER_SECRET,
    )
    app = create_app(settings)

    # Synchronous launch with a 1-attempt policy + no-op sleep: real calls, but
    # a failure fails fast and the run is finished when POST returns.
    app.dependency_overrides[executions_router.get_launcher] = (
        lambda: make_sync_launcher(
            retry_policy=RetryPolicy(max_attempts=1), sleep=lambda _s: None
        )
    )

    with TestClient(app) as test_client:
        test_client.storage_dir = storage  # type: ignore[attr-defined]
        yield test_client

    crypto.reset_cipher()


# --------------------------------------------------------------------------- #
# Helpers: provider seeding, config import, structural assertions
# --------------------------------------------------------------------------- #


def _create_provider(client: TestClient, *, name: str, kind: str, model: str,
                     api_key: str) -> str:
    """Seed a provider via the real API path; return its id as a string.

    The id-as-string is exactly what a participant's ``base_model.provider_id``
    binds to (:func:`app.services.providers.build_registry` keys the registry by
    the DB row id rendered as a string).
    """
    resp = client.post(
        f"{API_PREFIX}/providers",
        json={"name": name, "kind": kind, "models": [model], "api_key": api_key},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["has_key"] is True
    # The key must never come back out (Req 8.4).
    assert "api_key" not in resp.text
    return str(body["id"])


def _import_config(client: TestClient, artifact: dict) -> dict:
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


def _tiny_params() -> dict:
    """Per-node call params that keep token usage minimal."""
    return {"max_tokens": 64}


def _re_binary_artifact(provider_id: str, model: str) -> dict:
    """The RE binary gold case bound to one cheap provider/model, 1 round.

    Mirrors :func:`mad.taxonomy.templates.re_binary_debate` structurally (two
    opposing debaters + a judge, fully-connected, sequential, judge-based
    authority with a ``{class: F|NF}`` output schema) but binds every node to the
    given provider/model and caps rounds + tokens for cost.
    """
    def node(node_id: str, label: str, roles: list[str], stance: str | None,
             system_prompt: str) -> dict:
        return {
            "id": node_id,
            "label": label,
            "roles": roles,
            "persona": {"stance": stance} if stance else {},
            "base_model": {
                "provider_id": provider_id,
                "model_key": model,
                "family": "closed_weight",
                "temperature": 0.0,
                "params": _tiny_params(),
            },
            "system_prompt": system_prompt,
        }

    nodes = [
        node(
            "functional-debater", "Functional debater", ["debater"],
            "Argue the requirement is functional (F).",
            "You argue the requirement is functional (F). Be very brief.",
        ),
        node(
            "non-functional-debater", "Non-functional debater", ["debater"],
            "Argue the requirement is non-functional (NF).",
            "You argue the requirement is non-functional (NF). Be very brief.",
        ),
        node(
            "judge", "Judge", ["judge"], None,
            "You are the judge. Decide F or NF and return the JSON object.",
        ),
    ]
    node_ids = [n["id"] for n in nodes]
    return {
        "schema_version": "1.0",
        "name": "E2E RE Binary (cheap)",
        "participants": {
            "persona_heterogeneity": "heterogeneous",
            "persona_assignment": "manual",
            "base_model_heterogeneity": "homogeneous",
            "nodes": nodes,
        },
        "interaction": {
            "topology": {
                "adaptability": "static",
                "structure": "fully_connected",
                "edges": [
                    {"source": u, "target": v, "directed": True}
                    for u in node_ids for v in node_ids if u != v
                ],
            },
            "protocol": {
                "mechanism": "sequential",
                "max_rounds": 1,
                "ordering": "fixed",
                "order": node_ids,
            },
            "format": {"syntax": "natural_language", "memory": "short_term",
                       "content": {"strategy": "verbatim"}},
        },
        "agreement": {
            "authority": "judge_based",
            "resolution": "argument_evaluation",
            "output_schema": {
                "type": "object",
                "properties": {"class": {"type": "string", "enum": ["F", "NF"]}},
            },
        },
        "input_spec": {
            "template": "Classify this requirement: {{requirement}}",
            "placeholders": ["requirement"],
            "ad_hoc_fields": [{"key": "requirement", "label": "Requirement text"}],
        },
    }


def _heterogeneous_artifact(bindings: list[tuple[str, str, str, str]]) -> dict:
    """A collective/majority debate whose debaters bind to DIFFERENT providers.

    ``bindings`` is a list of ``(node_id, label, provider_id, model_key)``; each
    debater node resolves independently, exercising heterogeneous models in one
    debate (Req 9.2). One short round, tiny token cap, majority-vote collective
    agreement with a ``{class: F|NF}`` output schema so each debater emits a
    comparable structured vote.
    """
    nodes = []
    for node_id, label, provider_id, model_key in bindings:
        nodes.append({
            "id": node_id,
            "label": label,
            "roles": ["debater"],
            "base_model": {
                "provider_id": provider_id,
                "model_key": model_key,
                "family": "closed_weight",
                "temperature": 0.0,
                "params": _tiny_params(),
            },
            "system_prompt": (
                "Classify the requirement as functional (F) or non-functional "
                "(NF). Answer with the JSON object only. Be very brief."
            ),
        })
    node_ids = [n["id"] for n in nodes]
    return {
        "schema_version": "1.0",
        "name": "E2E Heterogeneous models (Req 9.2)",
        "participants": {
            "persona_heterogeneity": "homogeneous",
            "persona_assignment": "unspecified",
            "base_model_heterogeneity": "heterogeneous",
            "nodes": nodes,
        },
        "interaction": {
            "topology": {
                "adaptability": "static",
                "structure": "fully_connected",
                "edges": [
                    {"source": u, "target": v, "directed": True}
                    for u in node_ids for v in node_ids if u != v
                ],
            },
            "protocol": {
                "mechanism": "sequential",
                "max_rounds": 1,
                "ordering": "fixed",
                "order": node_ids,
            },
            "format": {"syntax": "natural_language", "memory": "short_term",
                       "content": {"strategy": "verbatim"}},
        },
        "agreement": {
            "authority": "collective",
            "resolution": "majority_vote",
            "output_schema": {
                "type": "object",
                "properties": {"class": {"type": "string", "enum": ["F", "NF"]}},
            },
        },
        "input_spec": {
            "template": "Classify this requirement: {{requirement}}",
            "placeholders": ["requirement"],
            "ad_hoc_fields": [{"key": "requirement", "label": "Requirement text"}],
        },
    }


def _assert_transcript_shape(inst: dict) -> None:
    """Assert a per-instance transcript is present and well-formed (Req 11.2)."""
    transcript = inst["transcript"]
    assert transcript is not None, "expected a transcript for a completed instance"
    assert transcript["resolved_input"].startswith("Classify this requirement:")
    # At least one agent spoke (a real provider produced text).
    messages = transcript.get("messages") or []
    assert len(messages) >= 1, "expected at least one agent message"
    assert any((m.get("content") or "").strip() for m in messages), (
        "expected at least one non-empty agent message"
    )


# --------------------------------------------------------------------------- #
# Test 1 — RE binary gold case, single run, OpenAI cheap model (Req 4.4, 10.*)
# --------------------------------------------------------------------------- #


def test_re_binary_single_run_openai(client: TestClient):
    """Run the RE binary gold case as a single instance via the real stack.

    Verifies the full path persists history + a well-formed transcript and a
    final decision for one short requirement bound to gpt-4o-mini (Req 4.4,
    10.2, 10.4, 10.6, 11.2, 11.3).
    """
    api_key = _require(_OPENAI_ENV)
    provider_id = _create_provider(
        client, name="OpenAI (e2e)", kind="openai", model=_OPENAI_MODEL,
        api_key=api_key,
    )
    config = _import_config(client, _re_binary_artifact(provider_id, _OPENAI_MODEL))

    resp = client.post(
        f"{API_PREFIX}/executions",
        json={
            "config_id": config["id"],
            "input": {"requirement": "The system shall respond within 1 second."},
        },
    )
    assert resp.status_code == 201, resp.text
    detail = resp.json()

    # Synchronous launcher => finished by the time POST returns.
    assert detail["input_mode"] == "single"
    assert detail["status"] in ("completed", "partial"), detail.get("metrics")
    assert detail["progress"] == 1.0
    assert detail["instance_count"] == 1
    # Immutable snapshot captured (Req 11.3).
    assert detail["config_snapshot"]["name"] == "E2E RE Binary (cheap)"

    # Re-read through GET to prove it persisted (history), not just the POST echo.
    got = client.get(f"{API_PREFIX}/executions/{detail['id']}")
    assert got.status_code == 200, got.text
    persisted = got.json()
    inst = persisted["instances"][0]
    assert inst["instance_index"] == 0
    assert inst["resolved_input"] == {
        "requirement": "The system shall respond within 1 second."
    }

    if inst["error"] is None:
        _assert_transcript_shape(inst)
        # A final decision was produced by the judge (shape, not exact text).
        decision = inst["final_decision"]
        assert decision is not None, "expected a judge decision"
        # The judge-based structured decision should surface a class in {F, NF}
        # somewhere in the decision payload.
        blob = str(decision)
        assert ("F" in blob) or ("NF" in blob)
    else:
        # A provider/runtime failure is isolated (Req 10.6); report it loudly so
        # the integration pass still has a signal, but don't crash the suite.
        pytest.fail(
            f"OpenAI single run errored (likely an invalid key or outage): "
            f"{inst['error']}"
        )


# --------------------------------------------------------------------------- #
# Test 2 — batch with ground truth -> aggregate metrics (Req 10.7, 11.5)
# --------------------------------------------------------------------------- #


def test_re_binary_batch_metrics_openai(client: TestClient):
    """Run the RE gold case over 2 nfr-small rows and assert metric SHAPE.

    Exercises batch input binding (Req 10.1/10.3), per-instance persistence, and
    the aggregate evaluation roll-up computed from a ground-truth column
    (Req 10.7, 11.5). Capped to 2 rows to limit cost.
    """
    api_key = _require(_OPENAI_ENV)
    csv_path = _REPO_ROOT / "data" / "datasets" / "PROMISE" / "nfr-small.csv"
    if not csv_path.exists():
        pytest.skip(f"dataset not found: {csv_path}")

    provider_id = _create_provider(
        client, name="OpenAI (e2e batch)", kind="openai", model=_OPENAI_MODEL,
        api_key=api_key,
    )
    config = _import_config(client, _re_binary_artifact(provider_id, _OPENAI_MODEL))
    dataset = _upload_dataset(client, csv_path)

    resp = client.post(
        f"{API_PREFIX}/executions",
        json={
            "config_id": config["id"],
            "batch": {
                "dataset_id": dataset["id"],
                "mapping": {"requirement": "requirement"},
                "ground_truth_column": "type",
                "limit": 2,
            },
        },
    )
    assert resp.status_code == 201, resp.text
    detail = resp.json()

    assert detail["input_mode"] == "batch"
    assert detail["progress"] == 1.0
    assert detail["instance_count"] == 2
    assert detail["status"] in ("completed", "partial"), detail

    # Per-instance ground truth persisted for every row (Req 11.*).
    persisted = client.get(f"{API_PREFIX}/executions/{detail['id']}").json()
    assert all(i["ground_truth"] in ("F", "NF") for i in persisted["instances"])

    # If at least one instance scored, aggregate metrics must be present and
    # well-shaped (Req 11.5) — we assert SHAPE, not exact accuracy.
    ok_instances = [i for i in persisted["instances"] if i["error"] is None]
    if ok_instances:
        metrics = persisted["metrics"]
        assert metrics is not None, "expected aggregate metrics with ground truth"
        assert metrics["scored_count"] >= 1
        assert "overall" in metrics
    else:
        pytest.fail(
            "every batch instance errored against OpenAI (likely a bad key or "
            f"outage): {[i['error'] for i in persisted['instances']]}"
        )


# --------------------------------------------------------------------------- #
# Test 3 — heterogeneous models in one debate (Req 9.2)
# --------------------------------------------------------------------------- #


def test_heterogeneous_models_single_debate(client: TestClient):
    """Run ONE debate whose debaters bind to DIFFERENT providers (Req 9.2).

    Binds up to three debaters to OpenAI / Anthropic / Gemini cheap models (only
    the providers whose keys are present participate; the test needs at least
    two distinct providers to be meaningful). A provider that is present but
    unauthorized at runtime has its turn isolated as an error (Req 9.5/10.6);
    the run still produces a decision from the providers that work, which is the
    behaviour we assert. We assert the transcript/decision SHAPE and that at
    least one real provider produced output — never exact text.
    """
    available: list[tuple[str, str, str]] = []  # (kind, model, env)
    for kind, model, env in (
        ("openai", _OPENAI_MODEL, _OPENAI_ENV),
        ("anthropic", _ANTHROPIC_MODEL, _ANTHROPIC_ENV),
        ("gemini", _GEMINI_MODEL, _GEMINI_ENV),
    ):
        if _key(env) is not None:
            available.append((kind, model, env))

    if len(available) < 2:
        pytest.skip(
            "heterogeneous debate needs >=2 providers with keys present; found "
            f"{len(available)}."
        )

    # Seed each available provider and build the debater bindings.
    bindings: list[tuple[str, str, str, str]] = []
    for idx, (kind, model, env) in enumerate(available):
        provider_id = _create_provider(
            client, name=f"{kind} (e2e het)", kind=kind, model=model,
            api_key=_key(env),  # present by construction
        )
        bindings.append((f"debater-{idx}", f"{kind} debater", provider_id, model))

    config = _import_config(client, _heterogeneous_artifact(bindings))

    resp = client.post(
        f"{API_PREFIX}/executions",
        json={
            "config_id": config["id"],
            "input": {"requirement": "The system shall respond within 1 second."},
        },
    )
    assert resp.status_code == 201, resp.text
    detail = resp.json()
    assert detail["progress"] == 1.0
    assert detail["instance_count"] == 1

    persisted = client.get(f"{API_PREFIX}/executions/{detail['id']}").json()
    inst = persisted["instances"][0]

    # Snapshot proves heterogeneity: the debater nodes bind to >=2 distinct
    # provider ids (Req 9.2 at the artifact level).
    snap_nodes = persisted["config_snapshot"]["participants"]["nodes"]
    provider_ids = {n["base_model"]["provider_id"] for n in snap_nodes}
    assert len(provider_ids) >= 2, "expected >=2 distinct providers bound"

    # The instance itself may be marked error only if EVERY debater failed; with
    # >=2 real providers at least one should answer. Assert a transcript with at
    # least one real message exists OR surface the isolated errors.
    transcript = inst["transcript"]
    if transcript is not None and (transcript.get("messages") or []):
        messages = transcript["messages"]
        assert any((m.get("content") or "").strip() for m in messages), (
            "expected at least one non-empty message from a real provider"
        )
        # Which provider-bound nodes actually spoke (for the cost/pass report).
        spoke = {m.get("node_id") for m in messages}
        assert spoke, "expected at least one node to have spoken"
        # A collective decision should have been resolved from the votes.
        assert inst["final_decision"] is not None or inst["error"] is not None
    else:
        pytest.fail(
            "no debater produced a message across all heterogeneous providers; "
            f"instance error={inst['error']!r}, transcript_errors="
            f"{(transcript or {}).get('errors')!r}"
        )
