"""Tests for FilePromptRecord (infrastructure adapter)."""

import os
import pytest

from code.infrastructure.persistence.file_prompt_record import FilePromptRecord


@pytest.fixture
def prompt_record(tmp_path):
    return FilePromptRecord(base_dir=str(tmp_path))


def test_get_returns_content(prompt_record, tmp_path):
    (tmp_path / "hello.txt").write_text("hello world")
    assert prompt_record.get("hello.txt") == "hello world"


def test_get_missing_file_raises_file_not_found(prompt_record):
    with pytest.raises(FileNotFoundError, match="Prompt file not found"):
        prompt_record.get("missing.txt")


def test_get_empty_file_raises_value_error(prompt_record, tmp_path):
    (tmp_path / "empty.txt").write_text("")
    with pytest.raises(ValueError, match="Prompt file is empty"):
        prompt_record.get("empty.txt")


def test_get_whitespace_only_file_raises_value_error(prompt_record, tmp_path):
    (tmp_path / "ws.txt").write_text("   \n\t  ")
    with pytest.raises(ValueError, match="Prompt file is empty"):
        prompt_record.get("ws.txt")


def test_create_writes_file(prompt_record, tmp_path):
    prompt_record.create("new.txt", "content here")
    assert (tmp_path / "new.txt").read_text() == "content here"


def test_create_with_nested_path_creates_parent_dirs(prompt_record, tmp_path):
    prompt_record.create("nested/dir/file.txt", "deep content")
    assert (tmp_path / "nested" / "dir" / "file.txt").read_text() == "deep content"


def test_create_overwrites_existing_file(prompt_record, tmp_path):
    (tmp_path / "x.txt").write_text("old")
    prompt_record.create("x.txt", "new")
    assert (tmp_path / "x.txt").read_text() == "new"


def test_update_replaces_content(prompt_record, tmp_path):
    (tmp_path / "f.txt").write_text("old content")
    prompt_record.update("f.txt", "fresh content")
    assert (tmp_path / "f.txt").read_text() == "fresh content"


def test_update_missing_file_raises_file_not_found(prompt_record):
    with pytest.raises(FileNotFoundError, match="Prompt file not found"):
        prompt_record.update("nope.txt", "anything")


def test_update_rejects_empty_content(prompt_record, tmp_path):
    (tmp_path / "p.txt").write_text("original")
    with pytest.raises(ValueError, match="Cannot update prompt with empty content"):
        prompt_record.update("p.txt", "")
    assert (tmp_path / "p.txt").read_text() == "original"


def test_update_rejects_whitespace_only_content(prompt_record, tmp_path):
    (tmp_path / "p.txt").write_text("original")
    with pytest.raises(ValueError, match="Cannot update prompt with empty content"):
        prompt_record.update("p.txt", "   \n\t  ")
    assert (tmp_path / "p.txt").read_text() == "original"


def test_delete_existing_returns_true(prompt_record, tmp_path):
    path = tmp_path / "rm.txt"
    path.write_text("bye")
    assert prompt_record.delete("rm.txt") is True
    assert not path.exists()


def test_delete_missing_returns_false(prompt_record):
    assert prompt_record.delete("ghost.txt") is False
