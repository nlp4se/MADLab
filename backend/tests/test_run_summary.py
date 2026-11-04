"""Task 11.18: run summary — execution time and input/output tokens.

Covers the pure aggregation helper (mixed / missing usage and cost, legacy
transcripts), the engine folding judge + summarizer calls into the transcript
totals, wall-clock timing on success and failure (instance ``duration_s``,
execution ``started_at`` / ``finished_at``), the v2 -> v3 column migration on an
old database, and the ``summary`` / per-instance shape of the detail and list
responses. Fully offline (mock model clients).

Validates: Requirements 9.4, 11.1, 11.2
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db.models import Execution, ExecutionInstance
from app.db.session import SCHEMA_VERSION, create_engine_for, get_schema_version, init_db
from app.main import API_PREFIX, create_app
from app.routers import executions as executions_router
from app.schemas.executions import InstanceUsage
from app.services.execution_summary import (
    instance_usage_from_parts,
    instance_usage_from_transcript,
    summarize_run,
    wall_time_s,
)
from app.services.executions import list_executions, make_sync_launcher
from mad.engine.orchestrator import run_debate
from mad.providers.base import Message, MockModelClient
from mad.providers.registry import ProviderConfig, ProviderRegistry
from mad.taxonomy import templates
from mad.taxonomy.schema import MADConfig

T0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _no_sleep(_seconds: float) -> None:
    """No-op backoff sleep."""


# --------------------------------------------------------------------------- #
# Pure aggregation
# --------------------------------------------------------------------------- #


def test_instance_usage_from_transcript_reads_the_rollup_and_calls():
    usage = instance_usage_from_transcript(
        {
            "messages": [{}, {}],
            "usage": {
                "prompt_tokens": 1200,
                "completion_tokens": 300,
                "total_tokens": 1500,
                "cost_usd": 0.002,
                "latency_s": 4.5,
            },
            "calls": 3,  # 2 turns + 1 summarizer compression
            "duration_s": 5.25,
        }
    )
    assert usage == InstanceUsage(
        input_tokens=1200,
        output_tokens=300,
        total_tokens=1500,
        cost_usd=0.002,
        model_time_s=4.5,
        calls=3,
    )


def test_legacy_and_malformed_transcripts_degrade_gracefully():
    # Pre-11.18 transcript: no ``calls`` -> one call per message; no total.
    legacy = instance_usage_from_transcript(
        {
            "messages": [{}, {}, {}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost_usd": None},
        }
    )
    assert legacy.calls == 3
    assert legacy.total_tokens == 15
    assert legacy.cost_usd is None and legacy.model_time_s is None

    # Garbage values count as absent, never crash.
    junk = instance_usage_from_parts(
        usage={"prompt_tokens": "lots", "completion_tokens": True, "latency_s": "x"},
        calls=None,
        message_count=None,
    )
    assert junk == InstanceUsage()
    assert instance_usage_from_transcript(None) is None


def test_summarize_run_mixes_reported_and_missing_usage():
    with_cost = InstanceUsage(
        input_tokens=100, output_tokens=40, total_tokens=140,
        cost_usd=0.01, model_time_s=2.0, calls=3,
    )
    no_cost = InstanceUsage(
        input_tokens=50, output_tokens=10, total_tokens=60,
        cost_usd=None, model_time_s=None, calls=2,
    )
    summary = summarize_run(
        status="partial",
        started_at=T0,
        finished_at=T0 + timedelta(seconds=12.5),
        # ok + ok + failed-with-partial-transcript + failed-without-transcript
        instances=[(False, with_cost), (False, no_cost), (True, no_cost), (True, None)],
    )
    assert summary.wall_time_s == pytest.approx(12.5)
    assert summary.model_time_s == pytest.approx(2.0)
    assert (summary.input_tokens, summary.output_tokens, summary.total_tokens) == (200, 60, 260)
    assert summary.cost_usd == pytest.approx(0.01)
    assert summary.calls == 7
    assert summary.instances.model_dump() == {"total": 4, "completed": 2, "failed": 2}


def test_summarize_run_without_any_reported_cost_or_latency():
    usage = InstanceUsage(input_tokens=5, output_tokens=1, total_tokens=6, calls=1)
    summary = summarize_run(
        status="completed", started_at=None, finished_at=None, instances=[(False, usage)]
    )
    assert summary.cost_usd is None
    assert summary.model_time_s is None
    assert summary.wall_time_s is None  # no timestamps (old execution)
    assert summary.input_tokens == 5


def test_summarize_run_uses_the_expected_total_while_running():
    summary = summarize_run(
        status="running",
        started_at=T0,
        finished_at=None,
        instances=[(False, InstanceUsage(calls=1))],
        expected_total=5,
        now=T0 + timedelta(seconds=3),
    )
    assert summary.instances.model_dump() == {"total": 5, "completed": 1, "failed": 0}
    assert summary.wall_time_s == pytest.approx(3.0)


def test_wall_time_rules():
    naive_start = T0.replace(tzinfo=None)  # SQLite returns naive UTC
    assert wall_time_s(
        status="completed", started_at=naive_start, finished_at=T0 + timedelta(minutes=2)
    ) == pytest.approx(120.0)
    assert wall_time_s(
        status="running", started_at=T0, finished_at=None, now=T0 + timedelta(seconds=9)
    ) == pytest.approx(9.0)
    # Terminal but never stamped as finished, or never started: unknown.
    assert wall_time_s(status="failed", started_at=T0, finished_at=None) is None
    assert wall_time_s(status="running", started_at=None, finished_at=None) is None


# --------------------------------------------------------------------------- #
# Engine: every model call (turns, judge, summarizer) is in the totals
# --------------------------------------------------------------------------- #


def _mock_registry(client) -> ProviderRegistry:
    return ProviderRegistry(
        providers=[ProviderConfig(id="mock", name="Mock", kind="mock", models=["m"])],
        client_factory=lambda _config: client,
    )


def _bind(config: MADConfig) -> MADConfig:
    for node in config.participants.nodes:
        node.base_model.provider_id = "mock"
        if not node.base_model.model_key:
            node.base_model.model_key = "m"
    return config


def _expected_prompt_tokens(client: MockModelClient) -> int:
    # MockModelClient counts whitespace-separated words of the request.
    return sum(
        sum(len(m.content.split()) for m in call.messages) for call in client.calls
    )


def test_summarizer_calls_are_folded_into_the_transcript_usage():
    """ChatEval S3: the summarizer's history compressions record no message."""
    client = MockModelClient(responder=lambda *a: "good")
    transcript = run_debate(
        _bind(templates.chateval_s3()),
        {"response": "The answer is correct."},
        _mock_registry(client),
        sleep=_no_sleep,
    )
    assert transcript.errors == []
    # More calls than messages: the compressions are counted too.
    assert len(client.calls) > len(transcript.messages)
    assert transcript.calls == len(client.calls)
    assert transcript.usage.prompt_tokens == _expected_prompt_tokens(client)
    assert transcript.usage.completion_tokens == len(client.calls)  # "good" = 1 word


