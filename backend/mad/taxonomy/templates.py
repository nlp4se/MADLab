"""Predefined templates (personas, roles, topologies) and gold-case configs.

This module is the data-driven *template layer* on top of the taxonomy catalog
(:mod:`mad.taxonomy.catalog`) and the configuration artifact schema
(:mod:`mad.taxonomy.schema`). It ships three selectable template families plus
the two reference ("gold") MAD systems from the papers:

* **Persona patterns** (CSUR §4.1) — catalog entries that, when *applied*, set a
  participant's ``background`` / ``personality`` / ``stance`` text. Many come in
  opposing pairs (angel/devil, prosecution/defence, ...); a few expand into a
  *set* of personas (Six Thinking Hats, domain-expert panel). Applying a pattern
  yields one or more :class:`~mad.taxonomy.schema.Persona` field-sets; the result
  stays fully editable.
* **Role definitions** — a thin convenience wrapper over the six catalog roles
  (``catalog.get_subdimension("participants", "roles")``), exposing each role's
  ``key`` / ``label`` / ``description`` / ``icon`` without duplicating the
  catalog.
* **Topology builders** (CSUR §5.1) — pure functions that turn a list of node
  ids into the directed :class:`~mad.taxonomy.schema.Edge` list for each
  canonical structure (fully_connected / chain / ring / star / tree / layered /
  sparse / bipartite), plus :func:`build_topology` /
  :func:`fully_connected_topology` that assemble a ready
  :class:`~mad.taxonomy.schema.Topology`. These builders are reused by the
  engine's graph layer (task 3.1) and the frontend "apply topology template"
  action, and are exercised by the gold cases below.

**Gold cases** (Req 4.4) — fresh-instance factory functions returning validated
:class:`~mad.taxonomy.schema.MADConfig` objects:

* :func:`re_binary_debate` — the current framework's requirement-classification
  debate (two opposing debaters + a judge), aligned with ``data/prompts``.
* :func:`chateval_s1` / :func:`chateval_s2` / :func:`chateval_s3` — ChatEval's
  three communication strategies exactly per CSUR Table 3. They differ *only* in
  the documented attributes (protocol mechanism; presence of a Summarizer node +
  its edges + the content strategy) and are otherwise identical — the paper's
  benchmarking claim, asserted in the tests.

The module stays importable without any web dependency: it uses only stdlib +
the dependency-light catalog/schema modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from mad.taxonomy import catalog
from mad.taxonomy.schema import (
    Agreement,
    BaseModelSpec,
    ContentSpec,
    Edge,
    Format,
    InputSpec,
    Interaction,
    MADConfig,
    AdHocField,
    ParticipantNode,
    Participants,
    Persona,
    Phase,
    Protocol,
    Topology,
)

# ===========================================================================
# Persona patterns (CSUR §4.1)
# ===========================================================================


@dataclass(frozen=True)
class PersonaFieldSet:
    """A concrete persona produced by applying a pattern.

    ``name`` is a suggested participant label (e.g. ``"Angel"``); ``fields`` is
    the persona content (background/personality/stance). Applying a pattern
    always yields one or more of these; the UI drops them straight into a
    :class:`~mad.taxonomy.schema.Persona` and they stay fully editable.
    """

    name: str
    background: Optional[str] = None
    personality: Optional[str] = None
    stance: Optional[str] = None

    def to_persona(self, template_ref: Optional[str] = None) -> Persona:
        """Materialise this field-set into a :class:`Persona`."""
        return Persona(
            background=self.background,
            personality=self.personality,
            stance=self.stance,
            template_ref=template_ref,
        )


@dataclass(frozen=True)
class PersonaPattern:
    """A selectable persona pattern.

    Attributes:
        key: Stable machine id (``angel``, ``six_thinking_hats``, ...).
        label: Human-readable name.
        description: Short description of what the pattern expresses.
        personas: One or more :class:`PersonaFieldSet` the pattern expands into.
            Single-persona patterns carry exactly one; set patterns (Six
            Thinking Hats, expert panel) carry several.
        pair_with: For opposing-pair patterns, the key of the complementary
            pattern (e.g. ``angel.pair_with == "devil"``); ``None`` otherwise.
    """

    key: str
    label: str
    description: str
    personas: tuple[PersonaFieldSet, ...]
    pair_with: Optional[str] = None

    @property
    def is_set(self) -> bool:
        """``True`` when the pattern expands into more than one persona."""
        return len(self.personas) > 1

    def apply(self) -> list[Persona]:
        """Return the persona(s) this pattern produces (fully editable)."""
        return [fs.to_persona(template_ref=self.key) for fs in self.personas]

    def to_dict(self) -> dict:
        """JSON-ready view for the ``/api/taxonomy`` payload / website."""
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "pair_with": self.pair_with,
            "is_set": self.is_set,
            "personas": [
                {
                    "name": fs.name,
                    "background": fs.background,
                    "personality": fs.personality,
                    "stance": fs.stance,
                }
                for fs in self.personas
            ],
        }


_PERSONA_PATTERNS: dict[str, PersonaPattern] = {}


def _register_pattern(pattern: PersonaPattern) -> PersonaPattern:
    _PERSONA_PATTERNS[pattern.key] = pattern
    return pattern


# --- opposing / adversarial pairs -----------------------------------------

_register_pattern(
    PersonaPattern(
        key="angel",
        label="Angel",
        description="The optimistic, supportive advocate who argues the favourable position.",
        pair_with="devil",
        personas=(
            PersonaFieldSet(
                name="Angel",
                background="A constructive advocate who looks for merits and the strongest supporting case.",
                personality="Optimistic, encouraging, and charitable in interpreting the proposal.",
                stance="Argue in favour of the proposition and defend its strengths.",
            ),
        ),
    )
)
_register_pattern(
    PersonaPattern(
        key="devil",
        label="Devil (devil's advocate)",
        description="The adversarial critic who argues the opposing, sceptical position.",
        pair_with="angel",
        personas=(
            PersonaFieldSet(
                name="Devil",
                background="A sceptical critic trained to surface flaws, risks, and counter-arguments.",
                personality="Adversarial, probing, and relentless in testing weak points.",
                stance="Argue against the proposition and expose its weaknesses.",
            ),
        ),
    )
)

_register_pattern(
    PersonaPattern(
        key="prosecution",
        label="Prosecution",
        description="The accusing party in an adversarial legal-style debate.",
        pair_with="defence",
        personas=(
            PersonaFieldSet(
                name="Prosecution",
                background="A prosecutor building the case that the claim/charge holds.",
                personality="Assertive, evidence-driven, and persuasive.",
                stance="Argue that the claim is true / the charge is warranted.",
            ),
        ),
    )
)
_register_pattern(
    PersonaPattern(
        key="defence",
        label="Defence",
        description="The defending party in an adversarial legal-style debate.",
        pair_with="prosecution",
        personas=(
            PersonaFieldSet(
                name="Defence",
                background="A defender rebutting the case and raising reasonable doubt.",
                personality="Measured, meticulous, and protective of the defendant's position.",
                stance="Argue that the claim is unproven / the charge is unwarranted.",
            ),
        ),
    )
)

_register_pattern(
    PersonaPattern(
        key="faithful",
        label="Faithful",
        description="Argues that a summary/answer is faithful to its source (summary-evaluation pair).",
        pair_with="unfaithful",
        personas=(
            PersonaFieldSet(
                name="Faithful",
                background="An evaluator defending that the candidate output is grounded in the source.",
                personality="Careful, source-anchored, and consistency-seeking.",
                stance="Argue that the output is faithful and consistent with the source.",
            ),
        ),
    )
)
_register_pattern(
    PersonaPattern(
        key="unfaithful",
        label="Unfaithful",
        description="Argues that a summary/answer is unfaithful to its source (summary-evaluation pair).",
        pair_with="faithful",
        personas=(
            PersonaFieldSet(
                name="Unfaithful",
                background="An evaluator hunting for hallucinations and unsupported claims.",
                personality="Suspicious, detail-oriented, and intolerant of unsupported content.",
                stance="Argue that the output is unfaithful or contains unsupported content.",
            ),
        ),
    )
)

_register_pattern(
    PersonaPattern(
        key="proponent",
        label="Proponent",
        description="Supports the retrieved/claimed answer (retrieval-debate pair).",
        pair_with="challenger",
        personas=(
            PersonaFieldSet(
                name="Proponent",
                background="An agent that defends the retrieved evidence and the answer it supports.",
                personality="Confident and grounded in the retrieved passages.",
                stance="Argue that the retrieved evidence supports the proposed answer.",
            ),
        ),
    )
)
_register_pattern(
    PersonaPattern(
        key="challenger",
        label="Challenger",
        description="Challenges the retrieved/claimed answer (retrieval-debate pair).",
        pair_with="proponent",
        personas=(
            PersonaFieldSet(
                name="Challenger",
                background="An agent that questions the retrieval and probes for contradicting evidence.",
                personality="Inquisitive and willing to reject weakly supported answers.",
                stance="Argue that the retrieved evidence is insufficient or contradicts the answer.",
            ),
        ),
    )
)

_register_pattern(
    PersonaPattern(
        key="gold",
        label="Gold answer advocate",
        description="Argues for the correct answer (gold/distractor pair for QA debates).",
        pair_with="distractor",
        personas=(
            PersonaFieldSet(
                name="Gold",
                background="An agent committed to defending the correct answer with sound reasoning.",
                personality="Rigorous, precise, and grounded in the question's constraints.",
                stance="Argue that the correct (gold) option is the right answer.",
            ),
        ),
    )
)
_register_pattern(
    PersonaPattern(
        key="distractor",
        label="Distractor advocate",
        description="Argues for the strongest incorrect option (gold/distractor pair for QA debates).",
        pair_with="gold",
        personas=(
            PersonaFieldSet(
                name="Distractor",
                background="An agent that mounts the most convincing case for a plausible wrong option.",
                personality="Persuasive and good at exploiting ambiguity.",
                stance="Argue that the strongest distractor option is the right answer.",
            ),
        ),
    )
)

# --- multi-persona set patterns -------------------------------------------

_register_pattern(
    PersonaPattern(
        key="six_thinking_hats",
        label="Six Thinking Hats",
        description="Edward de Bono's six thinking modes modelled as six distinct personalities.",
        personas=(
            PersonaFieldSet(
                name="White Hat",
                background="The information gatherer focused on data and known facts.",
                personality="Neutral and objective; reports facts without interpretation.",
                stance="Contribute only facts, figures, and information gaps.",
            ),
            PersonaFieldSet(
                name="Red Hat",
                background="The voice of intuition and emotion.",
                personality="Expresses feelings and hunches without needing to justify them.",
                stance="Contribute emotional and intuitive reactions to the proposal.",
            ),
            PersonaFieldSet(
                name="Black Hat",
                background="The cautious critic assessing risks.",
                personality="Careful and judgemental; identifies difficulties and dangers.",
                stance="Contribute risks, weaknesses, and reasons something may fail.",
            ),
            PersonaFieldSet(
                name="Yellow Hat",
                background="The optimist assessing value and benefits.",
                personality="Positive and constructive; seeks feasibility and upside.",
                stance="Contribute benefits, value, and reasons something may succeed.",
            ),
            PersonaFieldSet(
                name="Green Hat",
                background="The creative generator of alternatives.",
                personality="Inventive and lateral; proposes new ideas and options.",
                stance="Contribute creative alternatives and novel possibilities.",
            ),
            PersonaFieldSet(
                name="Blue Hat",
                background="The process manager organising the thinking.",
                personality="Reflective and organising; directs the discussion.",
                stance="Contribute structure, summaries, and next-step direction.",
            ),
        ),
    )
)

_register_pattern(
    PersonaPattern(
        key="domain_expert_panel",
        label="Domain expert panel",
        description="A set of differentiated domain-expert backgrounds for a cross-disciplinary panel.",
        personas=(
            PersonaFieldSet(
                name="Software Engineer",
                background="A senior software engineer with deep systems and architecture experience.",
                personality="Pragmatic and implementation-focused.",
                stance="Evaluate from a technical feasibility and engineering-cost perspective.",
            ),
            PersonaFieldSet(
                name="Domain Scientist",
                background="A subject-matter scientist grounded in the relevant research literature.",
                personality="Evidence-driven and methodical.",
                stance="Evaluate from a scientific validity and evidence perspective.",
            ),
            PersonaFieldSet(
                name="Product Strategist",
                background="A product strategist focused on users, market fit, and outcomes.",
                personality="User-centric and outcome-oriented.",
                stance="Evaluate from a user-value and strategic-fit perspective.",
            ),
            PersonaFieldSet(
                name="Ethicist",
                background="An ethicist assessing fairness, safety, and societal impact.",
                personality="Principled and risk-aware.",
                stance="Evaluate from an ethical, fairness, and safety perspective.",
            ),
        ),
    )
)


def list_persona_patterns() -> list[PersonaPattern]:
    """Return all persona patterns in registration order."""
    return list(_PERSONA_PATTERNS.values())


def get_persona_pattern(key: str) -> Optional[PersonaPattern]:
    """Return the persona pattern with ``key``, or ``None``."""
    return _PERSONA_PATTERNS.get(key)


def apply_persona_pattern(key: str) -> list[Persona]:
    """Apply a persona pattern by ``key`` and return its persona(s).

    Raises :class:`KeyError` with an actionable message if ``key`` is unknown.
    The returned personas carry ``template_ref=key`` and remain fully editable.
    """
    pattern = _PERSONA_PATTERNS.get(key)
    if pattern is None:
        known = ", ".join(sorted(_PERSONA_PATTERNS))
        raise KeyError(f"unknown persona pattern '{key}'; known patterns: [{known}]")
    return pattern.apply()


# ===========================================================================
# Role definitions (thin wrapper over the catalog — no duplication)
# ===========================================================================


@dataclass(frozen=True)
class RoleDefinition:
    """A role's catalog metadata (key / label / description / icon)."""

    key: str
    label: str
    description: str
    icon: Optional[str]

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "icon": self.icon,
        }


