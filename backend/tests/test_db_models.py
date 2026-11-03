"""Tests for the persistence layer (``app.db``).

Covers (Req 11.3, 14.3):

* schema init: ``init_db`` creates all tables and stamps the schema version
  marker; it is idempotent;
* model creation + session round-trips for every table (providers,
  configurations, datasets, executions, execution_instances), including JSON
  payload fidelity across many inputs;
* the immutable ``config_snapshot`` on executions: it is preserved verbatim and
  is independent of later edits to the source configuration (Req 11.3);
* referential behaviour: deleting a source configuration nulls the execution's
  ``config_id`` (SET NULL) while keeping the execution + its snapshot; deleting
  an execution cascades to its instances;
* ``Provider.has_key`` only reflects presence of an encrypted key;
* created_at/updated_at timestamps are populated.

Each test runs against a fresh in-memory SQLite engine so there is no shared
state and no on-disk artifacts.
"""

from __future__ import annotations

import copy

import pytest
from sqlalchemy import inspect, select

from app.db import (
    SCHEMA_VERSION,
    Configuration,
    Dataset,
    Execution,
    ExecutionInstance,
    ExecutionStatus,
    InputMode,
    Provider,
    SchemaMeta,
    create_engine_for,
    get_schema_version,
    init_db,
)
from app.db.session import session_scope
from sqlalchemy.orm import sessionmaker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    """A fresh in-memory SQLite engine with the schema initialized."""
    eng = create_engine_for("sqlite:///:memory:")
    init_db(eng)
    return eng


@pytest.fixture()
def Session(engine):
    """A sessionmaker bound to the in-memory engine."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _sample_artifact(name: str = "cfg") -> dict:
    """A representative MADConfig-shaped JSON artifact."""
    return {
        "name": name,
        "schema_version": "1.0",
        "participants": {
            "nodes": [
                {"id": "f", "label": "Functional", "roles": ["debater"]},
                {"id": "nf", "label": "Non-Functional", "roles": ["debater"]},
                {"id": "judge", "label": "Judge", "roles": ["judge"]},
            ]
        },
        "interaction": {"protocol": {"mechanism": "sequential", "max_rounds": 2}},
        "agreement": {"authority": "judge_based", "resolution": "argument_evaluation"},
        "input_spec": {"template": "Classify {{requirement}}", "placeholders": ["requirement"]},
    }


# ---------------------------------------------------------------------------
# Schema init / version marker
# ---------------------------------------------------------------------------


def test_init_db_creates_all_tables(engine):
    tables = set(inspect(engine).get_table_names())
    assert {
        "providers",
        "configurations",
        "datasets",
        "executions",
        "execution_instances",
        "schema_meta",
    } <= tables


def test_init_db_stamps_schema_version(engine):
    assert get_schema_version(engine) == SCHEMA_VERSION


def test_init_db_is_idempotent(engine):
    # Re-running must not duplicate the marker or error.
    first = init_db(engine)
    second = init_db(engine)
    assert first == second == SCHEMA_VERSION
    maker = sessionmaker(bind=engine, future=True)
    with maker() as s:
        markers = s.scalars(select(SchemaMeta)).all()
    assert len(markers) == 1


# ---------------------------------------------------------------------------
# Model creation + round-trips
# ---------------------------------------------------------------------------


def test_provider_round_trip(Session):
    with session_scope(Session) as s:
        s.add(
            Provider(
                name="OpenAI",
                kind="openai",
                base_url=None,
                encrypted_api_key="gAAA-cipher",
                models=["gpt-4o", "gpt-4o-mini"],
            )
        )
    with Session() as s:
        p = s.scalars(select(Provider)).one()
        assert p.name == "OpenAI"
        assert p.kind == "openai"
        assert p.models == ["gpt-4o", "gpt-4o-mini"]
        assert p.has_key is True
        assert p.created_at is not None and p.updated_at is not None


def test_provider_has_key_false_without_key(Session):
    with session_scope(Session) as s:
        s.add(Provider(name="Ollama", kind="ollama", base_url="http://localhost:11434", models=[]))
    with Session() as s:
        p = s.scalars(select(Provider)).one()
        assert p.has_key is False


@pytest.mark.parametrize(
    "models",
    [[], ["m1"], ["a", "b", "c"], ["unicode-é", "with space"]],
)
def test_provider_models_json_fidelity(Session, models):
    with session_scope(Session) as s:
        s.add(Provider(name="P", kind="openai_compatible", models=models))
    with Session() as s:
        assert s.scalars(select(Provider)).one().models == models


def test_configuration_round_trip(Session):
    art = _sample_artifact("RE binary debate")
    with session_scope(Session) as s:
        s.add(
            Configuration(
                name="RE binary debate",
                description="Functional vs Non-Functional + Judge",
                artifact=art,
                schema_version=art["schema_version"],
            )
        )
    with Session() as s:
        c = s.scalars(select(Configuration)).one()
        assert c.name == "RE binary debate"
        assert c.artifact == art
        assert c.schema_version == "1.0"


def test_dataset_round_trip(Session):
    with session_scope(Session) as s:
        s.add(
            Dataset(
                name="nfr-small",
                original_filename="nfr-small.csv",
                stored_path="/data/datasets/PROMISE/nfr-small.csv",
                columns=["RequirementText", "class"],
                row_count=25,
            )
        )
    with Session() as s:
        d = s.scalars(select(Dataset)).one()
        assert d.columns == ["RequirementText", "class"]
        assert d.row_count == 25


def test_execution_and_instances_round_trip(Session):
    art = _sample_artifact()
    with session_scope(Session) as s:
        cfg = Configuration(name="c", artifact=art, schema_version="1.0")
        s.add(cfg)
        s.flush()
        execution = Execution(
            config_id=cfg.id,
            config_snapshot=copy.deepcopy(art),
            input_mode=InputMode.BATCH.value,
            input_ref={"dataset_id": 1, "mapping": {"requirement": "RequirementText"}},
            status=ExecutionStatus.COMPLETED.value,
            progress=1.0,
            metrics={"accuracy": 0.8},
            instances=[
                ExecutionInstance(
                    instance_index=0,
                    resolved_input={"requirement": "The system shall be fast"},
                    transcript={"rounds": [{"agent": "f", "text": "NF"}]},
                    final_decision={"class": "NF"},
                    ground_truth="NF",
                    metrics={"correct": True},
                ),
                ExecutionInstance(
                    instance_index=1,
                    resolved_input={"requirement": "The user logs in"},
                    final_decision={"class": "F"},
                    ground_truth="F",
                    error=None,
                ),
            ],
        )
        s.add(execution)
    with Session() as s:
        ex = s.scalars(select(Execution)).one()
        assert ex.status == "completed"
        assert ex.progress == 1.0
        assert ex.metrics == {"accuracy": 0.8}
        assert ex.input_ref["mapping"] == {"requirement": "RequirementText"}
        assert len(ex.instances) == 2
        # ordered by instance_index
        assert [i.instance_index for i in ex.instances] == [0, 1]
        assert ex.instances[0].transcript == {"rounds": [{"agent": "f", "text": "NF"}]}
        assert ex.instances[0].ground_truth == "NF"
        assert ex.instances[1].transcript is None


# ---------------------------------------------------------------------------
# Immutable config_snapshot (Req 11.3)
# ---------------------------------------------------------------------------


def test_config_snapshot_independent_of_source_edits(Session):
    """Editing the source Configuration must not change an execution's snapshot."""
    art = _sample_artifact()
    with session_scope(Session) as s:
        cfg = Configuration(name="c", artifact=copy.deepcopy(art), schema_version="1.0")
        s.add(cfg)
        s.flush()
        s.add(
            Execution(
                config_id=cfg.id,
                config_snapshot=copy.deepcopy(art),
                input_mode=InputMode.SINGLE.value,
                input_ref={"requirement": "x"},
            )
        )

    # Mutate the source configuration after the run was created.
    with session_scope(Session) as s:
        cfg = s.scalars(select(Configuration)).one()
        changed = copy.deepcopy(cfg.artifact)
        changed["name"] = "MUTATED"
        changed["participants"]["nodes"].append(
            {"id": "extra", "label": "Extra", "roles": ["debater"]}
        )
        cfg.artifact = changed
        cfg.name = "MUTATED"

    with Session() as s:
        ex = s.scalars(select(Execution)).one()
        # Snapshot still reflects the original artifact, not the edit.
        assert ex.config_snapshot == art
        assert ex.config_snapshot["name"] == "cfg"
        assert len(ex.config_snapshot["participants"]["nodes"]) == 3