def test_judge_call_is_in_the_transcript_usage():
    client = MockModelClient(
        responder=lambda m, model, p, schema: '{"class": "NF"}' if schema else "argument"
    )
    transcript = run_debate(
        _bind(templates.re_binary_debate()),
        {"requirement": "Login must be fast"},
        _mock_registry(client),
        sleep=_no_sleep,
    )
    assert any(m.role == "judge" for m in transcript.messages)
    assert transcript.calls == len(client.calls)
    assert transcript.usage.prompt_tokens == _expected_prompt_tokens(client)


# --------------------------------------------------------------------------- #
# API: timing on success / failure + response shape
# --------------------------------------------------------------------------- #

PROVIDER_ID = "test-provider"


def _node(node_id: str, label: str, roles: list[str]) -> dict:
    return {
        "id": node_id,
        "label": label,
        "roles": roles,
        "base_model": {"provider_id": PROVIDER_ID, "model_key": "m", "temperature": 0.0},
        "system_prompt": f"You are {label}.",
    }


def _judge_artifact() -> dict:
    return {
        "schema_version": "1.0",
        "name": "Timed debate",
        "participants": {
            "nodes": [
                _node("alice", "Alice", ["debater"]),
                _node("bob", "Bob", ["debater"]),
                _node("judge", "Judge", ["judge"]),
            ]
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
        "agreement": {"authority": "judge_based", "resolution": "argument_evaluation"},
        "input_spec": {"template": "Debate: {{topic}}", "placeholders": ["topic"]},
    }


def _is_judge(messages: list[Message]) -> bool:
    return any("You are Judge." in m.content for m in messages if m.role == "system")


def _client(tmp_path, responder) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path.as_posix()}/summary.db",
        dataset_storage_path=str(tmp_path / "storage"),
    )
    app = create_app(settings)
    registry = ProviderRegistry(client_factory=lambda _c: MockModelClient(responder=responder))
    registry.add(
        ProviderConfig(id=PROVIDER_ID, name="Mock", kind="openai_compatible", models=["m"])
    )
    app.dependency_overrides[executions_router.get_registry] = lambda: registry
    app.dependency_overrides[executions_router.get_launcher] = lambda: make_sync_launcher(
        sleep=_no_sleep
    )
    return TestClient(app)


