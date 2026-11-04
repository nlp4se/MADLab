"""System-prompt construction for the AI design assistant (task 11.1).

The assistant is a *chat-to-configure* seam: a user describes a Multi-Agent
Debate (MAD) setup in natural language and the model fills the MAD
configuration JSON, asking clarifying questions first when the intent is
ambiguous. This module builds the single structured SYSTEM prompt that makes
that reliable across providers.

The prompt teaches four things and enforces one envelope:

1. **The taxonomy + the EXACT ``MADConfig`` JSON schema.** The allowed
   dimension / sub-dimension / value keys are *seeded from the catalog* (via
   :meth:`app.schemas.taxonomy.TaxonomyResponse.from_engine`, the same payload
   as ``GET /api/taxonomy``) so the model only ever emits valid values. The
   artifact shape mirrors :mod:`mad.taxonomy.schema` (``participants.nodes[]``,
   ``interaction.topology.edges[]``, ``protocol``, ``format``, ``agreement``,
   ``input_spec``), with the key human rules spelled out (edges set VISIBILITY
   not turn order; ``max_rounds`` controls rounds; a judge node + ``judge_based``
   authority makes the judge decide after the rounds and the judge is NOT
   connected by an edge; ``judge_based`` REQUIRES a judge-role node;
   ``weighted_vote`` / ``scoring`` require ``resolution_params``).

2. **Ask-first behaviour.** When the request is ambiguous or missing essentials
   (debater count, roles, rounds, agreement authority, provider/model binding
   intent, input template) the model must return a clarifying *question* before
   any JSON.

3. **Scope.** It designs/edits a MAD configuration only, and politely declines
   or redirects off-topic chat.

4. **A strict machine-readable envelope.** Because tool-use is not uniform
   across LiteLLM providers, the model must return a single JSON object
   ``{"mode": "question"|"proposal", "message": "...", "artifact": {...}|null}``.
   The service parses that robustly; this module only has to *specify* it.

When a current artifact is supplied, the prompt instructs the model to edit it
in place, preserving unknown fields and changing only what the user asked.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from app.schemas.taxonomy import TaxonomyResponse


def _allowed_values_block() -> str:
    """Render the catalog's allowed keys so the model emits only valid values.

    Built from :meth:`TaxonomyResponse.from_engine` (the ``GET /api/taxonomy``
    payload) so this stays a data edit in the engine: adding/removing a taxonomy
    value updates the prompt automatically. Each sub-dimension is listed with
    its value keys and whether each is executable (non-executable values are
    "under development" — still configurable, but execution is gated).
    """
    taxonomy = TaxonomyResponse.from_engine()
    lines: list[str] = []
    for dim in taxonomy.dimensions:
        lines.append(f"- {dim.key} ({dim.label}):")
        for sub in dim.subdimensions:
            keys = ", ".join(
                f"{v.key}{'' if v.executable else ' [under-development]'}"
                for v in sub.values
            )
            if not keys:
                continue
            lines.append(f"    - {sub.key} [{sub.selection}]: {keys}")
    return "\n".join(lines)


def _role_keys_block() -> str:
    """Render the allowed participant role keys from the templates payload."""
    taxonomy = TaxonomyResponse.from_engine()
    roles = ", ".join(r.key for r in taxonomy.templates.roles)
    return roles or "debater, judge, summarizer, leader, verifier, editor"


# The exact artifact shape, mirroring mad.taxonomy.schema.MADConfig. Kept as a
# compact JSON skeleton with inline comments stripped (JSON has no comments) so
# the model can copy the structure directly.
_SCHEMA_SKELETON: dict[str, Any] = {
    "schema_version": "1.0",
    "name": "<string, required>",
    "description": "<string>",
    "participants": {
        "base_model_heterogeneity": "homogeneous|heterogeneous",
        "persona_heterogeneity": "homogeneous|heterogeneous",
        "persona_assignment": "unspecified|manual|automatic",
        "nodes": [
            {
                "id": "<unique string id>",
                "label": "<display name>",
                "roles": ["debater"],
                "persona": {
                    "background": "<string|null>",
                    "personality": "<string|null>",
                    "stance": "<string|null>",
                    "template_ref": "<string|null>",
                },
                "base_model": {
                    "provider_id": None,
                    "model_key": None,
                    # No "family": it is derived from the bound provider, never
                    # chosen (task 11.9; see _KEY_RULES).
                    "temperature": 0.0,
                    "params": {},
                },
                "system_prompt": "<string|null>",
                "group": "<group id|null>",
            }
        ],
        "groups": [],
    },
    "interaction": {
        "topology": {
            "adaptability": "static|dynamic",
            "structure": "fully_connected|grouped|structured_network",
            "pattern": "chain|ring|star|tree|layered|sparse|bipartite|null",
            "edges": [
                {"source": "<node id>", "target": "<node id>", "directed": True}
            ],
            "entry_nodes": None,
            "exit_nodes": None,
        },
        "protocol": {
            "mechanism": "sequential|simultaneous|hybrid",
            "max_rounds": 1,
            "ordering": "fixed|randomized|coordinator",
            "order": ["<node id>", "..."],
        },
        "format": {
            "syntax": "natural_language|embeddings",
            "content": {"strategy": "verbatim|summarized|other", "metadata_signals": []},
            "memory": "short_term|long_term|knowledge_retrieval|parametric",
        },
    },
    "agreement": {
        "authority": "collective|judge_based|hybrid|other",
        "resolution": (
            "majority_vote|argument_evaluation|weighted_vote|scoring|average|consensus"
        ),
        "resolution_params": {},
        "output_schema": None,
    },
    "input_spec": {
        "template": "<non-empty task text, e.g. Debate this topic: {{topic}}>",
        "placeholders": ["topic"],
        "ad_hoc_fields": [{"key": "topic", "label": "Topic"}],
    },
}


_KEY_RULES = """\
Key rules a MAD designer must respect (enforce these so the artifact validates):
- Participants are the nodes in `participants.nodes[]`. Each node needs a unique
  `id`, a `label`, and at least one role. Allowed role keys: {roles} (or a
  custom role as `custom:<name>`).
