"""Tests for the headless CLI drivers (task 6.7, Req 12.4, 12.5).

The CLI is the headless research path: it drives the *same* services/engine the
FastAPI web layer uses, with no web server. These tests exercise each command
against a temp-file SQLite database, fully offline and deterministic by injecting
a :class:`~mad.providers.registry.ProviderRegistry` whose client factory returns
a :class:`~mad.providers.base.MockModelClient` (the ``registry_factory`` seam) —
so no network call is ever made.

The headline test is the **classification regression** (Req 12.5): it reproduces
the binary F/NF requirement classification on the real
``data/datasets/PROMISE/nfr-small.csv`` through the new engine via the CLI
``classify`` command, asserting per-instance predictions *and* that aggregate
metrics are produced.

Validates: Requirements 12.4, 12.5
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from cli.app import main as cli_main
from mad.providers.base import Message, ModelResponse, MockModelClient
from mad.providers.registry import ProviderConfig, ProviderRegistry

# The real research dataset the regression reproduces (Req 12.5). Resolved from
# this test file so it works regardless of the pytest working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]
NFR_SMALL = _REPO_ROOT / "data" / "datasets" / "PROMISE" / "nfr-small.csv"

PROVIDER_ID = "test-provider"
MODEL_KEY = "mock-model"


# --------------------------------------------------------------------------- #
# Offline registry seam
# --------------------------------------------------------------------------- #


def _classifying_responder(messages, model, params, response_schema):
    """A deterministic judge: classify the requirement F vs. NF by keyword.

    The RE binary debate wires a judge whose call carries the binary
    ``output_schema`` (``{"class": ["F","NF"]}``); only that call passes a
    ``response_schema``. For the judge call we return a JSON ``{"class": ...}``
    object the mock surfaces as the structured decision; every other (debater)
    turn falls back to a plain echo. The label is derived from the requirement
    text so predictions are reproducible: anything that reads like a quality
    attribute ("accessible", "fast", "secure", "usable") is NF, else F — which
    makes nfr-small.csv's two functional requirements both classify as F.
    """
    if response_schema is None:
        # A debater turn: echo deterministically (content is irrelevant to the
        # final decision, which the judge produces).
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        return ModelResponse(text=f"[debater] {last_user}")

    context = " ".join(m.content for m in messages).lower()
    nf_markers = ("accessible", "fast", "secure", "usable", "performance", "reliab")
    label = "NF" if any(marker in context for marker in nf_markers) else "F"
    return ModelResponse(text=json.dumps({"class": label}))


def _mock_registry_factory(_session) -> ProviderRegistry:
    """Build an offline registry whose provider resolves to the mock client."""

    def _factory(_config: ProviderConfig) -> MockModelClient:
        return MockModelClient(responder=_classifying_responder)

    registry = ProviderRegistry(client_factory=_factory)
    # The RE gold config binds nodes to model_key "gpt-4o"; register the mock
    # provider under every provider id the resolver might ask for. The gold
    # config leaves provider_id unset, so we also need to bind it — the classify
    # path rewrites bindings below via a provider the registry knows.
    registry.add(
        ProviderConfig(
            id=PROVIDER_ID,
            name="Mock provider",
            kind="openai_compatible",
            models=[MODEL_KEY, "gpt-4o"],
        )
    )
    return registry


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture()
def db_url(tmp_path) -> str:
    """A temp-file SQLite URL isolated per test."""
    return f"sqlite:///{tmp_path.as_posix()}/cli.db"


def _run(argv, *, registry_factory=_mock_registry_factory) -> tuple[int, str, str]:
    """Invoke the CLI capturing (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    code = cli_main(argv, registry_factory=registry_factory, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


# --------------------------------------------------------------------------- #
# version (preserved)
# --------------------------------------------------------------------------- #


def test_version_flag(db_url):
    code, out, _ = _run(["--version"])
    assert code == 0
    assert out.strip().startswith("mad ")


def test_version_subcommand(db_url):
    code, out, _ = _run(["version"])
    assert code == 0
    assert out.strip().startswith("mad ")


def test_no_command_prints_help(db_url):
    code, _, err = _run([])
    assert code == 2
    assert "usage" in err.lower()


# --------------------------------------------------------------------------- #
# create-config
# --------------------------------------------------------------------------- #


def test_create_config_from_defaults(db_url):
    code, out, err = _run(["--database-url", db_url, "create-config", "--name", "CLI cfg"])
    assert code == 0, err
    assert "Created configuration #" in out
    assert "'CLI cfg'" in out


def test_create_config_from_gold_case(db_url):
    code, out, err = _run(
        ["--database-url", db_url, "create-config", "--gold", "re_binary_debate"]
    )
    assert code == 0, err
    assert "Created configuration #" in out
    assert "RE Binary Classification Debate" in out


def test_create_config_from_artifact_file(db_url, tmp_path):
    # Export a gold artifact to a file, then import it via the CLI.
    from mad.taxonomy import templates
    from mad.taxonomy.version import export_config

    artifact = export_config(templates.build_gold_case("chateval_s1"))
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    code, out, err = _run(
        [
            "--database-url",
            db_url,
            "create-config",
            "--artifact",
            str(artifact_path),
            "--name",
            "Imported",
        ]
    )
    assert code == 0, err
    assert "Created configuration #" in out
    assert "'Imported'" in out


def test_create_config_rejects_conflicting_sources(db_url):
    code, _, err = _run(
        [
            "--database-url",
            db_url,
            "create-config",
            "--gold",
            "re_binary_debate",
            "--artifact",
            "x.json",
        ]
    )
    assert code == 2
    assert "at most one" in err


def test_create_config_unknown_gold_is_error(db_url):
    code, _, err = _run(
        ["--database-url", db_url, "create-config", "--gold", "does-not-exist"]
    )
    assert code == 2
    assert "unknown gold case" in err


# --------------------------------------------------------------------------- #
# run — single + batch
# --------------------------------------------------------------------------- #


def _create_executable_config(db_url) -> int:
    """Create a simple collective/majority config and return its id.

    Uses an artifact file import so the nodes bind to the mock provider id.
    """
    artifact = {
        "schema_version": "1.0",
        "name": "CLI run cfg",
        "participants": {
            "nodes": [
                {
                    "id": "alice",
                    "label": "Alice",
                    "roles": ["debater"],
                    "base_model": {
                        "provider_id": PROVIDER_ID,
                        "model_key": MODEL_KEY,
                        "family": "open_weight",
                        "temperature": 0.0,
                    },
                    "system_prompt": "You are Alice.",
                },
                {
                    "id": "bob",
                    "label": "Bob",
                    "roles": ["debater"],
                    "base_model": {
                        "provider_id": PROVIDER_ID,
                        "model_key": MODEL_KEY,
                        "family": "open_weight",
                        "temperature": 0.0,
                    },
                    "system_prompt": "You are Bob.",
                },
            ],
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
        "input_spec": {"template": "Debate: {{topic}}", "placeholders": ["topic"]},
    }
    from app.db.session import session_scope
    from app.services import configs as configs_service

    # The CLI initializes the datastore; run a no-op create-config to bind it.
    _run(["--database-url", db_url, "version"])
    from app.db.session import configure, create_engine_for, init_db

    configure(create_engine_for(db_url))
    init_db()
    with session_scope() as session:
        detail = configs_service.import_config_artifact(session, artifact)
        return detail.id


def test_run_single_instance(db_url):
    config_id = _create_executable_config(db_url)
    code, out, err = _run(
        [
            "--database-url",
            db_url,
            "run",
            str(config_id),
            "--input",
            "topic=cats vs dogs",
        ]
    )
    assert code == 0, err
    assert "Execution #" in out
    assert "completed" in out
    assert "1/1 instance" in out


def test_run_batch_over_csv(db_url, tmp_path):
    config_id = _create_executable_config(db_url)
    csv = tmp_path / "topics.csv"
    csv.write_text("topic\nalpha\nbeta\n", encoding="utf-8")

    code, out, err = _run(
        [
            "--database-url",
            db_url,
            "run",
            str(config_id),
            "--csv",
            str(csv),
            "--map",
            "topic=topic",
            "--storage-dir",
            str(tmp_path / "storage"),
        ]
    )
    assert code == 0, err
    assert "Execution #" in out
    assert "2/2 instance" in out


def test_run_requires_exactly_one_mode(db_url):
    config_id = _create_executable_config(db_url)
    code, _, err = _run(["--database-url", db_url, "run", str(config_id)])
    assert code == 2
    assert "exactly one" in err


# --------------------------------------------------------------------------- #
# Classification regression on nfr-small.csv (Req 12.5)
# --------------------------------------------------------------------------- #


def test_nfr_small_exists():
    assert NFR_SMALL.exists(), f"expected regression dataset at {NFR_SMALL}"


def test_classify_regression_reproduces_binary_classification(db_url, tmp_path):
    """Reproduce F/NF classification on nfr-small.csv through the new engine.

    Asserts per-instance predictions (the judge's F/NF class for each
    requirement) and that aggregate metrics are produced — the regression the
    design calls for (Req 12.5), run fully offline via the mock registry seam.
    """
    code, out, err = _run(
        [
            "--database-url",
            db_url,
            "classify",
            str(NFR_SMALL),
            "--requirement-column",
            "requirement",
            "--ground-truth",
            "type",
            "--storage-dir",
            str(tmp_path / "storage"),
        ]
    )
    assert code == 0, err

    # Status line: both requirements classified, no errors.
    assert "Classification execution #" in out
    assert "completed" in out
    assert "2/2 requirement" in out
    assert "0 error" in out

    # Per-instance predictions: both nfr-small rows are functional (F), and our
    # deterministic judge classifies them F; the ground truth is echoed.
    assert "#0: judge=F (truth=F)" in out
    assert "#1: judge=F (truth=F)" in out

    # Aggregate metrics produced (both correct => accuracy 1.0).
    assert "accuracy: 1.0000" in out


def test_classify_offline_asserts_per_instance_and_metrics_via_db(db_url, tmp_path):
    """Deeper assertion of the regression against the persisted execution.

    Runs the classify command, then reads the execution back out of the DB to
    assert each instance carries a judge decision + a per-instance correctness
    metric and that an aggregate metrics block was computed.
    """
    code, _, err = _run(
        [
            "--database-url",
            db_url,
            "classify",
            str(NFR_SMALL),
            "--ground-truth",
            "type",
            "--storage-dir",
            str(tmp_path / "storage"),
        ]
    )
    assert code == 0, err

    from app.db.session import configure, create_engine_for, init_db, session_scope
    from app.services import executions as executions_service

    configure(create_engine_for(db_url))
    init_db()
    with session_scope() as session:
        listing = executions_service.list_executions(session)
        assert listing, "a classify run should have created an execution"
        detail = executions_service.get_execution(session, listing[0].id)

    assert detail.status == "completed"
    assert detail.instance_count == 2
    # Every instance has a judge decision and a per-instance correctness record.
    for inst in detail.instances:
        assert inst.final_decision is not None
        assert inst.metrics is not None
        assert "prediction" in inst.metrics
        assert inst.metrics["prediction"] in ("F", "NF")
        assert inst.metrics["correct"] is True  # nfr-small rows are F; judge -> F
    # Aggregate metrics present + perfect accuracy on this 2-row fixture.
    assert detail.metrics is not None
    assert detail.metrics["overall"]["accuracy"] == pytest.approx(1.0)
    assert detail.metrics["scored_count"] == 2


# --------------------------------------------------------------------------- #
# evaluate
# --------------------------------------------------------------------------- #


def test_evaluate_prints_metrics_for_execution(db_url, tmp_path):
    # First run a classification so there is an execution with metrics.
    _run(
        [
            "--database-url",
            db_url,
            "classify",
            str(NFR_SMALL),
            "--ground-truth",
            "type",
            "--storage-dir",
            str(tmp_path / "storage"),
        ]
    )

    from app.db.session import configure, create_engine_for, init_db, session_scope
    from app.services import executions as executions_service

    configure(create_engine_for(db_url))
    init_db()
    with session_scope() as session:
        execution_id = executions_service.list_executions(session)[0].id

    code, out, err = _run(["--database-url", db_url, "evaluate", str(execution_id)])
    assert code == 0, err
    assert f"Execution #{execution_id}" in out
    assert "accuracy: 1.0000" in out
    assert '"overall"' in out


def test_evaluate_missing_execution_is_error(db_url):
    code, _, err = _run(["--database-url", db_url, "evaluate", "999999"])
    assert code == 1
    assert "not found" in err.lower()
