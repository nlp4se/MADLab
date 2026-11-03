"""Unit tests for dataset loading and column mapping (task 4.2).

Cover CSV loading, columns/row_count exposure, column→placeholder mapping and
its validation, per-row instance building, sample-row preview, and the
optional ground-truth column. Exercised against the real research dataset
``data/datasets/PROMISE/nfr-small.csv``.

Validates: Requirements 10.1, 10.3
"""

from pathlib import Path

import pandas as pd
import pytest

from mad.errors import TemplateError
from mad.input import Dataset, resolve_template


# ---------------------------------------------------------------------------
# Locate the real PROMISE dataset relative to the repo root.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
NFR_SMALL = REPO_ROOT / "data" / "datasets" / "PROMISE" / "nfr-small.csv"


@pytest.fixture()
def nfr_dataset() -> Dataset:
    assert NFR_SMALL.exists(), f"fixture dataset missing: {NFR_SMALL}"
    return Dataset.from_csv(NFR_SMALL)


# ---------------------------------------------------------------------------
# Loading + shape metadata
# ---------------------------------------------------------------------------


def test_from_csv_exposes_columns_and_row_count(nfr_dataset: Dataset):
    assert nfr_dataset.columns == ["requirement", "type"]
    assert nfr_dataset.row_count == 2
    assert len(nfr_dataset) == 2


def test_from_csv_default_name_is_file_stem(nfr_dataset: Dataset):
    assert nfr_dataset.name == "nfr-small"
    assert nfr_dataset.source_path == NFR_SMALL


def test_from_csv_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        Dataset.from_csv(REPO_ROOT / "data" / "datasets" / "does-not-exist.csv")


def test_from_csv_empty_file_raises(tmp_path: Path):
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        Dataset.from_csv(empty)


def test_from_dataframe_constructor():
    frame = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    ds = Dataset(frame, name="mem")
    assert ds.columns == ["a", "b"]
    assert ds.row_count == 2
    assert ds.name == "mem"


# ---------------------------------------------------------------------------
# Column → placeholder mapping
# ---------------------------------------------------------------------------


def test_map_columns_valid(nfr_dataset: Dataset):
    mapping = nfr_dataset.map_columns({"requirement": "requirement"})
    assert mapping == {"requirement": "requirement"}


def test_map_columns_rename_to_different_placeholder(nfr_dataset: Dataset):
    mapping = nfr_dataset.map_columns({"requirement": "text"})
    assert mapping == {"requirement": "text"}


def test_map_columns_unknown_column_raises(nfr_dataset: Dataset):
    with pytest.raises(TemplateError) as exc:
        nfr_dataset.map_columns({"missing": "requirement"})
    assert "missing" in str(exc.value)


def test_map_columns_template_coverage_ok(nfr_dataset: Dataset):
    mapping = nfr_dataset.map_columns(
        {"requirement": "requirement"},
        template="Classify: {{requirement}}",
    )
    assert mapping == {"requirement": "requirement"}


def test_map_columns_template_uncovered_placeholder_raises(nfr_dataset: Dataset):
    with pytest.raises(TemplateError) as exc:
        nfr_dataset.map_columns(
            {"requirement": "requirement"},
            template="Classify: {{requirement}} in {{context}}",
        )
    assert "context" in str(exc.value)


# ---------------------------------------------------------------------------
# Row → instance
# ---------------------------------------------------------------------------


def test_instance_builds_placeholder_dict(nfr_dataset: Dataset):
    inst = nfr_dataset.instance(0, {"requirement": "requirement"})
    assert set(inst.keys()) == {"requirement"}
    assert inst["requirement"].startswith("The system shall have a MDI form")


def test_instance_maps_column_to_renamed_placeholder(nfr_dataset: Dataset):
    inst = nfr_dataset.instance(1, {"requirement": "text"})
    assert inst == {"text": "The system shall display Events in a vertical table by time."}


def test_instance_out_of_range_raises(nfr_dataset: Dataset):
    with pytest.raises(IndexError):
        nfr_dataset.instance(5, {"requirement": "requirement"})


def test_instances_iterates_all_rows(nfr_dataset: Dataset):
    rows = list(nfr_dataset.instances({"requirement": "requirement"}))
    assert len(rows) == 2
    assert all("requirement" in r for r in rows)


# ---------------------------------------------------------------------------
# Preview (Req 10.3)
# ---------------------------------------------------------------------------


def test_preview_resolves_sample_row(nfr_dataset: Dataset):
    out = nfr_dataset.preview(
        "Classify this requirement: {{requirement}}",
        {"requirement": "requirement"},
    )
    assert out == (
        "Classify this requirement: "
        "The system shall have a MDI form that allows for the viewing of "
        "the graph and the data table."
    )


def test_preview_respects_index(nfr_dataset: Dataset):
    out = nfr_dataset.preview(
        "R: {{requirement}}",
        {"requirement": "requirement"},
        index=1,
    )
    assert out == "R: The system shall display Events in a vertical table by time."


def test_preview_renamed_placeholder(nfr_dataset: Dataset):
    out = nfr_dataset.preview("{{text}}", {"requirement": "text"})
    assert out.startswith("The system shall have a MDI form")


def test_preview_uncovered_placeholder_raises(nfr_dataset: Dataset):
    with pytest.raises(TemplateError):
        nfr_dataset.preview("{{requirement}} {{extra}}", {"requirement": "requirement"})


def test_preview_out_of_range_raises(nfr_dataset: Dataset):
    with pytest.raises(IndexError):
        nfr_dataset.preview("{{requirement}}", {"requirement": "requirement"}, index=9)


def test_preview_matches_manual_resolution(nfr_dataset: Dataset):
    """Preview is equivalent to resolving the instance directly."""
    template = "Req: {{requirement}}"
    mapping = {"requirement": "requirement"}
    expected = resolve_template(template, nfr_dataset.instance(0, mapping))
    assert nfr_dataset.preview(template, mapping) == expected


# ---------------------------------------------------------------------------
# Optional ground-truth column (Req 10.7)
# ---------------------------------------------------------------------------


def test_ground_truth_reads_label(nfr_dataset: Dataset):
    assert nfr_dataset.ground_truth(0, "type") == "F"
    assert nfr_dataset.ground_truth(1, "type") == "F"


def test_ground_truths_reads_all_labels(nfr_dataset: Dataset):
    assert nfr_dataset.ground_truths("type") == ["F", "F"]


def test_ground_truth_unknown_column_raises(nfr_dataset: Dataset):
    with pytest.raises(TemplateError):
        nfr_dataset.ground_truth(0, "label")


def test_ground_truth_out_of_range_raises(nfr_dataset: Dataset):
    with pytest.raises(IndexError):
        nfr_dataset.ground_truth(9, "type")


def test_ground_truths_unknown_column_raises(nfr_dataset: Dataset):
    with pytest.raises(TemplateError):
        nfr_dataset.ground_truths("nope")
