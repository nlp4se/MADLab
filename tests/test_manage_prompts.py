"""Tests for the manage_prompts CLI entry point.

Pattern: patch sys.argv + monkeypatch.chdir(tmp_path) + (for create/update)
substitute sys.stdin with an in-memory StringIO. main() is called in-process.
"""

import io
import sys
import pytest

import manage_prompts


def _run_cli(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", argv)
    manage_prompts.main()


# ---------- get ----------

def test_get_prints_prompt_content(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "prompts").mkdir(parents=True)
    (tmp_path / "data" / "prompts" / "hello.txt").write_text("hi there")

    _run_cli(monkeypatch, ["manage_prompts.py", "get", "--prompt-path", "hello.txt"])

    out = capsys.readouterr().out
    assert "hi there" in out


def test_get_missing_prompt_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        _run_cli(monkeypatch, ["manage_prompts.py", "get", "--prompt-path", "absent.txt"])


# ---------- create ----------

def test_create_writes_file_from_stdin(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("new prompt content"))

    _run_cli(monkeypatch, ["manage_prompts.py", "create", "--prompt-path", "new.txt"])

    assert (tmp_path / "data" / "prompts" / "new.txt").read_text() == "new prompt content"


def test_create_with_nested_path_makes_dirs(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("deep"))

    _run_cli(monkeypatch, ["manage_prompts.py", "create", "--prompt-path", "sub/dir/x.txt"])

    assert (tmp_path / "data" / "prompts" / "sub" / "dir" / "x.txt").read_text() == "deep"


# ---------- update ----------

def test_update_replaces_existing_content(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "data" / "prompts" / "p.txt"
    target.parent.mkdir(parents=True)
    target.write_text("old text")
    monkeypatch.setattr("sys.stdin", io.StringIO("new text"))

    _run_cli(monkeypatch, ["manage_prompts.py", "update", "--prompt-path", "p.txt"])

    assert target.read_text() == "new text"
    out = capsys.readouterr().out
    # Should display the previous content before reading new content
    assert "old text" in out


def test_update_missing_prompt_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        _run_cli(monkeypatch, ["manage_prompts.py", "update", "--prompt-path", "missing.txt"])


# ---------- delete ----------

def test_delete_removes_existing_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "data" / "prompts" / "rm.txt"
    target.parent.mkdir(parents=True)
    target.write_text("bye")

    _run_cli(monkeypatch, ["manage_prompts.py", "delete", "--prompt-path", "rm.txt"])

    assert not target.exists()


def test_delete_missing_prompt_prints_message(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    _run_cli(monkeypatch, ["manage_prompts.py", "delete", "--prompt-path", "ghost.txt"])

    out = capsys.readouterr().out
    assert "did not exist" in out


# ---------- argparse errors ----------

def test_missing_prompt_path_argument_exits(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, ["manage_prompts.py", "get"])


def test_unknown_subcommand_exits(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, ["manage_prompts.py", "wat", "--prompt-path", "x"])