def _launch(client: TestClient) -> dict:
    config = client.post(f"{API_PREFIX}/configs/import", json={"artifact": _judge_artifact()})
    assert config.status_code in (200, 201), config.text
    resp = client.post(
        f"{API_PREFIX}/executions",
        json={"config_id": config.json()["id"], "input": {"topic": "tabs vs spaces"}},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _parse(iso: Optional[str]) -> datetime:
    assert iso is not None and iso.endswith("+00:00")
    return datetime.fromisoformat(iso)


def test_successful_run_records_timing_and_exposes_the_summary(tmp_path):
    with _client(tmp_path, responder=lambda m, *_: "verdict" if _is_judge(m) else "argument") as client:
        created = _launch(client)
        detail = client.get(f"{API_PREFIX}/executions/{created['id']}").json()
        [listed] = client.get(f"{API_PREFIX}/executions").json()

    assert detail["status"] == "completed"
    started, finished = _parse(detail["started_at"]), _parse(detail["finished_at"])
    assert finished >= started

    [inst] = detail["instances"]
    transcript = inst["transcript"]
    assert transcript["calls"] == 3  # alice, bob, judge
    assert isinstance(transcript["duration_s"], float) and transcript["duration_s"] >= 0
    assert inst["duration_s"] == transcript["duration_s"]
    assert inst["usage"] == {
        "input_tokens": transcript["usage"]["prompt_tokens"],
        "output_tokens": transcript["usage"]["completion_tokens"],
        "total_tokens": transcript["usage"]["total_tokens"],
        "cost_usd": 0.0,
        "model_time_s": 0.0,
        "calls": 3,
    }

    summary = detail["summary"]
    assert set(summary) == {
        "wall_time_s", "model_time_s", "input_tokens", "output_tokens",
        "total_tokens", "cost_usd", "calls", "instances",
    }
    assert summary["wall_time_s"] == pytest.approx((finished - started).total_seconds())
    assert summary["input_tokens"] == transcript["usage"]["prompt_tokens"] > 0
    assert summary["output_tokens"] == transcript["usage"]["completion_tokens"] > 0
    assert summary["calls"] == 3
    assert summary["instances"] == {"total": 1, "completed": 1, "failed": 0}

    # The list carries the same summary (computed without loading transcripts).
    assert listed["summary"] == summary
    assert listed["started_at"] == detail["started_at"]
    assert "instances" not in listed


def test_failed_run_records_duration_on_the_partial_transcript(tmp_path):
    def responder(messages, *_):
        if _is_judge(messages):
            raise RuntimeError("judge offline")
        return "argument"

    with _client(tmp_path, responder=responder) as client:
        detail = _launch(client)
        [listed] = client.get(f"{API_PREFIX}/executions").json()

    assert detail["status"] == "failed"
    assert detail["started_at"] and detail["finished_at"]
    [inst] = detail["instances"]
    assert inst["error"].startswith("ExecutionError: judge node 'judge'")
    transcript = inst["transcript"]
    assert transcript["duration_s"] is not None and transcript["duration_s"] >= 0
    assert inst["duration_s"] == transcript["duration_s"]
    # The two debater turns are counted; the failed judge attempts are not.
    assert inst["usage"]["calls"] == 2
    assert detail["summary"]["calls"] == 2
    assert detail["summary"]["instances"] == {"total": 1, "completed": 0, "failed": 1}
    assert detail["summary"]["wall_time_s"] is not None
    assert listed["summary"] == detail["summary"]


def test_running_execution_reports_elapsed_wall_time(tmp_path):
    engine = create_engine_for(f"sqlite:///{tmp_path.as_posix()}/running.db")
    init_db(engine)
    maker = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with maker() as session:
        session.add(
            Execution(
                config_snapshot={"name": "x"},
                input_mode="single",
                input_ref={"input": {}},
                status="running",
                progress=0.0,
                started_at=datetime.now(timezone.utc) - timedelta(seconds=30),
            )
        )
        session.commit()
        [summary] = list_executions(session)
    assert summary.summary.wall_time_s is not None and summary.summary.wall_time_s >= 30
    assert summary.summary.instances.model_dump() == {"total": 1, "completed": 0, "failed": 0}
    assert summary.finished_at is None
    engine.dispose()


# --------------------------------------------------------------------------- #
# Migration: a schema-version-2 database gains the run timestamps
# --------------------------------------------------------------------------- #

LEGACY_TRANSCRIPT = (
    '{"config_id": "c", "config_name": "old", "resolved_input": "Debate: x", "rounds": 1,'
    ' "messages": ['
    '{"node_id": "a", "round_index": 0, "role": "debater", "content": "hi",'
    '  "usage": {"prompt_tokens": 1000, "completion_tokens": 4, "total_tokens": 1004,'
    '            "cost_usd": null, "latency_s": 0.5}},'
    '{"node_id": "j", "round_index": 1, "role": "judge", "content": "F",'
    '  "usage": {"prompt_tokens": 2000, "completion_tokens": 8, "total_tokens": 2008,'
    '            "cost_usd": null, "latency_s": 1.0}}],'
    ' "usage": {"prompt_tokens": 3000, "completion_tokens": 12, "total_tokens": 3012,'
    '           "cost_usd": null, "latency_s": 1.5},'
    ' "decision": null, "errors": [], "notes": []}'
)


def _make_v2_db(path) -> None:
    """The executions tables as they were at schema version 2."""
    conn = sqlite3.connect(path)
    conn.executescript(
        f"""
        CREATE TABLE executions (
            id INTEGER NOT NULL PRIMARY KEY,
            config_id INTEGER,
            config_snapshot JSON NOT NULL,
            input_mode VARCHAR(16) NOT NULL,
            input_ref JSON NOT NULL,
            status VARCHAR(16) NOT NULL,
            progress FLOAT NOT NULL,
            metrics JSON,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        );
        CREATE TABLE execution_instances (
            id INTEGER NOT NULL PRIMARY KEY,
            execution_id INTEGER NOT NULL REFERENCES executions (id) ON DELETE CASCADE,
            instance_index INTEGER NOT NULL,
            resolved_input JSON NOT NULL,
            transcript JSON,
            final_decision JSON,
            ground_truth TEXT,
            metrics JSON,
            error TEXT,
            CONSTRAINT uq_execution_instance_index UNIQUE (execution_id, instance_index)
        );
        CREATE TABLE schema_meta (
            key VARCHAR(64) NOT NULL PRIMARY KEY,
            value VARCHAR(256) NOT NULL
        );
        INSERT INTO executions VALUES
            (7, NULL, '{{"name": "old"}}', 'batch', '{{}}', 'partial', 1.0, NULL,
             '2024-01-01 00:00:00', '2024-01-01 00:01:00');
        INSERT INTO execution_instances VALUES
            (1, 7, 0, '{{"topic": "x"}}', '{LEGACY_TRANSCRIPT}', NULL, NULL, NULL, NULL),
            (2, 7, 1, '{{"topic": "y"}}', NULL, NULL, NULL, NULL, 'ProviderError: boom');
        INSERT INTO schema_meta (key, value) VALUES ('schema_version', '2');
        """
    )
    conn.commit()
    conn.close()


def test_v2_database_is_migrated_and_old_runs_get_token_totals(tmp_path):
    db_path = tmp_path / "v2.db"
    _make_v2_db(db_path)
    engine = create_engine_for(f"sqlite:///{db_path.as_posix()}")

    assert init_db(engine) == SCHEMA_VERSION == "3"
    columns = {c["name"] for c in inspect(engine).get_columns("executions")}
    assert {"started_at", "finished_at"} <= columns
    assert init_db(engine) == get_schema_version(engine) == "3"  # idempotent

    with sessionmaker(bind=engine)() as session:
        row = session.get(Execution, 7)
        assert row.status == "partial" and row.config_snapshot == {"name": "old"}
        assert row.started_at is None and row.finished_at is None
        assert session.query(ExecutionInstance).count() == 2
    engine.dispose()

    # Through the API: token totals from the stored transcripts, no wall time.
    settings = Settings(
        database_url=f"sqlite:///{db_path.as_posix()}",
        dataset_storage_path=str(tmp_path / "storage"),
    )
    with TestClient(create_app(settings)) as client:
        [listed] = client.get(f"{API_PREFIX}/executions").json()
        detail = client.get(f"{API_PREFIX}/executions/7").json()

    expected = {
        "wall_time_s": None,
        "model_time_s": 1.5,
        "input_tokens": 3000,
        "output_tokens": 12,
        "total_tokens": 3012,
        "cost_usd": None,
        "calls": 2,
        "instances": {"total": 2, "completed": 1, "failed": 1},
    }
    assert listed["summary"] == expected
    assert detail["summary"] == expected
    assert listed["started_at"] is None and listed["finished_at"] is None
    ok, failed = detail["instances"]
    assert ok["usage"]["calls"] == 2 and ok["duration_s"] is None
    assert failed["usage"] is None and failed["duration_s"] is None
