"""Tests for OpenAIAgentManager (infrastructure adapter).

The OpenAI client is fully mocked: no network calls are made.
"""

import json
from unittest.mock import MagicMock

import httpx
import pytest
from openai import NotFoundError, BadRequestError

from code.infrastructure.openai.openai_agent_manager import OpenAIAgentManager


# ---------- helpers ----------

def _make_not_found():
    req = httpx.Request("GET", "https://api.openai.com/v1/x")
    resp = httpx.Response(404, request=req)
    return NotFoundError(message="not found", response=resp, body=None)


def _make_bad_request(code: str):
    req = httpx.Request("GET", "https://api.openai.com/v1/x")
    resp = httpx.Response(400, request=req)
    err = BadRequestError(message="bad", response=resp, body=None)
    err.code = code
    return err


@pytest.fixture
def manager():
    m = OpenAIAgentManager(api_key="test-key")
    m.client = MagicMock()
    return m


# ---------- create_agent ----------

def test_create_agent_calls_openai_and_returns_id(manager):
    fake_assistant = MagicMock()
    fake_assistant.id = "asst_aaaaaaaaaaaaaaaaaaaaaaaa"
    manager.client.beta.assistants.create.return_value = fake_assistant

    returned = manager.create_agent(
        name="myAgent",
        instructions="be helpful",
        model="gpt-4o",
        temperature=0.7,
    )

    assert returned == "asst_aaaaaaaaaaaaaaaaaaaaaaaa"
    manager.client.beta.assistants.create.assert_called_once_with(
        name="myAgent",
        instructions="be helpful",
        model="gpt-4o",
        temperature=0.7,
        response_format=None,
    )


def test_create_agent_loads_schema_when_provided(manager, tmp_path):
    schema = {"name": "x", "schema": {"type": "object"}}
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema))

    fake_assistant = MagicMock()
    fake_assistant.id = "asst_ssssssssssssssssssssssss"
    manager.client.beta.assistants.create.return_value = fake_assistant

    manager.create_agent(
        name="schemaAgent",
        instructions="x",
        model="gpt-4o",
        schema_file_path=str(schema_path),
    )

    _, kwargs = manager.client.beta.assistants.create.call_args
    assert kwargs["response_format"] == {
        "type": "json_schema",
        "json_schema": schema,
    }


def test_create_agent_defaults_temperature_to_zero(manager):
    fake_assistant = MagicMock()
    fake_assistant.id = "asst_dddddddddddddddddddddddd"
    manager.client.beta.assistants.create.return_value = fake_assistant

    manager.create_agent(name="x", instructions="x", model="gpt-4o")

    _, kwargs = manager.client.beta.assistants.create.call_args
    assert kwargs["temperature"] == 0.0


# ---------- get_model ----------

def test_get_model_returns_model_from_openai(manager):
    fake_assistant = MagicMock()
    fake_assistant.model = "gpt-4o"
    manager.client.beta.assistants.retrieve.return_value = fake_assistant

    assert manager.get_model("asst_aaaaaaaaaaaaaaaaaaaaaaaa") == "gpt-4o"
    manager.client.beta.assistants.retrieve.assert_called_once_with("asst_aaaaaaaaaaaaaaaaaaaaaaaa")


def test_get_model_translates_not_found_to_value_error(manager):
    manager.client.beta.assistants.retrieve.side_effect = _make_not_found()
    with pytest.raises(ValueError, match="AgentRecord may be stale"):
        manager.get_model("asst_mmmmmmmmmmmmmmmmmmmmmmmm")


# ---------- change_model ----------

def test_change_model_calls_openai_update(manager):
    manager.change_model("asst_xxxxxxxxxxxxxxxxxxxxxxxx", "gpt-4o-mini")
    manager.client.beta.assistants.update.assert_called_once_with(
        "asst_xxxxxxxxxxxxxxxxxxxxxxxx", model="gpt-4o-mini"
    )


