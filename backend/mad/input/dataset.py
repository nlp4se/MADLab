"""Dataset loading and column→placeholder mapping (task 4.2).

A *dataset* is a CSV file where each row becomes one debate instance (Req 10.1).
Before a batch run, the user maps dataset columns onto the input template's
``{{placeholder}}`` tags (Req 10.3) and previews the resolved input for a
sample row. An optional *ground-truth* column is carried alongside so the
evaluation layer can compute metrics when labels are present (Req 10.7).

This module builds on :mod:`mad.input.template`:

* :class:`Dataset` wraps a loaded CSV, exposing ``columns`` and ``row_count``.
* :meth:`Dataset.map_columns` validates a column→placeholder mapping against
  the dataset's columns and a template's placeholders.
* :meth:`Dataset.instance` / :meth:`Dataset.instances` turn rows into instance
  dicts keyed by placeholder name, ready for :func:`resolve_template`.
* :meth:`Dataset.preview` resolves a template for one sample row.
* :meth:`Dataset.ground_truth` reads the optional label column for a row.

Like the rest of ``mad.input`` the module has no web/framework dependency: it
imports only pandas (a backend dependency), the standard library, and the
domain error and template helpers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, Mapping, Optional, Union

import pandas as pd

from mad.errors import TemplateError
from mad.input.template import resolve_template, validate_template

__all__ = ["ColumnMapping", "Dataset"]

# A column→placeholder mapping: maps a *dataset column name* to the
# *placeholder name* it supplies in the input template.
ColumnMapping = Mapping[str, str]


class Dataset:
    """A loaded CSV dataset: one row per debate instance (Req 10.1).

    Instances are produced lazily from the backing :class:`pandas.DataFrame`.
    Column→placeholder mapping, sample-row preview, and an optional
    ground-truth column are all surfaced here so the run launcher and job
    runner can bind a dataset to a configuration's input template.
    """

    def __init__(
        self,
        frame: pd.DataFrame,
        *,
        name: Optional[str] = None,
        source_path: Optional[Union[str, Path]] = None,
    ) -> None:
        """Wrap an already-loaded DataFrame.

        Most callers use :meth:`from_csv`; this constructor is useful for tests
        and for data assembled in memory.

        Args:
            frame: The backing table. Column order is preserved.
            name: Optional human-readable dataset name (defaults to the source
                file stem when loaded via :meth:`from_csv`).
            source_path: Optional path the dataset was loaded from.
        """
        self._frame = frame.reset_index(drop=True)
        self.name = name
        self.source_path = Path(source_path) if source_path is not None else None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @classmethod
    def from_csv(
        cls,
        path: Union[str, Path],
        *,
        name: Optional[str] = None,
        **read_csv_kwargs: Any,
    ) -> "Dataset":
        """Load a CSV file into a :class:`Dataset`.

        Args:
            path: Path to the CSV file.
            name: Optional dataset name; defaults to the file stem.
            **read_csv_kwargs: Extra keyword arguments forwarded to
                :func:`pandas.read_csv` (e.g. ``sep``, ``dtype``).

        Returns:
            A :class:`Dataset` wrapping the loaded rows.

        Raises:
            FileNotFoundError: When ``path`` does not exist.
            ValueError: When the file is empty or cannot be parsed as CSV.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Dataset file not found: {p}")
        try:
            # Keep values as read; stringification happens at resolve time.
            frame = pd.read_csv(p, **read_csv_kwargs)
        except pd.errors.EmptyDataError as exc:
            raise ValueError(f"Dataset file is empty: {p}") from exc
        except pd.errors.ParserError as exc:
            raise ValueError(f"Could not parse CSV file {p}: {exc}") from exc
        return cls(frame, name=name or p.stem, source_path=p)

    # ------------------------------------------------------------------
    # Shape / metadata
    # ------------------------------------------------------------------

    @property
    def columns(self) -> list[str]:
        """The dataset's column names, in file order."""
        return [str(c) for c in self._frame.columns]

    @property
    def row_count(self) -> int:
        """The number of data rows (excluding the header)."""
        return int(len(self._frame))

    def __len__(self) -> int:
        return self.row_count

    # ------------------------------------------------------------------
    # Column → placeholder mapping
    # ------------------------------------------------------------------

    def map_columns(
        self,
        mapping: ColumnMapping,
        *,
        template: Optional[str] = None,
    ) -> dict[str, str]:
        """Validate a column→placeholder ``mapping`` against this dataset.

        The mapping's keys must be columns that exist in the dataset; its
        values are the placeholder names those columns supply. When
        ``template`` is given, every placeholder the template references must
        be covered by the mapping (Req 10.3) — this is the pre-flight check the
        run launcher runs before a batch.

        Args:
            mapping: ``{column_name: placeholder_name}``.
            template: Optional input template to validate coverage against.

        Returns:
            The validated mapping as a plain ``dict`` (defensive copy).

        Raises:
            TemplateError: When a mapped column does not exist in the dataset,
                or when ``template`` references placeholders the mapping does
                not supply.
        """
        resolved = {str(col): str(ph) for col, ph in mapping.items()}

        unknown_cols = [c for c in resolved if c not in set(self.columns)]
        if unknown_cols:
            names = ", ".join(sorted(unknown_cols))
            raise TemplateError(
                f"Column mapping references column(s) not in the dataset: {names}. "
                f"Available columns: {', '.join(self.columns) or '(none)'}."
            )

        if template is not None:
            # validate_template raises TemplateError naming unmet placeholders.
            validate_template(template, resolved.values())

        return resolved

    # ------------------------------------------------------------------
    # Row → instance
    # ------------------------------------------------------------------

    def instance(self, index: int, mapping: ColumnMapping) -> dict[str, Any]:
        """Build one instance dict (placeholder → value) for row ``index``.

        Only the columns named in ``mapping`` are included, keyed by the
        placeholder they supply. The result is suitable for
        :func:`resolve_template`.

        Args:
            index: Zero-based row index.
            mapping: ``{column_name: placeholder_name}``.

        Returns:
            ``{placeholder_name: cell_value}`` for the requested row.

        Raises:
            IndexError: When ``index`` is out of range.
            TemplateError: When a mapped column does not exist.
        """
        if index < 0 or index >= self.row_count:
            raise IndexError(
                f"Row index {index} out of range for dataset with "
                f"{self.row_count} row(s)."
            )
        resolved = self.map_columns(mapping)
        row = self._frame.iloc[index]
        return {placeholder: row[col] for col, placeholder in resolved.items()}

    def instances(self, mapping: ColumnMapping) -> Iterator[dict[str, Any]]:
        """Iterate instance dicts for every row, in file order.

        Args:
            mapping: ``{column_name: placeholder_name}``.

        Yields:
            One ``{placeholder_name: cell_value}`` dict per row.

        Raises:
            TemplateError: When a mapped column does not exist.
        """
        resolved = self.map_columns(mapping)
        for _, row in self._frame.iterrows():
            yield {placeholder: row[col] for col, placeholder in resolved.items()}

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def preview(
        self,
        template: str,
        mapping: ColumnMapping,
        *,
        index: int = 0,
    ) -> str:
        """Resolve ``template`` for a sample row using ``mapping`` (Req 10.3).

        This is what the run launcher shows the user before launching a batch:
        the exact prompt that will be produced for one representative row.

        Args:
            template: The input template with ``{{placeholder}}`` tags.
            mapping: ``{column_name: placeholder_name}``.
            index: Which row to preview (defaults to the first row).

        Returns:
            The resolved prompt for the sample row.

        Raises:
            IndexError: When ``index`` is out of range.
            TemplateError: When the mapping does not cover the template's
                placeholders, or references a missing column.
        """
        # Validate coverage up front so the error names the template gap rather
        # than surfacing as a resolve-time missing-key error.
        self.map_columns(mapping, template=template)
        instance = self.instance(index, mapping)
        return resolve_template(template, instance)

    # ------------------------------------------------------------------
    # Optional ground truth
    # ------------------------------------------------------------------

    def ground_truth(self, index: int, column: str) -> Any:
        """Read the optional ground-truth label for row ``index`` (Req 10.7).

        Args:
            index: Zero-based row index.
            column: The dataset column holding the gold label.

        Returns:
            The label value for the requested row.

        Raises:
            IndexError: When ``index`` is out of range.
            TemplateError: When ``column`` is not a dataset column.
        """
        if column not in set(self.columns):
            raise TemplateError(
                f"Ground-truth column {column!r} is not in the dataset. "
                f"Available columns: {', '.join(self.columns) or '(none)'}."
            )
        if index < 0 or index >= self.row_count:
            raise IndexError(
                f"Row index {index} out of range for dataset with "
                f"{self.row_count} row(s)."
            )
        return self._frame.iloc[index][column]

    def ground_truths(self, column: str) -> list[Any]:
        """Read the ground-truth label for every row, in file order.

        Args:
            column: The dataset column holding the gold labels.

        Returns:
            One label per row.

        Raises:
            TemplateError: When ``column`` is not a dataset column.
        """
        if column not in set(self.columns):
            raise TemplateError(
                f"Ground-truth column {column!r} is not in the dataset. "
                f"Available columns: {', '.join(self.columns) or '(none)'}."
            )
        return list(self._frame[column])

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"Dataset(name={self.name!r}, rows={self.row_count}, "
            f"columns={self.columns})"
        )