def list_roles() -> list[RoleDefinition]:
    """Return the six roles with their catalog metadata (including icons).

    Reuses ``catalog.get_subdimension("participants", "roles")`` so the role
    labels/descriptions/icons are defined once in the catalog.
    """
    sub = catalog.get_subdimension("participants", "roles")
    assert sub is not None, "roles sub-dimension missing from catalog"
    return [
        RoleDefinition(key=v.key, label=v.label, description=v.description, icon=v.icon)
        for v in sub.values
    ]


def get_role(key: str) -> Optional[RoleDefinition]:
    """Return the role definition with ``key``, or ``None``."""
    for role in list_roles():
        if role.key == key:
            return role
    return None


# ===========================================================================
# Topology builders (CSUR §5.1)
# ===========================================================================
#
# Each builder is a pure function mapping node ids (+ optional parameters) to a
# list of directed ``Edge`` objects. ``build_topology`` wraps a builder into a
# ready ``Topology`` with the correct ``structure`` / ``pattern``.


def _edge(source: str, target: str) -> Edge:
    return Edge(source=source, target=target, directed=True)


def fully_connected(nodes: list[str]) -> list[Edge]:
    """All directed pairs ``(u, v)`` with ``u != v`` (|E| = n(n-1))."""
    return [_edge(u, v) for u in nodes for v in nodes if u != v]