- Edges in `interaction.topology.edges[]` set message VISIBILITY (who can see
  whom), NOT turn order. `source` and `target` must reference existing node ids.
- `interaction.topology.entry_nodes` / `exit_nodes` are the Start/End IO
  connections; leave both null by default (null = every speaking participant
  receives the input, and the decision comes from the judge or the aggregated
  debaters). Set them to non-empty lists of existing node ids only when the user
  wants to restrict who gets the input or whose outputs decide; with
  `judge_based`, `exit_nodes` must include a judge.
- Turn order and rounds live in `interaction.protocol`: `max_rounds` controls
  how many rounds run; `order` lists node ids for `fixed` ordering.
  - `ordering` / `order` only apply to the `sequential` mechanism. With `fixed`
    ordering, leave `order` empty for declaration order, or list EVERY
    speaking participant (a participant left out of `order` never speaks).
  - A `hybrid` mechanism REQUIRES at least one phase in `protocol.phases`
    (each `{{"mechanism": "sequential"|"simultaneous", "participants": [ids]}}`,
    empty `participants` = every participant); without phases the run fails.
  - `format.content.strategy` `summarized` needs a node with the `summarizer`
    role (without one the engine falls back to verbatim history).
- A judge node is a node whose `roles` include `judge`. If
  `agreement.authority` is `judge_based`, there MUST be at least one judge-role
  node, and the judge decides AFTER the rounds. The judge is NOT connected by an
  edge — it reads the transcript, it does not debate.
- `agreement.resolution` of `weighted_vote` or `scoring` REQUIRES a non-empty
  `agreement.resolution_params` (e.g. weights or a scoring rubric).
- Authority and resolution must be compatible:
  - `argument_evaluation` needs a judge: use it with `judge_based` or
    `hybrid` authority, NEVER with `collective` (that run fails).
  - With `judge_based` the judge's reply IS the decision, so use
    `argument_evaluation` (votes/scores/averages are not applied). To vote
    first and ask the judge only on a tie / no consensus, use `hybrid`.
  - `hybrid` also needs a judge-role node for its fallback.
- `structured_network` topology requires a `pattern`
  (chain/ring/star/tree/layered/sparse/bipartite); `fully_connected` and
  `grouped` leave `pattern` null. Prefer `fully_connected` or
  `structured_network`: the designer cannot assign participants to groups, so
  do not propose `grouped`.
- Participant settings must agree with the node data (the designer flags any
  mismatch as a conflict):
  - `persona_assignment` `unspecified` = NO personas: leave every node's
    `persona` empty. To give personas, set it to `manual`. `automatic` is under
    development; do not fill personas by hand for it.
  - With `manual` + `persona_heterogeneity` `homogeneous`, every node with the
    `debater` role has the SAME persona (judges/summarizers may differ). If the
    debaters need distinct personas, use `heterogeneous`.
  - `base_model_heterogeneity` `homogeneous` = EVERY node has the same
    `provider_id` / `model_key`. Different models per node require
    `heterogeneous`.
  - `system_prompt` is per node and independent of these settings.
- `base_model.provider_id` / `model_key` may be left null at design time; the
  user binds a concrete provider + model later in the designer. Only set them if
  the user explicitly names a provider/model.
- `base_model.family` (open/closed weight) is DERIVED from the bound provider
  by the designer and backend; it is not a parameter. Never choose or change
  it: omit it on new nodes and leave existing values as they are.
- Metadata signals, under-development values, and memory modes other than
  `short_term` are configurable but gate execution; prefer executable values
  unless the user asks otherwise.
