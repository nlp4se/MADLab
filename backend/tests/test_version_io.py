"""Unit tests for artifact versioning + round-trip I/O (``mad.taxonomy.version``).

Covers:
* the single-source-of-truth version constant (``CURRENT_SCHEMA_VERSION`` ==
  ``schema.SCHEMA_VERSION``),
* export -> import -> export round-trip stability,
* invalid artifacts rejected on import with actionable field errors,
* the schema-version stamp present on exported artifacts,
* ``migrate()`` as a no-op on current-version dicts and the registry
  mechanism (a registered one-step migration is applied),
* ``migrate()`` rejecting unknown/newer versions,
* malformed JSON string import raising a clear error,
* ``save_config`` / ``load_config`` file round-trip via ``tmp_path``.

Depends only on pydantic + the ``mad`` package.
"""

import json

import pytest

from mad.errors import ConfigValidationError
from mad.taxonomy import schema, version
from mad.taxonomy.schema import MADConfig
from mad.taxonomy.version import (
    CURRENT_SCHEMA_VERSION,
    export_config,
    export_config_json,
    import_config,
    load_config,
    migrate,
    save_config,
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _config(**overrides) -> MADConfig:
    """A representative valid config exercising nodes, edges, groups, roles."""
    data = {
        "name": "RoundTrip",
        "description": "a config for round-trip tests",
        "participants": {
            "nodes": [
                {"id": "alice", "label": "Alice", "roles": ["debater"]},
                {"id": "jury", "label": "Jury", "roles": ["judge"]},
            ],
            "groups": [{"id": "g1", "label": "Team A", "color": "#fff"}],
        },
        "interaction": {
            "topology": {"edges": [{"source": "alice", "target": "jury"}]},
            "protocol": {"order": ["alice", "jury"]},
        },
        "agreement": {"authority": "judge_based"},
        "input_spec": {"template": "Classify {{x}}", "placeholders": ["x"]},
    }
    data.update(overrides)
    return MADConfig.model_validate(data)


# ---------------------------------------------------------------------------
# Single source of truth
# ---------------------------------------------------------------------------


def test_version_constant_single_source_of_truth():
    assert CURRENT_SCHEMA_VERSION == schema.SCHEMA_VERSION == "1.0"


# ---------------------------------------------------------------------------
# Version stamp on export
# ---------------------------------------------------------------------------


def test_exported_artifact_carries_version_stamp():
    data = export_config(_config())
    assert data["schema_version"] == CURRENT_SCHEMA_VERSION


def test_export_json_is_valid_json_with_stamp():
    text = export_config_json(_config())
    parsed = json.loads(text)
    assert parsed["schema_version"] == CURRENT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Round-trip stability
# ---------------------------------------------------------------------------


def test_export_import_round_trip_equal_config():
    cfg = _config()
    reloaded = import_config(export_config(cfg))
    assert reloaded == cfg


def test_export_import_export_stable_via_dict():
    cfg = _config()
    first = export_config(cfg)
    reloaded = import_config(first)
    second = export_config(reloaded)
    assert second == first


def test_export_import_export_stable_via_json_string():
    cfg = _config()
    first = export_config_json(cfg)
    reloaded = import_config(first)
    second = export_config_json(reloaded)
    assert second == first


def test_import_accepts_json_string():
    cfg = _config()
    reloaded = import_config(export_config_json(cfg))
    assert reloaded == cfg


# ---------------------------------------------------------------------------
# Invalid artifacts rejected with actionable field errors
# ---------------------------------------------------------------------------


def test_import_missing_name_rejected_with_fields():
    bad = export_config(_config())
    del bad["name"]
    with pytest.raises(ConfigValidationError) as exc:
        import_config(bad)
    err = exc.value
    assert hasattr(err, "fields")
    assert any(f["field"] == "name" for f in err.fields)
    # message is actionable / mentions the offending field
    assert "name" in str(err)


def test_import_judge_based_without_judge_rejected():
    bad = export_config(_config())
    # drop the judge node so judge_based authority has no judge
    bad["participants"]["nodes"] = [
        n for n in bad["participants"]["nodes"] if "judge" not in n["roles"]
    ]
    # also drop references to the removed node to isolate the judge error
    bad["interaction"]["topology"]["edges"] = []
    bad["interaction"]["protocol"]["order"] = ["alice"]
    with pytest.raises(ConfigValidationError) as exc:
        import_config(bad)
    assert "judge" in str(exc.value)
    assert exc.value.fields  # structured errors present


def test_import_unknown_field_rejected():
    bad = export_config(_config())
    bad["totally_bogus"] = 1
    with pytest.raises(ConfigValidationError) as exc:
        import_config(bad)
    assert any("totally_bogus" in f["field"] for f in exc.value.fields)


# ---------------------------------------------------------------------------
# migrate(): no-op on current, mechanism works, rejects unknown/newer
# ---------------------------------------------------------------------------


def test_migrate_current_version_is_noop():
    data = export_config(_config())
    out = migrate(data)
    assert out == data
    assert out["schema_version"] == CURRENT_SCHEMA_VERSION


def test_migrate_fills_missing_version_as_current():
    data = export_config(_config())
    del data["schema_version"]
    out = migrate(data)
    assert out["schema_version"] == CURRENT_SCHEMA_VERSION


def test_migrate_rejects_unknown_newer_version():
    data = export_config(_config())
    data["schema_version"] = "99.0"
    with pytest.raises(ConfigValidationError) as exc:
        migrate(data)
    assert "99.0" in str(exc.value)
    assert "unsupported schema_version" in str(exc.value)


def test_import_rejects_unknown_version():
    data = export_config(_config())
    data["schema_version"] = "2.5"
    with pytest.raises(ConfigValidationError):
        import_config(data)


def test_migration_registry_mechanism_applies_step(monkeypatch):
    """A registered one-step migration should be applied by ``migrate``.

    We register a temporary ``"0.9" -> CURRENT`` migration into a copied
    registry so the real (empty) registry is not polluted across tests.
    """
    calls = {"n": 0}

    def _upgrade(d: dict) -> dict:
        calls["n"] += 1
        out = dict(d)
        out["schema_version"] = CURRENT_SCHEMA_VERSION
        return out

    monkeypatch.setitem(version._MIGRATIONS, "0.9", _upgrade)

    data = export_config(_config())
    data["schema_version"] = "0.9"
    out = migrate(data)

    assert calls["n"] == 1
    assert out["schema_version"] == CURRENT_SCHEMA_VERSION
    # and the migrated artifact validates
    assert import_config(out).name == "RoundTrip"


# ---------------------------------------------------------------------------
# Malformed JSON string
# ---------------------------------------------------------------------------


def test_import_malformed_json_raises_clear_error():
    with pytest.raises(ConfigValidationError) as exc:
        import_config("{ not valid json ]")
    assert "malformed JSON" in str(exc.value)


def test_import_non_object_json_rejected():
    with pytest.raises(ConfigValidationError) as exc:
        import_config("[1, 2, 3]")
    assert "must be an object" in str(exc.value)


# ---------------------------------------------------------------------------
# save_config / load_config file round-trip
# ---------------------------------------------------------------------------


def test_save_load_round_trip(tmp_path):
    cfg = _config()
    path = tmp_path / "my_config.json"
    written = save_config(cfg, path)
    assert written.exists()
    loaded = load_config(path)
    assert loaded == cfg


def test_save_creates_parent_dirs(tmp_path):
    cfg = _config()
    path = tmp_path / "nested" / "dir" / "config.json"
    save_config(cfg, path)
    assert path.exists()
    assert load_config(path) == cfg


def test_load_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config("this_file_does_not_exist_12345.json")


# ---------------------------------------------------------------------------
# Presentation-only ``ui`` layout (task 11.4)
# ---------------------------------------------------------------------------

_UI = {
    "nodes": {
        "alice": {"x": 10.5, "y": -20},
        "__start__": {"x": -180, "y": 0},
        "__end__": {"x": 400, "y": 0},
        "ghost": {"x": 1, "y": 1},  # stale key: tolerated, not cross-validated
    },
    "edges": {
        "alice->jury": {"x": 0, "y": 30},
        "__start__->alice": {"x": -5, "y": 5},
        "jury->__end__": {"x": 2.5, "y": -2.5},
    },
}


def test_ui_is_optional_and_defaults_to_none():
    cfg = _config()
    assert cfg.ui is None
    # Older artifacts without the key still import cleanly.
    data = export_config(cfg)
    data.pop("ui", None)
    assert import_config(data).ui is None
    assert CURRENT_SCHEMA_VERSION == "1.0"


def test_ui_round_trips_through_export_import():
    cfg = _config(ui=_UI)
    exported = export_config(cfg)
    assert exported["ui"]["nodes"]["__start__"] == {"x": -180.0, "y": 0.0}
    assert exported["ui"]["edges"]["alice->jury"] == {"x": 0.0, "y": 30.0}
    reloaded = import_config(export_config_json(cfg))
    assert reloaded == cfg
    assert reloaded.ui is not None
    assert set(reloaded.ui.nodes) == set(_UI["nodes"])
    assert set(reloaded.ui.edges) == set(_UI["edges"])


def test_ui_partial_shapes_are_accepted():
    assert _config(ui={}).ui.nodes == {}
    assert _config(ui={"nodes": {"alice": {"x": 1, "y": 2}}}).ui.edges == {}


@pytest.mark.parametrize(
    "bad_ui",
    [
        {"nodes": {}, "zoom": 1.5},  # unknown key inside UiLayout
        {"nodes": {"alice": {"x": 1}}},  # point missing y
        {"nodes": {"alice": {"x": 1, "y": 2, "z": 3}}},  # extra key on a point
        {"edges": {"alice->jury": {"x": "left", "y": 0}}},  # non-numeric
        {"nodes": [1, 2]},  # wrong container type
    ],
)
def test_ui_invalid_shapes_rejected(bad_ui):
    data = export_config(_config())
    data["ui"] = bad_ui
    with pytest.raises(ConfigValidationError) as exc:
        import_config(data)
    fields = getattr(exc.value, "fields", [])
    assert any(f["field"].startswith("ui") for f in fields)
