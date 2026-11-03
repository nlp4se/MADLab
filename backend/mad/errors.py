"""Domain error types for the MAD engine.

These are plain Python exceptions with no web/framework dependency. The web
layer (``app``) maps them to structured HTTP responses; the CLI prints them.
Concrete usage arrives with the engine implementation (phases 1-4); the base
hierarchy is defined here so modules can import a stable set of errors.
"""

from __future__ import annotations


class MADError(Exception):
    """Base class for all MAD engine errors."""


class ConfigValidationError(MADError):
    """Raised when a MAD configuration artifact fails validation."""


class UnderDevelopment(MADError):
    """Raised when a configured taxonomy value is not yet executable.

    The configuration can still be saved/persisted; only execution is gated.
    """


class TemplateError(MADError):
    """Raised when an input template cannot be resolved against an instance.

    Typically carries the names of placeholders that have no corresponding
    field in the instance (or in the available-field set during validation).
    """


class ProviderError(MADError):
    """Raised for model-provider resolution, connectivity, or invocation failures."""


class ExecutionError(MADError):
    """Raised when a debate execution fails at runtime."""