def chain(nodes: list[str]) -> list[Edge]:
    """Linear chain ``(v_i -> v_{i+1})`` (|E| = n-1)."""
    return [_edge(nodes[i], nodes[i + 1]) for i in range(len(nodes) - 1)]


def ring(nodes: list[str]) -> list[Edge]:
    """Chain plus a closing edge ``(v_n -> v_1)`` (|E| = n for n >= 2)."""
    edges = chain(nodes)
    if len(nodes) >= 2:
        edges.append(_edge(nodes[-1], nodes[0]))
    return edges


def star(nodes: list[str], center: str) -> list[Edge]:
    """Edges from every other node to ``center`` (center aggregates; |E| = n-1).

    Follows the paper's centralized star where a single node aggregates from
    all others. Raises :class:`ValueError` if ``center`` is not among ``nodes``.
    """
    if center not in nodes:
        raise ValueError(f"star center '{center}' is not one of the provided nodes")
    return [_edge(n, center) for n in nodes if n != center]


def tree(nodes: list[str], branching: int = 2) -> list[Edge]:
    """Hierarchical parent->child edges for a ``branching``-ary tree.

    ``nodes[0]`` is the root; node ``i`` has children at indices
    ``branching*i + 1 .. branching*i + branching`` (|E| = n-1 for a connected
    tree). Raises :class:`ValueError` if ``branching < 1``.
    """
    if branching < 1:
        raise ValueError("tree branching factor must be >= 1")
    edges: list[Edge] = []
    n = len(nodes)
    for i in range(n):
        for k in range(1, branching + 1):
            child = branching * i + k
            if child < n:
                edges.append(_edge(nodes[i], nodes[child]))
    return edges


