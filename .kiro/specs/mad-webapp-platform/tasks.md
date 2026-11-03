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
```

---

## Notes

- Phases 1–4 (engine) are provable with the MockModelClient and the gold cases *before* any UI exists,
  de-risking the taxonomy formalism early.
- Commit at phase boundaries (or finer), e.g. "feat(backend): taxonomy catalog + artifact schema",
  "feat(backend): MAD engine", "feat(backend): FastAPI + persistence", "feat(frontend): designer",
  "feat(website): docs" — sole author, on `feature/mad-webapp-platform`.
- "Under development" values remain fully configurable/persistable throughout; only execution is gated.
