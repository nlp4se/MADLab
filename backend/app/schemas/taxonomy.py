"""Response DTOs for the ``GET /api/taxonomy`` endpoint (Reqs 7.4, 12.3).

The taxonomy payload is *data-driven*: the engine's catalog
(:mod:`mad.taxonomy.catalog`) and template layer (:mod:`mad.taxonomy.templates`)
are the single source of truth, and this endpoint serializes them verbatim so
the frontend can render configuration forms and the website can render docs from
the same source (design: "Taxonomy is data, not code").

These Pydantic models exist to:

* give the endpoint an explicit, OpenAPI-documented response contract, and
* keep the web layer (``app/``) from leaking the engine's dataclasses directly
  while still mirroring their shape exactly.

The engine dataclasses already expose ``to_dict()`` producing JSON-ready plain
dicts; :func:`TaxonomyResponse.from_engine` assembles the payload from those,
so adding/editing a taxonomy value stays a data edit in the engine with no
change required here.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from mad.taxonomy import catalog, templates


class ValueDTO(BaseModel):
    """A single taxonomy value (mirrors :class:`mad.taxonomy.catalog.Value`)."""

    key: str
    label: str
    description: str
    default: bool = False
    executable: bool = True
    icon: Optional[str] = None


class SubDimensionDTO(BaseModel):
    """A sub-dimension and its ordered values."""

    key: str
    label: str
    description: str
    selection: str = Field(description="One of 'single', 'multi', or 'attributes'.")
    values: list[ValueDTO] = Field(default_factory=list)


class DimensionDTO(BaseModel):
    """A top-level dimension and its ordered sub-dimensions."""

    key: str
    label: str
    description: str
    subdimensions: list[SubDimensionDTO] = Field(default_factory=list)


class PersonaFieldSetDTO(BaseModel):
    """One concrete persona produced by a persona pattern."""

    name: str
    background: Optional[str] = None
    personality: Optional[str] = None
    stance: Optional[str] = None


class PersonaPatternDTO(BaseModel):
    """A predefined persona pattern (CSUR §4.1)."""

    key: str
    label: str
    description: str
    pair_with: Optional[str] = None
    is_set: bool = False
    personas: list[PersonaFieldSetDTO] = Field(default_factory=list)


class RoleDTO(BaseModel):
    """A predefined functional role (catalog-backed)."""

    key: str
    label: str
    description: str
    icon: Optional[str] = None


class TopologyPatternDTO(BaseModel):
    """A canonical topology pattern (chain/ring/star/... from the catalog)."""

    key: str
    label: str
    description: str
    icon: Optional[str] = None


class TemplatesDTO(BaseModel):
    """The predefined template families served alongside the catalog."""

    persona_patterns: list[PersonaPatternDTO] = Field(default_factory=list)
    roles: list[RoleDTO] = Field(default_factory=list)
    topologies: list[TopologyPatternDTO] = Field(default_factory=list)


class TaxonomyResponse(BaseModel):
    """Full ``GET /api/taxonomy`` payload: catalog + templates + defaults.

    * ``dimensions`` — the complete dimension → sub-dimension → value tree, each
      value carrying ``key``/``label``/``description``/``default``/``executable``
      /``icon`` flags (data-driven forms).
    * ``templates`` — predefined persona patterns, roles, and topology patterns.
    * ``defaults`` — the default single-selection value per sub-dimension
      (``{dimension: {subdimension: value_key}}``) for pre-filling a new config.
    * ``under_development`` — keys of all non-executable ("under development")
      values, so the UI can badge them without re-scanning the tree.
    """

    dimensions: list[DimensionDTO] = Field(default_factory=list)
    templates: TemplatesDTO
    defaults: dict[str, dict[str, str]] = Field(default_factory=dict)
    under_development: list[str] = Field(default_factory=list)

    @classmethod
    def from_engine(cls) -> "TaxonomyResponse":
        """Build the response from the engine catalog + template layer.

        Serializes :data:`mad.taxonomy.catalog.CATALOG` verbatim and gathers the
        predefined templates. Topology patterns are sourced from the
        ``interaction.topology_pattern`` sub-dimension so their labels, icons,
        and descriptions stay defined once in the catalog.
        """
        taxonomy = catalog.to_dict()

        topology_sub = catalog.get_subdimension("interaction", "topology_pattern")
        topology_values = topology_sub.values if topology_sub is not None else ()

        templates_payload = TemplatesDTO(
            persona_patterns=[
                PersonaPatternDTO.model_validate(p.to_dict())
                for p in templates.list_persona_patterns()
            ],
            roles=[
                RoleDTO.model_validate(r.to_dict()) for r in templates.list_roles()
            ],
            topologies=[
                TopologyPatternDTO(
                    key=v.key,
                    label=v.label,
                    description=v.description,
                    icon=v.icon,
                )
                for v in topology_values
            ],
        )

        return cls(
            dimensions=[
                DimensionDTO.model_validate(dim) for dim in taxonomy["dimensions"]
            ],
            templates=templates_payload,
            defaults=catalog.default_config(),
            under_development=list(catalog.under_development_keys()),
        )


__all__ = [
    "ValueDTO",
    "SubDimensionDTO",
    "DimensionDTO",
    "PersonaFieldSetDTO",
    "PersonaPatternDTO",
    "RoleDTO",
    "TopologyPatternDTO",
    "TemplatesDTO",
    "TaxonomyResponse",
]
