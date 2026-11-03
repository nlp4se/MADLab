"""Tests for OpenAIAgentManager (infrastructure adapter).

The OpenAI client is fully mocked: no network calls are made.
"""

import json
from unittest.mock import MagicMock

import httpx
import pytest
from openai import NotFoundError

from code.infrastructure.openai.openai_agent_manager import OpenAIAgentManager
from code.domain.contracts.agent_record import AgentDefinition


# ---------- helpers ----------

def _make_not_found():
    req = httpx.Request("GET", "https://api.openai.com/v1/x")
    resp = httpx.Response(404, request=req)
    return NotFoundError(message="not found", response=resp, body=None)


def _agent(model="gpt-4o", temperature=0.0):
    return AgentDefinition(
        name="myAgent",
        model=model,
        instructions="be helpful",
        temperature=temperature,
    )


@pytest.fixture
def manager():
    m = OpenAIAgentManager(api_key="test-key")
    m.client = MagicMock()
    return m


# ---------- create_agent ----------

def test_create_agent_validates_full_agent_with_openai(manager):
    manager.create_agent(_agent(model="gpt-4o", temperature=0.5))
    _, kwargs = manager.client.responses.create.call_args
    assert kwargs["model"] == "gpt-4o"
    assert kwargs["instructions"] == "be helpful"
    assert kwargs["temperature"] == 0.5
    assert kwargs["store"] is False


def test_create_agent_sends_schema_when_provided(manager, tmp_path):
    schema = {"name": "x", "schema": {"type": "object"}}
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema))
    agent = AgentDefinition(name="myAgent", model="gpt-4o", instructions="x", schema_file_path=str(schema_path))

    manager.create_agent(agent)

    _, kwargs = manager.client.responses.create.call_args
    assert kwargs["text"] == {"format": {"type": "json_schema", "strict": False, **schema}}


def test_create_agent_translates_openai_error_to_value_error(manager):
    manager.client.responses.create.side_effect = _make_not_found()
    with pytest.raises(ValueError, match="OpenAI rejected agent 'myAgent' \\(model 'gpt-4o-mni'\\)"):
        manager.create_agent(_agent(model="gpt-4o-mni"))


@pytest.mark.parametrize("temperature", [0.0, 2.0])
def test_create_agent_accepts_temperature_limits(manager, temperature):
    manager.create_agent(_agent(temperature=temperature))


@pytest.mark.parametrize("temperature", [-0.1, 2.1])
def test_create_agent_rejects_out_of_range_temperature_without_calling_openai(manager, temperature):
    with pytest.raises(ValueError, match="out of range for OpenAI"):
        manager.create_agent(_agent(temperature=temperature))
    assert manager.client.mock_calls == []


# ---------- get_model ----------

def test_get_model_returns_local_model_without_calling_openai(manager):
    assert manager.get_model(_agent(model="gpt-4o")) == "gpt-4o"
    assert manager.client.mock_calls == []


# ---------- change_model ----------

def test_change_model_validates_agent_with_new_model(manager):
    manager.change_model(_agent(model="gpt-4o", temperature=0.5), "gpt-4o-mini")
    _, kwargs = manager.client.responses.create.call_args
    assert kwargs["model"] == "gpt-4o-mini"
    assert kwargs["instructions"] == "be helpful"
    assert kwargs["temperature"] == 0.5


def test_change_model_translates_openai_error_to_value_error(manager):
    manager.client.responses.create.side_effect = _make_not_found()
    with pytest.raises(ValueError, match="OpenAI rejected agent 'myAgent' \\(model 'not-a-model'\\)"):
        manager.change_model(_agent(), "not-a-model")


# ---------- delete_agent ----------

def test_delete_agent_does_not_call_openai(manager):
    manager.delete_agent(_agent())
    assert manager.client.mock_calls == []
