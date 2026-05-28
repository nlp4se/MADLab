"""Tests for FileAgentRecord (infrastructure adapter)."""

import os
import pytest

from code.infrastructure.persistence.file_agent_record import FileAgentRecord


@pytest.fixture
def agent_record(tmp_path):
    return FileAgentRecord(base_dir=str(tmp_path))


def test_get_id_returns_stored_id(agent_record, tmp_path):
    (tmp_path / "assistant_alice.txt").write_text("asst_aaaaaaaaaaaaaaaaaaaaaaaa")
    assert agent_record.get_id("alice") == "asst_aaaaaaaaaaaaaaaaaaaaaaaa"


def test_get_id_strips_whitespace(agent_record, tmp_path):
    (tmp_path / "assistant_bob.txt").write_text("  asst_bbbbbbbbbbbbbbbbbbbbbbbb  \n")
    assert agent_record.get_id("bob") == "asst_bbbbbbbbbbbbbbbbbbbbbbbb"


def test_get_id_missing_file_raises_file_not_found(agent_record):
    with pytest.raises(FileNotFoundError, match="No AgentRecord found for 'ghost'"):
        agent_record.get_id("ghost")


def test_get_id_empty_file_raises_value_error(agent_record, tmp_path):
    (tmp_path / "assistant_empty.txt").write_text("")
    with pytest.raises(ValueError, match="AgentRecord for 'empty' is empty"):
        agent_record.get_id("empty")


def test_get_id_whitespace_only_raises_value_error(agent_record, tmp_path):
    (tmp_path / "assistant_ws.txt").write_text("   \n  ")
    with pytest.raises(ValueError, match="AgentRecord for 'ws' is empty"):
        agent_record.get_id("ws")


def test_create_writes_file(agent_record, tmp_path):
    agent_record.create("newAgent", "asst_xxxxxxxxxxxxxxxxxxxxxxxx")
    assert (tmp_path / "assistant_newAgent.txt").read_text() == "asst_xxxxxxxxxxxxxxxxxxxxxxxx"


def test_create_makes_base_dir_if_missing(tmp_path):
    missing_dir = tmp_path / "does_not_exist_yet"
    record = FileAgentRecord(base_dir=str(missing_dir))
    record.create("agent1", "asst_111111111111111111111111")
    assert (missing_dir / "assistant_agent1.txt").read_text() == "asst_111111111111111111111111"


def test_create_overwrites_existing(agent_record, tmp_path):
    (tmp_path / "assistant_dup.txt").write_text("asst_oooooooooooooooooooooooo")
    agent_record.create("dup", "asst_nnnnnnnnnnnnnnnnnnnnnnnn")
    assert (tmp_path / "assistant_dup.txt").read_text() == "asst_nnnnnnnnnnnnnnnnnnnnnnnn"


def test_list_names_empty_dir_returns_empty_list(agent_record):
    assert agent_record.list_names() == []


def test_list_names_nonexistent_dir_returns_empty_list(tmp_path):
    record = FileAgentRecord(base_dir=str(tmp_path / "absent"))
    assert record.list_names() == []


def test_list_names_returns_only_matching_files(agent_record, tmp_path):
    (tmp_path / "assistant_alice.txt").write_text("asst_aaaaaaaaaaaaaaaaaaaaaaaa")
    (tmp_path / "assistant_bob.txt").write_text("asst_bbbbbbbbbbbbbbbbbbbbbbbb")
    (tmp_path / "notes.txt").write_text("ignore me")
    (tmp_path / "assistant_carol.log").write_text("also ignore")
    (tmp_path / "random_file.txt").write_text("ignore too")

    names = agent_record.list_names()
    assert sorted(names) == ["alice", "bob"]


def test_delete_existing_returns_true(agent_record, tmp_path):
    path = tmp_path / "assistant_byebye.txt"
    path.write_text("asst_yyyyyyyyyyyyyyyyyyyyyyyy")
    assert agent_record.delete("byebye") is True
    assert not path.exists()


def test_delete_missing_returns_false(agent_record):
    assert agent_record.delete("never_existed") is False
