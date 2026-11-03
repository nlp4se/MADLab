"""Unit tests for the provider base protocol and the deterministic mock.

These cover the contract every provider must satisfy (task 2.1) using only the
offline :class:`MockModelClient` — no network, no litellm.

Validates: Requirements 9.1
"""

import json

from mad.providers import (
    Message,
    ModelClient,
    ModelResponse,
    MockModelClient,
    Usage,
)


def _messages(user: str = "Is this a security requirement?") -> list[Message]:
    return [
        Message(role="system", content="You are a classifier."),
        Message(role="user", content=user),
    ]


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_mock_implements_model_client_protocol():
    client = MockModelClient()
    assert isinstance(client, ModelClient)


def test_model_client_is_runtime_checkable_structural():
    # An object with a compatible complete() is structurally a ModelClient.
    class _Other:
        def complete(self, messages, model, params=None, response_schema=None):
            return ModelResponse(text="x")

    assert isinstance(_Other(), ModelClient)


# ---------------------------------------------------------------------------
# Default echo responder
# ---------------------------------------------------------------------------


def test_default_echo_is_deterministic():
    client = MockModelClient()
    first = client.complete(_messages(), model="gpt-4o")
    second = client.complete(_messages(), model="gpt-4o")
    assert first.text == second.text
    assert first.text == "[mock:gpt-4o] Is this a security requirement?"


def test_default_echo_varies_with_model_and_input():
    client = MockModelClient()
    a = client.complete(_messages("Q1"), model="gpt-4o").text
    b = client.complete(_messages("Q1"), model="claude-3").text
    c = client.complete(_messages("Q2"), model="gpt-4o").text
    assert a != b
    assert a != c


# ---------------------------------------------------------------------------
# Scripted replies + call log
# ---------------------------------------------------------------------------


def test_scripted_replies_returned_in_order():
    client = MockModelClient(scripted=["one", "two", ModelResponse(text="three")])
    assert client.complete(_messages(), model="m").text == "one"
    assert client.complete(_messages(), model="m").text == "two"
    assert client.complete(_messages(), model="m").text == "three"


def test_scripted_exhaustion_falls_back_to_echo():
    client = MockModelClient(scripted=["only"])
    assert client.complete(_messages("hi"), model="m").text == "only"
    # Next call falls back to the deterministic echo.
    assert client.complete(_messages("hi"), model="m").text == "[mock:m] hi"


def test_call_log_records_calls():
    client = MockModelClient()
    client.complete(_messages("first"), model="m1", params={"temperature": 0.0})
    client.complete(_messages("second"), model="m2")

    assert client.call_count == 2
    assert len(client.calls) == 2
    assert client.calls[0].model == "m1"
    assert client.calls[0].params == {"temperature": 0.0}
    assert client.calls[0].messages[-1].content == "first"
    assert client.calls[1].model == "m2"
    assert client.calls[1].messages[-1].content == "second"


def test_reset_clears_log_and_rewinds_script():
    client = MockModelClient(scripted=["a", "b"])
    client.complete(_messages(), model="m")
    client.reset()
    assert client.call_count == 0
    # Script cursor rewound to the start.
    assert client.complete(_messages(), model="m").text == "a"


# ---------------------------------------------------------------------------
# Deterministic usage
# ---------------------------------------------------------------------------


def test_usage_numbers_are_stable_across_runs():
    msgs = _messages("one two three")
    u1 = MockModelClient().complete(msgs, model="m").usage
    u2 = MockModelClient().complete(msgs, model="m").usage
    assert u1 == u2
    assert isinstance(u1, Usage)
    assert u1.total_tokens == u1.prompt_tokens + u1.completion_tokens
    assert u1.prompt_tokens > 0
    assert u1.completion_tokens > 0


# ---------------------------------------------------------------------------
# Structured output (response_schema)
# ---------------------------------------------------------------------------


_BINARY_SCHEMA = {
    "type": "object",
    "properties": {"class": {"type": "string", "enum": ["F", "NF"]}},
    "required": ["class"],
}


def test_response_schema_without_json_text_uses_schema_defaults():
    client = MockModelClient()
    resp = client.complete(_messages(), model="m", response_schema=_BINARY_SCHEMA)
    assert resp.structured == {"class": "F"}  # first enum value
    assert resp.structured_mode == "native"


def test_response_schema_parses_json_text_reply():
    client = MockModelClient(scripted=[json.dumps({"class": "NF"})])
    resp = client.complete(_messages(), model="m", response_schema=_BINARY_SCHEMA)
    assert resp.structured == {"class": "NF"}
    assert resp.structured_mode == "native"


def test_no_schema_means_no_structured_output():
    resp = MockModelClient().complete(_messages(), model="m")
    assert resp.structured is None
    assert resp.structured_mode is None


def test_schema_default_value_types():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "score": {"type": "integer"},
            "ratio": {"type": "number"},
            "ok": {"type": "boolean"},
            "items": {"type": "array"},
            "choice": {"type": "string", "enum": ["a", "b"]},
        },
    }
    resp = MockModelClient().complete(_messages(), model="m", response_schema=schema)
    assert resp.structured == {
        "name": "",
        "score": 0,
        "ratio": 0,
        "ok": False,
        "items": [],
        "choice": "a",
    }


# ---------------------------------------------------------------------------
# Responder callable (drives judge-style replies)
# ---------------------------------------------------------------------------


def test_responder_callable_drives_text():
    def responder(messages, model, params, response_schema):
        return "F"

    client = MockModelClient(responder=responder)
    assert client.complete(_messages(), model="m").text == "F"
    assert client.complete(_messages(), model="m").text == "F"


def test_responder_can_return_structured_judge_class():
    def responder(messages, model, params, response_schema):
        # Simulate a binary judge that always answers NF.
        return json.dumps({"class": "NF"})

    client = MockModelClient(responder=responder)
    resp = client.complete(_messages(), model="m", response_schema=_BINARY_SCHEMA)
    assert resp.structured == {"class": "NF"}
    assert resp.structured_mode == "native"


def test_responder_returning_model_response_is_used_as_is():
    canned = ModelResponse(
        text="done",
        usage=Usage(prompt_tokens=10, completion_tokens=2, total_tokens=12),
        structured={"class": "F"},
        structured_mode="native",
    )

    def responder(messages, model, params, response_schema):
        return canned

    client = MockModelClient(responder=responder)
    resp = client.complete(_messages(), model="m", response_schema=_BINARY_SCHEMA)
    assert resp is canned
    assert resp.structured == {"class": "F"}
    assert resp.usage.total_tokens == 12