def layered(layers: list[list[str]]) -> list[Edge]:
    """Edges from every node in each layer to every node in the next layer.

    ``layers`` is an ordered list of layers (each a list of node ids). |E| =
    sum over consecutive layer pairs of ``len(L_i) * len(L_{i+1})``.
    """
    edges: list[Edge] = []
    for i in range(len(layers) - 1):
        for src in layers[i]:
            for dst in layers[i + 1]:
                edges.append(_edge(src, dst))
    return edges


def sparse(nodes: list[str], neighbors: int = 1) -> list[Edge]:
    """Low-density neighbour-connected graph: each node links to its next
    ``neighbors`` successors (wrapping), |E| = n*neighbors for n > neighbors.

    With ``neighbors == 1`` this is a ring. Raises :class:`ValueError` if
    ``neighbors < 1``.
    """
    if neighbors < 1:
        raise ValueError("sparse neighbors must be >= 1")
    n = len(nodes)
    edges: list[Edge] = []
    if n < 2:
        return edges
    reach = min(neighbors, n - 1)
    for i in range(n):
        for k in range(1, reach + 1):
            edges.append(_edge(nodes[i], nodes[(i + k) % n]))
    return edges


def bipartite(set_a: list[str], set_b: list[str]) -> list[Edge]:
    """Directed edges from every node in ``set_a`` to every node in ``set_b``
    (|E| = |A| * |B|)."""
    return [_edge(a, b) for a in set_a for b in set_b]


