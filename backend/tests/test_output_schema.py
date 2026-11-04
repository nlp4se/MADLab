"""The agreement output_schema is enforced consistently (task 11.13).

One normalizer (:mod:`mad.output_schema`) unwraps the OpenAI envelope for the
provider request, the judge-reply validation, and label extraction. Covers
envelope and bare schemas, required / extra-property rejection, the provider
request payload per kind, label extraction from enveloped schemas, and a
regression with execution 3's actual shapes (config 8). Fully offline.

Validates: Requirements 3.5, 9.1, 10.7
"""

from __future__ import annotations

import copy
import json

import pytest

from mad.engine.agreement import _pragmatic_validate, resolve_agreement
from mad.engine.orchestrator import run_debate
from mad.evaluation.transcript_adapter import decision_label, prediction_from_transcript
from mad.output_schema import (
    DEFAULT_SCHEMA_NAME,
    is_strict_compatible,
    normalize_output_schema,
    unwrap_output_schema,
)
from mad.providers import LiteLLMClient, Message, MockModelClient
from mad.providers.litellm_client import build_response_format
from mad.providers.registry import ProviderConfig, ProviderRegistry
from mad.taxonomy import templates
from mad.taxonomy.schema import Agreement

# Config 8 / execution 3's output_schema as stored (same as
# data/prompts/coordinator/requirements-schema-binary.json): the envelope, no
# "required", no "additionalProperties".
INNER = {
    "type": "object",
    "properties": {"class": {"type": "string", "enum": ["F", "NF"]}},
}
ENVELOPE = {
    "name": "requirements-schema",
    "description": "A schema for classifying requirements into categories",
    "schema": INNER,
}
STRICT_INNER = {**INNER, "required": ["class"], "additionalProperties": False}

# Execution 3 instance 0's judge reply (abridged): off-schema, accepted before.
EXEC3_REPLY = {
    "requirement": "The system shall have a MDI form that allows for the viewing "
    "of the graph and the data table.",
    "debaters_arguments": ["Debater 1: Functional.", "Debater 2: Non-Functional."],
    "moderator_evaluation": "It defines what the system must do.",
    "final_classification": "Functional",
}
# Execution 2's judge reply: the model copied the envelope.
EXEC2_REPLY = {"name": "requirements-schema", "schema": {"class": "NF"}}
# Execution 4 instance 1's judge reply: a different label key.
EXEC4_REPLY = {"requirement": "...", "classification": "F", "reasoning": "...", "winner": "p1"}


def _judge(schema):
    return Agreement(
        authority="judge_based", resolution="argument_evaluation", output_schema=schema
    )


def _resolve(schema, reply):
    return resolve_agreement(_judge(schema), outputs=[], judge_fn=lambda _ctx: reply)


# ---------------------------------------------------------------------------
# normalizer
# ---------------------------------------------------------------------------


def test_bare_schema_is_returned_as_is():
    n = normalize_output_schema(INNER)
    assert n.schema is INNER
    assert n.name == DEFAULT_SCHEMA_NAME
    assert n.description is None and n.enveloped is False


def test_envelope_is_unwrapped_keeping_name_and_description():
    n = normalize_output_schema(ENVELOPE)
    assert n.schema == INNER
    assert n.name == "requirements-schema"
    assert n.description == ENVELOPE["description"]
    assert n.enveloped is True


def test_full_response_format_is_unwrapped():
    rf = {"type": "json_schema", "json_schema": {**ENVELOPE, "strict": True}}
    n = normalize_output_schema(rf)
    assert n.schema == INNER and n.name == "requirements-schema" and n.strict is True


def test_name_is_sanitised_and_non_objects_are_none():
    assert normalize_output_schema({"name": "my schema!", "schema": INNER}).name == "my_schema_"
    assert normalize_output_schema(None) is None
    assert unwrap_output_schema("nope") is None


def test_strict_compatibility():
    assert is_strict_compatible(INNER) is False  # no required / additionalProperties
    assert is_strict_compatible({**INNER, "required": ["class"]}) is False
    assert is_strict_compatible(STRICT_INNER) is True
    nested = {
        **STRICT_INNER,
        "properties": {**INNER["properties"], "meta": {"type": "object", "properties": {"x": {}}}},
        "required": ["class", "meta"],
    }
    assert is_strict_compatible(nested) is False  # the nested object is open
    assert normalize_output_schema({"name": "s", "schema": STRICT_INNER, "strict": False}).request_strict is False


# ---------------------------------------------------------------------------
# validation (envelope and bare)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("schema", [INNER, ENVELOPE])
def test_on_schema_reply_is_accepted(schema):
    result = _resolve(schema, {"class": "F"})
    assert result.undecided is False
    assert result.structured == {"class": "F"}


@pytest.mark.parametrize("schema", [INNER, ENVELOPE])
def test_bare_scalar_is_coerced_into_the_enum_property(schema):
    assert _resolve(schema, "NF").structured == {"class": "NF"}


@pytest.mark.parametrize("reply", [EXEC3_REPLY, EXEC2_REPLY, EXEC4_REPLY, {}])
def test_off_schema_reply_is_undecided_with_reason(reply):
    result = _resolve(ENVELOPE, reply)
    assert result.undecided is True
    assert result.structured is None
    assert result.decision == reply  # raw reply kept for debugging
    assert "none of the schema's properties ['class']" in result.detail


def test_enum_violation_through_envelope_is_rejected():
    result = _resolve(ENVELOPE, {"class": "MAYBE"})
    assert result.undecided is True
    assert "MAYBE" in result.detail


