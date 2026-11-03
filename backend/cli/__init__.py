"""Headless CLI drivers that call the same services/engine as the API.

Preserves the existing research workflow (config creation, batch runs over CSV,
binary F/NF classification, evaluation) by driving the same service + engine
layer the FastAPI routers use, with no web server (Req 12.4, 12.5). See
:mod:`cli.app` for the command implementations.
"""

from cli.app import build_parser, main

__all__ = ["main", "build_parser"]