def test_config_snapshot_survives_source_deletion(Session):
    """Deleting the source config nulls config_id but keeps the snapshot (Req 11.3)."""
    art = _sample_artifact()
    with session_scope(Session) as s:
        cfg = Configuration(name="c", artifact=art, schema_version="1.0")
        s.add(cfg)
        s.flush()
        s.add(
            Execution(
                config_id=cfg.id,
                config_snapshot=copy.deepcopy(art),
                input_mode=InputMode.SINGLE.value,
                input_ref={},
            )
        )

    with session_scope(Session) as s:
        cfg = s.scalars(select(Configuration)).one()
        s.delete(cfg)

    with Session() as s:
        assert s.scalars(select(Configuration)).all() == []
        ex = s.scalars(select(Execution)).one()
        assert ex.config_id is None  # SET NULL
        assert ex.config_snapshot == art  # snapshot intact


# ---------------------------------------------------------------------------
# Cascade behaviour
# ---------------------------------------------------------------------------


def test_deleting_execution_cascades_to_instances(Session):
    art = _sample_artifact()
    with session_scope(Session) as s:
        s.add(
            Execution(
                config_snapshot=art,
                input_mode=InputMode.BATCH.value,
                input_ref={},
                instances=[
                    ExecutionInstance(instance_index=0, resolved_input={"a": 1}),
                    ExecutionInstance(instance_index=1, resolved_input={"a": 2}),
                ],
            )
        )
    with session_scope(Session) as s:
        ex = s.scalars(select(Execution)).one()
        s.delete(ex)
    with Session() as s:
        assert s.scalars(select(Execution)).all() == []
        assert s.scalars(select(ExecutionInstance)).all() == []


def test_instance_index_unique_per_execution(Session):
    from sqlalchemy.exc import IntegrityError

    art = _sample_artifact()
    with pytest.raises(IntegrityError):
        with session_scope(Session) as s:
            s.add(
                Execution(
                    config_snapshot=art,
                    input_mode=InputMode.BATCH.value,
                    input_ref={},
                    instances=[
                        ExecutionInstance(instance_index=0, resolved_input={}),
                        ExecutionInstance(instance_index=0, resolved_input={}),
                    ],
                )
            )
