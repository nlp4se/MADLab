"""API tests for the AI design-assistant router (task 11.1).

Exercises ``POST /api/assistant/design`` over a FastAPI ``TestClient`` with a
temp-file SQLite database, fully offline: the ``get_registry`` dependency is
overridden with a :class:`ProviderRegistry` whose client factory returns a
:class:`~mad.providers.base.MockModelClient`, so no LiteLLM client is built and
no network call is made. The mock's ``responder`` lets each test script the
model's reply (a question, a valid/invalid proposal, free text, or a raised
error).

Covers the envelope contract:

* a clarifying-question reply → ``mode="question"``;
* a valid ``MADConfig`` reply (fenced or raw JSON) → ``mode="proposal"`` with a
  validating artifact and ``under_development`` populated when applicable;
* an INVALID artifact → downgraded to ``mode="question"`` (no broken proposal);
* a non-JSON free-text reply → treated as ``mode="question"``;
* a provider runtime error (mock raises) → ``mode="question"`` with a clear
  message, not a 500;
* an unknown ``provider_id`` → 404.

Validates: Requirements 4.1, 4.2, 6.1, 6.8, 7.3, 8.6, 12.2
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import API_PREFIX, create_app
from app.routers import assistant as assistant_router
from mad.providers.base import MockModelClient, ModelResponse
from mad.providers.registry import ProviderConfig, ProviderRegistry

FRONTEND_ORIGIN = "http://localhost:5173"

# The provider the request binds to; the mock registry registers it so
# resolution succeeds offline.
PROVIDER_ID = 1
MODEL_KEY = "mock-model"


# --------------------------------------------------------------------------- #
# Mock registry / client
# --------------------------------------------------------------------------- #


def _make_mock_registry(responder) -> ProviderRegistry:
    """A registry whose only provider resolves to a MockModelClient (offline)."""

    def _factory(_config: ProviderConfig) -> MockModelClient:
        return MockModelClient(responder=responder)

    registry = ProviderRegistry(client_factory=_factory)
    registry.add(
        ProviderConfig(
            id=str(PROVIDER_ID),
            name="Test provider",
            kind="openai_compatible",
            models=[MODEL_KEY],
        )
    )
    return registry


def _build_client(tmp_path, *, responder) -> TestClient:
    db_url = f"sqlite:///{tmp_path.as_posix()}/assistant.db"
    settings = Settings(database_url=db_url, cors_origins=[FRONTEND_ORIGIN])
    app = create_app(settings)
    registry = _make_mock_registry(responder)
    app.dependency_overrides[assistant_router.get_registry] = lambda: registry
    return TestClient(app)


def _responder_returning(reply):
    """A responder that always returns the same canned reply text/object."""

    def _responder(_messages, _model, _params, _schema):
        return reply

    return _responder


def _post(client: TestClient, **overrides) -> "object":
    payload = {
        "provider_id": PROVIDER_ID,
        "model": MODEL_KEY,
        "message": "Design a debate for me",
        "history": [],
        "artifact": None,
    }
    payload.update(overrides)
    return client.post(f"{API_PREFIX}/assistant/design", json=payload)


# --------------------------------------------------------------------------- #
# A valid, minimal MADConfig the model can "propose".
# --------------------------------------------------------------------------- #


def _valid_artifact() -> dict:
    return {
        "schema_version": "1.0",
        "name": "Two-debater majority vote",
        "participants": {
            "nodes": [
                {"id": "alice", "label": "Alice", "roles": ["debater"]},
                {"id": "bob", "label": "Bob", "roles": ["debater"]},
            ]
        },
        "interaction": {
            "topology": {"adaptability": "static", "structure": "fully_connected"},
            "protocol": {
                "mechanism": "sequential",
                "max_rounds": 2,
                "ordering": "fixed",
                "order": ["alice", "bob"],
            },
            "format": {"syntax": "natural_language", "memory": "short_term"},
        },
        "agreement": {"authority": "collective", "resolution": "majority_vote"},
        "input_spec": {"template": "Debate: {{topic}}", "placeholders": ["topic"]},
    }


# --------------------------------------------------------------------------- #
# Routing / OpenAPI
# --------------------------------------------------------------------------- #


def test_openapi_exposes_assistant_path(tmp_path):
    client = _build_client(tmp_path, responder=_responder_returning("hi"))
    paths = client.get("/openapi.json").json()["paths"]
    assert f"{API_PREFIX}/assistant/design" in paths


# --------------------------------------------------------------------------- #
# Question envelope
# --------------------------------------------------------------------------- #


def test_clarifying_question_reply(tmp_path):
    reply = json.dumps(
        {
            "mode": "question",
            "message": "How many debaters should there be, and who judges?",
            "artifact": None,
        }
    )
    client = _build_client(tmp_path, responder=_responder_returning(reply))

    resp = _post(client, message="I want a debate")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "question"
    assert "debaters" in body["message"]
    assert body["artifact"] is None
    assert body["under_development"] == []


# --------------------------------------------------------------------------- #
# Proposal envelope (raw + fenced JSON)
# --------------------------------------------------------------------------- #


def test_valid_proposal_raw_json(tmp_path):
    reply = json.dumps(
        {
            "mode": "proposal",
            "message": "Two debaters over two rounds, decided by majority vote.",
            "artifact": _valid_artifact(),
        }
    )
    client = _build_client(tmp_path, responder=_responder_returning(reply))

    resp = _post(client)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "proposal"
    assert body["artifact"] is not None
    # The returned artifact validates (it round-trips through the engine).
    assert body["artifact"]["name"] == "Two-debater majority vote"
    assert len(body["artifact"]["participants"]["nodes"]) == 2
    # Fully-executable config → no under-development selections.
    assert body["under_development"] == []


def test_valid_proposal_fenced_json_with_prose(tmp_path):
    # Model wraps the envelope in a ```json fence and adds prose around it.
    reply = (
        "Sure, here is the configuration you asked for:\n\n"
        "```json\n"
        + json.dumps(
            {
                "mode": "proposal",
                "message": "A judge decides after one round.",
                "artifact": _artifact_with_judge(),
            }
        )
        + "\n```\n\nLet me know if you want changes."
    )
    client = _build_client(tmp_path, responder=_responder_returning(reply))

    resp = _post(client)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "proposal"
    assert body["artifact"]["agreement"]["authority"] == "judge_based"


def test_proposal_populates_under_development(tmp_path):
    # A config selecting a non-executable value (coordinator ordering) is still
    # valid and proposable, but its under-development selection is surfaced.
    artifact = _valid_artifact()
    artifact["interaction"]["protocol"]["ordering"] = "coordinator"
    reply = json.dumps(
        {"mode": "proposal", "message": "Coordinator-ordered debate.", "artifact": artifact}
    )
    client = _build_client(tmp_path, responder=_responder_returning(reply))

    resp = _post(client)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "proposal"
    assert "coordinator" in body["under_development"]


# --------------------------------------------------------------------------- #
# Invalid proposal → downgraded to a question (no broken proposal leaks)
# --------------------------------------------------------------------------- #


def test_invalid_artifact_downgraded_to_question(tmp_path):
    # judge_based authority with NO judge node fails schema validation.
    artifact = _valid_artifact()
    artifact["agreement"]["authority"] = "judge_based"
    reply = json.dumps(
        {"mode": "proposal", "message": "Judge decides.", "artifact": artifact}
    )
    client = _build_client(tmp_path, responder=_responder_returning(reply))

    resp = _post(client)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "question"
    assert body["artifact"] is None
    # The message explains the validation problem.
    assert "judge" in body["message"].lower()


# --------------------------------------------------------------------------- #
# Non-JSON free text → treated as a question
# --------------------------------------------------------------------------- #


def test_non_json_free_text_is_a_question(tmp_path):
    client = _build_client(
        tmp_path,
        responder=_responder_returning(
            "Happy to help! Roughly how many agents do you have in mind?"
        ),
    )

    resp = _post(client)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "question"
    assert body["artifact"] is None
    assert "agents" in body["message"]


# --------------------------------------------------------------------------- #
# Provider runtime error → inline question, not a 500
# --------------------------------------------------------------------------- #


def test_provider_runtime_error_is_a_question(tmp_path):
    def _boom(_messages, _model, _params, _schema):
        raise RuntimeError("Anthropic key is not scoped for this model")

    client = _build_client(tmp_path, responder=_boom)

    resp = _post(client)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "question"
    assert body["artifact"] is None
    assert "failed" in body["message"].lower()
    assert "Anthropic key" in body["message"]


# --------------------------------------------------------------------------- #
# Token budget: reasoning models / truncation
# --------------------------------------------------------------------------- #


def test_reasoning_exhausted_budget_explains_truncation(tmp_path):
    # A reasoning model that spends the whole budget thinking returns empty
    # content with finish_reason="length"; this used to surface as the generic
    # "Could you tell me more..." question on every turn.
    reply = ModelResponse(text="", raw={"choices": [{"finish_reason": "length"}]})
    client = _build_client(tmp_path, responder=_responder_returning(reply))

    body = _post(client).json()
    assert body["mode"] == "question"
    assert body["artifact"] is None
    assert "ran out of output tokens" in body["message"]
    assert "reasoning" in body["message"]


def test_truncated_json_explains_truncation(tmp_path):
    cut = json.dumps({"mode": "proposal", "message": "x", "artifact": _valid_artifact()})[:120]
    reply = ModelResponse(text=cut, raw={"choices": [{"finish_reason": "length"}]})
    client = _build_client(tmp_path, responder=_responder_returning(reply))

    body = _post(client).json()
    assert body["mode"] == "question"
    assert "ran out of output tokens" in body["message"]


def test_empty_reply_is_reported(tmp_path):
    client = _build_client(tmp_path, responder=_responder_returning(""))

    body = _post(client).json()
    assert body["mode"] == "question"
    assert "empty reply" in body["message"]


def test_request_uses_large_token_budget(tmp_path):
    seen: dict = {}

    def _responder(_messages, _model, params, _schema):
        seen.update(params or {})
        return json.dumps({"mode": "question", "message": "ok", "artifact": None})

    client = _build_client(tmp_path, responder=_responder)
    _post(client)
    assert seen["max_tokens"] >= 16000


def test_token_budget_clamped_to_model_output_limit():
    from app.services.assistant import _MAX_TOKENS, _max_tokens_for

    class _Client:
        kind = "openai"

    # gpt-4o-mini caps output at 16384 in LiteLLM's catalog; gpt-4 at 4096.
    assert _max_tokens_for(_Client(), "gpt-4") == 4096
    assert _max_tokens_for(_Client(), "not-a-real-model") == _MAX_TOKENS


# --------------------------------------------------------------------------- #
# Unknown provider → 404
# --------------------------------------------------------------------------- #


def test_unknown_provider_returns_404(tmp_path):
    client = _build_client(tmp_path, responder=_responder_returning("hi"))

    resp = _post(client, provider_id=9999)
    assert resp.status_code == 404, resp.text


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _artifact_with_judge() -> dict:
    artifact = _valid_artifact()
    artifact["name"] = "Judged debate"
    artifact["participants"]["nodes"].append(
        {"id": "judge", "label": "Judge", "roles": ["judge"]}
    )
    artifact["agreement"]["authority"] = "judge_based"
    artifact["agreement"]["resolution"] = "argument_evaluation"
    return artifact
