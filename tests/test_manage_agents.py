"""Tests for the manage_agents CLI entry point.

Pattern:
- patch sys.argv
- monkeypatch.chdir(tmp_path) so FileAgentRecord/FilePromptRecord land in tmp
- monkeypatch manage_agents.OpenAIAgentManager to a factory returning a MagicMock
- call main() in-process
"""

import sys
from unittest.mock import MagicMock
import pytest

import manage_agents


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


# ---------- create ----------

def test_create_wires_setup_agent(monkeypatch, tmp_path, fake_external):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "prompts").mkdir(parents=True)
    (tmp_path / "data" / "prompts" / "p.txt").write_text("system instructions")
    fake_external.create_agent.return_value = "asst_nnnnnnnnnnnnnnnnnnnnnnnn"

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

    fake_external.create_agent.assert_called_once()
    args, kwargs = fake_external.create_agent.call_args
    assert args[0] == "myAgent"
    assert args[1] == "system instructions"
    assert args[2] == "gpt-4o"
    assert kwargs["temperature"] == 0.3

    # Record file was written
    rec_path = tmp_path / "data" / "agent_records" / "agent_myAgent.txt"
    assert rec_path.read_text() == "asst_nnnnnnnnnnnnnnnnnnnnnnnn"


# ---------- delete ----------

def test_delete_wires_delete_agent(monkeypatch, tmp_path, fake_external):
    monkeypatch.chdir(tmp_path)
    rec_path = tmp_path / "data" / "agent_records" / "agent_myAgent.txt"
    rec_path.parent.mkdir(parents=True)
    rec_path.write_text("asst_xxxxxxxxxxxxxxxxxxxxxxxx")

    _run_cli(
        monkeypatch,
        ["manage_agents.py", "delete", "--agent-name", "myAgent"],
        fake_external,
    )

    fake_external.delete_agent.assert_called_once_with("asst_xxxxxxxxxxxxxxxxxxxxxxxx")
    assert not rec_path.exists()


# ---------- change-model ----------

def test_change_model_wires_change_model(monkeypatch, tmp_path, fake_external, capsys):
    monkeypatch.chdir(tmp_path)
    rec_path = tmp_path / "data" / "agent_records" / "agent_myAgent.txt"
    rec_path.parent.mkdir(parents=True)
    rec_path.write_text("asst_xxxxxxxxxxxxxxxxxxxxxxxx")

    _run_cli(
        monkeypatch,
        [
            "manage_agents.py", "change-model",
            "--agent-name", "myAgent",
            "--model", "gpt-4o-mini",
        ],
        fake_external,
    )

    fake_external.change_model.assert_called_once_with("asst_xxxxxxxxxxxxxxxxxxxxxxxx", "gpt-4o-mini")
    out = capsys.readouterr().out
    assert "Model updated to 'gpt-4o-mini'" in out


# ---------- get-model ----------

def test_get_model_wires_get_model_and_prints(monkeypatch, tmp_path, fake_external, capsys):
    monkeypatch.chdir(tmp_path)
    rec_path = tmp_path / "data" / "agent_records" / "agent_myAgent.txt"
    rec_path.parent.mkdir(parents=True)
    rec_path.write_text("asst_xxxxxxxxxxxxxxxxxxxxxxxx")
    fake_external.get_model.return_value = "gpt-4o"

    _run_cli(
        monkeypatch,
        ["manage_agents.py", "get-model", "--agent-name", "myAgent"],
        fake_external,
    )

    fake_external.get_model.assert_called_once_with("asst_xxxxxxxxxxxxxxxxxxxxxxxx")
    out = capsys.readouterr().out
    assert "is using model: 'gpt-4o'" in out


# ---------- get-all ----------

def test_get_all_prints_local_record_names(monkeypatch, tmp_path, fake_external, capsys):
    monkeypatch.chdir(tmp_path)
    recs = tmp_path / "data" / "agent_records"
    recs.mkdir(parents=True)
    (recs / "agent_alice.txt").write_text("asst_aaaaaaaaaaaaaaaaaaaaaaaa")
    (recs / "agent_bob.txt").write_text("asst_bbbbbbbbbbbbbbbbbbbbbbbb")

    _run_cli(
        monkeypatch,
        ["manage_agents.py", "get-all"],
        fake_external,
    )

    out = capsys.readouterr().out
    assert "Name: alice" in out
    assert "Name: bob" in out
    # Should NOT touch OpenAI for a get-all
    fake_external.list_agents.assert_not_called()


def test_get_all_empty_prints_empty_message(monkeypatch, tmp_path, fake_external, capsys):
    monkeypatch.chdir(tmp_path)
    _run_cli(
        monkeypatch,
        ["manage_agents.py", "get-all"],
        fake_external,
    )
    out = capsys.readouterr().out
    assert "No AgentRecords were found in local storage." in out


# ---------- delete-invalid ----------

def test_delete_invalid_removes_local_records_and_skips_openai_deletion(
    monkeypatch, tmp_path, fake_external
):
    monkeypatch.chdir(tmp_path)
    recs = tmp_path / "data" / "agent_records"
    recs.mkdir(parents=True)
    (recs / "agent_alice.txt").write_text("asst_aaaaaaaaaaaaaaaaaaaaaaaa")        # valid
    (recs / "agent_bob.txt").write_text("asst_wwwwwwwwwwwwwwwwwwwwwwww")      # id mismatch
    (recs / "agent_ghost.txt").write_text("asst_gggggggggggggggggggggggg")        # name missing

    fake_external.list_agents.return_value = {
        "alice": {"asst_aaaaaaaaaaaaaaaaaaaaaaaa"},
        "bob": {"asst_bbbbbbbbbbbbbbbbbbbbbbbb"},
    }

    _run_cli(
        monkeypatch,
        ["manage_agents.py", "delete-invalid"],
        fake_external,
    )

    # Valid record stays; the other two are removed locally
    assert (recs / "agent_alice.txt").exists()
    assert not (recs / "agent_bob.txt").exists()
    assert not (recs / "agent_ghost.txt").exists()

    # OpenAI-side deletion must never happen here
    fake_external.delete_agent.assert_not_called()


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