# Registry of structured-network pattern builders. ``star``/``tree``/``layered``/
# ``sparse``/``bipartite`` take extra kwargs, handled by ``build_topology``.
_PATTERN_BUILDERS: dict[str, Callable[..., list[Edge]]] = {
    "chain": chain,
    "ring": ring,
    "star": star,
    "tree": tree,
    "layered": layered,
    "sparse": sparse,
    "bipartite": bipartite,
}


def fully_connected_topology(nodes: list[str]) -> Topology:
    """Build a fully-connected :class:`Topology` over ``nodes``."""
    return Topology(
        adaptability="static",
        structure="fully_connected",
        pattern=None,
        edges=fully_connected(nodes),
    )


def build_topology(pattern: str, nodes: list[str], **kwargs: Any) -> Topology:
    """Assemble a structured-network :class:`Topology` for ``pattern``.

    ``pattern`` is one of the canonical structured-network patterns
    (chain/ring/star/tree/layered/sparse/bipartite). Builder-specific arguments
    are forwarded as ``kwargs`` (e.g. ``center=`` for star, ``branching=`` for
    tree, ``neighbors=`` for sparse). For ``layered`` and ``bipartite`` the
    ``nodes`` positional is ignored in favour of keyword layer/set arguments:

    * ``build_topology("layered", [], layers=[[...], [...]])``
    * ``build_topology("bipartite", [], set_a=[...], set_b=[...])``

    For ``fully_connected`` use :func:`fully_connected_topology`. Raises
    :class:`ValueError` for an unknown pattern.
    """
    if pattern not in _PATTERN_BUILDERS:
        known = ", ".join(sorted(_PATTERN_BUILDERS))
        raise ValueError(f"unknown topology pattern '{pattern}'; known: [{known}]")

    builder = _PATTERN_BUILDERS[pattern]
    if pattern == "layered":
        edges = builder(kwargs["layers"])
    elif pattern == "bipartite":
        edges = builder(kwargs["set_a"], kwargs["set_b"])
    else:
        edges = builder(nodes, **kwargs)

    return Topology(
        adaptability="static",
        structure="structured_network",
        pattern=pattern,  # type: ignore[arg-type]
        edges=edges,
    )


# ===========================================================================
# Gold case 1: RE binary classification debate
# ===========================================================================

