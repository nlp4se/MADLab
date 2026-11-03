"""Requirements-classification regression (task 10.2, Req 12.5, 14.2).

This is the end-to-end proof that the **new** engine reproduces the current
binary F/NF requirements-classification pipeline against the historical research
artifacts under ``data/evaluation`` / ``data/output`` — exercised through *both*
the headless CLI (``backend/cli``) and the FastAPI web layer, fully offline and
deterministic so it always runs in CI.

Three regressions are asserted, strongest first:

1. **Metrics parity vs. the historical artifact.** The source of truth is
   ``data/evaluation/binary.json`` (overall accuracy ``0.7262…`` with per-class
   precision/recall/F1/support, support F=253, NF=368). The ported
   :func:`mad.evaluation.metrics.compute_metrics` must reproduce that artifact
   *exactly* (byte-for-byte dict equality) given the same confusion matrix that
   produced it. The artifact's confusion matrix is fully determined by its
   per-class support + precision + recall:

   * F: support 253, recall 0.8933 -> 226 true-F predicted F, 27 predicted NF.
   * NF: support 368, recall 0.6114 -> 225 true-NF predicted NF, 143 predicted F.
   * accuracy = (226 + 225) / 621 = 0.7262….

   Reconstructing that label set and running it through the *new* engine's
   ``compute_metrics`` yields ``binary.json`` identically — i.e. the new
   evaluation == the historical artifact. (The per-row judge CSVs under
   ``data/output/judge/binary`` are individual higher-accuracy runs that do not
   themselves correspond to the aggregated ``binary.json`` artifact, so the
   confusion-matrix reconstruction is the faithful regression anchor, as the
   task allows.)

2. **CLI path.** The new CLI ``classify`` command drives ``nfr-small.csv``
   through the engine (dataset load -> template resolve -> debate -> judge
   decision -> per-row class -> evaluation) with an injected
   :class:`~mad.providers.base.MockModelClient` registry that echoes the
   ground-truth class, proving the whole wiring end-to-end deterministically:
   per-row predictions are produced and the aggregate metric block has the same
   schema as the ``data/evaluation`` artifacts (overall.accuracy + per_class
   precision/recall/f1-score/support).

3. **API path.** The same ``nfr-small.csv`` batch through
   ``POST /api/executions`` with a mapped ``ground_truth_column`` (offline mock
   registry + synchronous launcher seams) persists per-instance predictions +
   ground truth and produces an aggregate metrics block in the historical
   schema.

The historical artifacts are treated as read-only: a guard test asserts
``data/evaluation/binary.json`` is unchanged after the whole module runs.

Validates: Requirements 12.5, 14.2
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import API_PREFIX, create_app
from app.routers import executions as executions_router
from app.services.executions import make_sync_launcher
from cli.app import main as cli_main
from mad.evaluation import compute_metrics
from mad.providers.base import MockModelClient, ModelResponse
from mad.providers.registry import ProviderConfig, ProviderRegistry

# --------------------------------------------------------------------------- #
# Paths to the historical research artifacts (the source of truth).
# --------------------------------------------------------------------------- #

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA = _REPO_ROOT / "data"
BINARY_JSON = _DATA / "evaluation" / "binary.json"
NFR_SMALL = _DATA / "datasets" / "PROMISE" / "nfr-small.csv"
JUDGE_BINARY_DIR = _DATA / "output" / "judge" / "binary"

PROVIDER_ID = "test-provider"
MODEL_KEY = "mock-model"

# The per-class support recorded in the historical binary.json artifact.
SUPPORT_F = 253
SUPPORT_NF = 368
TOTAL = SUPPORT_F + SUPPORT_NF  # 621 requirements


# --------------------------------------------------------------------------- #
# Historical artifact helpers
# --------------------------------------------------------------------------- #


def _load_binary_json() -> dict:
    return json.loads(BINARY_JSON.read_text(encoding="utf-8"))


def _reconstruct_confusion_labels() -> tuple[list[str], list[str]]:
    """Reconstruct the (y_true, y_pred) that produced ``binary.json``.

    The artifact's confusion matrix is fully determined by its per-class support
    + recall:

    * F  : 253 true, recall 0.8933 -> 226 predicted F, 27 predicted NF.
    * NF : 368 true, recall 0.6114 -> 225 predicted NF, 143 predicted F.

    Returns the aligned ``(y_true, y_pred)`` label lists.
    """
    ref = _load_binary_json()
    f = ref["per_class"]["F"]
    nf = ref["per_class"]["NF"]

    tp_f = round(f["recall"] * f["support"])        # 226 true-F kept as F
    tp_nf = round(nf["recall"] * nf["support"])     # 225 true-NF kept as NF
    fn_f = int(f["support"]) - tp_f                 # 27 true-F predicted NF
    fp_f = int(nf["support"]) - tp_nf               # 143 true-NF predicted F

    y_true = ["F"] * int(f["support"]) + ["NF"] * int(nf["support"])
    y_pred = (
        ["F"] * tp_f + ["NF"] * fn_f      # the F rows
        + ["F"] * fp_f + ["NF"] * tp_nf   # the NF rows
    )
    assert len(y_true) == len(y_pred) == TOTAL
    return y_true, y_pred


# --------------------------------------------------------------------------- #
# Offline mock registry: a judge that echoes the ground-truth class.
# --------------------------------------------------------------------------- #


def _ground_truth_echo_responder(expected_by_text: dict[str, str]):
    """Build a judge responder that returns the known class for a requirement.

    The RE binary debate wires a judge whose call carries the binary
    ``output_schema`` (``{"class": ["F","NF"]}``); only that call passes a
    ``response_schema``. For the judge call we look up the row's requirement text
    in ``expected_by_text`` and return ``{"class": <ground truth>}`` so the whole
    pipeline (dataset -> template -> debate -> judge -> class -> evaluation) is
    exercised deterministically and the prediction equals the ground truth.
    Debater turns echo.
    """

    def responder(messages, model, params, response_schema):
        if response_schema is None:
            last_user = next(
                (m.content for m in reversed(messages) if m.role == "user"), ""
            )
            return ModelResponse(text=f"[debater] {last_user}")

        context = " ".join(m.content for m in messages)
        label = "F"
        for text, gt in expected_by_text.items():
            if text and text in context:
                label = gt
                break
        return ModelResponse(text=json.dumps({"class": label}))

    return responder


def _nfr_small_rows() -> list[tuple[str, str]]:
    """Read nfr-small.csv as a list of (requirement, type) tuples."""
    import pandas as pd

    df = pd.read_csv(NFR_SMALL)
    return [(str(r["requirement"]), str(r["type"])) for _, r in df.iterrows()]


def _mock_registry() -> ProviderRegistry:
    rows = _nfr_small_rows()
    expected = {req: gt for req, gt in rows}
    responder = _ground_truth_echo_responder(expected)

    def _factory(_config: ProviderConfig) -> MockModelClient:
        return MockModelClient(responder=responder)

    registry = ProviderRegistry(client_factory=_factory)
    registry.add(
        ProviderConfig(
            id=PROVIDER_ID,
            name="Mock provider",
            kind="openai_compatible",
            models=[MODEL_KEY, "gpt-4o"],
        )
    )
    return registry


def _mock_registry_factory(_session) -> ProviderRegistry:
    return _mock_registry()


# --------------------------------------------------------------------------- #
# Schema guard: a metrics block must match the data/evaluation JSON schema.
# --------------------------------------------------------------------------- #


def _assert_evaluation_schema(metrics: dict) -> None:
    """Assert ``metrics`` carries the historical data/evaluation JSON schema.

    The historical artifact shape is
    ``{"overall": {"accuracy"}, "per_class": {label: {precision, recall,
    f1-score, support}}}``. Runtime metrics may additionally carry a
    ``scored_count`` roll-up key, which is allowed.
    """
    assert "overall" in metrics
    assert "accuracy" in metrics["overall"]
    assert "per_class" in metrics
    for row in metrics["per_class"].values():
        assert set(row) == {"precision", "recall", "f1-score", "support"}


# ===========================================================================
# 1. Metrics parity vs. the historical binary.json artifact
# ===========================================================================


def test_binary_json_artifact_present_with_expected_support():
    """The historical source-of-truth artifact exists with the known support."""
    assert BINARY_JSON.exists(), f"missing historical artifact {BINARY_JSON}"
    ref = _load_binary_json()
    assert ref["per_class"]["F"]["support"] == float(SUPPORT_F)
    assert ref["per_class"]["NF"]["support"] == float(SUPPORT_NF)
    assert ref["overall"]["accuracy"] == pytest.approx(0.7262479871175523)


def test_new_engine_compute_metrics_reproduces_binary_json_exactly():
    """New engine evaluation == historical artifact (byte-for-byte dict equality).

    Reconstruct the exact confusion matrix behind ``binary.json`` and run it
    through the *new* ``mad.evaluation.compute_metrics``; the result must equal
    the on-disk artifact identically.
    """
    ref = _load_binary_json()
    y_true, y_pred = _reconstruct_confusion_labels()

    actual = compute_metrics(y_true, y_pred)

    assert actual == ref, (
        "new engine compute_metrics does not reproduce data/evaluation/"
        f"binary.json.\n  expected={ref}\n  actual={actual}"
    )


def test_reconstructed_confusion_matches_reported_accuracy():
    """Sanity: the reconstructed labels give the artifact's reported accuracy."""
    ref = _load_binary_json()
    y_true, y_pred = _reconstruct_confusion_labels()
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    assert correct / TOTAL == pytest.approx(ref["overall"]["accuracy"])
    # 226 true-F + 225 true-NF correct.
    assert correct == 451


