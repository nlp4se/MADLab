# Design Document

## Overview

This design turns the existing OpenAI-only, CLI MAD research code into a three-component platform:
a **taxonomy-complete backend** (FastAPI + a refactored MAD engine + multi-provider model execution),
a **React management webapp** (visual designer, CRUD, execution history, provider management), and a
**static documentation website**.

The architectural spine is the **MAD Configuration Artifact** — a single versioned JSON document that
instantiates the full three-dimensional taxonomy (Participants / Interaction / Agreement) and carries
the paper's formal notation (`G=(V,E)`, `E(t)`, `m̃=f(m)`, `(authority, resolution)`). Every other part
of the system is organized around producing, validating, persisting, executing, and visualizing this
artifact.

Three principles drive the design:

1. **Taxonomy is data, not code.** The taxonomy (dimensions, values, defaults, descriptions, predefined
   templates, "under development" flags) is a declarative catalog served by the backend. The frontend
   renders forms and the website renders docs from this catalog. Adding a taxonomy value is a data edit,
   not a UI rewrite.
2. **Configuration ≠ execution.** A configuration is an input-free template. An execution binds a
   configuration snapshot to a concrete input (one instance or a CSV batch) via an input template.
3. **Engine is headless-first.** The MAD engine is a pure Python library with no web dependency; FastAPI
   and the CLI are two thin drivers over it, preserving the current research workflow.

```
┌──────────────┐     REST/JSON      ┌─────────────────────────────────────┐
│  Frontend    │ ◀────────────────▶ │  Backend (FastAPI)                  │
│  React/TS    │                    │  ┌───────────────────────────────┐  │
│  - Designer  │                    │  │ API layer (routers)           │  │
│  - CRUD list │                    │  ├───────────────────────────────┤  │
│  - Providers │                    │  │ Services (config/exec/provider)│ │
│  - History   │                    │  ├───────────────────────────────┤  │
└──────────────┘                    │  │ MAD Engine (headless)         │  │
                                     │  │  topology/protocol/format/    │  │
┌──────────────┐    static assets   │  │  agreement + orchestrator     │  │
│  Website      │  (shared taxonomy  │  ├───────────────────────────────┤  │
│  static/Astro │   catalog + icons) │  │ Provider adapters (LiteLLM)   │  │
└──────────────┘                    │  ├───────────────────────────────┤  │
                                     │  │ Persistence (SQLAlchemy/SQLite)│ │
                                     │  └───────────────────────────────┘  │
                                     └─────────────────────────────────────┘
                                                      │
                                             SQLite + JSON artifacts
```

Requirements traceability is given per component below and summarized in the final section.

---

## Repository Architecture (Req 14)

```
llm-discussion/
├── backend/
│   ├── mad/                      # headless engine + domain (no web deps)
│   │   ├── taxonomy/             # taxonomy catalog + schema + defaults + templates
│   │   │   ├── catalog.py        # data-driven taxonomy definition (values, flags, docs)
│   │   │   ├── schema.py         # Pydantic models for the Config Artifact
│   │   │   ├── templates.py      # predefined personas, roles, topologies, gold cases
│   │   │   └── version.py        # artifact schema version + migrations
│   │   ├── engine/
│   │   │   ├── graph.py          # G=(V,E) topology model + builders for canonical patterns
│   │   │   ├── protocol.py       # scheduler: sequential/simultaneous/hybrid, E(t), rounds
│   │   │   ├── format.py         # content transforms m̃=f(m), memory assembly, metadata
│   │   │   ├── agreement.py      # authority + resolution strategies
│   │   │   ├── orchestrator.py   # runs one debate over one instance
│   │   │   └── transcript.py     # structured debate record
│   │   ├── providers/            # unified model invocation
│   │   │   ├── base.py           # ModelClient protocol
│   │   │   ├── litellm_client.py # LiteLLM-backed adapter (all providers)
│   │   │   └── registry.py       # provider/model resolution + connectivity test
│   │   ├── input/
│   │   │   ├── template.py       # placeholder/tag resolution ({{col}})
│   │   │   └── dataset.py        # CSV loading, column mapping, sampling
│   │   ├── evaluation/           # refactor of existing metrics/baseline
│   │   └── errors.py
│   ├── app/                      # FastAPI web layer
│   │   ├── main.py
│   │   ├── routers/              # taxonomy, configs, providers, executions, datasets
│   │   ├── schemas/              # request/response DTOs
│   │   ├── services/             # orchestration between API and engine
│   │   ├── db/                   # SQLAlchemy models, session, migrations
│   │   ├── security/             # credential encryption (Fernet)
│   │   └── jobs/                 # async execution runner + progress
│   ├── cli/                      # headless CLI drivers (preserve research workflow)
│   ├── tests/
│   ├── pyproject.toml / requirements.txt
│   └── README.md
├── frontend/                     # React + TS + Vite
│   ├── src/
│   │   ├── api/                  # typed client (generated/hand-written)
│   │   ├── taxonomy/             # catalog loader + dimension theming
│   │   ├── features/
│   │   │   ├── configs/          # list, CRUD, copy
│   │   │   ├── designer/         # React Flow canvas, node/edge editors
│   │   │   ├── providers/        # provider + credential management
│   │   │   └── executions/       # run launcher, history, transcript viewer
│   │   ├── components/           # shared UI (dimension panels, icons)
│   │   └── assets/icons/         # role + topology SVGs (shared with website)
│   └── README.md
├── website/                      # static docs/landing (Astro or prerendered React)
│   ├── src/ (pages, components)
│   ├── public/ (shared taxonomy catalog snapshot + icons)
│   └── README.md
├── shared/
│   └── icons/                    # single source of role/topology SVGs
├── data/                         # preserved research assets (datasets, prompts, outputs)
├── paper/                        # unchanged
└── README.md                     # top-level: project overview + component links
```

