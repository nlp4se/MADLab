# Implementation Plan

Each task is incremental, test-backed, and references the requirements it fulfills. The order builds
the headless engine first (so the taxonomy artifact and gold cases are provable without a UI), then
the web/API layer, then the frontend, then the website. Commit in coherent batches on
`feature/mad-webapp-platform` with the project owner as sole author.

Legend: `[ ]` not started · `[~]` in progress · `[x]` done.

---

## Phase 0 — Repository restructure & scaffolding

- [x] 0.1 Create the top-level component folders and move preserved assets
  - Create `backend/`, `frontend/`, `website/`, `shared/icons/`.
  - Keep `data/` and `paper/` in place; update top-level `README.md` to describe the three components.
  - Add per-component `README.md` stubs.
  - _Requirements: 14.1_

- [x] 0.2 Scaffold the Python backend project
  - `backend/pyproject.toml` (or `requirements.txt`) with: fastapi, uvicorn, pydantic v2, sqlalchemy,
    litellm, cryptography, pandas, python-dotenv, pytest, httpx. Preserve existing analysis deps.
  - Create package skeleton `backend/mad/`, `backend/app/`, `backend/cli/`, `backend/tests/`.
  - Add a dev run script and document setup.
  - _Requirements: 12.2, 14.5_

---

## Phase 1 — Taxonomy catalog, artifact schema & templates (engine core)

- [x] 1.1 Implement the taxonomy catalog as data
  - `backend/mad/taxonomy/catalog.py`: define every dimension → sub-dimension → value with
    `key`, `label`, `description` (paper-aligned), `default`, `executable`, optional `icon`.
  - Cover Participants (persona attributes/heterogeneity/assignment, 6 roles, base-model family/
    heterogeneity), Interaction (topology adaptability/structure + 7 canonical patterns, protocol
    mechanisms, format syntax/content/memory + metadata signals), Agreement (authority, resolution).
  - Mark non-executable values (`embeddings`, `parametric`, `long_term`, `knowledge_retrieval`,
    `dynamic` without policy) as `executable=False`.
  - _Requirements: 1.1-1.8, 2.1-2.9, 3.1-3.6, 7.4, 7.5, 12.3_

- [x] 1.2 Implement the MAD Configuration Artifact schema (Pydantic)
  - `backend/mad/taxonomy/schema.py`: `MADConfig` with `participants`, `interaction`, `agreement`,
    `input_spec`, `schema_version`, ids/metadata — matching the design's JSON shape.
  - Add semantic validators: edges reference existing nodes; judge_based authority requires a judge
    node; weighted_vote/scoring require resolution_params; executable-flag gating hook.
  - Unit tests for valid/invalid artifacts and field-level error reporting.
  - _Requirements: 1.*, 2.*, 3.*, 4.1, 4.2, 7.3_

- [x] 1.3 Implement artifact versioning and round-trip I/O
  - `backend/mad/taxonomy/version.py`: schema version constant + forward-migration hook.
  - Export to JSON / import from JSON with validation; reject invalid with actionable errors.
  - Tests: round-trip export→import equality; invalid rejection; version stamp present.
  - _Requirements: 4.1, 4.2, 4.3, 4.5_

- [x] 1.4 Implement predefined templates (personas, roles, topologies) and gold cases
  - `backend/mad/taxonomy/templates.py`: persona patterns (angel/devil, prosecution/defence,
    faithful/unfaithful, proponent/challenger, gold/distractor, Six Thinking Hats, expert panel);
    role definitions with icon refs; topology builders (chain/ring/star/tree/layered/sparse/
    bipartite/fully_connected) that generate nodes/edges.
  - Build the two gold configs: **RE binary debate** and **ChatEval S1/S2/S3** (per Table 3).
  - Tests: each gold config loads + validates; S1/S2/S3 differ only in documented attributes.
  - _Requirements: 1.9, 2.4, 4.4, 5.7_

---

## Phase 2 — Provider abstraction & model execution

- [x] 2.1 Define the ModelClient protocol and response types
  - `backend/mad/providers/base.py`: `complete(messages, model, params, response_schema) ->
    ModelResponse` (text + usage). Define `ModelResponse`, `Usage`.
  - A deterministic **MockModelClient** for tests.
  - _Requirements: 9.1_