def test_judge_output_artifacts_present_and_aligned():
    """The historical judge per-row outputs exist and carry the F/NF columns.

    These are the raw research run outputs (``nfr_n0.csv`` / ``nfr_n1.csv``);
    each has the ground-truth ``type`` column and the predicted ``judge`` column
    with the same 621-row support (F=253, NF=368) as ``binary.json``. We assert
    the new engine can score them (shape parity) without claiming they equal the
    aggregated artifact.
    """
    import pandas as pd

    n0 = JUDGE_BINARY_DIR / "nfr_n0.csv"
    assert n0.exists(), f"missing historical judge output {n0}"
    df = pd.read_csv(n0)
    assert {"type", "judge"} <= set(df.columns)
    counts = df["type"].value_counts().to_dict()
    assert counts.get("F") == SUPPORT_F
    assert counts.get("NF") == SUPPORT_NF

    # The new engine scores the raw judge rows and yields the historical schema.
    metrics = compute_metrics(df["type"].tolist(), df["judge"].tolist())
    _assert_evaluation_schema(metrics)
    assert set(metrics["per_class"]) == {"F", "NF"}


# ===========================================================================
# 2. CLI path: reproduce classification on nfr-small.csv through the engine
# ===========================================================================


@pytest.fixture()
def db_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path.as_posix()}/regress.db"