def test_change_model_translates_not_found_to_value_error(manager):
    manager.client.beta.assistants.update.side_effect = _make_not_found()
    with pytest.raises(ValueError, match="AgentRecord may be stale"):
        manager.change_model("asst_mmmmmmmmmmmmmmmmmmmmmmmm", "gpt-4o")


# ---------- delete_agent ----------

def test_delete_agent_calls_openai_delete(manager):
    manager.delete_agent("asst_xxxxxxxxxxxxxxxxxxxxxxxx")
    manager.client.beta.assistants.delete.assert_called_once_with("asst_xxxxxxxxxxxxxxxxxxxxxxxx")


def test_delete_agent_translates_not_found_to_value_error(manager):
    manager.client.beta.assistants.delete.side_effect = _make_not_found()
    with pytest.raises(ValueError, match="AgentRecord may be stale"):
        manager.delete_agent("asst_mmmmmmmmmmmmmmmmmmmmmmmm")


def test_delete_agent_translates_invalid_value_bad_request_to_value_error(manager):
    manager.client.beta.assistants.delete.side_effect = _make_bad_request("invalid_value")
    with pytest.raises(ValueError, match="invalid OpenAI Assistant ID"):
        # Intentionally malformed: missing 'asst_' prefix and wrong length.
        manager.delete_agent("not_a_valid_openai_id")


def test_delete_agent_reraises_other_bad_requests(manager):
    other = _make_bad_request("some_other_code")
    manager.client.beta.assistants.delete.side_effect = other
    with pytest.raises(BadRequestError):
        manager.delete_agent("asst_xxxxxxxxxxxxxxxxxxxxxxxx")


# ---------- list_agents ----------

def _make_page(assistants, has_next=False, next_page=None):
    page = MagicMock()
    page.data = assistants
    page.has_next_page.return_value = has_next
    if next_page is not None:
        page.get_next_page.return_value = next_page
    return page


def _fake_assistant(name, asst_id):
    a = MagicMock()
    a.name = name
    a.id = asst_id
    return a


def test_list_agents_single_page(manager):
    page = _make_page([
        _fake_assistant("alice", "asst_aaaaaaaaaaaaaaaaaaaaaaaa"),
        _fake_assistant("bob", "asst_bbbbbbbbbbbbbbbbbbbbbbbb"),
    ], has_next=False)
    manager.client.beta.assistants.list.return_value = page

    result = manager.list_agents()
    assert result == {"alice": {"asst_aaaaaaaaaaaaaaaaaaaaaaaa"}, "bob": {"asst_bbbbbbbbbbbbbbbbbbbbbbbb"}}


def test_list_agents_paginates(manager):
    page2 = _make_page([_fake_assistant("carol", "asst_cccccccccccccccccccccccc")], has_next=False)
    page1 = _make_page(
        [_fake_assistant("alice", "asst_aaaaaaaaaaaaaaaaaaaaaaaa")],
        has_next=True,
        next_page=page2,
    )
    manager.client.beta.assistants.list.return_value = page1

    result = manager.list_agents()
    assert result == {"alice": {"asst_aaaaaaaaaaaaaaaaaaaaaaaa"}, "carol": {"asst_cccccccccccccccccccccccc"}}


def test_list_agents_groups_duplicate_names_into_set(manager):
    page = _make_page([
        _fake_assistant("alice", "asst_aaaaaaaaaaaaaaaaaaaaaaaa"),
        _fake_assistant("alice", "asst_bbbbbbbbbbbbbbbbbbbbbbbb"),
        _fake_assistant("bob", "asst_cccccccccccccccccccccccc"),
    ], has_next=False)
    manager.client.beta.assistants.list.return_value = page

    result = manager.list_agents()
    assert result == {"alice": {"asst_aaaaaaaaaaaaaaaaaaaaaaaa", "asst_bbbbbbbbbbbbbbbbbbbbbbbb"}, "bob": {"asst_cccccccccccccccccccccccc"}}
