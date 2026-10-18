"""Tests for FileAgentRecord (infrastructure adapter)."""

import json
import pytest

from code.infrastructure.persistence.file_agent_record import FileAgentRecord
from code.domain.contracts.agent_record import AgentDefinition


def _agent(name="alice", model="gpt-4o"):
    return AgentDefinition(
        name=name,
        model=model,
        instructions="be helpful",
        temperature=0.0,
        schema_file_path=None,
    )


def _write(path, agent: AgentDefinition):
    path.write_text(json.dumps({
        "name": agent.name,
        "model": agent.model,
        "instructions": agent.instructions,
        "temperature": agent.temperature,
        "schema_file_path": agent.schema_file_path,
    }))


@pytest.fixture
def agent_record(tmp_path):
    return FileAgentRecord(base_dir=str(tmp_path))


def test_get_returns_stored_definition(agent_record, tmp_path):
    _write(tmp_path / "agent_alice.json", _agent("alice"))
    assert agent_record.get("alice") == _agent("alice")


def test_get_missing_file_raises_file_not_found(agent_record):
    with pytest.raises(FileNotFoundError, match="No AgentRecord found for 'ghost'"):
        agent_record.get("ghost")


def test_get_empty_file_raises_value_error(agent_record, tmp_path):
    (tmp_path / "agent_empty.json").write_text("")
    with pytest.raises(ValueError, match="AgentRecord for 'empty' is not valid JSON"):
        agent_record.get("empty")


def test_get_whitespace_only_raises_value_error(agent_record, tmp_path):
    (tmp_path / "agent_ws.json").write_text("   \n  ")
    with pytest.raises(ValueError, match="AgentRecord for 'ws' is not valid JSON"):
        agent_record.get("ws")


def test_get_missing_or_unexpected_fields_raises_value_error(agent_record, tmp_path):
    (tmp_path / "agent_partial.json").write_text(json.dumps({"name": "partial", "unknown": 1}))
    with pytest.raises(ValueError, match="AgentRecord for 'partial' has missing or unexpected fields"):
        agent_record.get("partial")


def test_save_writes_file(agent_record, tmp_path):
    agent_record.save(_agent("newAgent"))
    stored = json.loads((tmp_path / "agent_newAgent.json").read_text())
    assert AgentDefinition(**stored) == _agent("newAgent")


def test_save_makes_base_dir_if_missing(tmp_path):
    missing_dir = tmp_path / "does_not_exist_yet"
    record = FileAgentRecord(base_dir=str(missing_dir))
    record.save(_agent("agent1"))
    assert (missing_dir / "agent_agent1.json").exists()


def test_save_overwrites_existing(agent_record, tmp_path):
    _write(tmp_path / "agent_dup.json", _agent("dup", model="gpt-4o"))
    agent_record.save(_agent("dup", model="gpt-4o-mini"))
    assert agent_record.get("dup").model == "gpt-4o-mini"


def test_list_names_empty_dir_returns_empty_list(agent_record):
    assert agent_record.list_names() == []


def test_list_names_nonexistent_dir_returns_empty_list(tmp_path):
    record = FileAgentRecord(base_dir=str(tmp_path / "absent"))
    assert record.list_names() == []


def test_list_names_returns_only_matching_files(agent_record, tmp_path):
    _write(tmp_path / "agent_alice.json", _agent("alice"))
    _write(tmp_path / "agent_bob.json", _agent("bob"))
    (tmp_path / "agent_legacy.txt").write_text("asst_llllllllllllllllllllllll")  # old format is ignored
    (tmp_path / "notes.json").write_text("{}")
    (tmp_path / "agent_carol.log").write_text("also ignore")
    (tmp_path / "random_file.txt").write_text("ignore too")

    names = agent_record.list_names()
    assert sorted(names) == ["alice", "bob"]


def test_delete_existing_returns_true(agent_record, tmp_path):
    path = tmp_path / "agent_byebye.json"
    _write(path, _agent("byebye"))
    assert agent_record.delete("byebye") is True
    assert not path.exists()


def test_delete_missing_returns_false(agent_record):
    assert agent_record.delete("never_existed") is False
