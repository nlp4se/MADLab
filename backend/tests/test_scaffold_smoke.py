"""Smoke tests for the backend scaffold.

These verify the package skeleton imports cleanly and the expected subpackages
exist. They depend only on the standard library + the ``mad``/``app``/``cli``
packages themselves, so they run even before third-party backend dependencies
(FastAPI, LiteLLM, etc.) are installed.
"""

import importlib

import pytest


def test_mad_imports():
    """The top-level engine package imports and exposes a version."""
    mad = importlib.import_module("mad")
    assert isinstance(mad.__version__, str)
    assert mad.__version__


@pytest.mark.parametrize(
    "module_name",
    [
        "mad",
        "mad.taxonomy",
        "mad.engine",
        "mad.providers",
        "mad.input",
        "mad.evaluation",
        "mad.errors",
        "app",
        "app.routers",
        "app.schemas",
        "app.services",
        "app.db",
        "app.security",
        "app.jobs",
        "app.main",
        "cli",
    ],
)
def test_subpackages_import(module_name):
    """Every scaffolded package/module imports without error."""
    assert importlib.import_module(module_name) is not None


def test_errors_hierarchy():
    """Domain error types are defined and rooted at MADError."""
    from mad import errors

    assert issubclass(errors.ConfigValidationError, errors.MADError)
    assert issubclass(errors.UnderDevelopment, errors.MADError)
    assert issubclass(errors.ProviderError, errors.MADError)
    assert issubclass(errors.ExecutionError, errors.MADError)
