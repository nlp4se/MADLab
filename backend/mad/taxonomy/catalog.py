"""Data-driven definition of the three-dimensional MAD taxonomy.

This module is the single source of truth for the Multi-Agent Debate taxonomy
described in the ACM CSUR paper *"Multi-Agent Debate Strategies: Survey,
Taxonomy, and Challenges"*. It encodes every dimension -> sub-dimension ->
value as plain data so that:

* the ``/api/taxonomy`` endpoint (task 6.2) can serialize it verbatim,
* the frontend renders configuration forms from it, and
* the documentation website renders the taxonomy docs from the same source.

Adding or editing a taxonomy value is therefore a *data edit* in this file, not
a code rewrite anywhere else.

Design constraints (see design.md "Taxonomy Catalog"):

* Keep this module dependency-light: plain :mod:`dataclasses` + stdlib only. No
  web framework, no pydantic. It is imported by both the headless engine and
  the web layer.
* Every value carries ``key`` (stable snake_case machine id), ``label``
  (human-readable, paper-aligned), ``description`` (short paper-aligned
  sentence), ``default`` (is this the default for its sub-dimension?),
  ``executable`` (``False`` => "under development": configurable and
  persistable but not yet runnable by the engine), and an optional ``icon``
  reference (set for roles and topology patterns, else ``None``).

Sub-dimensions declare a ``selection`` mode:

* ``"single"``     — exactly one value is chosen (mutually exclusive). Exactly
  one value in the sub-dimension is flagged ``default``.
* ``"multi"``      — zero or more values may be chosen (e.g. roles a single
  participant combines, or metadata signals attached to an exchange).
* ``"attributes"`` — descriptive, prompt-designed free-form fields rather than
  enumerated mutually-exclusive choices (e.g. the persona attribute families
  background/personality/stance). These label free-form inputs; they are not
  "values" in the selectable sense and carry no default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Literal, Optional

Selection = Literal["single", "multi", "attributes"]


@dataclass(frozen=True)
class Value:
    """A single taxonomy value within a sub-dimension.

    Attributes:
        key: Stable machine identifier, snake_case, unique within its
            sub-dimension.
        label: Human-readable, paper-aligned name.
        description: Short, paper-aligned sentence describing the value.
        default: Whether this is the default value for its sub-dimension. Only
            meaningful for ``single``-selection sub-dimensions, where exactly
            one value is the default.
        executable: ``True`` if the engine can execute this value today;
            ``False`` marks it "under development" (still configurable and
            persistable, but execution is gated).
        icon: Optional icon reference (e.g. ``"topology/sparse"`` or
            ``"role/judge"``). Set for roles and topology patterns; ``None``
            otherwise.
    """

    key: str
    label: str
    description: str
    default: bool = False
    executable: bool = True
    icon: Optional[str] = None

    def to_dict(self) -> dict:
        """Return a JSON-ready plain ``dict`` for this value."""
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "default": self.default,
            "executable": self.executable,
            "icon": self.icon,
        }


@dataclass(frozen=True)
class SubDimension:
    """A sub-dimension grouping a list of related values.

    Attributes:
        key: Stable machine identifier, snake_case, unique within its dimension.
        label: Human-readable, paper-aligned name.
        description: Short sentence describing what this sub-dimension governs.
        selection: One of ``"single"``, ``"multi"``, or ``"attributes"`` (see
            the module docstring).
        values: Ordered tuple of :class:`Value` entries.
    """

    key: str
    label: str
    description: str
    selection: Selection
    values: tuple[Value, ...] = field(default_factory=tuple)

    @property
    def default(self) -> Optional[Value]:
        """The default value for a ``single``-selection sub-dimension, if any."""
        for value in self.values:
            if value.default:
                return value
        return None

    def get(self, key: str) -> Optional[Value]:
        """Return the value with ``key`` in this sub-dimension, or ``None``."""
        for value in self.values:
            if value.key == key:
                return value
        return None

    def to_dict(self) -> dict:
        """Return a JSON-ready plain ``dict`` for this sub-dimension."""
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "selection": self.selection,
            "values": [value.to_dict() for value in self.values],
        }


@dataclass(frozen=True)
class Dimension:
    """A top-level taxonomy dimension grouping sub-dimensions.

    Attributes:
        key: Stable machine identifier, snake_case (``participants`` /
            ``interaction`` / ``agreement``).
        label: Human-readable, paper-aligned name.
        description: Short sentence describing the dimension.
        subdimensions: Ordered tuple of :class:`SubDimension` entries.
    """

    key: str
    label: str
    description: str
    subdimensions: tuple[SubDimension, ...] = field(default_factory=tuple)

    def get(self, key: str) -> Optional[SubDimension]:
        """Return the sub-dimension with ``key`` in this dimension, or ``None``."""
        for subdimension in self.subdimensions:
            if subdimension.key == key:
                return subdimension
        return None

    def to_dict(self) -> dict:
        """Return a JSON-ready plain ``dict`` for this dimension."""
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "subdimensions": [sub.to_dict() for sub in self.subdimensions],
        }


@dataclass(frozen=True)
class Taxonomy:
    """The complete MAD taxonomy: an ordered collection of dimensions."""

    dimensions: tuple[Dimension, ...] = field(default_factory=tuple)

    def get(self, key: str) -> Optional[Dimension]:
        """Return the dimension with ``key``, or ``None``."""
        for dimension in self.dimensions:
            if dimension.key == key:
                return dimension
        return None

    def to_dict(self) -> dict:
        """Return a JSON-ready plain ``dict`` for the whole taxonomy."""
        return {"dimensions": [dim.to_dict() for dim in self.dimensions]}


# ---------------------------------------------------------------------------
# Catalog content — the complete taxonomy as data.
#
# Values marked ``executable=False`` are "under development": configurable and
# persistable, but the engine cannot run them yet. The set of non-executable
# values is: automatic (persona assignment), dynamic (topology adaptability),
# coordinator (protocol ordering), embeddings (format syntax), other (format
# content), long_term / knowledge_retrieval / parametric (format memory).
# ---------------------------------------------------------------------------

# === Dimension 1: PARTICIPANTS =============================================

_PERSONA_ATTRIBUTES = SubDimension(
    key="persona_attributes",
    label="Persona attributes",
    description=(
        "The three prompt-designed persona attribute families; each is a "
        "free-form field, not a mutually-exclusive choice."
    ),
    selection="attributes",
    values=(
        Value(
            key="background",
            label="Background",
            description="The identity, knowledge, and expertise of the agent.",
        ),
        Value(
            key="personality",
            label="Personality",
            description="Behavioural tendencies that shape how an agent debates.",
        ),
        Value(
            key="stance",
            label="Stance",
            description="A predefined positioning on the topic under discussion.",
        ),
    ),
)

_PERSONA_HETEROGENEITY = SubDimension(
    key="persona_heterogeneity",
    label="Persona heterogeneity",
    description="Whether debaters share one persona or are assigned distinct personas.",
    selection="single",
    values=(
        Value(
            key="homogeneous",
            label="Homogeneous",
            description="All debaters share the same persona.",
            default=True,
        ),
        Value(
            key="heterogeneous",
            label="Heterogeneous",
            description="Debaters are assigned distinct personas.",
        ),
    ),
)

_PERSONA_ASSIGNMENT = SubDimension(
    key="persona_assignment",
    label="Persona assignment",
    description="How personas are assigned to debaters.",
    selection="single",
    values=(
        Value(
            key="unspecified",
            label="Unspecified",
            description="No explicit persona is assigned.",
            default=True,
        ),
        Value(
            key="manual",
            label="Manually identified",
            description="Personas are assigned manually at design time.",
        ),
        Value(
            key="automatic",
            label="Automatically identified",
            description="Personas are automatically assigned at runtime.",
            executable=False,
        ),
    ),
)

_ROLES = SubDimension(
    key="roles",
    label="Roles",
    description=(
        "The functional roles an agent can take; a single participant may "
        "combine multiple roles."
    ),
    selection="multi",
    values=(
        Value(
            key="debater",
            label="Debater",
            description=(
                "Presents and defends positions, engaging in the exchange to "
                "reach consensus."
            ),
            default=True,
            icon="role/debater",
        ),
        Value(
            key="judge",
            label="Judge",
            description="Delivers the final decision and may determine when consensus is reached.",
            icon="role/judge",
        ),
        Value(
            key="summarizer",
            label="Summarizer",
            description="Synthesizes debaters' statements to reduce token consumption.",
            icon="role/summarizer",
        ),
        Value(
            key="leader",
            label="Leader",
            description="Oversees and guides the debate (also called moderator).",
            icon="role/leader",
        ),
        Value(
            key="verifier",
            label="Verifier",
            description="Fact-checks the statements produced by debaters.",
            icon="role/verifier",
        ),
        Value(
            key="editor",
            label="Editor",
            description="Refines and produces the final response from the debate outcome.",
            icon="role/editor",
        ),
    ),
)

_BASE_MODEL_FAMILY = SubDimension(
    key="base_model_family",
    label="Base model family",
    description="Whether the base model is proprietary or publicly available.",
    selection="single",
    values=(
        Value(
            key="closed_weight",
            label="Closed-weight",
            description="Proprietary parameters, accessed via an external provider.",
            default=True,
        ),
        Value(
            key="open_weight",
            label="Open-weight",
            description="Publicly available parameters, deployable locally.",
        ),
    ),
)

_BASE_MODEL_HETEROGENEITY = SubDimension(
    key="base_model_heterogeneity",
    label="Base model heterogeneity",
    description="Whether all agents share one base model or draw on different ones.",
    selection="single",
    values=(
        Value(
            key="homogeneous",
            label="Homogeneous",
            description="All agents share the same base model.",
            default=True,
        ),
        Value(
            key="heterogeneous",
            label="Heterogeneous",
            description="Agents draw on different base models.",
        ),
    ),
)

PARTICIPANTS = Dimension(
    key="participants",
    label="Participants",
    description=(
        "Who debates: persona design, functional roles, and base-model "
        "selection for each agent (node v in V)."
    ),
    subdimensions=(
        _PERSONA_ATTRIBUTES,
        _PERSONA_HETEROGENEITY,
        _PERSONA_ASSIGNMENT,
        _ROLES,
        _BASE_MODEL_FAMILY,
        _BASE_MODEL_HETEROGENEITY,
    ),
)


# === Dimension 2: INTERACTION ==============================================

_TOPOLOGY_ADAPTABILITY = SubDimension(
    key="topology_adaptability",
    label="Topology adaptability",
    description="Whether communication channels change throughout the debate (E(t)).",
    selection="single",
    values=(
        Value(
            key="static",
            label="Static",
            description="Communication channels remain unchanged throughout the debate.",
            default=True,
        ),
        Value(
            key="dynamic",
            label="Dynamic",
            description="Communication channels adapt throughout the debate.",
            executable=False,
        ),
    ),
)

_TOPOLOGY_STRUCTURE = SubDimension(
    key="topology_structure",
    label="Topology structure",
    description="The overall shape of the communication graph G=(V,E).",
    selection="single",
    values=(
        Value(
            key="fully_connected",
            label="Fully connected",
            description="All agents interact with each other.",
            default=True,
        ),
        Value(
            key="grouped",
            label="Divided into groups",
            description="Agents interact within disconnected subgroups.",
        ),
        Value(
            key="structured_network",
            label="Structured networks",
            description="Interaction follows a predefined network topology.",
        ),
    ),
)

_TOPOLOGY_PATTERN = SubDimension(
    key="topology_pattern",
    label="Topology pattern",
    description=(
        "Canonical structured-network patterns selectable when the structure "
        "is a structured network."
    ),
    selection="single",
    values=(
        Value(
            key="chain",
            label="Chain",
            description="A linear topology where each agent builds on its predecessor.",
            icon="topology/chain",
        ),
        Value(
            key="ring",
            label="Ring",
            description="A cyclic chain where each agent communicates with a fixed neighbour set.",
            icon="topology/ring",
        ),
        Value(
            key="star",
            label="Star",
            description="A centralized topology where a single node aggregates from all others.",
            icon="topology/star",
        ),
        Value(
            key="tree",
            label="Tree",
            description="A hierarchical topology enabling recursive decomposition of reasoning.",
            icon="topology/tree",
        ),
        Value(
            key="layered",
            label="Layered network",
            description=(
                "A multi-stage topology where agents form sequential layers, "
                "each performing a distinct transformation."
            ),
            icon="topology/layered",
        ),
        Value(
            key="sparse",
            label="Sparse",
            description="Each agent interacts with a limited subset of peers (|E| << |V|(|V|-1)).",
            icon="topology/sparse",
        ),
        Value(
            key="bipartite",
            label="Bipartite",
            description=(
                "Agents split into two disjoint sets interacting primarily "
                "across the partition."
            ),
            icon="topology/bipartite",
        ),
    ),
)

_PROTOCOL_MECHANISM = SubDimension(
    key="protocol_mechanism",
    label="Protocol mechanism",
    description="How agents take turns contributing to the debate.",
    selection="single",
    values=(
        Value(
            key="sequential",
            label="Sequential",
            description="Agents intervene in ordered turns.",
            default=True,
        ),
        Value(
            key="simultaneous",
            label="Simultaneous",
            description="Agents contribute to the debate at the same time.",
        ),
        Value(
            key="hybrid",
            label="Hybrid",
            description="Combines sequential and simultaneous exchanges.",
        ),
    ),
)

_PROTOCOL_ORDERING = SubDimension(
    key="protocol_ordering",
    label="Protocol ordering",
    description="How speaking order is determined for sequential turn-taking.",
    selection="single",
    values=(
        Value(
            key="fixed",
            label="Fixed",
            description="A predefined speaking order.",
            default=True,
        ),
        Value(
            key="randomized",
            label="Randomized",
            description="Randomized turn-taking to mitigate ordering/dominance bias.",
        ),
        Value(
            key="coordinator",
            label="Coordinator-selected",
            description=(
                "A coordinator/leader agent selects the next speaker from the "
                "evolving context."
            ),
            executable=False,
        ),
    ),
)

_FORMAT_SYNTAX = SubDimension(
    key="format_syntax",
    label="Format syntax",
    description="The representation in which arguments are exchanged.",
    selection="single",
    values=(
        Value(
            key="natural_language",
            label="Natural language",
            description="Arguments are exchanged in human-readable text.",
            default=True,
        ),
        Value(
            key="embeddings",
            label="Embeddings",
            description="Arguments are exchanged as vector embeddings directly.",
            executable=False,
        ),
    ),
)

_FORMAT_CONTENT = SubDimension(
    key="format_content",
    label="Format content",
    description="How argument content is transformed before being shared.",
    selection="single",
    values=(
        Value(
            key="verbatim",
            label="Verbatim",
            description="Full arguments are shared without modification.",
            default=True,
        ),
        Value(
            key="summarized",
            label="Summarized",
            description="Arguments are compressed into shorter representations.",
        ),
        Value(
            key="other",
            label="Other",
            description="Alternative content transformation strategies are applied.",
            executable=False,
        ),
    ),
)

_FORMAT_CONTENT_METADATA = SubDimension(
    key="format_content_metadata",
    label="Format content metadata",
    description=(
        "Optional signals attachable to an exchange, used to weight or guide "
        "aggregation."
    ),
    selection="multi",
    values=(
        Value(
            key="confidence",
            label="Confidence",
            description="An agent's degree of certainty, used to weight aggregation.",
        ),
        Value(
            key="uncertainty",
            label="Uncertainty",
            description="Typically the inverse of confidence.",
        ),
        Value(
            key="verifier_score",
            label="Verifier score",
            description="A dedicated component scores answers and intermediate reasoning.",
        ),
        Value(
            key="judge_likelihood",
            label="Judge likelihood",
            description="A judge assigns a plausibility signal used for final selection.",
        ),
        Value(
            key="bias_quality",
            label="Bias/quality score",
            description="Auxiliary agents compute bias or quality scores to guide selection.",
        ),
        Value(
            key="guideline_weight",
            label="Guideline weight",
            description="External signals encoding priorities such as utility or fairness.",
        ),
    ),
)

_FORMAT_MEMORY = SubDimension(
    key="format_memory",
    label="Format memory",
    description="The scope of context an agent can access.",
    selection="single",
    values=(
        Value(
            key="short_term",
            label="Short-term",
            description="Access limited to current debate context.",
            default=True,
        ),
        Value(
            key="long_term",
            label="Long-term",
            description="Access extends to persistent memory across debates.",
            executable=False,
        ),
        Value(
            key="knowledge_retrieval",
            label="Knowledge retrieval",
            description="Agents query external knowledge sources.",
            executable=False,
        ),
        Value(
            key="parametric",
            label="Parametric",
            description="Debates embedded into model parameters through training.",
            executable=False,
        ),
    ),
)

INTERACTION = Dimension(
    key="interaction",
    label="Interaction",
    description=(
        "How agents communicate: topology (G=(V,E)), protocol (temporal edge "
        "activation E(t)), and message format (transformations m~=f(m))."
    ),
    subdimensions=(
        _TOPOLOGY_ADAPTABILITY,
        _TOPOLOGY_STRUCTURE,
        _TOPOLOGY_PATTERN,
        _PROTOCOL_MECHANISM,
        _PROTOCOL_ORDERING,
        _FORMAT_SYNTAX,
        _FORMAT_CONTENT,
        _FORMAT_CONTENT_METADATA,
        _FORMAT_MEMORY,
    ),
)


# === Dimension 3: AGREEMENT ================================================

_AUTHORITY = SubDimension(
    key="authority",
    label="Authority",
    description="Who holds the power to make the final decision.",
    selection="single",
    values=(
        Value(
            key="collective",
            label="Collective",
            description="The final decision is made jointly by multiple agents.",
            default=True,
        ),
        Value(
            key="judge_based",
            label="Judge-based",
            description="The final decision is made by a designated judge agent.",
        ),
        Value(
            key="hybrid",
            label="Hybrid",
            description="The final decision combines collective and judge-based authority.",
        ),
        Value(
            key="other",
            label="Other",
            description="User-dependent, undefined, or non-standard decision authority.",
        ),
    ),
)

_RESOLUTION = SubDimension(
    key="resolution",
    label="Resolution",
    description="The mechanism by which the debate resolves to a final output.",
    selection="single",
    values=(
        Value(
            key="majority_vote",
            label="Majority vote",
            description="The option supported by most agents is selected.",
            default=True,
        ),
        Value(
            key="argument_evaluation",
            label="Argument evaluation",
            description="The decision is made by evaluating the debate.",
        ),
        Value(
            key="weighted_vote",
            label="Weighted vote",
            description="Votes are aggregated with agent-specific weights.",
        ),
        Value(
            key="scoring",
            label="Scoring",
            description="The decision is made through agent response scoring and ranking.",
        ),
        Value(
            key="average",
            label="Average",
            description="The decision is derived by averaging agent outputs or scores.",
        ),
        Value(
            key="consensus",
            label="Consensus",
            description="Agents deliberate until reaching a common agreement.",
        ),
    ),
)

AGREEMENT = Dimension(
    key="agreement",
    label="Agreement",
    description=(
        "How the debate resolves to a final output: the (authority, "
        "resolution) pair."
    ),
    subdimensions=(
        _AUTHORITY,
        _RESOLUTION,
    ),
)


# === Top-level catalog =====================================================

CATALOG = Taxonomy(dimensions=(PARTICIPANTS, INTERACTION, AGREEMENT))
"""The single, module-level instance of the complete MAD taxonomy."""


# ---------------------------------------------------------------------------
# Accessor helpers
# ---------------------------------------------------------------------------


def list_dimensions() -> tuple[Dimension, ...]:
    """Return all dimensions in declaration order."""
    return CATALOG.dimensions


def get_dimension(dimension: str) -> Optional[Dimension]:
    """Return the dimension with ``key == dimension``, or ``None``."""
    return CATALOG.get(dimension)


def get_subdimension(dimension: str, subdimension: str) -> Optional[SubDimension]:
    """Return a sub-dimension by ``(dimension, subdimension)`` keys, or ``None``."""
    dim = CATALOG.get(dimension)
    if dim is None:
        return None
    return dim.get(subdimension)


def get_value(dimension: str, subdimension: str, key: str) -> Optional[Value]:
    """Return a value by ``(dimension, subdimension, key)``, or ``None``."""
    sub = get_subdimension(dimension, subdimension)
    if sub is None:
        return None
    return sub.get(key)


def iter_values() -> Iterator[tuple[Dimension, SubDimension, Value]]:
    """Iterate over every ``(dimension, subdimension, value)`` triple."""
    for dim in CATALOG.dimensions:
        for sub in dim.subdimensions:
            for value in sub.values:
                yield dim, sub, value


def default_value(dimension: str, subdimension: str) -> Optional[Value]:
    """Return the default value of a single-selection sub-dimension, or ``None``."""
    sub = get_subdimension(dimension, subdimension)
    if sub is None:
        return None
    return sub.default


def default_config() -> dict:
    """Return the default selection for every single-selection sub-dimension.

    Produces a ``{dimension_key: {subdimension_key: value_key}}`` mapping for
    the sub-dimensions that have a single default. ``multi`` and ``attributes``
    sub-dimensions are omitted (they have no single default). This is a
    convenience for pre-filling a new configuration (Req 7.1).
    """
    result: dict[str, dict[str, str]] = {}
    for dim in CATALOG.dimensions:
        dim_defaults: dict[str, str] = {}
        for sub in dim.subdimensions:
            if sub.selection == "single" and sub.default is not None:
                dim_defaults[sub.key] = sub.default.key
        if dim_defaults:
            result[dim.key] = dim_defaults
    return result


def under_development_keys() -> tuple[str, ...]:
    """Return the keys of all non-executable ("under development") values."""
    return tuple(value.key for _, _, value in iter_values() if not value.executable)


def to_dict() -> dict:
    """Return the full taxonomy as a JSON-ready plain ``dict``.

    This is what the ``/api/taxonomy`` endpoint serves and what the website
    snapshots for its documentation pages.
    """
    return CATALOG.to_dict()
