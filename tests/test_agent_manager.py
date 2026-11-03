"""Tests for AgentManager (core orchestration).

All three ports (ExternalAgentManager, AgentRecord, PromptRecord) are mocked.
"""

from unittest.mock import MagicMock, call
import pytest

from code.domain.agent_manager import AgentManager
from code.domain.contracts.agent_record import AgentDefinition


AGENT = AgentDefinition(
    name="myAgent",
    model="gpt-4o",
    instructions="system instructions",
    temperature=0.5,
    schema_file_path=None,
)


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
        agent_name="myAgent",
        external_manager=external,
        agent_record=agent_rec,
        prompt_record=prompt_rec,
    )


# ---------- setup_agent ----------

def test_setup_agent_orchestration_order(manager, ports):
    external, agent_rec, prompt_rec = ports
    prompt_rec.get.return_value = "system instructions"

    parent = MagicMock()
    parent.attach_mock(prompt_rec, "prompt_rec")
    parent.attach_mock(external, "external")
    parent.attach_mock(agent_rec, "agent_rec")

    manager.setup_agent(prompt_path="p.txt", model="gpt-4o", temperature=0.5)

    expected = [
        call.prompt_rec.get("p.txt"),
        call.external.create_agent(AGENT),
        call.agent_rec.save(AGENT),
    ]
    assert parent.mock_calls == expected


def test_setup_agent_does_not_save_when_validation_fails(manager, ports):
    external, agent_rec, prompt_rec = ports
    prompt_rec.get.return_value = "system instructions"
    external.create_agent.side_effect = ValueError("invalid model")

    with pytest.raises(ValueError, match="invalid model"):
        manager.setup_agent(prompt_path="p.txt", model="gpt-4o", temperature=0.5)

    agent_rec.save.assert_not_called()


# ---------- get_model ----------

def test_get_model_looks_up_definition_then_delegates(manager, ports):
    external, agent_rec, _ = ports
    agent_rec.get.return_value = AGENT
    external.get_model.return_value = "gpt-4o"

    assert manager.get_model() == "gpt-4o"
    agent_rec.get.assert_called_once_with("myAgent")
    external.get_model.assert_called_once_with(AGENT)


# ---------- change_model ----------

def test_change_model_looks_up_definition_then_delegates_and_saves(manager, ports):
    external, agent_rec, _ = ports
    agent_rec.get.return_value = AGENT

    parent = MagicMock()
    parent.attach_mock(agent_rec, "agent_rec")
    parent.attach_mock(external, "external")

    manager.change_model("gpt-4o-mini")

    expected = [
        call.agent_rec.get("myAgent"),
        call.external.change_model(AGENT, "gpt-4o-mini"),
        call.agent_rec.save(AgentDefinition(
            name="myAgent",
            model="gpt-4o-mini",
            instructions="system instructions",
            temperature=0.5,
            schema_file_path=None,
        )),
    ]
    assert parent.mock_calls == expected


def test_change_model_does_not_save_when_validation_fails(manager, ports):
    external, agent_rec, _ = ports
    agent_rec.get.return_value = AGENT
    external.change_model.side_effect = ValueError("invalid model")

    with pytest.raises(ValueError, match="invalid model"):
        manager.change_model("not-a-model")

    agent_rec.save.assert_not_called()


# ---------- delete_agent ----------

def test_delete_agent_orchestration_order(manager, ports):
    external, agent_rec, prompt_rec = ports
    agent_rec.get.return_value = AGENT

    parent = MagicMock()
    parent.attach_mock(agent_rec, "agent_rec")
    parent.attach_mock(external, "external")

    manager.delete_agent()

    expected = [
        call.agent_rec.get("myAgent"),
        call.external.delete_agent(AGENT),
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