The current `code/` is migrated: `code/llm/*` → `backend/mad/engine` + `backend/mad/providers`;
`code/evaluation/*` → `backend/mad/evaluation`; `data/config` + `data/prompts` become seed templates
in `backend/mad/taxonomy/templates.py` and built-in example configs.

---

## The MAD Configuration Artifact (Reqs 1–4)

A single JSON document, validated by Pydantic. This is the normative schema (abridged; full field docs
live in `taxonomy/schema.py`). `executable` flags in the taxonomy catalog drive "under development"
labelling; the artifact itself just carries values.

```jsonc
{
  "schema_version": "1.0",
  "id": "uuid",
  "name": "ChatEval — Simultaneous-Talk + Summarizer",
  "description": "...",
  "participants": {
    "base_model_heterogeneity": "homogeneous | heterogeneous",
    "persona_heterogeneity": "homogeneous | heterogeneous",
    "persona_assignment": "unspecified | manual | automatic",
    "nodes": [
      {
        "id": "alice",
        "label": "Alice",
        "roles": ["debater"],                 // debater|judge|summarizer|leader|verifier|editor|custom:*
        "persona": {
          "background": "string | null",
          "personality": "string | null",
          "stance": "string | null",
          "template_ref": "angel | devil | prosecution | ... | null"
        },
        "base_model": {
          "provider_id": "uuid",
          "model_key": "gpt-4o",
          "family": "open_weight | closed_weight",
          "temperature": 0.0,
          "params": { }
        },
        "system_prompt": "free-form override, composed from persona if absent",
        "group": "group-id | null"
      }
    ],
    "groups": [ { "id": "g1", "label": "Team A", "color": "#..." } ]
  },
  "interaction": {
    "topology": {
      "adaptability": "static | dynamic",      // dynamic => under_development policy
      "dynamic_policy": null,
      "structure": "fully_connected | grouped | structured_network",
      "pattern": "chain|ring|star|tree|layered|sparse|bipartite|null",
      "edges": [
        { "source": "alice", "target": "bob", "directed": true,
          "label": "critique", "color": "#3b82f6" }
      ]
    },
    "protocol": {
      "mechanism": "sequential | simultaneous | hybrid",
      "max_rounds": 2,
      "ordering": "fixed | randomized | coordinator",
      "order": ["alice", "bob", "carol"],
      "phases": null                            // for hybrid: ordered seq/sim phases
    },
    "format": {
      "syntax": "natural_language | embeddings",  // embeddings => under_development
      "content": {
        "strategy": "verbatim | summarized | other",
        "metadata_signals": ["confidence", "uncertainty", "verifier_score",
                              "judge_likelihood", "bias_quality", "guideline_weight"],
        "transform_ref": null
      },
      "memory": "short_term | long_term | knowledge_retrieval | parametric"
    }
  },
  "agreement": {
    "authority": "collective | judge_based | hybrid | other",
    "resolution": "argument_evaluation | majority_vote | weighted_vote | scoring | average | consensus",
    "resolution_params": { "weights": null, "scoring": null, "tie_breaker": null },
    "output_schema": { /* optional JSON Schema, e.g. { class: [F, NF] } */ }
  },
  "input_spec": {
    "template": "Classify this requirement: {{requirement}}",
    "placeholders": ["requirement"],
    "ad_hoc_fields": [ { "key": "requirement", "label": "Requirement text" } ]
  }
}
```