# Source prompts (aligned with data/prompts/*):
_RE_FUNCTIONAL_PROMPT = (
    "You are a debater arguing that the received requirement is functional (F)."
)
_RE_NON_FUNCTIONAL_PROMPT = (
    "You are a debater arguing that the received requirement is non-functional (NF)."
)
_RE_JUDGE_PROMPT = (
    "You are a moderator. There will be two debaters involved in a debate "
    "competition. They will present their answers and discuss their perspectives "
    "on whether a given requirement should be classified as functional (F) or "
    "non-functional (NF). At the end of each round, you will evaluate their "
    "answers and decide which classification is more appropriate."
)

# Mirror data/prompts/coordinator/requirements-schema-binary.json's inner schema.
_RE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"class": {"type": "string", "enum": ["F", "NF"]}},
}


def re_binary_debate() -> MADConfig:
    """Gold case: requirement functional/non-functional binary debate.

    Two opposing debaters (stance = F / NF) plus a judge, fully-connected static
    topology, sequential protocol, judge-based authority with argument
    evaluation, and an output schema constraining ``class`` to ``[F, NF]``. Base
    models default to the closed-weight ``gpt-4o`` key (provider bound at run
    time). Returns a fresh, validated :class:`MADConfig` on each call.
    """
    nodes = [
        ParticipantNode(
            id="functional-debater",
            label="Functional debater",
            roles=["debater"],
            persona=Persona(stance="Argue the requirement is functional (F)."),
            base_model=BaseModelSpec(model_key="gpt-4o", family="closed_weight"),
            system_prompt=_RE_FUNCTIONAL_PROMPT,
        ),
        ParticipantNode(
            id="non-functional-debater",
            label="Non-functional debater",
            roles=["debater"],
            persona=Persona(stance="Argue the requirement is non-functional (NF)."),
            base_model=BaseModelSpec(model_key="gpt-4o", family="closed_weight"),
            system_prompt=_RE_NON_FUNCTIONAL_PROMPT,
        ),
        ParticipantNode(
            id="judge",
            label="Judge",
            roles=["judge"],
            persona=Persona(),
            base_model=BaseModelSpec(model_key="gpt-4o", family="closed_weight"),
            system_prompt=_RE_JUDGE_PROMPT,
        ),
    ]
    node_ids = [n.id for n in nodes]

    return MADConfig(
        name="RE Binary Classification Debate",
        description=(
            "Requirement functional (F) vs. non-functional (NF) classification "
            "debate: two opposing debaters and a judge. Reproduces the current "
            "framework's binary classification workflow."
        ),
        participants=Participants(
            persona_heterogeneity="heterogeneous",
            persona_assignment="manual",
            base_model_heterogeneity="homogeneous",
            nodes=nodes,
        ),
        interaction=Interaction(
            topology=fully_connected_topology(node_ids),
            protocol=Protocol(
                mechanism="sequential",
                max_rounds=2,
                ordering="fixed",
                order=node_ids,
            ),
            format=Format(
                syntax="natural_language",
                content=ContentSpec(strategy="verbatim"),
                memory="short_term",
            ),
        ),
        agreement=Agreement(
            authority="judge_based",
            resolution="argument_evaluation",
            output_schema=_RE_OUTPUT_SCHEMA,
        ),
        input_spec=InputSpec(
            template="Classify this requirement: {{requirement}}",
            placeholders=["requirement"],
            ad_hoc_fields=[AdHocField(key="requirement", label="Requirement text")],
        ),
    )


