"""Tests for AgentManager (core orchestration).

All three ports (ExternalAgentManager, AgentRecord, PromptRecord) are mocked.
"""

from unittest.mock import MagicMock, call
import pytest

from code.core.agent_manager import AgentManager


@pytest.fixture
def ports():
    external = MagicMock()
    agent_rec = MagicMock()
    prompt_rec = MagicMock()
    return external, agent_rec, prompt_rec


@pytest.fixture
def manager(ports):
    external, agent_rec, prompt_rec = ports
    return AgentManager(
        assistant_name="myAgent",
        external_manager=external,
        agent_record=agent_rec,
        prompt_record=prompt_rec,
    )


# ---------- setup_assistant ----------

def test_setup_assistant_orchestration_order(manager, ports):
    external, agent_rec, prompt_rec = ports
    prompt_rec.get.return_value = "system instructions"
    external.create_assistant.return_value = "asst_new"

    parent = MagicMock()
    parent.attach_mock(prompt_rec, "prompt_rec")
    parent.attach_mock(external, "external")
    parent.attach_mock(agent_rec, "agent_rec")

    manager.setup_assistant(prompt_path="p.txt", model="gpt-4o", temperature=0.5)

    expected = [
        call.prompt_rec.get("p.txt"),
        call.external.create_assistant("myAgent", "system instructions", "gpt-4o", temperature=0.5),
        call.agent_rec.create("myAgent", "asst_new"),
    ]
    assert parent.mock_calls == expected


# ---------- get_model ----------

def test_get_model_looks_up_id_then_delegates(manager, ports):
    external, agent_rec, _ = ports
    agent_rec.get_id.return_value = "asst_xyz"
    external.get_model.return_value = "gpt-4o"

    assert manager.get_model() == "gpt-4o"
    agent_rec.get_id.assert_called_once_with("myAgent")
    external.get_model.assert_called_once_with("asst_xyz")


# ---------- change_model ----------

def test_change_model_looks_up_id_then_delegates(manager, ports):
    external, agent_rec, _ = ports
    agent_rec.get_id.return_value = "asst_xyz"

    manager.change_model("gpt-4o-mini")

    agent_rec.get_id.assert_called_once_with("myAgent")
    external.change_model.assert_called_once_with("asst_xyz", "gpt-4o-mini")


# ---------- delete_assistant ----------

def test_delete_assistant_orchestration_order(manager, ports):
    external, agent_rec, prompt_rec = ports
    agent_rec.get_id.return_value = "asst_xyz"

    parent = MagicMock()
    parent.attach_mock(agent_rec, "agent_rec")
    parent.attach_mock(external, "external")

    manager.delete_assistant()

    expected = [
        call.agent_rec.get_id("myAgent"),
        call.external.delete_assistant("asst_xyz"),
        call.agent_rec.delete("myAgent"),
    ]
    assert parent.mock_calls == expected


# ---------- list_agent_records ----------

def test_list_agent_records_prints_names(manager, ports, capsys):
    _, agent_rec, _ = ports
    agent_rec.list_names.return_value = ["alice", "bob"]

    manager.list_agent_records()

    out = capsys.readouterr().out
    assert "AgentRecords:" in out
    assert "Name: alice" in out
    assert "Name: bob" in out


def test_list_agent_records_prints_empty_message_when_none(manager, ports, capsys):
    _, agent_rec, _ = ports
    agent_rec.list_names.return_value = []

    manager.list_agent_records()

    out = capsys.readouterr().out
    assert "No AgentRecords were found in local storage." in out


# ---------- delete_invalid_agent_records ----------

def _stub_agent_record(local_records: dict):
    """Build an AgentRecord mock from a {name: id} dict."""
    rec = MagicMock()
    rec.list_names.return_value = list(local_records.keys())
    rec.get_id.side_effect = lambda name: local_records[name]
    return rec


def _stub_external(openai_state: dict):
    """Build an ExternalAgentManager mock from a {name: set(ids)} dict."""
    ext = MagicMock()
    ext.list_assistants.return_value = openai_state
    return ext


def test_delete_invalid_all_valid_deletes_nothing():
    external = _stub_external({"alice": {"asst_a"}, "bob": {"asst_b"}})
    agent_rec = _stub_agent_record({"alice": "asst_a", "bob": "asst_b"})
    mgr = AgentManager("any", external, agent_rec, MagicMock())

    mgr.delete_invalid_agent_records()

    agent_rec.delete.assert_not_called()


def test_delete_invalid_when_name_missing_in_openai(capsys):
    external = _stub_external({"alice": {"asst_a"}})
    agent_rec = _stub_agent_record({"alice": "asst_a", "ghost": "asst_g"})
    mgr = AgentManager("any", external, agent_rec, MagicMock())

    mgr.delete_invalid_agent_records()

    agent_rec.delete.assert_called_once_with("ghost")
    out = capsys.readouterr().out
    assert "name not found in OpenAI" in out
    assert "ghost" in out


def test_delete_invalid_when_id_mismatches(capsys):
    external = _stub_external({"alice": {"asst_a_correct"}})
    agent_rec = _stub_agent_record({"alice": "asst_a_wrong"})
    mgr = AgentManager("any", external, agent_rec, MagicMock())

    mgr.delete_invalid_agent_records()

    agent_rec.delete.assert_called_once_with("alice")
    out = capsys.readouterr().out
    assert "stored ID does not match" in out
    assert "alice" in out


def test_delete_invalid_keeps_record_when_id_matches_one_of_duplicate_names():
    # OpenAI has two assistants named "alice" with different ids; local record
    # holds one of those ids → must be kept.
    external = _stub_external({"alice": {"asst_a1", "asst_a2"}})
    agent_rec = _stub_agent_record({"alice": "asst_a2"})
    mgr = AgentManager("any", external, agent_rec, MagicMock())

    mgr.delete_invalid_agent_records()

    agent_rec.delete.assert_not_called()


def test_delete_invalid_deletes_when_id_matches_none_of_duplicate_names():
    external = _stub_external({"alice": {"asst_a1", "asst_a2"}})
    agent_rec = _stub_agent_record({"alice": "asst_a_none_of_those"})
    mgr = AgentManager("any", external, agent_rec, MagicMock())

    mgr.delete_invalid_agent_records()

    agent_rec.delete.assert_called_once_with("alice")


def test_delete_invalid_mixed_categories(capsys):
    external = _stub_external({"alice": {"asst_a"}, "bob": {"asst_b"}})
    agent_rec = _stub_agent_record({
        "alice": "asst_a",          # valid
        "bob": "asst_wrong",        # id mismatch
        "ghost": "asst_g",          # name missing
    })
    mgr = AgentManager("any", external, agent_rec, MagicMock())

    mgr.delete_invalid_agent_records()

    deleted_names = {c.args[0] for c in agent_rec.delete.call_args_list}
    assert deleted_names == {"bob", "ghost"}

    out = capsys.readouterr().out
    # "name not found" section should mention ghost (not bob)
    name_section, id_section = out.split("stored ID does not match")
    assert "ghost" in name_section
    assert "bob" in id_section


def test_delete_invalid_never_calls_external_delete():
    """delete-invalid is local-only: OpenAI-side assistants must not be touched."""
    external = _stub_external({"alice": {"asst_a"}})
    agent_rec = _stub_agent_record({"alice": "asst_wrong", "ghost": "asst_g"})
    mgr = AgentManager("any", external, agent_rec, MagicMock())

    mgr.delete_invalid_agent_records()

    external.delete_assistant.assert_not_called()