- [x] 2.2 Implement the LiteLLM-backed adapter
  - `backend/mad/providers/litellm_client.py`: map provider kinds (openai/anthropic/gemini/mistral/
    deepseek/ollama/vllm/openai_compatible) + base-URL override to LiteLLM calls.
  - Structured output: native JSON-schema where supported, JSON-mode + Pydantic validation fallback
    otherwise; record which path was used (capability flag).
  - Tests against a stubbed endpoint incl. the fallback path.
  - _Requirements: 8.2, 9.1, 9.3, 9.4_

- [x] 2.3 Implement the provider registry and connectivity test
  - `backend/mad/providers/registry.py`: resolve `(provider_id, model_key)` → client; support
    heterogeneous models in one debate; `test_connection(provider)` minimal call.
  - Tests: resolution, heterogeneous selection, connectivity success/failure.
  - _Requirements: 8.5, 8.6, 9.2_

---

## Phase 3 — MAD engine (headless orchestration)

- [x] 3.1 Implement the topology graph model
  - `backend/mad/engine/graph.py`: build `G=(V,E)` from `interaction.topology`; neighbour queries;
    pattern builders reused from templates; dynamic-without-policy raises controlled `UnderDevelopment`.
  - Tests: each canonical pattern produces correct edge sets; fully-connected/grouped correctness.
  - _Requirements: 2.1, 2.3, 2.4, 7.5_

- [x] 3.2 Implement the protocol scheduler
  - `backend/mad/engine/protocol.py`: generate activation `E(t)` for sequential (fixed/randomized/
    coordinator), simultaneous (broadcast), and hybrid (phased); loop to `max_rounds` or consensus stop.
  - Tests: ordering correctness, round counts, hybrid phase sequencing, randomized determinism w/ seed.
  - _Requirements: 2.5_

- [x] 3.3 Implement the format layer
  - `backend/mad/engine/format.py`: assemble context from short-term memory `M(t)`; content transform
    `m̃=f(m)` (verbatim passthrough, summarized via summarizer role, other=registered transform);
    attach metadata signals. Gate embeddings syntax and long/retrieval/parametric memory as under-dev.
  - Tests: verbatim vs. summarized context assembly; metadata attachment; under-dev gating.
  - _Requirements: 2.6, 2.7, 2.8_

- [x] 3.4 Implement the agreement layer
  - `backend/mad/engine/agreement.py`: resolution strategies (majority_vote, average,
    argument_evaluation, consensus; weighted_vote, scoring with params); authority routing
    (collective aggregate / judge_based routes transcript|summary to judge, parse `output_schema`;
    hybrid; other). Mark non-executable resolutions under-dev.
  - Tests: each executable strategy on synthetic transcripts; output_schema parsing; tie-breaking.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3.5 Implement the transcript model and the orchestrator
  - `backend/mad/engine/transcript.py`: structured record (rounds, per-agent messages, metadata,
    usage, final decision, errors).
  - `backend/mad/engine/orchestrator.py`: `run_debate(config, instance, registry) -> Transcript`
    wiring graph → protocol → format → model calls → agreement; per-call retry/backoff.
  - Tests with MockModelClient: single debate end-to-end.
  - _Requirements: 9.4, 9.5, 10.4_

- [x] 3.6 Gold-case engine tests
  - Run RE binary debate and ChatEval S1/S2/S3 through the orchestrator with MockModelClient; assert
    transcript structure and decisions; assert attribute-level differences among S1/S2/S3.
  - _Requirements: 4.4, 12.5_

---

## Phase 4 — Input binding, datasets & evaluation

- [x] 4.1 Implement input template resolution
  - `backend/mad/input/template.py`: resolve `{{placeholder}}` tags against an instance dict; list
    placeholders; validate template vs. available fields.
  - Tests: resolution, missing-placeholder errors, ad-hoc field mapping.
  - _Requirements: 10.2_

- [x] 4.2 Implement dataset loading and column mapping
  - `backend/mad/input/dataset.py`: load CSV, expose columns/row_count, map columns→placeholders,
    sample-row preview, optional ground-truth column.
  - Tests on `data/datasets/PROMISE/nfr-small.csv`.
  - _Requirements: 10.1, 10.3_

- [x] 4.3 Refactor evaluation metrics into the engine
  - `backend/mad/evaluation/`: port existing `baseline.py`/`metrics.py`; compute per-instance and
    aggregate metrics when ground truth present.
  - Tests: metrics match current outputs on a known sample.
  - _Requirements: 10.7, 11.5, 12.5, 14.2_