# ===========================================================================
# Gold case 2: ChatEval S1/S2/S3 (CSUR Table 3)
# ===========================================================================
#
# Three debaters Alice/Bob/Carol with DISTINCT personalities (heterogeneous
# personas, manual assignment). Base model homogeneous closed-weight. Static
# topology, natural-language syntax, short-term memory. Agreement: collective
# authority; resolution = majority_vote with a hybrid note recorded in
# resolution_params ("majority vote if categorical; average if numerical").
#
# S1 (One-by-One):            sequential, order Alice->Bob->Carol, fully-connected
#                             over the 3 debaters (|E| = 6), verbatim.
# S2 (Simultaneous-Talk):     simultaneous, fully-connected over the 3 debaters
#                             (|E| = 6), verbatim.
# S3 (+ Summarizer):          simultaneous debaters + a Summarizer node activated
#                             once per round; topology = 6 debater edges PLUS one
#                             directed edge from each debater to the Summarizer
#                             (|E| = 9); content hybrid (verbatim among debaters,
#                             summarized from summarizer to debaters).
#
# --- S3 CONTENT-MODELING DECISION -----------------------------------------
# The schema's ``content.strategy`` is a SINGLE enum (verbatim | summarized |
# other) and cannot express "verbatim among debaters, summarized on the
# summarizer path" in one field. We model S3 as ``strategy="summarized"``
# because the summarizer is the attribute that distinguishes S3 from S2 — the
# defining feature of this strategy is that a Summarizer compresses the exchange
# and feeds it back. The debater->debater exchange being verbatim is captured
# structurally by the summarizer *role* + the debater->summarizer edges (not by
# the content enum). This choice is what makes S2 and S3 differ by EXACTLY the
# documented attributes (mechanism is identical = simultaneous; the deltas are:
# the Summarizer node, its 3 inbound edges, and content strategy). Documented
# here and in the task report.
# ---------------------------------------------------------------------------

_CHATEVAL_MODEL_KEY = "gpt-4o"

# Distinct personalities for the three ChatEval debaters (heterogeneous personas).
_CHATEVAL_DEBATERS: tuple[tuple[str, str, str], ...] = (
    (
        "alice",
        "Alice",
        "A meticulous and critical thinker who scrutinises every claim for rigour.",
    ),
    (
        "bob",
        "Bob",
        "A pragmatic and concise reasoner who focuses on the most consequential points.",
    ),
    (
        "carol",
        "Carol",
        "An open-minded and creative explorer who surfaces overlooked perspectives.",
    ),
)

_CHATEVAL_RESOLUTION_PARAMS: dict[str, Any] = {
    "categorical": "majority_vote",
    "numerical": "average",
    "note": (
        "Table 3: majority vote if the evaluation is categorical; average if "
        "numerical. Encoded as resolution=majority_vote with this hybrid note."
    ),
}


def _chateval_debater_nodes() -> list[ParticipantNode]:
    """The three distinct-personality debater nodes shared by S1/S2/S3."""
    return [
        ParticipantNode(
            id=node_id,
            label=label,
            roles=["debater"],
            persona=Persona(personality=personality),
            base_model=BaseModelSpec(
                model_key=_CHATEVAL_MODEL_KEY, family="closed_weight"
            ),
        )
        for node_id, label, personality in _CHATEVAL_DEBATERS
    ]


def _chateval_base(
    *,
    name: str,
    description: str,
    nodes: list[ParticipantNode],
    topology: Topology,
    protocol: Protocol,
    content: ContentSpec,
) -> MADConfig:
    """Assemble a ChatEval config with the attributes shared across S1/S2/S3."""
    return MADConfig(
        name=name,
        description=description,
        participants=Participants(
            persona_heterogeneity="heterogeneous",
            persona_assignment="manual",
            base_model_heterogeneity="homogeneous",
            nodes=nodes,
        ),
        interaction=Interaction(
            topology=topology,
            protocol=protocol,
            format=Format(
                syntax="natural_language",
                content=content,
                memory="short_term",
            ),
        ),
        agreement=Agreement(
            authority="collective",
            resolution="majority_vote",
            resolution_params=dict(_CHATEVAL_RESOLUTION_PARAMS),
        ),
        input_spec=InputSpec(
            template="Evaluate the following response: {{response}}",
            placeholders=["response"],
            ad_hoc_fields=[AdHocField(key="response", label="Response to evaluate")],
        ),
    )


def chateval_s1() -> MADConfig:
    """ChatEval S1 — One-by-One (sequential, fully-connected debaters)."""
    nodes = _chateval_debater_nodes()
    debater_ids = [n.id for n in nodes]
    return _chateval_base(
        name="ChatEval S1 — One-by-One",
        description=(
            "ChatEval communication strategy S1 (One-by-One): three debaters "
            "take turns in sequential order over a fully-connected topology."
        ),
        nodes=nodes,
        topology=fully_connected_topology(debater_ids),
        protocol=Protocol(
            mechanism="sequential",
            max_rounds=2,
            ordering="fixed",
            order=debater_ids,
        ),
        content=ContentSpec(strategy="verbatim"),
    )


