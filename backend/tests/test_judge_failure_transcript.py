"""Task 11.17: the Gemini judge failure of config 8 and lost transcripts.

Executions 5 and 6 (config 8: two OpenAI debaters + a ``gemini-3.6-flash``
judge with the ``requirements-schema`` envelope) failed with "judge node
'participant-3' failed to produce a decision after retries; see transcript
errors", and the failed instances stored no transcript. Reproduced with one
real call: Gemini answered **HTTP 429 RESOURCE_EXHAUSTED** ("Generate content
requests per day limit exceeded on Free Tier", limit 20, retryDelay ~50000s).
The request itself was valid. The engine made it worse: every judge attempt
sent the native call *and* the JSON-mode fallback (both 429), three times, so
one failed decision burned six requests of the 20/day quota, and the error
text never reached the user.

All tests are offline: the Gemini HTTP exchange is replayed at the
``httpx.Client.send`` seam, so LiteLLM's real Gemini transformation and error
mapping run.

Validates: Requirements 3.5, 9.1, 9.5, 11.2
"""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import API_PREFIX, create_app
from app.routers import executions as executions_router
from app.services.executions import make_sync_launcher
from mad.engine.orchestrator import RetryPolicy, run_debate
from mad.errors import ExecutionError, ProviderError, error_summary
from mad.providers.base import Message, ModelResponse
from mad.providers.litellm_client import LiteLLMClient, classify_provider_exception
from mad.providers.registry import ProviderConfig, ProviderRegistry
from mad.taxonomy.schema import MADConfig

FAKE_KEY = "AIzaFAKEFAKEFAKEFAKEFAKEFAKEFAKE0000"

# Config 8's agreement.output_schema (OpenAI envelope).
CONFIG8_SCHEMA = {
    "name": "requirements-schema",
    "description": "A schema for classifying requirements into categories",
    "schema": {
        "type": "object",
        "properties": {"class": {"type": "string", "enum": ["F", "NF"]}},
        "required": ["class"],
        "additionalProperties": False,
    },
}

# The body Gemini returned to the real reproduction call (trimmed details).
GEMINI_429 = {
    "error": {
        "code": 429,
        "message": (
            "You exceeded your current quota, please check your plan and billing "
            "details. For more information on this error, head to: "
            "https://ai.google.dev/gemini-api/docs/rate-limits. \n* Quota exceeded "
            "for metric: generativelanguage.googleapis.com/"
            "generate_content_free_tier_requests, limit: 20, model: "
            "gemini-3.6-flash\nPlease retry in 13h53m45.824513831s."
        ),
        "status": "RESOURCE_EXHAUSTED",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                "retryDelay": "50025s",
            }
        ],
    }
}


class _GeminiWire:
    """Replays Gemini HTTP responses at ``httpx.Client.send`` and records requests."""

    def __init__(self, status: int, body: dict[str, Any]):
        self.status = status
        self.body = body
        self.requests: list[httpx.Request] = []

    def send(self, client: httpx.Client, request: httpx.Request, **_kw: Any) -> httpx.Response:
        if request.url.host != "generativelanguage.googleapis.com":
            # Anything else (e.g. LiteLLM's remote cost-map fetch) stays offline.
            return httpx.Response(404, request=request)
        self.requests.append(request)
        return httpx.Response(self.status, json=self.body, request=request)

    def payloads(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests]


@pytest.fixture()
def gemini_429(monkeypatch) -> _GeminiWire:
    wire = _GeminiWire(429, GEMINI_429)
    monkeypatch.setattr(httpx.Client, "send", lambda self, req, **kw: wire.send(self, req, **kw))
    return wire


def _judge_messages() -> list[Message]:
    return [
        Message(role="system", content="You are a moderator."),
        Message(
            role="user",
            content="Task: Classify this requirement: X\n\nDebate transcript:\n"
            "[Round 1] Functional Debater: F\n\nThe debate is over.",
        ),
    ]


# --------------------------------------------------------------------------- #
# Provider layer: the request config 8's judge sends, and the 429 handling
# --------------------------------------------------------------------------- #


def test_gemini_judge_request_payload_and_quota_error_handling(gemini_429):
    """One native request with the inner schema; a 429 is not doubled by the fallback."""
    client = LiteLLMClient(kind="gemini", api_key=FAKE_KEY)

    with pytest.raises(ProviderError) as info:
        client.complete(
            _judge_messages(),
            model="gemini-3.6-flash",
            params={"temperature": 0.0},
            response_schema=CONFIG8_SCHEMA,
        )

    # Exactly one HTTP request: the JSON-mode fallback is skipped for a 429.
    assert len(gemini_429.requests) == 1
    payload = gemini_429.payloads()[0]
    generation = payload["generationConfig"]
    # The inner schema proper, as response_json_schema (no envelope, no strict).
    assert generation["response_mime_type"] == "application/json"
    assert generation["response_json_schema"] == CONFIG8_SCHEMA["schema"]
    assert "strict" not in json.dumps(generation)
    assert payload["system_instruction"]["parts"][0]["text"] == "You are a moderator."

    err = info.value
    assert err.category == "rate_limit"
    assert err.status_code == 429
    assert err.retry_after_s == pytest.approx(50025.0)
    assert not err.request_rejected
    assert "exceeded your current quota" in str(err)
    assert FAKE_KEY not in str(err)


