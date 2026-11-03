"""Unit tests for input template resolution (task 4.1).

Cover placeholder extraction, strict/lenient resolution, missing-placeholder
errors, ad-hoc field mapping, and the pre-flight ``validate_template`` check.

Validates: Requirements 10.2
"""

import pytest

from mad.errors import TemplateError
from mad.input import (
    extract_placeholders,
    resolve_template,
    validate_template,
)


# ---------------------------------------------------------------------------
# extract_placeholders
# ---------------------------------------------------------------------------


def test_extract_placeholders_basic():
    assert extract_placeholders("Classify {{requirement}}") == ["requirement"]


def test_extract_placeholders_multiple_in_order():
    tmpl = "Compare {{a}} against {{b}} and {{c}}"
    assert extract_placeholders(tmpl) == ["a", "b", "c"]


def test_extract_placeholders_deduplicates_preserving_order():
    tmpl = "{{x}} then {{y}} then {{x}} again"
    assert extract_placeholders(tmpl) == ["x", "y"]


def test_extract_placeholders_ignores_internal_whitespace():
    assert extract_placeholders("A {{ requirement }} B") == ["requirement"]


def test_extract_placeholders_empty_and_tagless():
    assert extract_placeholders("") == []
    assert extract_placeholders("no tags here") == []


def test_extract_placeholders_allows_dotted_and_hyphenated_keys():
    tmpl = "{{col.name}} / {{ground-truth}}"
    assert extract_placeholders(tmpl) == ["col.name", "ground-truth"]


# ---------------------------------------------------------------------------
# resolve_template — happy paths
# ---------------------------------------------------------------------------


def test_resolve_single_placeholder():
    out = resolve_template("Classify: {{requirement}}", {"requirement": "The app must log in"})
    assert out == "Classify: The app must log in"


def test_resolve_multiple_and_repeated_placeholders():
    tmpl = "{{a}} and {{b}}; again {{a}}"
    out = resolve_template(tmpl, {"a": "X", "b": "Y"})
    assert out == "X and Y; again X"


def test_resolve_stringifies_non_string_values():
    out = resolve_template("n={{n}} ok={{ok}}", {"n": 42, "ok": True})
    assert out == "n=42 ok=True"


def test_resolve_ignores_internal_whitespace_in_tag():
    out = resolve_template("v={{ value }}", {"value": "hi"})
    assert out == "v=hi"


def test_resolve_empty_template_returns_empty_string():
    assert resolve_template("", {"anything": 1}) == ""


def test_resolve_ignores_extra_instance_fields():
    out = resolve_template("{{a}}", {"a": "ok", "unused": "x"})
    assert out == "ok"


def test_resolve_adhoc_field_mapping():
    """Ad-hoc form keys map onto template placeholders (Req 10.2)."""
    template = "Requirement: {{requirement}}\nContext: {{context}}"
    instance = {"requirement": "login", "context": "mobile"}
    assert resolve_template(template, instance) == (
        "Requirement: login\nContext: mobile"
    )


# ---------------------------------------------------------------------------
# resolve_template — missing placeholders
# ---------------------------------------------------------------------------


def test_resolve_strict_missing_placeholder_raises():
    with pytest.raises(TemplateError) as exc:
        resolve_template("Hi {{name}}", {})
    assert "name" in str(exc.value)


def test_resolve_strict_missing_reports_all_missing():
    with pytest.raises(TemplateError) as exc:
        resolve_template("{{a}} {{b}} {{c}}", {"b": "present"})
    msg = str(exc.value)
    assert "a" in msg and "c" in msg
    # The satisfied placeholder is not reported as missing.
    assert "not present in the instance: a, c" in msg


def test_resolve_non_strict_leaves_unknown_tags_untouched():
    out = resolve_template("{{known}} {{unknown}}", {"known": "ok"}, strict=False)
    assert out == "ok {{unknown}}"


# ---------------------------------------------------------------------------
# validate_template
# ---------------------------------------------------------------------------


def test_validate_template_all_fields_available_returns_empty():
    assert validate_template("{{a}} {{b}}", ["a", "b", "extra"]) == []


def test_validate_template_missing_fields_raises_with_names():
    with pytest.raises(TemplateError) as exc:
        validate_template("{{a}} {{missing}}", ["a"])
    assert "missing" in str(exc.value)


def test_validate_template_no_placeholders_is_ok():
    assert validate_template("static prompt", []) == []
