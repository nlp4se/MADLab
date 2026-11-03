"""Tests for the manage_agents CLI entry point.

Pattern:
- patch sys.argv
- monkeypatch.chdir(tmp_path) so FileAgentRecord/FilePromptRecord land in tmp
- monkeypatch manage_agents.OpenAIAgentManager to a factory returning a MagicMock
- call main() in-process
"""

import sys
import json
from unittest.mock import MagicMock
import pytest

import manage_agents
from code.domain.contracts.agent_record import AgentDefinition


AGENT = AgentDefinition(
    name="myAgent",
    model="gpt-4o",
    instructions="system instructions",
    temperature=0.0,
    schema_file_path=None,
)


@pytest.fixture
def fake_external():
    """A MagicMock that replaces OpenAIAgentManager. The factory swap is set up
    per-test inside _run_cli to ensure isolation."""
    return MagicMock()


def _run_cli(monkeypatch, argv, fake_external):
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(
        manage_agents,
        "OpenAIAgentManager",
        lambda api_key: fake_external,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    manage_agents.main()


def _write_record(tmp_path, agent: AgentDefinition):
    rec_path = tmp_path / "data" / "agent_records" / f"agent_{agent.name}.json"
    rec_path.parent.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps({
        "name": agent.name,
        "model": agent.model,
        "instructions": agent.instructions,
        "temperature": agent.temperature,
        "schema_file_path": agent.schema_file_path,
    }))
    return rec_path


# ---------- create ----------

def test_create_wires_setup_agent(monkeypatch, tmp_path, fake_external):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "prompts").mkdir(parents=True)
    (tmp_path / "data" / "prompts" / "p.txt").write_text("system instructions")

    _run_cli(
        monkeypatch,
        [
            "manage_agents.py", "create",
            "--agent-name", "myAgent",
            "--prompt-path", "p.txt",
            "--model", "gpt-4o",
            "--temperature", "0.3",
        ],
        fake_external,
    )

    expected = AgentDefinition(
        name="myAgent",
        model="gpt-4o",
        instructions="system instructions",
        temperature=0.3,
        schema_file_path=None,
    )
    fake_external.create_agent.assert_called_once_with(expected)

    # Record file was written
    rec_path = tmp_path / "data" / "agent_records" / "agent_myAgent.json"
    assert AgentDefinition(**json.loads(rec_path.read_text())) == expected


# ---------- delete ----------

def test_delete_wires_delete_agent(monkeypatch, tmp_path, fake_external):
    monkeypatch.chdir(tmp_path)
    rec_path = _write_record(tmp_path, AGENT)

    _run_cli(
        monkeypatch,
        ["manage_agents.py", "delete", "--agent-name", "myAgent"],
        fake_external,
    )

    fake_external.delete_agent.assert_called_once_with(AGENT)
    assert not rec_path.exists()


# ---------- change-model ----------

def test_change_model_wires_change_model(monkeypatch, tmp_path, fake_external, capsys):
    monkeypatch.chdir(tmp_path)
    rec_path = _write_record(tmp_path, AGENT)

    _run_cli(
        monkeypatch,
        [
            "manage_agents.py", "change-model",
            "--agent-name", "myAgent",
            "--model", "gpt-4o-mini",
        ],
        fake_external,
    )

    fake_external.change_model.assert_called_once_with(AGENT, "gpt-4o-mini")
    assert json.loads(rec_path.read_text())["model"] == "gpt-4o-mini"
    out = capsys.readouterr().out
    assert "Model updated to 'gpt-4o-mini'" in out


# ---------- get-model ----------

def test_get_model_wires_get_model_and_prints(monkeypatch, tmp_path, fake_external, capsys):
    monkeypatch.chdir(tmp_path)
    _write_record(tmp_path, AGENT)
    fake_external.get_model.return_value = "gpt-4o"

    _run_cli(
        monkeypatch,
        ["manage_agents.py", "get-model", "--agent-name", "myAgent"],
        fake_external,
    )

    fake_external.get_model.assert_called_once_with(AGENT)
    out = capsys.readouterr().out
    assert "is using model: 'gpt-4o'" in out


# ---------- get-all ----------

def test_get_all_prints_local_record_names(monkeypatch, tmp_path, fake_external, capsys):
    monkeypatch.chdir(tmp_path)
    _write_record(tmp_path, AgentDefinition(name="alice", model="gpt-4o", instructions="x"))
    _write_record(tmp_path, AgentDefinition(name="bob", model="gpt-4o", instructions="x"))

    _run_cli(
        monkeypatch,
        ["manage_agents.py", "get-all"],
        fake_external,
    )

    out = capsys.readouterr().out
    assert "Name: alice" in out
    assert "Name: bob" in out
    # Should NOT touch the provider for a get-all
    assert fake_external.mock_calls == []


def test_get_all_empty_prints_empty_message(monkeypatch, tmp_path, fake_external, capsys):
    monkeypatch.chdir(tmp_path)
    _run_cli(
        monkeypatch,
        ["manage_agents.py", "get-all"],
        fake_external,
    )
    out = capsys.readouterr().out
    assert "No AgentRecords were found in local storage." in out


# ---------- argparse errors ----------

def test_missing_agent_name_for_delete_exits(monkeypatch, tmp_path, fake_external):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _run_cli(
            monkeypatch,
            ["manage_agents.py", "delete"],
            fake_external,
        )


def test_unknown_subcommand_exits(monkeypatch, tmp_path, fake_external):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _run_cli(
            monkeypatch,
            ["manage_agents.py", "bogus"],
            fake_external,
        )