def chateval_s2() -> MADConfig:
    """ChatEval S2 — Simultaneous-Talk (simultaneous, fully-connected debaters)."""
    nodes = _chateval_debater_nodes()
    debater_ids = [n.id for n in nodes]
    return _chateval_base(
        name="ChatEval S2 — Simultaneous-Talk",
        description=(
            "ChatEval communication strategy S2 (Simultaneous-Talk): three "
            "debaters contribute simultaneously over a fully-connected topology."
        ),
        nodes=nodes,
        topology=fully_connected_topology(debater_ids),
        protocol=Protocol(
            mechanism="simultaneous",
            max_rounds=2,
        ),
        content=ContentSpec(strategy="verbatim"),
    )


def chateval_s3() -> MADConfig:
    """ChatEval S3 — Simultaneous-Talk + Summarizer.

    Adds a Summarizer node. Topology = fully-connected over the three debaters
    (6 edges) PLUS one directed edge from each debater to the Summarizer
    (|E| = 9). Content strategy = ``summarized`` (see the module-level
    S3 CONTENT-MODELING DECISION note).
    """
    nodes = _chateval_debater_nodes()
    debater_ids = [n.id for n in nodes]
    summarizer = ParticipantNode(
        id="summarizer",
        label="Summarizer",
        roles=["summarizer"],
        persona=Persona(
            background="A summarizer that compresses the debaters' exchange each round."
        ),
        base_model=BaseModelSpec(model_key=_CHATEVAL_MODEL_KEY, family="closed_weight"),
    )
    nodes.append(summarizer)

    # Fully-connected among debaters (6 edges) + each debater -> summarizer (3).
    edges = fully_connected(debater_ids) + bipartite(debater_ids, [summarizer.id])
    topology = Topology(
        adaptability="static",
        structure="fully_connected",
        pattern=None,
        edges=edges,
    )

    # Summarizer activated once per round: debaters speak simultaneously, then
    # the summarizer phase runs. Modelled as a hybrid protocol with two phases.
    protocol = Protocol(
        mechanism="hybrid",
        max_rounds=2,
        phases=[
            Phase(mechanism="simultaneous", participants=debater_ids),
            Phase(mechanism="sequential", participants=[summarizer.id]),
        ],
    )

    return _chateval_base(
        name="ChatEval S3 — Simultaneous-Talk + Summarizer",
        description=(
            "ChatEval communication strategy S3: three debaters contribute "
            "simultaneously and a Summarizer compresses the exchange once per "
            "round (debater->summarizer edges). Content is hybrid: verbatim among "
            "debaters, summarized on the summarizer path (modelled as "
            "strategy=summarized; see module note)."
        ),
        nodes=nodes,
        topology=topology,
        protocol=protocol,
        content=ContentSpec(strategy="summarized"),
    )


# ===========================================================================
# Gold-case registry
# ===========================================================================


def gold_cases() -> dict[str, Callable[[], MADConfig]]:
    """Return the gold-case factory registry (key -> fresh-instance builder)."""
    return {
        "re_binary_debate": re_binary_debate,
        "chateval_s1": chateval_s1,
        "chateval_s2": chateval_s2,
        "chateval_s3": chateval_s3,
    }


def build_gold_case(key: str) -> MADConfig:
    """Build a gold-case config by ``key``. Raises :class:`KeyError` if unknown."""
    registry = gold_cases()
    if key not in registry:
        known = ", ".join(sorted(registry))
        raise KeyError(f"unknown gold case '{key}'; known: [{known}]")
    return registry[key]()


__all__ = [
    # persona patterns
    "PersonaFieldSet",
    "PersonaPattern",
    "list_persona_patterns",
    "get_persona_pattern",
    "apply_persona_pattern",
    # roles
    "RoleDefinition",
    "list_roles",
    "get_role",
    # topology builders
    "fully_connected",
    "chain",
    "ring",
    "star",
    "tree",
    "layered",
    "sparse",
    "bipartite",
    "fully_connected_topology",
    "build_topology",
    # gold cases
    "re_binary_debate",
    "chateval_s1",
    "chateval_s2",
    "chateval_s3",
    "gold_cases",
    "build_gold_case",
]
