"""Headless CLI drivers over the same services/engine as the API (task 6.7).

This module is the headless research path promised by the design (design.md
"Backend REST API": *"A CLI under ``backend/cli/`` calls the same services/
engine, preserving the headless research path and the current classification
commands"*). It is a thin ``argparse`` driver — **no web server** — that
initializes the SQLite datastore directly (:func:`app.db.session.init_db`) and
drives the exact same service + engine layer the FastAPI routers use, so a run
launched from the terminal is byte-for-byte the run the webapp would produce
(Req 12.4, 12.5).

Commands (mirroring the current workflow):

* ``version`` — report the engine version (preserved from the original stub).
* ``create-config`` — create a configuration, either from defaults, from an
  imported artifact JSON file (``--artifact``), or from a built-in gold case
  (``--gold``), persisting it to the DB via :mod:`app.services.configs`.
* ``run`` — run a stored configuration over a CSV dataset (``--csv`` +
  ``--map`` column→placeholder bindings, optional ``--ground-truth`` /
  ``--limit``) **or** a single ad-hoc instance (``--input key=value``). The CSV
  is loaded via :class:`mad.input.dataset.Dataset`, the run goes through
  :func:`mad.engine.orchestrator.run_debate` (wired via the service +
  :mod:`app.jobs.runner`), and the execution is persisted.
* ``classify`` — the preserved classification workflow (Req 12.5): run the
  built-in **RE binary F/NF debate** gold config over a requirement CSV,
  producing a per-instance ``judge`` class column (F/NF) exactly as the old
  ``code/llm/coordinator.py`` did — debaters + judge over a requirement CSV —
  but through the new engine. Prints per-instance predictions and aggregate
  metrics when a ground-truth column is present.
* ``evaluate`` — compute/print metrics for a finished execution via
  :mod:`mad.evaluation` when ground truth was recorded (Req 12.5).

Testability (the registry seam): every command that executes a debate resolves
its :class:`~mad.providers.registry.ProviderRegistry` through an injectable
``registry_factory``. The default builds a registry from the stored providers
(:func:`app.services.providers.build_registry`, real LiteLLM clients, used in
production). Tests inject a factory returning a registry backed by a
:class:`~mad.providers.base.MockModelClient`, so the regression test runs the
binary classification over ``nfr-small.csv`` fully offline and deterministically
— no network — asserting per-instance predictions and that aggregate metrics are
produced. The background launch likewise goes through the service's synchronous
launch seam (:func:`app.services.executions.make_sync_launcher`) so a CLI run
finishes before the command returns.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, TextIO

from sqlalchemy.orm import Session

from app.db.session import (
    configure,
    create_engine_for,
    init_db,
    session_scope,
)
from app.config import DEFAULT_DATASET_STORAGE_PATH
from app.schemas.executions import BatchInput, ExecutionCreateRequest
from app.services import configs as configs_service
from app.services import datasets as datasets_service
from app.services import executions as executions_service
from app.services import providers as providers_service
from mad import __version__ as mad_version
from mad.errors import MADError
from mad.providers.registry import ProviderRegistry

# A factory that builds the engine provider registry for a run, given the active
# DB session. The default reads the stored providers; tests inject an offline
# MockModelClient-backed registry (see module docstring).
RegistryFactory = Callable[[Session], ProviderRegistry]

# The name of the built-in gold config the ``classify`` command reproduces, and
# its engine gold-case key. Used to look the config up (seeding it if needed).
_RE_GOLD_KEY = "re_binary_debate"


def _default_registry_factory(session: Session) -> ProviderRegistry:
    """Build a registry from the stored providers (real clients)."""
    return providers_service.build_registry(session)


# ---------------------------------------------------------------------------
# Shared setup
# ---------------------------------------------------------------------------


def _init_datastore(database_url: Optional[str]) -> None:
    """Bind + initialize the datastore headlessly (no web server).

    Mirrors the web layer's startup (:func:`app.main._make_lifespan`): bind an
    engine for ``database_url`` as the process-wide default, create/stamp the
    schema, and idempotently seed the built-in gold/template configs so the
    ``classify`` command always finds the RE binary config.
    """
    if database_url:
        configure(create_engine_for(database_url))
    init_db()
    with session_scope() as session:
        configs_service.seed_builtin_configs(session)


def _storage_dir(args: argparse.Namespace) -> Path:
    """Resolve the directory uploaded CSVs are stored in for a CLI run.

    Mirrors the web layer's dataset storage: an explicit ``--storage-dir`` wins,
    otherwise the same default the API uses (``data/datasets``) so the CLI and
    webapp share one dataset store.
    """
    return Path(getattr(args, "storage_dir", None) or DEFAULT_DATASET_STORAGE_PATH)


def _parse_key_values(pairs: Sequence[str], *, what: str) -> dict[str, str]:
    """Parse ``key=value`` CLI pairs into a dict, raising on a malformed pair."""
    result: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise CLIError(
                f"Invalid {what} {pair!r}: expected key=value (e.g. requirement=req)."
            )
        key, _, value = pair.partition("=")
        key = key.strip()
        if not key:
            raise CLIError(f"Invalid {what} {pair!r}: the key is empty.")
        result[key] = value
    return result


class CLIError(MADError):
    """A user-facing CLI error: printed to stderr, exits non-zero."""


# ---------------------------------------------------------------------------
# create-config
# ---------------------------------------------------------------------------


def _cmd_create_config(args: argparse.Namespace, out: TextIO) -> int:
    """Create a configuration from defaults / an artifact file / a gold case."""
    _init_datastore(args.database_url)

    sources = [bool(args.artifact), bool(args.gold)]
    if sum(sources) > 1:
        raise CLIError("Provide at most one of --artifact / --gold.")

    with session_scope() as session:
        if args.gold:
            try:
                model = configs_service.templates.build_gold_case(args.gold)
            except KeyError as exc:
                raise CLIError(str(exc).strip("'")) from exc
            artifact = configs_service.export_config(model)
            detail = configs_service.import_config_artifact(
                session, artifact, name=args.name, description=args.description
            )
        elif args.artifact:
            artifact = _load_json_file(args.artifact)
            detail = configs_service.import_config_artifact(
                session, artifact, name=args.name, description=args.description
            )
        else:
            detail = configs_service.create_config(
                session, name=args.name, description=args.description
            )

    print(
        f"Created configuration #{detail.id}: {detail.name!r} "
        f"(schema {detail.schema_version}).",
        file=out,
    )
    if detail.under_development:
        joined = ", ".join(detail.under_development)
        print(
            f"  note: selects under-development value(s) and cannot be executed "
            f"until changed: {joined}.",
            file=out,
        )
    return 0


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def _cmd_run(
    args: argparse.Namespace, out: TextIO, *, registry_factory: RegistryFactory
) -> int:
    """Run a stored config over a CSV batch or a single ad-hoc instance."""
    _init_datastore(args.database_url)

    if bool(args.csv) == bool(args.input):
        raise CLIError("Provide exactly one of --csv (batch) or --input (single).")

    with session_scope() as session:
        registry = registry_factory(session)
        launch = executions_service.make_sync_launcher(sleep=lambda _s: None)

        if args.csv:
            detail = _launch_batch(session, args, launch=launch, registry=registry)
        else:
            instance = _parse_key_values(args.input, what="input")
            body = ExecutionCreateRequest(config_id=args.config_id, input=instance)
            detail = executions_service.create_execution(
                session, body, launch=launch, registry=registry
            )

    _print_execution(detail, out)
    return 0


def _launch_batch(
    session: Session,
    args: argparse.Namespace,
    *,
    launch: executions_service.LaunchFn,
    registry: ProviderRegistry,
):
    """Upload the CSV as a dataset and launch a batch execution over it."""
    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise CLIError(f"CSV file not found: {csv_path}")

    dataset = datasets_service.create_dataset(
        session,
        content=csv_path.read_bytes(),
        original_filename=csv_path.name,
        storage_dir=_storage_dir(args),
    )
    mapping = _parse_key_values(args.map or [], what="mapping")
    if not mapping:
        raise CLIError(
            "A batch run needs at least one --map column=placeholder binding."
        )

    batch = BatchInput(
        dataset_id=dataset.id,
        mapping=mapping,
        ground_truth_column=args.ground_truth,
        limit=args.limit,
    )
    body = ExecutionCreateRequest(config_id=args.config_id, batch=batch)
    return executions_service.create_execution(
        session, body, launch=launch, registry=registry
    )


# ---------------------------------------------------------------------------
# classify (preserved classification workflow, Req 12.5)
# ---------------------------------------------------------------------------


def _cmd_classify(
    args: argparse.Namespace, out: TextIO, *, registry_factory: RegistryFactory
) -> int:
    """Reproduce the binary F/NF classification over a requirement CSV.

    This preserves the old ``code/llm/coordinator.py`` workflow — two opposing
    debaters + a judge over a requirement CSV, producing a per-instance ``judge``
    class (F/NF) — but routes it through the new engine via the built-in RE
    binary gold config and the standard execution service.
    """
    _init_datastore(args.database_url)

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise CLIError(f"CSV file not found: {csv_path}")

    with session_scope() as session:
        registry = registry_factory(session)
        provider_id, model_key = _resolve_binding(
            registry, provider_id=args.provider_id, model=args.model
        )
        config_id = _create_re_binary_config(
            session, provider_id=provider_id, model_key=model_key
        )
        launch = executions_service.make_sync_launcher(sleep=lambda _s: None)

        dataset = datasets_service.create_dataset(
            session,
            content=csv_path.read_bytes(),
            original_filename=csv_path.name,
            storage_dir=_storage_dir(args),
        )
        batch = BatchInput(
            dataset_id=dataset.id,
            # The RE gold config's template is "Classify this requirement:
            # {{requirement}}", so the requirement column supplies `requirement`.
            mapping={args.requirement_column: "requirement"},
            ground_truth_column=args.ground_truth,
            limit=args.limit,
        )
        body = ExecutionCreateRequest(config_id=config_id, batch=batch)
        detail = executions_service.create_execution(
            session, body, launch=launch, registry=registry
        )

    _print_classification(detail, out)
    return 0


def _create_re_binary_config(
    session: Session, *, provider_id: str, model_key: str
) -> int:
    """Create the RE binary gold config bound to a provider, return its id.

    The built-in gold case authors its nodes with ``model_key="gpt-4o"`` but no
    ``provider_id`` (configs are provider-free until bound in the UI). The
    headless classification workflow has no UI binding step, so we bind every
    node to the chosen ``(provider_id, model_key)`` here, then persist it as a
    fresh config the execution service snapshots and runs.
    """
    model = configs_service.templates.build_gold_case(_RE_GOLD_KEY)
    for node in model.participants.nodes:
        node.base_model.provider_id = provider_id
        node.base_model.model_key = model_key
    artifact = configs_service.export_config(model)
    detail = configs_service.import_config_artifact(session, artifact)
    return detail.id


def _resolve_binding(
    registry: ProviderRegistry,
    *,
    provider_id: Optional[str],
    model: Optional[str],
) -> tuple[str, str]:
    """Resolve the ``(provider_id, model_key)`` to bind the debaters/judge to.

    An explicit ``--provider-id`` wins; otherwise the sole registered provider
    is used (ambiguous when several are configured). The model comes from
    ``--model`` or the provider's first configured model.
    """
    providers = registry.list_providers()
    if provider_id:
        if not registry.has(provider_id):
            raise CLIError(
                f"Unknown provider id {provider_id!r}. Configure it first "
                "(e.g. via the API/webapp) or pass --provider-id."
            )
        config = registry.get_config(provider_id)
    elif len(providers) == 1:
        config = providers[0]
    elif not providers:
        raise CLIError(
            "No providers are configured. Add a provider (via the API/webapp) "
            "and pass --provider-id, so the debaters/judge can be bound to a "
            "model."
        )
    else:
        known = ", ".join(p.id for p in providers)
        raise CLIError(
            f"Several providers are configured ({known}); pass --provider-id to "
            "choose which to bind the debaters/judge to."
        )

    model_key = model or (config.models[0] if config.models else None)
    if not model_key:
        raise CLIError(
            f"Provider {config.id!r} has no configured models; pass --model."
        )
    return config.id, model_key


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


def _cmd_evaluate(args: argparse.Namespace, out: TextIO) -> int:
    """Print metrics for a finished execution (Req 12.5)."""
    _init_datastore(args.database_url)

    with session_scope() as session:
        detail = executions_service.get_execution(session, args.execution_id)

    print(
        f"Execution #{detail.id}: status={detail.status} "
        f"({detail.completed_count}/{detail.instance_count} instances, "
        f"{detail.error_count} error(s)).",
        file=out,
    )
    if detail.metrics:
        overall = (detail.metrics.get("overall") or {}).get("accuracy")
        if overall is not None:
            print(f"  accuracy: {overall:.4f}", file=out)
        print(json.dumps(detail.metrics, indent=2, sort_keys=True), file=out)
    else:
        print(
            "  no aggregate metrics (no ground-truth column was mapped).",
            file=out,
        )
    return 0


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_execution(detail, out: TextIO) -> None:
    """Print a short summary of a finished execution."""
    print(
        f"Execution #{detail.id} ({detail.input_mode}): {detail.status} — "
        f"{detail.completed_count}/{detail.instance_count} instance(s), "
        f"{detail.error_count} error(s).",
        file=out,
    )
    for inst in detail.instances:
        decision = _decision_text(inst.final_decision)
        suffix = f" [error: {inst.error}]" if inst.error else ""
        print(f"  #{inst.instance_index}: {decision}{suffix}", file=out)
    if detail.metrics:
        overall = (detail.metrics.get("overall") or {}).get("accuracy")
        if overall is not None:
            print(f"  accuracy: {overall:.4f}", file=out)


def _print_classification(detail, out: TextIO) -> None:
    """Print the per-instance F/NF predictions + metrics (classify command)."""
    print(
        f"Classification execution #{detail.id}: {detail.status} — "
        f"{detail.completed_count}/{detail.instance_count} requirement(s), "
        f"{detail.error_count} error(s).",
        file=out,
    )
    for inst in detail.instances:
        label = _classification_label(inst)
        gt = f" (truth={inst.ground_truth})" if inst.ground_truth is not None else ""
        suffix = f" [error: {inst.error}]" if inst.error else ""
        print(f"  #{inst.instance_index}: judge={label}{gt}{suffix}", file=out)
    if detail.metrics:
        overall = (detail.metrics.get("overall") or {}).get("accuracy")
        if overall is not None:
            print(f"  accuracy: {overall:.4f}", file=out)


def _classification_label(inst) -> Optional[str]:
    """Extract the judge's F/NF class from a per-instance result.

    The RE binary judge returns ``{"class": "F"|"NF"}``; the runner stores it as
    the instance's ``final_decision`` and, when a ground-truth column is mapped,
    records the scored prediction in ``metrics["prediction"]``. Prefer the latter
    (already reduced to the label) and fall back to the decision's ``class``.
    """
    if inst.metrics and inst.metrics.get("prediction") is not None:
        return str(inst.metrics["prediction"])
    return _decision_text(inst.final_decision)


def _decision_text(decision: Any) -> Optional[str]:
    """Render a final-decision payload to a short display string."""
    if decision is None:
        return "(no decision)"
    if isinstance(decision, dict):
        # A single-property structured decision (e.g. {"class": "F"}) -> value.
        if len(decision) == 1:
            return str(next(iter(decision.values())))
        return json.dumps(decision, sort_keys=True)
    return str(decision)


def _load_json_file(path: str) -> dict[str, Any]:
    """Load + parse a JSON artifact file, raising a clear CLI error on failure."""
    p = Path(path)
    if not p.exists():
        raise CLIError(f"Artifact file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise CLIError(f"Could not read artifact JSON {p}: {exc}") from exc
    if not isinstance(data, dict):
        raise CLIError(f"Artifact JSON {p} must be a JSON object.")
    return data


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level ``mad`` argument parser with its subcommands."""
    parser = argparse.ArgumentParser(
        prog="mad",
        description=(
            "Headless MAD CLI — create configs, run debates over a CSV, and "
            "evaluate results through the same engine as the web API."
        ),
    )
    parser.add_argument(
        "-V",
        "--version",
        action="store_true",
        help="Print the engine version and exit.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="SQLAlchemy database URL (defaults to the on-disk sqlite:///mad.db).",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # version
    sub.add_parser("version", help="Print the engine version and exit.")

    # create-config
    cc = sub.add_parser(
        "create-config",
        help="Create a configuration (defaults / --artifact / --gold).",
    )
    cc.add_argument("--name", default=None, help="Configuration name.")
    cc.add_argument("--description", default=None, help="Configuration description.")
    cc.add_argument(
        "--artifact",
        default=None,
        help="Path to a MAD config artifact JSON file to import.",
    )
    cc.add_argument(
        "--gold",
        default=None,
        help="Create from a built-in gold case key (e.g. re_binary_debate).",
    )

    # run
    run_p = sub.add_parser(
        "run", help="Run a stored config over a CSV batch or a single input."
    )
    run_p.add_argument(
        "config_id", type=int, help="Id of the stored configuration to run."
    )
    run_p.add_argument("--csv", default=None, help="CSV dataset to run over (batch).")
    run_p.add_argument(
        "--map",
        action="append",
        metavar="COLUMN=PLACEHOLDER",
        help="Map a CSV column to a template placeholder (repeatable).",
    )
    run_p.add_argument(
        "--ground-truth",
        dest="ground_truth",
        default=None,
        help="CSV column holding gold labels (enables metrics).",
    )
    run_p.add_argument(
        "--limit", type=int, default=None, help="Cap the number of CSV rows run."
    )
    run_p.add_argument(
        "--input",
        action="append",
        metavar="KEY=VALUE",
        help="A single ad-hoc instance value (repeatable); alternative to --csv.",
    )
    run_p.add_argument(
        "--storage-dir",
        dest="storage_dir",
        default=None,
        help="Directory to store the uploaded CSV in (default: data/datasets).",
    )

    # classify
    cls_p = sub.add_parser(
        "classify",
        help="Binary F/NF requirement classification (preserved workflow).",
    )
    cls_p.add_argument("csv", help="Requirement CSV to classify.")
    cls_p.add_argument(
        "--requirement-column",
        dest="requirement_column",
        default="requirement",
        help="CSV column holding the requirement text (default: requirement).",
    )
    cls_p.add_argument(
        "--ground-truth",
        dest="ground_truth",
        default=None,
        help="CSV column holding the gold F/NF label (enables metrics).",
    )
    cls_p.add_argument(
        "--provider-id",
        dest="provider_id",
        default=None,
        help="Provider to bind the debaters/judge to (default: the sole one).",
    )
    cls_p.add_argument(
        "--model",
        default=None,
        help="Model key for the debaters/judge (default: the provider's first).",
    )
    cls_p.add_argument(
        "--storage-dir",
        dest="storage_dir",
        default=None,
        help="Directory to store the uploaded CSV in (default: data/datasets).",
    )
    cls_p.add_argument(
        "--limit", type=int, default=None, help="Cap the number of rows classified."
    )

    # evaluate
    ev = sub.add_parser("evaluate", help="Print metrics for a finished execution.")
    ev.add_argument("execution_id", type=int, help="Id of the execution to score.")

    return parser


# ---------------------------------------------------------------------------
# Dispatch / entry point
# ---------------------------------------------------------------------------


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    registry_factory: RegistryFactory = _default_registry_factory,
    out: Optional[TextIO] = None,
    err: Optional[TextIO] = None,
) -> int:
    """CLI entry point.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``).
        registry_factory: Builds the engine provider registry for a run; the
            default reads stored providers, tests inject an offline mock.
        out: Stream for normal output (defaults to ``sys.stdout``).
        err: Stream for errors (defaults to ``sys.stderr``).

    Returns:
        A process exit code (0 on success, non-zero on a user-facing error).
    """
    out = out or sys.stdout
    err = err or sys.stderr

    parser = build_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    if args.version or args.command == "version":
        print(f"mad {mad_version}", file=out)
        return 0

    if args.command is None:
        parser.print_help(err)
        return 2

    try:
        if args.command == "create-config":
            return _cmd_create_config(args, out)
        if args.command == "run":
            return _cmd_run(args, out, registry_factory=registry_factory)
        if args.command == "classify":
            return _cmd_classify(args, out, registry_factory=registry_factory)
        if args.command == "evaluate":
            return _cmd_evaluate(args, out)
    except CLIError as exc:
        print(f"error: {exc}", file=err)
        return 2
    except MADError as exc:
        # Domain errors (validation, provider, template, under-development, ...)
        # surface as a clear message rather than a traceback.
        print(f"error: {type(exc).__name__}: {exc}", file=err)
        return 1

    parser.print_help(err)  # pragma: no cover - unreachable with known commands.
    return 2


__all__ = ["build_parser", "main", "CLIError", "RegistryFactory"]
