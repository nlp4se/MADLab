"""Taxonomy router (Reqs 7.4, 12.3).

Serves the full MAD taxonomy catalog plus the predefined template families in a
single ``GET /api/taxonomy`` payload so the frontend can render data-driven
configuration forms and the website can render docs from the same source.

Layering (Req 12.2): this router reads the dependency-light engine catalog
(:mod:`mad.taxonomy.catalog`) and template layer (:mod:`mad.taxonomy.templates`)
directly through the :class:`~app.schemas.taxonomy.TaxonomyResponse` assembler.
The taxonomy is static, read-only data with no persistence or orchestration, so
no intermediate service is needed; the engine never imports FastAPI.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.taxonomy import TaxonomyResponse

router = APIRouter(tags=["taxonomy"])


@router.get(
    "/taxonomy",
    response_model=TaxonomyResponse,
    summary="Full taxonomy catalog + templates + defaults + flags",
)
def get_taxonomy() -> TaxonomyResponse:
    """Return the complete taxonomy catalog, templates, defaults, and flags.

    The payload carries every dimension → sub-dimension → value (with
    ``key``/``label``/``description``/``default``/``executable``/``icon``), the
    predefined persona/role/topology templates, the default selection per
    single-selection sub-dimension, and the keys of all "under development"
    (non-executable) values.
    """
    return TaxonomyResponse.from_engine()


__all__ = ["router"]