---

## Phase 5 — Persistence & security

- [x] 5.1 Implement SQLAlchemy models and session/migrations
  - `backend/app/db/`: tables providers, configurations, datasets, executions, execution_instances
    (per design). Immutable `config_snapshot` on executions.
  - _Requirements: 11.3, 14.3_

- [x] 5.2 Implement credential encryption
  - `backend/app/security/`: Fernet encrypt/decrypt keyed from a `.env` server secret; store encrypted
    API keys; expose only `has_key` upward.
  - Tests: round-trip encrypt/decrypt; plaintext never serialized.
  - _Requirements: 8.4_

---

## Phase 6 — FastAPI web layer

- [x] 6.1 App bootstrap, config, OpenAPI
  - `backend/app/main.py`: app factory, CORS for frontend, settings, DB init, error handlers mapping
    validation/engine errors to structured responses.
  - _Requirements: 12.1, 12.2_

- [x] 6.2 Taxonomy router
  - `GET /api/taxonomy`: serve catalog + templates + defaults + executable flags.
  - _Requirements: 7.4, 12.3_

- [x] 6.3 Configurations router (CRUD, copy, import/export, validate)
  - `GET/POST /api/configs`, `GET/PUT/DELETE /api/configs/{id}`, `POST /configs/{id}/copy`,
    `POST /configs/import`, `GET /configs/{id}/export`, `POST /configs/validate`.
  - Seed built-in gold/template configs on first run.
  - API tests for each path.
  - _Requirements: 4.2, 4.3, 5.1-5.7, 7.3_

- [x] 6.4 Providers router (CRUD, test) with write-only keys
  - `GET/POST /api/providers`, `PUT/DELETE /api/providers/{id}`, `POST /providers/{id}/test`.
  - Responses expose metadata + `has_key` only.
  - API tests incl. key-never-returned assertion.
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 6.5 Datasets router
  - `POST /api/datasets` (upload CSV), `GET /api/datasets/{id}`, `GET /api/datasets/{id}/preview`
    (resolved template for a sample row + a given config).
  - _Requirements: 10.1, 10.3_

- [x] 6.6 Executions router + async job runner
  - `POST /api/executions` (single or batch) → background job; `GET /api/executions`,
    `GET /api/executions/{id}`, `GET /api/executions/{id}/stream` (SSE progress),
    `DELETE /api/executions/{id}`, `GET /api/executions/{id}/export`.
  - Job runner: iterate instances, concurrency limit, per-instance error isolation, progress + metrics
    to DB, immutable config snapshot, under-dev pre-run gating.
  - API tests: single-run lifecycle, batch progress, failure isolation.
  - _Requirements: 10.4, 10.5, 10.6, 11.1, 11.2, 11.3, 11.4, 7.5_

- [x] 6.7 Headless CLI drivers
  - `backend/cli/`: commands mirroring current workflow (create config, run over CSV, evaluate) calling
    the same services/engine; preserve existing classification commands.
  - Regression test: reproduce classification on `nfr-small.csv` via CLI through the new engine.
  - _Requirements: 12.4, 12.5_

---

## Phase 7 — Shared icon assets

- [x] 7.1 Author role and topology SVG icons
  - `shared/icons/`: six role icons (debater/judge/summarizer/leader/verifier/editor) and topology
    diagrams (chain/ring/star/tree/layered/sparse/bipartite/fully_connected); consumed by both
    frontend and website.
  - _Requirements: 6.7, 13.4_

---

## Phase 8 — Frontend (React + TS + Vite)

- [x] 8.1 Scaffold the frontend and typed API client
  - Vite + React + TS; React Query + Zustand; shadcn/ui; base layout and routing.
  - Typed API client; load `/api/taxonomy` once and provide via context.
  - Dimension theming tokens (Participants/Interaction/Agreement colours + icons).
  - _Requirements: 6.6, 7.4, 14.5_

- [x] 8.2 Configurations list view (CRUD + copy + import/export)
  - List with summary chips; actions open/copy/delete/export/import; "new from template" (gold cases
    + patterns); delete confirmation with execution-reference warning.
  - _Requirements: 5.1-5.7, 4.3_