def test_rejected_native_request_still_falls_back(monkeypatch):
    """A 400 on the native response_format keeps the JSON-mode fallback."""
    calls: list[dict[str, Any]] = []

    class _BadRequest(Exception):
        status_code = 400

    def _raw(**kwargs):
        calls.append(kwargs)
        if "response_format" in kwargs:
            raise _BadRequest("Invalid JSON payload: unknown field response_json_schema")
        return {"choices": [{"message": {"content": '{"class": "NF"}'}}]}

    client = LiteLLMClient(kind="gemini", api_key=FAKE_KEY)
    client._raw_completion = _raw  # type: ignore[assignment]
    resp = client.complete(_judge_messages(), model="gemini-3.6-flash", response_schema=CONFIG8_SCHEMA)
    assert resp.structured == {"class": "NF"}
    assert resp.structured_mode == "json_mode_fallback"
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("exc", "category", "retryable"),
    [
        (type("RateLimitError", (Exception,), {"status_code": 429})("x"), "rate_limit", True),
        (type("AuthenticationError", (Exception,), {"status_code": 401})("x"), "auth", False),
        (type("NotFoundError", (Exception,), {"status_code": 404})("x"), "not_found", False),
        (type("APIConnectionError", (Exception,), {"status_code": 500})("x"), "connection", True),
        (type("Boom", (Exception,), {"status_code": 503})("x"), "server", True),
        (RuntimeError("anything"), "other", True),
    ],
)
def test_classify_provider_exception(exc, category, retryable):
    got, _status, _after = classify_provider_exception(exc)
    assert got == category
    assert ProviderError("m", category=got).retryable is retryable


def test_error_summary_is_short_and_secret_free():
    text = (
        f"Model call failed for 'gemini/gemini-3.6-flash' (kind='gemini'): "
        f"litellm.RateLimitError: litellm.RateLimitError: geminiException - "
        f"{json.dumps(GEMINI_429, indent=2)} url=https://x/y?key={FAKE_KEY}"
    )
    summary = error_summary(ProviderError(text, category="rate_limit", status_code=429), 200)
    assert summary.startswith("[rate limit, HTTP 429] Model call failed for 'gemini/gemini-3.6-flash'")
    assert "You exceeded your current quota" in summary
    assert FAKE_KEY not in summary and "\n" not in summary
    assert len(summary) <= 200


# --------------------------------------------------------------------------- #
# Engine: retries stop on a long quota wait; the partial transcript survives
# --------------------------------------------------------------------------- #


def _config8_like() -> MADConfig:
    def node(node_id: str, label: str, roles: list[str], provider: str) -> dict:
        return {
            "id": node_id,
            "label": label,
            "roles": roles,
            "base_model": {"provider_id": provider, "model_key": "m", "temperature": 0.0},
            "system_prompt": f"You are {label}.",
        }

    return MADConfig.model_validate(
        {
            "schema_version": "1.0",
            "name": "config 8 shape",
            "participants": {
                "nodes": [
                    node("participant-1", "Functional Debater", ["debater"], "openai"),
                    node("participant-2", "Non-functional Debater", ["debater"], "openai"),
                    node("participant-3", "Participant 3", ["judge"], "gemini"),
                ]
            },
            "interaction": {
                "topology": {
                    "adaptability": "static",
                    "structure": "fully_connected",
                    "edges": [
                        {"source": "participant-1", "target": "participant-2"},
                        {"source": "participant-2", "target": "participant-1"},
                    ],
                    "entry_nodes": ["participant-1", "participant-2"],
                },
                "protocol": {"mechanism": "sequential", "max_rounds": 2, "ordering": "fixed"},
                "format": {"syntax": "natural_language", "memory": "short_term"},
            },
            "agreement": {
                "authority": "judge_based",
                "resolution": "argument_evaluation",
                "output_schema": CONFIG8_SCHEMA,
            },
            "input_spec": {
                "template": "Classify this requirement: {{requirement}}",
                "placeholders": ["requirement"],
            },
        }
    )


class _Debater:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages, model, params=None, response_schema=None) -> ModelResponse:
        self.calls += 1
        return ModelResponse(text=f"argument {self.calls}")


def _registry(gemini_client: Any, debater: Optional[_Debater] = None) -> ProviderRegistry:
    clients = {"openai": debater or _Debater(), "gemini": gemini_client}
    registry = ProviderRegistry(client_factory=lambda cfg: clients[cfg.id])
    registry.add(ProviderConfig(id="openai", name="OpenAI", kind="openai", models=["m"]))
    registry.add(ProviderConfig(id="gemini", name="Gemini", kind="gemini", models=["m"]))
    return registry


