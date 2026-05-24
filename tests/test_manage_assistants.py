"""Tests for the manage_assistants CLI entry point.

Pattern:
- patch sys.argv
- monkeypatch.chdir(tmp_path) so FileAgentRecord/FilePromptRecord land in tmp
- monkeypatch manage_assistants.OpenAIAgentManager to a factory returning a MagicMock
- call main() in-process
"""

import sys
from unittest.mock import MagicMock
import pytest

import manage_assistants


@pytest.fixture
def fake_external():
    """A MagicMock that replaces OpenAIAgentManager. The factory swap is set up
    per-test inside _run_cli to ensure isolation."""
    return MagicMock()


def _run_cli(monkeypatch, argv, fake_external):
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(
        manage_assistants,
        "OpenAIAgentManager",
        lambda api_key: fake_external,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    manage_assistants.main()


# ---------- create ----------

def test_create_wires_setup_assistant(monkeypatch, tmp_path, fake_external):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "prompts").mkdir(parents=True)
    (tmp_path / "data" / "prompts" / "p.txt").write_text("system instructions")
    fake_external.create_assistant.return_value = "asst_new"

    _run_cli(
        monkeypatch,
        [
            "manage_assistants.py", "create",
            "--assistant-name", "myAgent",
            "--prompt-path", "p.txt",
            "--model", "gpt-4o",
            "--temperature", "0.3",
        ],
        fake_external,
    )

    fake_external.create_assistant.assert_called_once()
    args, kwargs = fake_external.create_assistant.call_args
    assert args[0] == "myAgent"
    assert args[1] == "system instructions"
    assert args[2] == "gpt-4o"
    assert kwargs["temperature"] == 0.3

    # Record file was written
    rec_path = tmp_path / "data" / "assistant_records" / "assistant_myAgent.txt"
    assert rec_path.read_text() == "asst_new"


# ---------- delete ----------

def test_delete_wires_delete_assistant(monkeypatch, tmp_path, fake_external):
    monkeypatch.chdir(tmp_path)
    rec_path = tmp_path / "data" / "assistant_records" / "assistant_myAgent.txt"
    rec_path.parent.mkdir(parents=True)
    rec_path.write_text("asst_xyz")

    _run_cli(
        monkeypatch,
        ["manage_assistants.py", "delete", "--assistant-name", "myAgent"],
        fake_external,
    )

    fake_external.delete_assistant.assert_called_once_with("asst_xyz")
    assert not rec_path.exists()


# ---------- change-model ----------

def test_change_model_wires_change_model(monkeypatch, tmp_path, fake_external, capsys):
    monkeypatch.chdir(tmp_path)
    rec_path = tmp_path / "data" / "assistant_records" / "assistant_myAgent.txt"
    rec_path.parent.mkdir(parents=True)
    rec_path.write_text("asst_xyz")

    _run_cli(
        monkeypatch,
        [
            "manage_assistants.py", "change-model",
            "--assistant-name", "myAgent",
            "--model", "gpt-4o-mini",
        ],
        fake_external,
    )

    fake_external.change_model.assert_called_once_with("asst_xyz", "gpt-4o-mini")
    out = capsys.readouterr().out
    assert "Model updated to 'gpt-4o-mini'" in out


# ---------- get-model ----------

def test_get_model_wires_get_model_and_prints(monkeypatch, tmp_path, fake_external, capsys):
    monkeypatch.chdir(tmp_path)
    rec_path = tmp_path / "data" / "assistant_records" / "assistant_myAgent.txt"
    rec_path.parent.mkdir(parents=True)
    rec_path.write_text("asst_xyz")
    fake_external.get_model.return_value = "gpt-4o"

    _run_cli(
        monkeypatch,
        ["manage_assistants.py", "get-model", "--assistant-name", "myAgent"],
        fake_external,
    )

    fake_external.get_model.assert_called_once_with("asst_xyz")
    out = capsys.readouterr().out
    assert "is using model: 'gpt-4o'" in out


# ---------- get-all ----------

def test_get_all_prints_local_record_names(monkeypatch, tmp_path, fake_external, capsys):
    monkeypatch.chdir(tmp_path)
    recs = tmp_path / "data" / "assistant_records"
    recs.mkdir(parents=True)
    (recs / "assistant_alice.txt").write_text("asst_a")
    (recs / "assistant_bob.txt").write_text("asst_b")

    _run_cli(
        monkeypatch,
        ["manage_assistants.py", "get-all"],
        fake_external,
    )

    out = capsys.readouterr().out
    assert "Name: alice" in out
    assert "Name: bob" in out
    # Should NOT touch OpenAI for a get-all
    fake_external.list_assistants.assert_not_called()


def test_get_all_empty_prints_empty_message(monkeypatch, tmp_path, fake_external, capsys):
    monkeypatch.chdir(tmp_path)
    _run_cli(
        monkeypatch,
        ["manage_assistants.py", "get-all"],
        fake_external,
    )
    out = capsys.readouterr().out
    assert "No AgentRecords were found in local storage." in out


# ---------- delete-invalid ----------

def test_delete_invalid_removes_local_records_and_skips_openai_deletion(
    monkeypatch, tmp_path, fake_external
):
    monkeypatch.chdir(tmp_path)
    recs = tmp_path / "data" / "assistant_records"
    recs.mkdir(parents=True)
    (recs / "assistant_alice.txt").write_text("asst_a")        # valid
    (recs / "assistant_bob.txt").write_text("asst_wrong")      # id mismatch
    (recs / "assistant_ghost.txt").write_text("asst_g")        # name missing

    fake_external.list_assistants.return_value = {
        "alice": {"asst_a"},
        "bob": {"asst_b"},
    }

    _run_cli(
        monkeypatch,
        ["manage_assistants.py", "delete-invalid"],
        fake_external,
    )

    # Valid record stays; the other two are removed locally
    assert (recs / "assistant_alice.txt").exists()
    assert not (recs / "assistant_bob.txt").exists()
    assert not (recs / "assistant_ghost.txt").exists()

    # OpenAI-side deletion must never happen here
    fake_external.delete_assistant.assert_not_called()


# ---------- argparse errors ----------

def test_missing_assistant_name_for_delete_exits(monkeypatch, tmp_path, fake_external):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _run_cli(
            monkeypatch,
            ["manage_assistants.py", "delete"],
            fake_external,
        )


def test_unknown_subcommand_exits(monkeypatch, tmp_path, fake_external):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _run_cli(
            monkeypatch,
            ["manage_assistants.py", "bogus"],
            fake_external,
        )