- [x] 8.3 Visual designer — canvas (React Flow)
  - Nodes = participants (role icon + model badge), directed edges with name/colour/direction; add/
    move/connect/remove; apply topology template to auto-generate nodes/edges; auto-layout; two-way
    sync with the `G=(V,E)` artifact.
  - _Requirements: 6.1, 6.2, 6.4, 6.5, 6.8, 6.7_

- [x] 8.4 Visual designer — inspector & dimension panels
  - Click node → Participants panel (roles multi-select incl. custom; persona background/personality/
    stance with template picker; base-model binding to configured provider/model). Select edge → edge
    props. Interaction panel (topology meta, protocol, format) and Agreement panel (authority,
    resolution, params, output_schema). Group prompt-designed vs. structured fields with labels.
  - Defaults pre-filled; progressive disclosure; under-dev badges; client+server validation surfacing.
  - _Requirements: 1.*, 2.*, 3.*, 6.3, 6.6, 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 8.5 Providers management view
  - Add/edit/remove providers; kind selector; write-only API key field (shows configured state), base
    URL, model keys; test-connection button with result feedback.
  - _Requirements: 8.1-8.6_

- [x] 8.6 Run launcher view
  - Pick config → input mode: single (form from `ad_hoc_fields`) or batch (upload/select CSV → map
    columns to placeholders → preview resolved input for a sample row) → launch.
  - _Requirements: 10.1, 10.2, 10.3_

- [x] 8.7 Executions history & transcript viewer
  - List with status/metrics; detail shows per-instance transcript (rounds × agents, colour-coded by
    dimension/role), final decision, metrics, evaluation charts when ground truth present; delete +
    export; live progress for running executions.
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 10.5_

- [x] 8.8 Frontend tests
  - Component tests: designer canvas↔artifact sync; taxonomy-driven forms; providers write-only key.
  - Smoke e2e: create→save→run (mock/local provider)→inspect loop.
  - _Requirements: 6.8, 7.1, 8.4_

---

## Phase 9 — Documentation website (static)

- [x] 9.1 Scaffold the static site
  - Astro (or prerendered React); independent build/deploy; import shared icons + a taxonomy-catalog
    snapshot.
  - _Requirements: 13.1_

- [x] 9.2 Overview & taxonomy pages
  - Home (project summary + links to both papers); Taxonomy page with three colour-themed sections
    listing sub-dimensions/values using the shared labels/descriptions/icons.
  - _Requirements: 13.2, 13.3, 13.5_

- [x] 9.3 Patterns gallery
  - Persona patterns, roles, and topology diagrams illustrated with shared SVGs.
  - _Requirements: 13.4_

---

## Phase 10 — Integration, regression & delivery

- [x] 10.1 End-to-end integration pass
  - Run both gold cases through the full stack (frontend → API → engine → a real local provider via
    Ollama/OpenAI-compatible and a closed-weight provider if keys available); verify history + metrics.
  - _Requirements: 4.4, 9.2, 10.*, 11.*_

- [x] 10.2 Requirements-classification regression
  - Reproduce the current binary classification result on `nfr-small.csv` through the new engine (CLI
    and API) and compare against existing `data/output`/`data/evaluation` artifacts.
  - _Requirements: 12.5, 14.2_

- [x] 10.3 Finalize docs and setup instructions
  - Top-level + per-component READMEs: setup, run, and the gold-case walkthrough.
  - _Requirements: 14.5_

---

## Phase 11 — AI design assistant (chat-to-configure)

- [x] 11.1 Conversational MAD design assistant in the designer
  - Backend: `POST /api/assistant/design` — accepts the user message, the running conversation, the
    current MAD artifact, and a chosen provider_id + model; returns a structured envelope that is
    either a free-text clarifying question (when intent is ambiguous) or a proposed full `MADConfig`
    artifact + a short explanation. A structured system prompt teaches the taxonomy + exact JSON
    schema (seeded from the catalog so only valid keys/values are used), instructs the model to ask
    verification questions before proposing when needed, keeps it scoped to MAD-config design, and
    enforces the response envelope. Proposed artifacts are validated through `MADConfig` before being
    returned. Calls go through the existing LiteLLM provider layer (keys decrypted at call time);
    provider + model are configurable per request.
  - Frontend: a floating chat button on the designer canvas opens a popup panel. Free chat; clarifying
    questions render as chat turns; a proposed config is shown for **review** with an **Apply to
    canvas** action that loads it into the designer store (two-way sync persists on Save). Provider +
    model are selectable in the panel. Provider errors (e.g. an unscoped key) surface clearly.
  - Tests: backend route (mocked provider) for the question vs. proposal envelopes and artifact
    validation; frontend component test for the chat flow + apply-to-canvas.
  - _Requirements: 4.1, 4.2, 6.1, 6.8, 7.3, 8.6, 12.2_