- `input_spec` is the task every run starts from. `template` is text with
  `{{{{name}}}}` placeholders (letters, digits, `_`, `.`, `-` or spaces) that each
  run fills in (single-run form values or mapped CSV columns); `placeholders`
  lists exactly the names the template uses, in order; `ad_hoc_fields` has one
  `{{"key": "<placeholder>", "label": "<form label>"}}` per placeholder. The
  engine appends "Task: <resolved template>" to the system prompt of the entry
  participants (the Start connectors), and judges see the same Task line at the
  top of their decision context.
  - NEVER leave `template` empty: the participants would get no task and the
    run view cannot launch the configuration.
  - When editing, keep a non-empty existing `input_spec` unchanged unless the
    user asks to change it; if it is empty, set a sensible one.
  - For a new design, set a template that fits the debate (e.g.
    `Classify this requirement: {{{{requirement}}}}`); when the task is unknown,
    use `{{{{input}}}}` with the label "Input".
- The top-level `ui` field is presentation-only canvas layout (node positions,
  edge bends); the engine ignores it. Never invent it; when editing, keep it
  unchanged.
"""


_ENVELOPE = """\
RESPONSE FORMAT — follow this EXACTLY:
Return a SINGLE JSON object and nothing else (no prose before or after, no
markdown fences). The object has exactly these fields:
  {
    "mode": "question" | "proposal",
    "message": "<your reply as plain text>",
    "artifact": <the full MADConfig JSON object> | null
  }
- Use "question" when the request is ambiguous or missing essentials. Put your
  clarifying question(s) in "message" and set "artifact" to null.
- Use "proposal" only when you have enough to build a coherent, VALID config.
  Put a short (1-3 sentence) explanation in "message" and the COMPLETE artifact
  in "artifact". Do not propose a partial or placeholder config.
- Never include commentary outside the JSON object.
"""


_ASK_FIRST = """\
Ask clarifying questions FIRST (mode="question") whenever the request is
ambiguous or missing any essential detail, for example: how many debaters, what
roles/personas, how many rounds, the agreement authority (collective debate vs a
judge deciding), whether to bind a specific provider/model, and the input
template (what question/text the debate runs over). Only move to a proposal once
you can build a coherent, valid configuration. A good assistant confirms intent
before committing to structure.
"""


_SCOPE = """\
You ONLY design and edit MAD (Multi-Agent Debate) configurations. If the user
asks for something unrelated (general chit-chat, coding help, world facts),
politely decline in one sentence and steer back to describing the debate setup
they want. Do not answer off-topic requests.
"""


def _edit_in_place_block(artifact: Optional[dict[str, Any]]) -> str:
    """Instruct the model to edit a provided artifact in place, if any.

    When a current artifact exists, the model must preserve fields it does not
    change (including unknown ones) and only touch what the user asked for. When
    none exists, it designs from scratch.
    """
    if artifact:
        pretty = json.dumps(artifact, indent=2, ensure_ascii=False)
        return (
            "The user is EDITING an existing configuration. Change only what the "
            "user asks for; preserve every other field (including any you do not "
            "recognise) verbatim. When you make a proposal, return the FULL "
            "updated artifact, not a diff.\n\n"
            "Current artifact being edited:\n"
            f"```json\n{pretty}\n```"
        )
    return (
        "There is no current artifact — the user is starting a NEW design. Build "
        "a complete artifact from scratch once you have enough detail."
    )


def build_system_prompt(artifact: Optional[dict[str, Any]] = None) -> str:
    """Build the full structured SYSTEM prompt for the design assistant.

    Assembles, in order: the role/scope framing, the ask-first guidance, the
    taxonomy's allowed keys (seeded from the catalog), the exact ``MADConfig``
    JSON skeleton, the key design rules, the edit-in-place instruction for the
    current artifact (if any), and the strict response envelope.

    Args:
        artifact: The current MAD config being edited, or ``None`` for a fresh
            design. When present, it is embedded so the model edits in place.

    Returns:
        The complete system-prompt string to send as the leading message.
    """
    skeleton = json.dumps(_SCHEMA_SKELETON, indent=2, ensure_ascii=False)
    roles = _role_keys_block()

    sections = [
        (
            "You are the MAD Design Assistant, an expert at configuring "
            "Multi-Agent Debate (MAD) systems. You help a user turn a natural-"
            "language description into a valid MAD configuration artifact."
        ),
        _SCOPE.strip(),
        _ASK_FIRST.strip(),
        "Allowed taxonomy keys (emit ONLY these values):\n" + _allowed_values_block(),
        "The MADConfig artifact JSON shape (match this structure exactly):\n"
        + f"```json\n{skeleton}\n```",
        _KEY_RULES.format(roles=roles).strip(),
        _edit_in_place_block(artifact).strip(),
        _ENVELOPE.strip(),
    ]
    return "\n\n".join(sections)


__all__ = ["build_system_prompt"]
