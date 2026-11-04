"""Pydantic v2 models for the MAD Configuration Artifact.

The *MAD Configuration Artifact* is the single versioned JSON document that
instantiates the full three-dimensional taxonomy (Participants / Interaction /
Agreement) defined in :mod:`mad.taxonomy.catalog`. It is the architectural
spine of the platform: the web API, the headless engine, the CLI, and the
persistence layer all read and write this one structure.

Design notes (see design.md "The MAD Configuration Artifact"):

* Field keys mirror the catalog value keys so that a configuration's selected
  values line up with the data-driven taxonomy. Where a selection is a closed
  set, the field is typed as a ``Literal`` of the exact catalog keys.
* The catalog's ``executable`` flags drive "under development" labelling. The
  artifact itself merely *carries* values; it does not block on non-executable
  selections. :meth:`MADConfig.under_development_values` inspects a config and
  returns any non-executable selections so the execution layer can gate runs
  while validation and saving stay permissive.
* Structural/semantic invariants that cross fields (edge endpoints referencing
  existing nodes, judge-based authority requiring a judge, ...) are enforced by
  model-level validators that raise ``ValueError`` with actionable,
  UI-friendly messages.

This module stays importable without any web dependency: it imports only
``pydantic`` and the dependency-light catalog.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal, Optional

from pydantic import BaseModel as _PydanticBaseModel
from pydantic import Field, ValidationError, model_validator

from mad.taxonomy import catalog

# ---------------------------------------------------------------------------
# Schema version. Task 1.3 adds ``version.py``; until then this module-level
# constant is the source of truth and 1.3 may re-export / centralise it.
# ---------------------------------------------------------------------------
SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Catalog-derived key sets (authoritative). Used to validate role entries and
# to drive the under-development gating hook. Keys are unique only *within* a
# sub-dimension in the catalog, so we always disambiguate by sub-dimension.
# ---------------------------------------------------------------------------

_ROLE_KEYS: frozenset[str] = frozenset(
    v.key for v in catalog.get_subdimension("participants", "roles").values
)
_METADATA_KEYS: frozenset[str] = frozenset(
    v.key
    for v in catalog.get_subdimension("interaction", "format_content_metadata").values
)
_CUSTOM_ROLE_PREFIX = "custom:"


class _Base(_PydanticBaseModel):
    """Shared base: forbid unknown fields so typos surface as field errors."""

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Participants dimension
# ---------------------------------------------------------------------------


class Persona(_Base):
    """Prompt-designed persona content for a participant.

    All attributes are free-form text; ``template_ref`` optionally references a
    predefined persona pattern (resolved in task 1.4). Validation here is
    loose — any non-empty string is accepted.
    """

    background: Optional[str] = None
    personality: Optional[str] = None
    stance: Optional[str] = None
    template_ref: Optional[str] = None


class BaseModelSpec(_Base):
    """Base-model selection for a participant.

    Named ``BaseModelSpec`` to avoid clashing with :class:`pydantic.BaseModel`.
    ``provider_id`` / ``model_key`` are nullable so a configuration can be
    authored before any provider exists; the execution layer validates their
    presence at run time.
    """

    provider_id: Optional[str] = None
    model_key: Optional[str] = None
    family: Literal["open_weight", "closed_weight"] = "closed_weight"
    temperature: float = 0.0
    params: dict[str, Any] = Field(default_factory=dict)


class ParticipantNode(_Base):
    """A single participant (node ``v`` in ``V``)."""

    id: str
    label: str
    roles: list[str] = Field(default_factory=lambda: ["debater"])
    persona: Persona = Field(default_factory=Persona)
    base_model: BaseModelSpec = Field(default_factory=BaseModelSpec)
    system_prompt: Optional[str] = None
    group: Optional[str] = None

    @model_validator(mode="after")
    def _check_roles(self) -> "ParticipantNode":
        for role in self.roles:
            if role.startswith(_CUSTOM_ROLE_PREFIX):
                custom_name = role[len(_CUSTOM_ROLE_PREFIX):]
                if not custom_name.strip():
                    raise ValueError(
                        f"node '{self.id}': custom role '{role}' must have a "
                        f"non-empty name after the '{_CUSTOM_ROLE_PREFIX}' prefix"
                    )
            elif role not in _ROLE_KEYS:
                allowed = ", ".join(sorted(_ROLE_KEYS))
                raise ValueError(
                    f"node '{self.id}': role '{role}' is not a known role; "
                    f"use one of [{allowed}] or a '{_CUSTOM_ROLE_PREFIX}<name>' value"
                )
        return self


class Group(_Base):
    """A labelled grouping of participants (for the ``grouped`` topology)."""

    id: str
    label: str
    color: Optional[str] = None


class Participants(_Base):
    """The Participants dimension: who debates (``V``)."""

    base_model_heterogeneity: Literal["homogeneous", "heterogeneous"] = "homogeneous"
    persona_heterogeneity: Literal["homogeneous", "heterogeneous"] = "homogeneous"
    persona_assignment: Literal["unspecified", "manual", "automatic"] = "unspecified"
    nodes: list[ParticipantNode] = Field(default_factory=list)
    groups: list[Group] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Interaction dimension
# ---------------------------------------------------------------------------


class Edge(_Base):
    """A directed (or undirected) communication channel in ``E``."""

    source: str
    target: str
    directed: bool = True
    label: Optional[str] = None
    color: Optional[str] = None


class Topology(_Base):
    """Communication graph ``G=(V,E)`` and its adaptability.

    ``entry_nodes`` / ``exit_nodes`` are the optional, persisted Start/End IO
    connections drawn on the designer canvas:

    * ``entry_nodes`` — participants that receive the task input in their
      system prompt. ``None`` (default) = every participant that speaks in the
      rounds receives it.
    * ``exit_nodes`` — participants whose outputs form the final decision.
      ``None`` (default) = the judge decides (``judge_based``) or the debaters'
      latest outputs are aggregated (otherwise).

    Both default to ``None`` so existing configs are unchanged (no schema
    version bump). When set, each must be a non-empty list of existing node ids
    (see :class:`MADConfig` validators).
    """

    adaptability: Literal["static", "dynamic"] = "static"
    dynamic_policy: Optional[dict[str, Any]] = None
    structure: Literal[
        "fully_connected", "grouped", "structured_network"
    ] = "fully_connected"
    pattern: Optional[
        Literal["chain", "ring", "star", "tree", "layered", "sparse", "bipartite"]
    ] = None
    edges: list[Edge] = Field(default_factory=list)
    entry_nodes: Optional[list[str]] = None
    exit_nodes: Optional[list[str]] = None


class Phase(_Base):
    """One phase of a hybrid protocol, tagged sequential or simultaneous."""

    mechanism: Literal["sequential", "simultaneous"]
    participants: list[str] = Field(default_factory=list)


class Protocol(_Base):
    """Temporal edge activation ``E(t)``: turn-taking and ordering."""

    mechanism: Literal["sequential", "simultaneous", "hybrid"] = "sequential"
    max_rounds: int = Field(default=1, ge=1)
    ordering: Literal["fixed", "randomized", "coordinator"] = "fixed"
    order: list[str] = Field(default_factory=list)
    phases: Optional[list[Phase]] = None


class ContentSpec(_Base):
    """Message content transformation ``m̃=f(m)`` and attached signals."""

    strategy: Literal["verbatim", "summarized", "other"] = "verbatim"
    metadata_signals: list[str] = Field(default_factory=list)
    transform_ref: Optional[str] = None

    @model_validator(mode="after")
    def _check_metadata_signals(self) -> "ContentSpec":
        unknown = [s for s in self.metadata_signals if s not in _METADATA_KEYS]
        if unknown:
            allowed = ", ".join(sorted(_METADATA_KEYS))
            raise ValueError(
                f"unknown metadata signal(s) {unknown}; allowed signals are "
                f"[{allowed}]"
            )
        return self


class Format(_Base):
    """Message format: syntax, content transform, and memory scope."""

    syntax: Literal["natural_language", "embeddings"] = "natural_language"
    content: ContentSpec = Field(default_factory=ContentSpec)
    memory: Literal[
        "short_term", "long_term", "knowledge_retrieval", "parametric"
    ] = "short_term"


class Interaction(_Base):
    """The Interaction dimension: topology, protocol, and format."""

    topology: Topology = Field(default_factory=Topology)
    protocol: Protocol = Field(default_factory=Protocol)
    format: Format = Field(default_factory=Format)


# ---------------------------------------------------------------------------
# Agreement dimension
# ---------------------------------------------------------------------------


class Agreement(_Base):
    """The Agreement dimension: the ``(authority, resolution)`` pair."""

    authority: Literal[
        "collective", "judge_based", "hybrid", "other"
    ] = "collective"
    resolution: Literal[
        "argument_evaluation",
        "majority_vote",
        "weighted_vote",
        "scoring",
        "average",
        "consensus",
    ] = "majority_vote"
    resolution_params: dict[str, Any] = Field(default_factory=dict)
    output_schema: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Input specification
# ---------------------------------------------------------------------------


class AdHocField(_Base):
    """A single ad-hoc input field bound to a template placeholder."""

    key: str
    label: str


class InputSpec(_Base):
    """How instances are produced from a prompt template and inputs."""

    template: str = ""
    placeholders: list[str] = Field(default_factory=list)
    ad_hoc_fields: list[AdHocField] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Presentation-only canvas layout
# ---------------------------------------------------------------------------


class Point(_Base):
    """A 2-D point in designer canvas (flow) coordinates."""

    x: float
    y: float


class UiLayout(_Base):
    """Presentation-only designer layout. The engine NEVER reads this.

    It only records how the visual designer draws the graph so a saved config
    reopens with the same picture:

    * ``nodes`` — canvas position per node id. Keys are participant ids and may
      also include the synthetic Start/End sentinels ``__start__`` / ``__end__``.
    * ``edges`` — bend offset per canvas edge id (``source->target`` for real
      edges, ``__start__->X`` / ``X->__end__`` for the IO connectors): the
      offset of the edge's drag knob from the straight midpoint between the two
      node centres.

    Keys are deliberately NOT cross-validated against the graph: stale keys
    (e.g. for a deleted node) are harmless and simply ignored by the designer.
    Has no effect on execution, validation of the debate, or results.
    """

    nodes: dict[str, Point] = Field(default_factory=dict)
    edges: dict[str, Point] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Top-level artifact
# ---------------------------------------------------------------------------


# Catalog keys that are "under development" (non-executable), kept as a frozen
# set for fast membership checks by the gating hook.
_UNDER_DEV_KEYS: frozenset[str] = frozenset(catalog.under_development_keys())


class MADConfig(_Base):
    """The complete MAD Configuration Artifact.

    This is the normative, versioned schema. A config may select "under
    development" taxonomy values and still validate and persist; use
    :meth:`under_development_values` to discover such selections before running.
    """

    schema_version: str = SCHEMA_VERSION
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    participants: Participants = Field(default_factory=Participants)
    interaction: Interaction = Field(default_factory=Interaction)
    agreement: Agreement = Field(default_factory=Agreement)
    input_spec: InputSpec = Field(default_factory=InputSpec)
    # Presentation-only designer layout (node positions + edge bends). Ignored
    # by the engine; optional so existing artifacts stay valid unchanged.
    ui: Optional[UiLayout] = None

    # -- semantic / cross-field validators ---------------------------------

    @model_validator(mode="after")
    def _check_unique_ids(self) -> "MADConfig":
        node_ids = [n.id for n in self.participants.nodes]
        dupes = _duplicates(node_ids)
        if dupes:
            raise ValueError(
                f"participant node ids must be unique; duplicated: {sorted(dupes)}"
            )
        group_ids = [g.id for g in self.participants.groups]
        gdupes = _duplicates(group_ids)
        if gdupes:
            raise ValueError(
                f"group ids must be unique; duplicated: {sorted(gdupes)}"
            )
        return self

    @model_validator(mode="after")
    def _check_edge_endpoints(self) -> "MADConfig":
        node_ids = {n.id for n in self.participants.nodes}
        for edge in self.interaction.topology.edges:
            if edge.source not in node_ids:
                raise ValueError(
                    f"edge source '{edge.source}' does not reference an existing "
                    f"participant node"
                )
            if edge.target not in node_ids:
                raise ValueError(
                    f"edge target '{edge.target}' does not reference an existing "
                    f"participant node"
                )
        return self

    @model_validator(mode="after")
    def _check_order_and_phase_refs(self) -> "MADConfig":
        node_ids = {n.id for n in self.participants.nodes}
        for ref in self.interaction.protocol.order:
            if ref not in node_ids:
                raise ValueError(
                    f"protocol order entry '{ref}' does not reference an existing "
                    f"participant node"
                )
        for i, phase in enumerate(self.interaction.protocol.phases or []):
            for ref in phase.participants:
                if ref not in node_ids:
                    raise ValueError(
                        f"phase {i} participant '{ref}' does not reference an "
                        f"existing participant node"
                    )
        return self

    @model_validator(mode="after")
    def _check_group_refs(self) -> "MADConfig":
        group_ids = {g.id for g in self.participants.groups}
        for node in self.participants.nodes:
            if node.group is not None and node.group not in group_ids:
                raise ValueError(
                    f"node '{node.id}' references group '{node.group}' which is not "
                    f"defined in participants.groups"
                )
        return self

    @model_validator(mode="after")
    def _check_judge_authority(self) -> "MADConfig":
        if self.agreement.authority == "judge_based":
            has_judge = any(
                "judge" in node.roles for node in self.participants.nodes
            )
            if not has_judge:
                raise ValueError(
                    "judge_based authority requires at least one node with the "
                    "'judge' role"
                )
        return self

    @model_validator(mode="after")
    def _check_io_nodes(self) -> "MADConfig":
        """Validate the optional Start/End IO connections (entry/exit nodes)."""
        node_ids = {n.id for n in self.participants.nodes}
        topo = self.interaction.topology
        for field_name in ("entry_nodes", "exit_nodes"):
            refs = getattr(topo, field_name)
            if refs is None:
                continue
            if len(refs) == 0:
                raise ValueError(
                    f"interaction.topology.{field_name} must be non-empty when "
                    f"set; connect at least one participant or reset it to null "
                    f"(default)"
                )
            for ref in refs:
                if ref not in node_ids:
                    raise ValueError(
                        f"interaction.topology.{field_name} entry '{ref}' does not "
                        f"reference an existing participant node"
                    )
        if self.agreement.authority == "judge_based" and topo.exit_nodes is not None:
            judge_ids = {
                n.id for n in self.participants.nodes if "judge" in n.roles
            }
            if not any(ref in judge_ids for ref in topo.exit_nodes):
                raise ValueError(
                    "judge_based authority requires interaction.topology.exit_nodes "
                    "to include at least one node with the 'judge' role"
                )
        return self

    @model_validator(mode="after")
    def _check_resolution_params(self) -> "MADConfig":
        if (
            self.agreement.resolution in {"weighted_vote", "scoring"}
            and not self.agreement.resolution_params
        ):
            raise ValueError(
                f"resolution '{self.agreement.resolution}' requires non-empty "
                f"resolution_params (e.g. weights / scoring config)"
            )
        return self

    @model_validator(mode="after")
    def _check_structured_network_pattern(self) -> "MADConfig":
        topo = self.interaction.topology
        if topo.structure == "structured_network" and topo.pattern is None:
            raise ValueError(
                "structured_network topology requires a 'pattern' "
                "(one of chain, ring, star, tree, layered, sparse, bipartite)"
            )
        return self

    # -- executable-flag gating hook (NOT a validator) ---------------------

    def under_development_values(self) -> list[str]:
        """Return the config's selected taxonomy values that are not executable.

        Inspects the chosen values against the catalog ``executable`` flags and
        returns the keys of any "under development" selections (e.g.
        ``automatic`` persona assignment, ``dynamic`` topology, ``coordinator``
        ordering, ``embeddings`` syntax, ``other`` content strategy,
        ``long_term`` / ``knowledge_retrieval`` / ``parametric`` memory).

        This does *not* raise — validation and saving stay permissive. The
        execution layer calls this to gate runs. The returned list preserves a
        stable dimension order and is de-duplicated.
        """
        selected: list[str] = []

        p = self.participants
        selected.append(p.base_model_heterogeneity)
        selected.append(p.persona_heterogeneity)
        selected.append(p.persona_assignment)

        topo = self.interaction.topology
        selected.append(topo.adaptability)
        selected.append(topo.structure)
        if topo.pattern is not None:
            selected.append(topo.pattern)

        proto = self.interaction.protocol
        selected.append(proto.mechanism)
        selected.append(proto.ordering)

        fmt = self.interaction.format
        selected.append(fmt.syntax)
        selected.append(fmt.content.strategy)
        selected.extend(fmt.content.metadata_signals)
        selected.append(fmt.memory)

        selected.append(self.agreement.authority)
        selected.append(self.agreement.resolution)

        result: list[str] = []
        seen: set[str] = set()
        for key in selected:
            if key in _UNDER_DEV_KEYS and key not in seen:
                seen.add(key)
                result.append(key)
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _duplicates(items: list[str]) -> set[str]:
    """Return the set of values appearing more than once in ``items``."""
    seen: set[str] = set()
    dupes: set[str] = set()
    for item in items:
        if item in seen:
            dupes.add(item)
        else:
            seen.add(item)
    return dupes


def validation_error_to_fields(error: ValidationError) -> list[dict[str, str]]:
    """Convert a Pydantic :class:`ValidationError` to UI-friendly field errors.

    Returns a list of ``{"field": <dotted path>, "message": <message>}`` dicts,
    one per underlying error. The dotted ``field`` path mirrors the JSON shape
    (e.g. ``"participants.nodes.0.roles"``). ``model_validator`` failures that
    are not tied to a single field surface with an empty field path (or the
    model root), carrying the actionable message raised by the validator.

    This is the small helper the API layer (task 6.3) uses to translate schema
    validation failures into structured responses.
    """
    fields: list[dict[str, str]] = []
    for err in error.errors():
        loc = err.get("loc", ())
        field_path = ".".join(str(part) for part in loc)
        fields.append({"field": field_path, "message": err.get("msg", "")})
    return fields


__all__ = [
    "SCHEMA_VERSION",
    "Persona",
    "BaseModelSpec",
    "ParticipantNode",
    "Group",
    "Participants",
    "Edge",
    "Topology",
    "Phase",
    "Protocol",
    "ContentSpec",
    "Format",
    "Interaction",
    "Agreement",
    "AdHocField",
    "InputSpec",
    "Point",
    "UiLayout",
    "MADConfig",
    "validation_error_to_fields",
]