- [x] 11.2 Deletable edges and persisted Start/End IO connections
  - Canvas: right-click any edge (participant edges and Start/End connectors) opens a context menu
    with Delete. Start -> node and node -> End connectors can be re-added by dragging.
  - Artifact: optional `interaction.topology.entry_nodes` / `exit_nodes` (null = default). The
    default derivation matches engine behaviour: Start feeds every speaking participant; End
    receives from the judge (judge-based) or the aggregated debaters (otherwise). Validators: ids
    reference existing nodes; lists non-empty when set; judge-based exit_nodes must include a judge.
  - Engine: only entry nodes receive the task input; only exit nodes' outputs feed the decision
    (deciding judge = first judge in exit_nodes for judge-based). Null keeps current behaviour, so
    gold cases and existing configs are unchanged.
  - Tests: schema validation, engine honouring overrides, canvas derivation + delete/re-add.
  - _Requirements: 2.1, 3.1, 6.2, 6.4, 6.8, 9.4_

- [x] 11.3 Chat-style debate replay for an execution instance
  - In the execution detail view, each instance gets an action that opens a popup showing that
    instance's debate as a group-chat conversation: the task input first, then every agent turn in
    order with round dividers, each message attributed to its participant (label, role colour, model
    badge resolved from the config snapshot), recoverable errors inline, and the final decision as
    the closing message.
  - Playback controls (play/pause, step, show all) to watch how the discussion unfolded.
  - Frontend-only: built from the stored transcript + config snapshot.
  - Tests: component test for opening the replay, message order/attribution, and playback.
  - _Requirements: 11.2, 13.3_

- [x] 11.4 Floating, bendable edges and a persisted canvas layout
  - Nodes no longer have fixed left-in / right-out ports: a connection can start or end at any point
    of a node's border, and edges attach to the node boundary nearest the other end (floating
    edges). Arrowheads alone convey direction. Reciprocal pairs (A->B and B->A) render as two
    separated curves so circular exchanges are visible.
  - Every edge (participant edges and Start/End connectors) has a draggable bend point to reshape
    it; double-click resets it.
  - Layout persistence: optional presentation-only `ui` field on MADConfig (node positions incl.
    Start/End, edge bends), ignored by the engine, saved with the config and kept on export/import.
  - Tests: geometry helpers, bend/store actions, layout persistence round trip, schema/export.
  - _Requirements: 4.1, 4.3, 6.1, 6.2, 6.4, 6.8_

- [x] 11.5 Session-persistent assistant chat and right-click node delete
  - Assistant chat history lives in an in-memory (not persisted) store keyed by config id: closing and
    reopening the panel, or navigating inside the app, keeps the conversation and the provider/model
    choice so the user can continue; a pending reply still lands if the panel was closed. A page
    reload or closing the window clears it. A "New chat" action clears the current config's history.
  - Canvas: right-click a participant node opens the same portalled context menu with Delete
    (`removeNode`, which also removes incident edges and Start/End connectors). Start/End are
    synthetic and always present, so they get no Delete. Menu closes on outside click, Escape, pane
    click, or canvas move.
  - Tests: history survives close/reopen and is per config; New chat clears it; node context menu
    deletes the node and its edges; no menu for Start/End.
  - _Requirements: 6.1, 6.2, 6.8, 12.2_