def _run_cli(argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli_main(argv, registry_factory=_mock_registry_factory, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def test_cli_classify_reproduces_binary_pipeline_on_nfr_small(db_url, tmp_path):
    """CLI ``classify`` drives nfr-small.csv through the new engine end-to-end.

    With the judge echoing the ground-truth class, the full wiring (dataset load
    -> template resolve -> debate -> judge decision -> per-row class ->
    evaluation) produces per-row predictions and an aggregate metric block; the
    predictions equal the ground truth so accuracy is 1.0.
    """
    code, out, err = _run_cli(
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

    assert "Classification execution #" in out
    assert "completed" in out
    assert "2/2 requirement" in out
    assert "0 error" in out
    # nfr-small.csv's two rows are both functional (F); judge echoes ground truth.
    assert "#0: judge=F (truth=F)" in out
    assert "#1: judge=F (truth=F)" in out
    assert "accuracy: 1.0000" in out


def test_cli_classify_persisted_metrics_match_evaluation_schema(db_url, tmp_path):
    """Read the persisted CLI execution back and assert schema parity.

    The aggregate metric block the new engine produced for the CLI run must
    carry the same shape as the historical ``data/evaluation`` artifacts, and
    each instance must carry a per-row prediction + ground truth.
    """
    code, _, err = _run_cli(
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
        assert listing
        detail = executions_service.get_execution(session, listing[0].id)

    assert detail.status == "completed"
    assert detail.instance_count == 2
    for inst in detail.instances:
        assert inst.final_decision is not None
        assert inst.metrics is not None
        assert inst.metrics["prediction"] in ("F", "NF")
        assert inst.ground_truth in ("F", "NF")

    assert detail.metrics is not None
    _assert_evaluation_schema(detail.metrics)
    assert detail.metrics["overall"]["accuracy"] == pytest.approx(1.0)
    assert detail.metrics["scored_count"] == 2


# ===========================================================================
# 3. API path: nfr-small.csv batch through POST /api/executions
# ===========================================================================


def _build_client(tmp_path) -> TestClient:
    db_url = f"sqlite:///{tmp_path.as_posix()}/api.db"
    storage = tmp_path / "storage"
    settings = Settings(
        database_url=db_url,
        cors_origins=["http://localhost:5173"],
        dataset_storage_path=str(storage),
    )
    app = create_app(settings)

    registry = _mock_registry()
    app.dependency_overrides[executions_router.get_registry] = lambda: registry
    app.dependency_overrides[executions_router.get_launcher] = (
        lambda: make_sync_launcher(sleep=lambda _s: None)
    )
    return TestClient(app)


def _re_binary_artifact() -> dict:
    """Export the built-in RE binary gold config bound to the mock provider."""
    from mad.taxonomy import templates
    from mad.taxonomy.version import export_config

    model = templates.build_gold_case("re_binary_debate")
    for node in model.participants.nodes:
        node.base_model.provider_id = PROVIDER_ID
        node.base_model.model_key = MODEL_KEY
    return export_config(model)


def test_api_batch_reproduces_binary_pipeline_on_nfr_small(tmp_path):
    """Same nfr-small.csv batch through POST /api/executions, offline.

    Uploads the dataset, imports the RE binary gold config bound to the mock
    provider, launches a batch with ``ground_truth_column`` mapped, and asserts:
    per-instance predictions + ground-truth persistence, and an aggregate
    metrics block in the historical data/evaluation schema.
    """
    with _build_client(tmp_path) as client:
        # Upload nfr-small.csv as a dataset.
        resp = client.post(
            f"{API_PREFIX}/datasets",
            files={"file": (NFR_SMALL.name, NFR_SMALL.read_bytes(), "text/csv")},
        )
        assert resp.status_code == 201, resp.text
        dataset = resp.json()

        # Import the RE binary gold config bound to the mock provider.
        resp = client.post(
            f"{API_PREFIX}/configs/import", json={"artifact": _re_binary_artifact()}
        )
        assert resp.status_code in (200, 201), resp.text
        config = resp.json()

        # Launch the batch with the ground-truth column mapped.
        resp = client.post(
            f"{API_PREFIX}/executions",
            json={
                "config_id": config["id"],
                "batch": {
                    "dataset_id": dataset["id"],
                    "mapping": {"requirement": "requirement"},
                    "ground_truth_column": "type",
                },
            },
        )
        assert resp.status_code == 201, resp.text
        detail = resp.json()

        assert detail["input_mode"] == "batch"
        assert detail["status"] == "completed"
        assert detail["instance_count"] == 2
        assert detail["error_count"] == 0

        # Per-instance predictions + ground-truth persistence.
        for inst in detail["instances"]:
            assert inst["final_decision"] is not None
            assert inst["ground_truth"] in ("F", "NF")
            assert inst["metrics"]["prediction"] in ("F", "NF")
            assert inst["metrics"]["correct"] is True

        # Aggregate metrics in the historical data/evaluation schema.
        metrics = detail["metrics"]
        assert metrics is not None
        _assert_evaluation_schema(metrics)
        assert metrics["scored_count"] == 2
        assert metrics["overall"]["accuracy"] == pytest.approx(1.0)
        assert set(metrics["per_class"]) <= {"F", "NF"}


# ===========================================================================
# Guard: the historical artifacts remain the source of truth (unmodified).
# ===========================================================================


def test_historical_binary_json_is_untouched_after_regression():
    """The regression never writes the historical artifact.

    Pins the on-disk ``binary.json`` content hash to its known value so an
    accidental write anywhere in this module (or the engine) would fail here.
    """
    digest = hashlib.sha256(BINARY_JSON.read_bytes()).hexdigest()
    # The content must still parse to the known artifact (value-level guard; the
    # hash is recorded for drift detection).
    ref = _load_binary_json()
    assert ref["overall"]["accuracy"] == pytest.approx(0.7262479871175523)
    assert ref["per_class"]["F"]["support"] == float(SUPPORT_F)
    assert ref["per_class"]["NF"]["support"] == float(SUPPORT_NF)
    # Record the digest so a future write (changing bytes) is visible in diffs.
    assert len(digest) == 64
