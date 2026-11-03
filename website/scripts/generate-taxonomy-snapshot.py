#!/usr/bin/env python3
"""Regenerate the committed taxonomy-catalog snapshot consumed by the website.

The website is a *static* site and must not call the backend at runtime
(Req 13.1). To keep the docs from drifting from the product, the taxonomy
catalog + templates are serialized once at build time (from the same source the
``GET /api/taxonomy`` endpoint uses) and committed to
``website/src/data/taxonomy.json``.

This script imports the backend engine catalog/templates via the same
``TaxonomyResponse.from_engine()`` assembler the API uses, so the snapshot shape
matches the live API exactly (dimensions -> sub-dimensions -> values with
key/label/description/default/executable/icon, plus templates:
persona_patterns / roles / topologies).

Usage (from the repo root), using the backend's virtualenv so the engine deps
are importable::

    # Windows (PowerShell)
    backend\\.venv\\Scripts\\python.exe website\\scripts\\generate-taxonomy-snapshot.py

    # macOS / Linux
    backend/.venv/bin/python website/scripts/generate-taxonomy-snapshot.py

Commit the regenerated ``website/src/data/taxonomy.json`` alongside any taxonomy
change in ``backend/mad/taxonomy/``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Resolve repo layout: this file lives at website/scripts/, so the repo root is
# two levels up and the backend package root is <repo>/backend.
HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
OUTPUT_PATH = REPO_ROOT / "website" / "src" / "data" / "taxonomy.json"


def main() -> int:
    # Make the backend packages (``app`` and ``mad``) importable.
    sys.path.insert(0, str(BACKEND_ROOT))

    try:
        from app.schemas.taxonomy import TaxonomyResponse
    except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
        sys.stderr.write(
            "Could not import the backend taxonomy serializer "
            f"({exc}). Run this script with the backend virtualenv's Python so "
            "the engine dependencies (pydantic, etc.) are available:\n"
            "  backend/.venv/bin/python website/scripts/generate-taxonomy-snapshot.py\n"
        )
        return 1

    payload = TaxonomyResponse.from_engine().model_dump()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    rel = OUTPUT_PATH.relative_to(REPO_ROOT)
    print(f"Wrote taxonomy snapshot -> {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