- [x] 11.6 Consistent debate-level vs node-level scope for Participants settings
  - Scope rule: a setting is edited in exactly one place. Debate level = inspector with no selection;
    node level = selected node. Values governed at debate level are read-only on nodes (shown with a
    "Shared: edit in debate settings" link that clears the selection). The store keeps the artifact
    consistent; the canvas reflects every change immediately (badges, colours).
  - Persona assignment is the FIRST participant setting. `unspecified`: persona fields disabled at
    both levels, heterogeneity disabled with a hint. `manual`: persona options appear. `automatic`:
    under development; fields disabled with a note. Switching to `unspecified` while personas exist
    asks for confirmation (like the topology overwrite warning) and clears them.
  - Persona heterogeneity (only when manual). `homogeneous`: a shared persona editor (template picker
    + background/personality/stance) at debate level, applied to every debater-role node (catalog:
    "whether debaters share one persona"; judges/summarizers keep their own). `heterogeneous`: a
    debate-level message says personas are set per participant; node panels are editable.
  - Base model heterogeneity. `homogeneous`: a shared provider/model/family editor at debate level,
    applied to ALL nodes (canvas model badges update at once). `heterogeneous`: debate-level message
    says models are set per participant; node panels are editable.
  - Switching heterogeneous -> homogeneous with divergent values asks for confirmation and copies the
    first debater's persona / first bound node's model. New nodes, and nodes gaining the debater role,
    inherit the shared values. The system prompt stays per node in its own Instructions group, always
    editable, independent of persona settings.
  - Loaded/imported/assistant artifacts whose data contradicts the declared mode are never silently
    rewritten: an inline conflict banner (and an amber marker on affected nodes) offers the two fixes
    (e.g. "Make all match" / "Switch to heterogeneous"; "Switch to Manual" / "Clear personas").
  - Engine and schema unchanged (they already read per-node values). Add assistant prompt rules so
    proposals respect these invariants.
  - Tests: store invariants (broadcast, inherit, switch with/without divergence, clear on unspecified),
    panel visibility/disabled states per mode, conflict detection and both fixes, canvas badges update.
  - _Requirements: 1.2, 1.3, 1.4, 1.7, 1.8, 6.3, 6.8, 7.4_

- [x] 11.7 Consistent scope and dependent fields for Interaction and Agreement settings
  - Same scope rule as 11.6. Debate level: topology (template + adaptability), protocol, format,
    agreement. Edge level: label/colour/direction only. Node level: roles (and group if the grouped
    structure is offered). Every dependent field shows only when it has an effect; options that
    would fail at run time are disabled with the reason (mirroring the engine), not silently allowed.
  - Topology: show adaptability (static; dynamic under development). Detect drift: when the edges no
    longer match the applied template over the current nodes, the summary and toolbar say "Custom
    (edited from <template>)" and offer Re-apply. If the grouped structure is offered, nodes need a
    group assignment; otherwise do not offer it.
  - Protocol, mechanism first. Sequential: ordering shown. Fixed: a Turn order list (reorder
    participants; writes `protocol.order`; empty = declaration order, shown as such) and turn-number
    badges on canvas nodes. Randomized: note, no list. Simultaneous: ordering hidden, note that all act
    each round. Hybrid: a phases editor (add/remove/reorder; per-phase mechanism + participants,
    empty = all), ordering hidden, inline error when no phase exists. Node delete/rename prunes
    `order` and `phases`.
  - Format: debate level; if a choice requires a role (e.g. summarized content needs a summarizer, if
    the engine requires it), show the requirement inline.
  - Agreement, authority first, then resolution filtered by an engine-derived compatibility matrix
    (e.g. argument_evaluation needs a judge, so it is disabled under collective). judge_based/hybrid
    without a judge node: inline notice with an "Add judge" action. Collective with judge nodes:
    notice that judges do not decide. End connectors update immediately when authority changes.
    resolution_params only for weighted_vote/scoring.
  - Tests: visibility per mechanism/ordering, turn order + badges, phases editor and pruning, drift
    detection, compatibility matrix, judge notices and Add judge.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 6.3, 6.5, 7.4_