def test_required_is_enforced_when_declared():
    schema = {
        "name": "s",
        "schema": {**INNER, "properties": {**INNER["properties"], "why": {"type": "string"}}, "required": ["class"]},
    }
    result = _resolve(schema, {"why": "because"})
    assert result.undecided is True
    assert "'class' is a required property" in result.detail


def test_additional_properties_false_rejects_extra_keys():
    result = _resolve({"name": "s", "schema": STRICT_INNER}, {"class": "F", "why": "x"})
    assert result.undecided is True
    assert "Additional properties are not allowed" in result.detail


def test_pragmatic_fallback_enforces_required_and_extra_keys():
    assert _pragmatic_validate({"class": "F"}, STRICT_INNER) is None
    assert "missing required key 'class'" in _pragmatic_validate({}, STRICT_INNER)
    assert "why" in _pragmatic_validate({"class": "F", "why": "x"}, STRICT_INNER)
    assert "not one of" in _pragmatic_validate({"class": "X"}, STRICT_INNER)


# ---------------------------------------------------------------------------
# label extraction from enveloped schemas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "schema", [ENVELOPE, {"type": "json_schema", "json_schema": ENVELOPE}, INNER]
)
def test_label_from_enveloped_schema(schema):
    result = _resolve(schema, {"class": "NF"})
    assert decision_label(result, schema) == "NF"


# ---------------------------------------------------------------------------
# provider request payload per kind
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]
        self.usage = None


def _capture(kind, schema, replies=('{"class": "F"}',), **client_kwargs):
    client = LiteLLMClient(kind=kind, **client_kwargs)
    calls = []

    def _raw(**kwargs):
        calls.append(kwargs)
        return _Resp(replies[min(len(calls), len(replies)) - 1])

    client._raw_completion = _raw  # type: ignore[assignment]
    resp = client.complete(
        [Message(role="system", content="judge"), Message(role="user", content="decide")],
        model="m",
        response_schema=schema,
    )
    return resp, calls


@pytest.mark.parametrize(
    "kind,kwargs",
    [
        ("openai", {"api_key": "k"}),
        ("anthropic", {"api_key": "k"}),
        ("gemini", {"api_key": "k"}),
        ("ollama", {}),
        ("openai_compatible", {"base_url": "http://localhost:1234/v1"}),
    ],
)
def test_request_carries_inner_schema_not_the_envelope(kind, kwargs):
    resp, calls = _capture(kind, ENVELOPE, **kwargs)
    rf = calls[0]["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["schema"] == INNER  # not double-wrapped
    assert rf["json_schema"]["name"] == "requirements-schema"
    assert rf["json_schema"]["description"] == ENVELOPE["description"]
    # The schema is not strict-compatible, so strict is not requested.
    assert rf["json_schema"]["strict"] is False
    assert resp.structured == {"class": "F"} and resp.structured_mode == "native"


def test_strict_requested_only_for_strict_compatible_schema():
    _, calls = _capture("openai", {"name": "s", "schema": STRICT_INNER}, api_key="k")
    assert calls[0]["response_format"]["json_schema"]["strict"] is True
    _, calls = _capture("openai", STRICT_INNER, api_key="k")
    assert calls[0]["response_format"]["json_schema"] == {
        "name": DEFAULT_SCHEMA_NAME,
        "schema": STRICT_INNER,
        "strict": True,
    }


def test_build_response_format_from_normalized_envelope():
    rf = build_response_format(normalize_output_schema(ENVELOPE))
    assert rf == {
        "type": "json_schema",
        "json_schema": {
            "name": "requirements-schema",
            "schema": INNER,
            "strict": False,
            "description": ENVELOPE["description"],
        },
    }


def test_json_mode_fallback_instruction_uses_inner_schema():
    _, calls = _capture("openai", ENVELOPE, replies=("no json", '{"class": "NF"}'), api_key="k")
    assert len(calls) == 2 and "response_format" not in calls[1]
    system = " ".join(m["content"] for m in calls[1]["messages"] if m["role"] == "system")
    assert json.dumps(INNER, ensure_ascii=False) in system
    assert "requirements-schema" not in system


# ---------------------------------------------------------------------------
# regression: config 8 / execution 3 shapes through the orchestrator
# ---------------------------------------------------------------------------


def _config8():
    config = templates.re_binary_debate()
    config.agreement.output_schema = copy.deepcopy(ENVELOPE)
    for node in config.participants.nodes:
        node.base_model.provider_id = "mock"
        node.base_model.model_key = "m"
    return config


def _run(judge_reply):
    def responder(messages, model, params, response_schema):
        if response_schema is not None:
            return json.dumps(judge_reply)
        return "An argument."

    client = MockModelClient(responder=responder)
    registry = ProviderRegistry(
        providers=[ProviderConfig(id="mock", name="Mock", kind="mock", models=["m"])],
        client_factory=lambda _c: client,
    )
    transcript = run_debate(
        _config8(), {"requirement": "The system shall have a MDI form."},
        registry, sleep=lambda _s: None,
    )
    return transcript, client


def test_exec3_off_schema_judge_reply_is_now_undecided():
    transcript, client = _run(EXEC3_REPLY)
    judge_calls = [c for c in client.calls if c.response_schema is not None]
    assert len(judge_calls) == 1
    decision = transcript.decision
    assert decision.undecided is True
    assert decision.structured is None
    assert "none of the schema's properties" in decision.detail


def test_exec3_on_schema_judge_reply_is_accepted_with_label_f():
    transcript, _ = _run({"class": "F"})
    assert transcript.decision.undecided is False
    assert transcript.decision.structured == {"class": "F"}
    assert prediction_from_transcript(transcript, ENVELOPE) == "F"