### Why this shape

- **Formal-notation fidelity:** `participants.nodes` = `V`; `interaction.topology.edges` = `E`;
  `protocol` carries `E(t)` semantics via `mechanism` + `max_rounds` + `ordering`; `format.content`
  carries `m̃=f(m)` via `strategy`/`transform_ref`; `agreement` is the `(authority, resolution)` pair.
- **Templates vs. free-form (per Req 1.9, 1.10, 2.4):** `persona.template_ref` and
  `topology.pattern` reference catalog templates that expand into concrete fields/edges but stay
  fully editable; `system_prompt` and `persona.*` allow arbitrary free-form text.
- **Structured vs. prompt-designed (the user's distinction):** persona *content* (background/
  personality/stance, system_prompt) is **prompt-designed**; everything else (heterogeneity,
  assignment mode, roles, topology, protocol, format, agreement, output_schema) is **structured
  input**. The UI labels each field accordingly.

### Gold-case validation (Req 4.4)
`taxonomy/templates.py` ships:
- **RE binary debate**: 2 debater nodes (stance = functional / non-functional) + 1 judge node,
  fully connected, sequential with `max_rounds` = iterations, authority = judge_based, resolution =
  argument_evaluation, `output_schema = {class: [F, NF]}`, input template `{{requirement}}`.
- **ChatEval S1/S2/S3** exactly as Table 3: three debaters (Alice/Bob/Carol) with distinct
  personalities (heterogeneous personas, manual assignment); S1 sequential / S2 simultaneous / S3
  simultaneous + Summarizer node with debater→summarizer edges; static fully-connected topology;
  verbatim (S1/S2) vs. hybrid verbatim+summarized (S3); short-term memory; collective authority;
  resolution = majority_vote (categorical) / average (numerical). A unit test asserts each loads,
  validates, and (for executable parts) runs.

A versioned loader in `taxonomy/version.py` migrates older artifacts forward (Req 4.5).

---

## Taxonomy Catalog (Reqs 7, 12.3, 13.3)

`taxonomy/catalog.py` defines, as data, every dimension → sub-dimension → value with:
`key`, `label`, `description` (paper-aligned), `default` flag, `executable` flag (false ⇒ "under
development"), and optional `icon` ref. The `/api/taxonomy` endpoint serves this verbatim. Frontend
and website both consume it so labels, tooltips, defaults, and "under development" badges are defined
once. Example entry:

```python
Value(key="sparse", label="Sparse network",
      description="Each agent interacts with a limited subset of peers (|E| ≪ |V|(|V|-1)).",
      executable=True, icon="topology/sparse")
```

Predefined template catalogs (also data-driven):
- **Persona patterns:** angel/devil, prosecution/defence, faithful/unfaithful, proponent/challenger,
  gold/distractor, Six Thinking Hats, domain-expert panel.
- **Roles:** the six paper roles, each with an icon.
- **Topologies:** chain, ring, star, tree, layered, sparse, bipartite, fully-connected — each with a
  builder function (produces nodes/edges) and a diagram icon.

---

## MAD Engine (Reqs 9, 10.4, 12.4)

Headless, pure-Python. One public entry point:

```python
def run_debate(config: MADConfig, instance: dict, clients: ProviderRegistry) -> Transcript
```

### Components

- **graph.py** — Builds the runtime graph from `interaction.topology`. Pattern builders generate
  canonical structures. Exposes neighbour queries used by the scheduler. Dynamic adaptability is
  modeled but, where no executable policy exists, raises a controlled `UnderDevelopment` signal the
  service surfaces as a pre-run validation error.
- **protocol.py** — The scheduler. Produces the activation sequence `E(t)` per round:
  - *sequential*: one edge/agent per step in `order` (fixed/randomized/coordinator-picked).
  - *simultaneous*: all eligible agents act per round, then broadcast.
  - *hybrid*: ordered phases each tagged sequential/simultaneous.
  Loops until `max_rounds` or a consensus stop condition.
- **format.py** — Assembles each agent's input context from accessible memory `M(t)` (short-term =
  current debate history), applies content transform `m̃=f(m)` (verbatim passes through; summarized
  invokes a summarizer role/model; other = registered transform). Attaches metadata signals. Non-NL
  syntax and long-term/retrieval/parametric memory are gated as "under development".