- [x] 11.8 Overlap-avoiding, flow-aware auto layout
  - Replace the fixed declaration-order circle with a dependency-free layered layout over the full
    canvas graph INCLUDING Start/End: Start in the first layer, End in the last, ranks from the
    Start -> ... -> End flow (cycles broken; strongly connected components such as fully connected
    debaters share a rank and are arranged as a compact cluster so intra-cluster edges do not run
    through each other's nodes), barycenter ordering sweeps to reduce edge crossings, judges and
    summarizers placed by their connections (typically next to End).
  - Spacing from real node sizes (React Flow measured width/height when available, else defaults),
    with a minimum gap so no two node boxes overlap.
  - Edge clearance pass: for any edge whose rendered curve passes through a non-endpoint node box,
    set its bend offset (the 11.4 bend model) so it routes around the box; reciprocal pairs keep
    their separation. Auto layout writes positions for Start/End too and replaces all bends.
  - Triggers: the toolbar Auto layout button, loading a config without stored ui, and new configs.
    Adding a node places it in free space near its neighbours without moving existing nodes.
    Stored layouts are never re-laid-out automatically.
  - Tests: for every offered topology template x 2..10 participants (+ judge and summarizer
    variants): no node-box overlaps, no edge curve crossing a non-endpoint node box, Start left of
    every participant and End right of every participant, deterministic output; crossing count not
    worse than the old circle on chain/star/tree; new-node placement does not overlap.
  - _Requirements: 6.1, 6.2, 6.4, 6.8_

- [x] 11.9 Base model family derived from the provider (not a free parameter)
  - Providers: new nullable `family` column on `providers` (open_weight | closed_weight), added on
    startup for existing databases (idempotent ALTER TABLE in `init_db`; bump the schema version
    marker). Fixed by kind: openai / anthropic / gemini = closed_weight; ollama / vllm / deepseek =
    open_weight. Mixed kinds (mistral, openai_compatible) take the stored value, defaulting to
    closed_weight (mistral) and open_weight (openai_compatible). `ProviderResponse` returns the
    effective `family`; create/update accept it only for mixed kinds and reject a value that
    contradicts a fixed kind (422).
  - Providers view: Family field, pre-filled from the kind; read-only with the reason for fixed kinds,
    editable for mixed kinds.
  - Designer: family is no longer editable at node or debate level. ModelEditor shows it read-only
    (derived from the bound provider; "Unbound" when none). Binding or changing a provider writes
    the derived family into `base_model.family`. Base-model homogeneity compares provider/model only.
  - Backend normalization: configuration create/update/import and the execution config snapshot set
    `base_model.family` from the bound provider when it exists (unbound nodes keep the stored value).
    Engine and artifact schema unchanged. Assistant prompt: family is derived, never chosen.
  - Tests: kind -> family mapping, column added to an old DB, provider API accept/reject, Providers
    view field states, designer read-only display and write-on-bind, save/snapshot normalization.
  - _Requirements: 1.7, 1.8, 8.2, 8.6, 14.3_

- [x] 11.10 Editable config name and an Input editor in the designer
  - Name/description: the designer header shows the config name as an inline-editable title (click or
    pencil icon; Enter/blur commits, Escape cancels, empty name rejected inline) plus an optional
    description; edits mark the store dirty and are saved with the existing Save.
  - Input editor: the instance input (`input_spec`) becomes editable where it enters the debate.
    Selecting the Start node (and a new Input tab in the inspector) opens an Input panel:
    template textarea with `{{placeholder}}` tags; placeholders auto-detected and kept in
    `input_spec.placeholders`; a label per placeholder (`ad_hoc_fields`, defaulting to the key);
    a live preview with sample values; a note on which participants receive it (the Start
    connectors) and how it is injected ("Task: <resolved input>" in their system prompt; judges
    see it in their context). Placeholder syntax matches the backend `PLACEHOLDER_PATTERN`
    (also fix the frontend run-launcher regex to match it).
  - Readiness: an empty template shows an inline warning in the Input panel, on the Start node, and
    in the Run launcher (with a link to the designer's Input panel) instead of a silent disabled
    Launch. New configs start with a starter template (e.g. `{{input}}` labelled "Input").
  - Assistant: proposals keep or set a sensible `input_spec`; the prompt documents it.
  - Tests: name edit/validation/dirty/save, template parsing and label sync, preview, Start-node
    selection opens the panel, empty-template warnings, run-launcher fields from the edited spec.
  - _Requirements: 6.1, 6.3, 10.2, 12.2_
```

---

## Notes

- Phases 1–4 (engine) are provable with the MockModelClient and the gold cases *before* any UI exists,
  de-risking the taxonomy formalism early.
- Commit at phase boundaries (or finer), e.g. "feat(backend): taxonomy catalog + artifact schema",
  "feat(backend): MAD engine", "feat(backend): FastAPI + persistence", "feat(frontend): designer",
  "feat(website): docs" — sole author, on `feature/mad-webapp-platform`.
- "Under development" values remain fully configurable/persistable throughout; only execution is gated.