def test_quota_exhausted_judge_fails_fast_and_keeps_the_partial_transcript(gemini_429):
    """Through the real LiteLLM Gemini path: one request, actionable error, transcript kept."""
    config = _config8_like()
    gemini = LiteLLMClient(kind="gemini", api_key=FAKE_KEY)
    sleeps: list[float] = []

    with pytest.raises(ExecutionError) as info:
        run_debate(
            config,
            {"requirement": "The system shall display Events in a vertical table by time."},
            _registry(gemini),
            retry_policy=RetryPolicy(max_attempts=3),
            sleep=sleeps.append,
        )

    # Before: 3 attempts x (native + fallback) = 6 requests. Now: 1, no waiting.
    assert len(gemini_429.requests) == 1
    assert sleeps == []

    message = str(info.value)
    assert message.startswith("judge node 'participant-3' failed to produce a decision after 1 attempt(s): ")
    assert "[rate limit, HTTP 429]" in message
    assert "exceeded your current quota" in message
    assert FAKE_KEY not in message

    transcript = info.value.transcript
    assert transcript is not None
    assert transcript.resolved_input.startswith("Classify this requirement: The system shall display")
    assert [m.node_id for m in transcript.messages] == ["participant-1", "participant-2"] * 2
    assert transcript.decision is None
    [error] = transcript.errors
    assert error.node_id == "participant-3" and error.attempts == 1 and error.round_index == 2
    assert "exceeded your current quota" in error.message
    assert FAKE_KEY not in error.message


class _Flaky:
    """Raises ``errors`` in order, then answers with the decision JSON."""

    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.calls = 0

    def complete(self, messages, model, params=None, response_schema=None) -> ModelResponse:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return ModelResponse(text='{"class": "F"}', structured={"class": "F"})


def test_short_retry_after_stretches_the_backoff():
    judge = _Flaky(ProviderError("slow down", category="rate_limit", status_code=429, retry_after_s=7.0))
    sleeps: list[float] = []
    transcript = run_debate(
        _config8_like(),
        {"requirement": "r"},
        _registry(judge),
        retry_policy=RetryPolicy(max_attempts=3, base_delay_s=0.5),
        sleep=sleeps.append,
    )
    assert judge.calls == 2
    assert sleeps == [7.0]
    assert transcript.decision is not None and transcript.decision.structured == {"class": "F"}


def test_auth_error_is_not_retried():
    judge = _Flaky(*[ProviderError("bad key", category="auth", status_code=401)] * 3)
    with pytest.raises(ExecutionError) as info:
        run_debate(
            _config8_like(),
            {"requirement": "r"},
            _registry(judge),
            retry_policy=RetryPolicy(max_attempts=3),
            sleep=lambda _s: None,
        )
    assert judge.calls == 1
    assert "after 1 attempt(s): [auth, HTTP 401] bad key" in str(info.value)


# --------------------------------------------------------------------------- #
# Runner: a failed instance persists its partial transcript
# --------------------------------------------------------------------------- #


def test_failed_instance_persists_partial_transcript(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path.as_posix()}/exec.db",
        dataset_storage_path=str(tmp_path / "storage"),
    )
    app = create_app(settings)
    judge = _Flaky(
        *[
            ProviderError(
                "Model call failed: quota", category="rate_limit", status_code=429, retry_after_s=50025.0
            )
        ]
    )
    registry = _registry(judge)
    app.dependency_overrides[executions_router.get_registry] = lambda: registry
    app.dependency_overrides[executions_router.get_launcher] = lambda: make_sync_launcher(
        sleep=lambda _s: None
    )

    artifact = _config8_like().model_dump(mode="json")
    with TestClient(app) as client:
        config = client.post(f"{API_PREFIX}/configs/import", json={"artifact": artifact})
        assert config.status_code in (200, 201), config.text
        resp = client.post(
            f"{API_PREFIX}/executions",
            json={"config_id": config.json()["id"], "input": {"requirement": "The system shall log."}},
        )
        assert resp.status_code == 201, resp.text
        detail = resp.json()

    assert detail["status"] == "failed"
    [inst] = detail["instances"]
    assert inst["error"].startswith(
        "ExecutionError: judge node 'participant-3' failed to produce a decision after 1 attempt(s): "
        "[rate limit, HTTP 429] Model call failed: quota"
    )
    assert inst["final_decision"] is None
    assert inst["metrics"] is None
    transcript = inst["transcript"]
    assert transcript is not None
    assert transcript["resolved_input"] == "Classify this requirement: The system shall log."
    assert len(transcript["messages"]) == 4
    assert transcript["decision"] is None
    assert [(e["node_id"], e["attempts"]) for e in transcript["errors"]] == [("participant-3", 1)]
    assert "Model call failed: quota" in transcript["errors"][0]["message"]