- **agreement.py** — Resolution strategies (`majority_vote`, `average`, `argument_evaluation`,
  `consensus`, `weighted_vote`, `scoring`) selected by `(authority, resolution)`. Judge-based
  authority routes the transcript (or its summary) to the judge node and parses against
  `output_schema`. Collective authority aggregates debater outputs.
- **orchestrator.py** — Ties it together for one instance: build graph → run protocol rounds (each
  step: format context → invoke model → record) → apply agreement → emit `Transcript`.
- **transcript.py** — Structured record: rounds, per-agent messages, metadata, token/latency/cost,
  final decision, errors. This is what gets persisted and shown in the history viewer.

### Execution over input (Req 10)
- **Single instance:** `input_spec.template` resolved against ad-hoc form values → one `run_debate`.
- **Batch:** `dataset.py` loads CSV; user maps columns → placeholders; each row → one instance → one
  `run_debate`. A job runner iterates rows with progress, concurrency limits, and per-row error
  isolation (Req 9.5, 10.5). When a ground-truth column is mapped, `evaluation/` computes aggregate
  metrics (Req 10.7, 11.5), reusing the refactored current metrics code.

---

## Provider Abstraction & Credentials (Reqs 8, 9)

- **`ModelClient` protocol** with a single `complete(messages, model, params, response_schema) ->
  ModelResponse` method returning text + usage.
- **`litellm_client.py`** uses **LiteLLM** to reach OpenAI, Anthropic, Gemini, Mistral, DeepSeek, and
  any **OpenAI-compatible** endpoint (Ollama, vLLM, LM Studio, local servers) via base-URL override.
  This replaces the OpenAI Assistants API with portable Chat Completions; structured output uses
  provider-native JSON schema where available, else a JSON-mode + validation fallback (Req 9.3).
- **`registry.py`** resolves a participant's `(provider_id, model_key)` to a configured client,
  supporting heterogeneous models in one debate (Req 9.2). `test_connection(provider)` issues a
  minimal call for the UI connectivity check (Req 8.5).
- **Credential security (Req 8.4):** keys encrypted at rest with **Fernet** (symmetric key derived
  from a server secret in `.env`). The API returns provider metadata and a `has_key` boolean only —
  never plaintext. Decryption happens solely inside the provider layer at call time.

---

## Persistence (Req 14.3)

SQLAlchemy over SQLite. Tables:

- **providers** — id, name, kind (openai/anthropic/.../ollama/openai_compatible), base_url,
  encrypted_api_key, models (JSON list), created/updated.
- **configurations** — id, name, description, artifact (JSON, the full MADConfig),
  schema_version, created/updated.
- **datasets** — id, name, original filename, stored path, columns (JSON), row_count.
- **executions** — id, config_id (nullable on source delete), config_snapshot (JSON, immutable per
  Req 11.3), input_mode (single/batch), input_ref (ad-hoc values or dataset id + column mapping),
  status (queued/running/completed/failed/partial), progress, metrics (JSON), created/updated.
- **execution_instances** — id, execution_id, instance_index, resolved_input (JSON), transcript
  (JSON), final_decision, ground_truth (nullable), per-instance metrics, error (nullable).

Config artifacts are also exportable/importable as standalone JSON files (Req 4.3, 14.3).

---

## Backend REST API (Req 12)

FastAPI, OpenAPI-documented. Resource routers:

| Method & Path | Purpose |
|---|---|
| `GET /api/taxonomy` | Full taxonomy catalog + templates + defaults + flags (Req 12.3) |
| `GET/POST /api/configs` · `GET/PUT/DELETE /api/configs/{id}` | Config CRUD (Req 5) |
| `POST /api/configs/{id}/copy` | Duplicate config (Req 5.5) |
| `POST /api/configs/import` · `GET /api/configs/{id}/export` | Artifact import/export (Req 4.3) |
| `POST /api/configs/validate` | Validate artifact, return errors (Req 4.2, 7.3) |
| `GET/POST /api/providers` · `PUT/DELETE /api/providers/{id}` | Provider CRUD (Req 8) |
| `POST /api/providers/{id}/test` | Connectivity test (Req 8.5) |
| `POST /api/datasets` · `GET /api/datasets/{id}` · `GET /api/datasets/{id}/preview` | Upload/inspect CSV, preview resolved template (Req 10.3) |
| `POST /api/executions` | Launch run (single or batch) → async job (Req 10, 12) |
| `GET /api/executions` · `GET /api/executions/{id}` | List/inspect runs + transcripts (Req 11) |
| `GET /api/executions/{id}/stream` | Progress (SSE) for long runs (Req 10.5) |
| `DELETE /api/executions/{id}` · `GET /api/executions/{id}/export` | Delete/export results (Req 11.4) |

Layering (Req 12.2): routers → services → engine/providers/persistence. Engine never imports FastAPI.
A **CLI** under `backend/cli/` calls the same services/engine, preserving the headless research path
and the current classification commands (Req 12.4, 12.5).

Async model (Req 10.5): executions run in a background task runner (FastAPI `BackgroundTasks` /
`asyncio` worker) writing progress to the DB; the frontend polls or subscribes via SSE.

---

## Frontend (Reqs 5, 6, 7, 8, 10, 11)

React + TypeScript + Vite. State via React Query (server cache) + Zustand (designer canvas state).
UI library: shadcn/ui (clean, default-friendly forms). Canvas: **React Flow**.

### Dimension theming (Reqs 6.6, 7.4)
Each taxonomy dimension gets a fixed colour + icon identity used everywhere:
- **Participants** (e.g., indigo) · **Interaction** (e.g., teal) · **Agreement** (e.g., amber).
Panels, badges, tabs, and the designer's inspector are colour-coded so the active dimension is always
unmistakable.

### Key views
1. **Configurations list** — cards/table with summary chips (participant count, topology pattern,
   authority), actions: open, copy, delete, export, "new from template" (gold cases + patterns).
