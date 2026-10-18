"""Tests for OpenAIAgentManager (infrastructure adapter).

The OpenAI client is fully mocked: no network calls are made.
"""

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

def test_create_agent_validates_model_with_openai(manager):
    manager.create_agent(_agent(model="gpt-4o"))
    manager.client.models.retrieve.assert_called_once_with("gpt-4o")


def test_create_agent_translates_not_found_model_to_value_error(manager):
    manager.client.models.retrieve.side_effect = _make_not_found()
    with pytest.raises(ValueError, match="OpenAI model 'gpt-4o-mni' does not exist"):
        manager.create_agent(_agent(model="gpt-4o-mni"))


@pytest.mark.parametrize("temperature", [0.0, 2.0])
def test_create_agent_accepts_temperature_limits(manager, temperature):
    manager.create_agent(_agent(temperature=temperature))


@pytest.mark.parametrize("temperature", [-0.1, 2.1])
def test_create_agent_rejects_out_of_range_temperature(manager, temperature):
    with pytest.raises(ValueError, match="out of range for OpenAI"):
        manager.create_agent(_agent(temperature=temperature))


# ---------- get_model ----------

def test_get_model_returns_local_model_without_calling_openai(manager):
    assert manager.get_model(_agent(model="gpt-4o")) == "gpt-4o"
    assert manager.client.mock_calls == []


# ---------- change_model ----------

def test_change_model_validates_new_model(manager):
    manager.change_model(_agent(model="gpt-4o"), "gpt-4o-mini")
    manager.client.models.retrieve.assert_called_once_with("gpt-4o-mini")


def test_change_model_translates_not_found_to_value_error(manager):
    manager.client.models.retrieve.side_effect = _make_not_found()
    with pytest.raises(ValueError, match="does not exist or is not accessible"):
        manager.change_model(_agent(), "not-a-model")


# ---------- delete_agent ----------

def test_delete_agent_does_not_call_openai(manager):
    manager.delete_agent(_agent())
    assert manager.client.mock_calls == []
