"""Input binding: template placeholder resolution and dataset loading.

Template resolution (task 4.1) is implemented in :mod:`mad.input.template`;
dataset loading / column mapping (task 4.2) in :mod:`mad.input.dataset`.
"""

from mad.input.dataset import ColumnMapping, Dataset
from mad.input.template import (
    PLACEHOLDER_PATTERN,
    extract_placeholders,
    resolve_template,
    validate_template,
)

__all__ = [
    "PLACEHOLDER_PATTERN",
    "extract_placeholders",
    "resolve_template",
    "validate_template",
    "ColumnMapping",
    "Dataset",
]