2. **Designer** — three-pane layout:
   - **Canvas (center):** React Flow. Participant nodes show role icons + model badge; edges are
     directed, named, coloured. Toolbar: add node, apply topology template (auto-generates nodes/
     edges), auto-layout. The canvas *is* `G=(V,E)`, kept in sync both ways (Req 6.8).
   - **Inspector (right):** context-sensitive — click a node → Participants panel (roles, persona
     background/personality/stance with template picker, base-model binding); select an edge → edge
     name/colour/direction. Prompt-designed fields and structured fields are visually grouped and
     labelled (the user's distinction).
   - **Dimension tabs (left/top):** Participants / Interaction / Agreement, colour-themed; Interaction
     and Agreement panels configure topology meta/protocol/format and authority/resolution.
   - Defaults pre-filled everywhere (Req 7.1); advanced options behind progressive disclosure (7.2);
     "under development" values badged and blocked/ warned before run (7.5).
3. **Providers** — list + add/edit/remove; kind selector (OpenAI/Anthropic/Gemini/Mistral/DeepSeek/
   Ollama/vLLM/OpenAI-compatible); API key (write-only, shows `•••• configured`), base URL, model
   keys; "Test connection" button (Req 8).
4. **Run launcher** — choose config → choose input mode: *single* (form generated from
   `input_spec.ad_hoc_fields`) or *batch* (upload/select CSV → map columns to placeholders → preview
   resolved input for a sample row) → launch (Req 10.2, 10.3).
5. **Executions history** — list with status/metrics; detail view shows per-instance debate transcript
   (rounds × agents, color-coded by dimension/role), final decision, metrics, and evaluation charts
   when ground truth present (Req 11).

Icons for roles and topologies come from `shared/icons/` (same assets the website uses).

---

## Website (Req 13)

Static site (Astro, or prerendered React to reuse components/icons). Pages:
- **Home/Overview** — project summary, links to both papers.
- **Taxonomy** — three clearly separated, colour-themed sections (Participants/Interaction/Agreement),
  each listing sub-dimensions and values with the same labels/descriptions/icons as the app, rendered
  from a snapshot of the taxonomy catalog so docs never drift from the product (Reqs 13.3, 13.5).
- **Patterns gallery** — persona patterns, roles, and topology diagrams (chain/ring/star/tree/layered/
  sparse/bipartite) illustrated with the shared SVGs (Req 13.4).
- Built and deployable independently (Req 13.1).

---

## Error Handling

- **Config validation:** Pydantic + semantic checks (e.g., judge_based authority requires a judge
  node; edges reference existing nodes; executable-flag gating). Returned as structured field errors
  for the UI (Req 4.2, 7.3).
- **Provider/model failures:** ret/ry with configurable attempts + backoff; per-instance isolation in
  batch so one failure never aborts a run; failures recorded on the instance and surfaced in history
  (Req 9.5, 10.6).
- **Credentials:** decryption/invalid-key errors reported via the connectivity test, never leaking key
  material.
- **"Under development" gating:** pre-run validation blocks execution of non-executable values with a
  clear message; the artifact still saves (Req 2/3/7.5).

---

## Testing Strategy

- **Engine unit tests:** topology builders (each canonical pattern), protocol scheduler
  (sequential/simultaneous/hybrid ordering + rounds), format transforms, agreement strategies — using
  a **mock ModelClient** (deterministic, no network).
- **Gold-case tests (Req 4.4):** load + validate + run RE binary debate and ChatEval S1/S2/S3 against
  the mock client; assert transcripts and decisions match expected structure; assert S1/S2/S3 differ
  only in the documented attributes.
- **Schema tests:** round-trip export/import, version migration, invalid-artifact rejection.
- **Provider tests:** LiteLLM adapter against a stubbed endpoint; structured-output fallback path.
- **API tests:** FastAPI TestClient over each router incl. credential write-only behaviour and async
  execution lifecycle.
- **Regression:** the existing requirements-classification flow reproduced end-to-end through the new
  engine on `data/datasets/PROMISE/nfr-small.csv` (Req 12.5), compared against current outputs.
- **Frontend:** component tests for the designer sync (canvas ↔ artifact) and taxonomy-driven forms;
  smoke e2e for the create→save→run→inspect loop.

---

## Requirements Traceability (summary)

| Requirement | Primary design locations |
|---|---|
| 1 Participants | Config Artifact `participants`; schema.py; templates.py; Designer inspector |
| 2 Interaction | Config Artifact `interaction`; graph.py; protocol.py; format.py; designer canvas |
| 3 Agreement | Config Artifact `agreement`; agreement.py; designer Agreement panel |
| 4 Artifact | schema.py; version.py; import/export + validate endpoints; gold-case tests |
| 5 CRUD+copy | configs router; configurations table; Configurations list view |
| 6 Visual designer | React Flow canvas; graph.py sync; shared icons |
| 7 Default UX | catalog defaults; progressive disclosure; validate endpoint; under-dev gating |
| 8 Providers/creds | providers router; registry.py; security (Fernet); Providers view |
| 9 Open-source exec | litellm_client.py; registry.py; orchestrator; retry/isolation |
| 10 Execution/input | input/template.py; input/dataset.py; executions router; jobs; Run launcher |
| 11 History/analysis | executions + execution_instances tables; transcript.py; History view |
| 12 API/clean arch | app/ layering; /api/taxonomy; CLI headless path |
| 13 Website | website/ static site; shared catalog snapshot + icons |
| 14 Repo/delivery | top-level backend/frontend/website; SQLite; batched commits |
```

---

## Open design decisions (resolved defaults, revisit if needed)

- **Async runner:** start with in-process `asyncio`/BackgroundTasks + DB-backed progress (no external
  broker). If long batch runs need durability across restarts, a lightweight queue can be added later.
- **Website generator:** Astro preferred for a true static site; prerendered React acceptable to
  maximize component/icon reuse. Either satisfies Req 13; final pick at implementation time.
- **Structured output across providers:** native JSON-schema where supported; JSON-mode + Pydantic
  validation fallback elsewhere; a provider capability flag records which path is used.
