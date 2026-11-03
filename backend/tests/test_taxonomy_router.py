"""Tests for the taxonomy router (task 6.2, Reqs 7.4, 12.3).

Verifies ``GET /api/taxonomy`` serves the full catalog (dimensions →
sub-dimensions → values with flags), the default selection per single-selection
sub-dimension, the "under development" (non-executable) keys, and the predefined
persona/role/topology templates — all sourced verbatim from the engine catalog
(:mod:`mad.taxonomy.catalog`) and template layer (:mod:`mad.taxonomy.templates`).

Each test uses a FastAPI ``TestClient`` over an app built with an in-memory
SQLite database so no on-disk state is left behind.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import API_PREFIX, create_app
from mad.taxonomy import catalog, templates

FRONTEND_ORIGIN = "http://localhost:5173"


def _settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        cors_origins=[FRONTEND_ORIGIN],
        secret_key="test-secret",
    )


@pytest.fixture()
def client() -> TestClient:
    app = create_app(_settings())
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def payload(client: TestClient) -> dict:
    resp = client.get(f"{API_PREFIX}/taxonomy")
    assert resp.status_code == 200
    return resp.json()


# --------------------------------------------------------------------------- #
# Routing / OpenAPI
# --------------------------------------------------------------------------- #


def test_openapi_exposes_taxonomy(client: TestClient):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert f"{API_PREFIX}/taxonomy" in resp.json()["paths"]


# --------------------------------------------------------------------------- #
# Dimensions / sub-dimensions / values
# --------------------------------------------------------------------------- #


def test_returns_three_dimensions_in_order(payload: dict):
    keys = [dim["key"] for dim in payload["dimensions"]]
    assert keys == ["participants", "interaction", "agreement"]


def test_dimensions_match_catalog_verbatim(payload: dict):
    """The serialized tree equals the engine catalog's own ``to_dict``."""
    assert payload["dimensions"] == catalog.to_dict()["dimensions"]


def test_values_carry_all_flags(payload: dict):
    """Every value exposes key/label/description/default/executable/icon."""
    required = {"key", "label", "description", "default", "executable", "icon"}
    seen_value = False
    for dim in payload["dimensions"]:
        for sub in dim["subdimensions"]:
            assert sub["selection"] in {"single", "multi", "attributes"}
            for value in sub["values"]:
                seen_value = True
                assert required <= set(value)
    assert seen_value, "expected at least one value in the catalog"


def test_executable_flag_distinguishes_values(payload: dict):
    """Both executable and non-executable (under-development) values appear."""
    executables = {
        value["executable"]
        for dim in payload["dimensions"]
        for sub in dim["subdimensions"]
        for value in sub["values"]
    }
    assert executables == {True, False}


# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #


def test_defaults_match_catalog(payload: dict):
    assert payload["defaults"] == catalog.default_config()


def test_defaults_are_marked_default_in_tree(payload: dict):
    """Each defaults entry points at the value flagged ``default`` in the tree.

    A single-selection sub-dimension carries at most one ``default`` value. When
    one exists it appears in ``defaults``; otherwise the sub-dimension is absent
    from ``defaults`` (matching ``catalog.default_config``).
    """
    assert payload["defaults"]  # non-empty
    for dim in payload["dimensions"]:
        for sub in dim["subdimensions"]:
            default_values = [v["key"] for v in sub["values"] if v["default"]]
            dim_defaults = payload["defaults"].get(dim["key"], {})
            if sub["selection"] == "single" and default_values:
                assert len(default_values) == 1
                assert dim_defaults[sub["key"]] == default_values[0]
            else:
                assert sub["key"] not in dim_defaults


# --------------------------------------------------------------------------- #
# Under-development keys
# --------------------------------------------------------------------------- #


def test_under_development_keys_match_catalog(payload: dict):
    assert sorted(payload["under_development"]) == sorted(
        catalog.under_development_keys()
    )
    # Known gated values per the catalog docstring.
    assert "dynamic" in payload["under_development"]
    assert "embeddings" in payload["under_development"]


# --------------------------------------------------------------------------- #
# Templates
# --------------------------------------------------------------------------- #


def test_templates_persona_patterns(payload: dict):
    patterns = payload["templates"]["persona_patterns"]
    keys = {p["key"] for p in patterns}
    assert {"angel", "devil", "six_thinking_hats"} <= keys
    assert len(patterns) == len(templates.list_persona_patterns())

    angel = next(p for p in patterns if p["key"] == "angel")
    assert angel["pair_with"] == "devil"
    assert angel["is_set"] is False
    assert angel["personas"][0]["name"] == "Angel"

    hats = next(p for p in patterns if p["key"] == "six_thinking_hats")
    assert hats["is_set"] is True
    assert len(hats["personas"]) == 6


def test_templates_roles(payload: dict):
    roles = payload["templates"]["roles"]
    keys = [r["key"] for r in roles]
    assert keys == [r.key for r in templates.list_roles()]
    debater = next(r for r in roles if r["key"] == "debater")
    assert debater["icon"] == "role/debater"


def test_templates_topologies(payload: dict):
    topologies = payload["templates"]["topologies"]
    keys = {t["key"] for t in topologies}
    assert {"chain", "ring", "star", "tree", "layered", "sparse", "bipartite"} <= keys
    star = next(t for t in topologies if t["key"] == "star")
    assert star["icon"] == "topology/star"
