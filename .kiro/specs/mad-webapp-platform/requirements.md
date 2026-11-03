# Requirements Document

## Introduction

This project evolves the existing research codebase (`llm-discussion`) — currently an OpenAI-only,
CLI-driven framework for Multi-Agent Debate (MAD) applied to requirements classification — into a
full-featured, taxonomy-complete web application for **designing, configuring, saving, executing,
and analysing MAD configurations for scientific purposes**.

The platform is grounded in the three-dimensional MAD taxonomy from *"Multi-Agent Debate Strategies:
Survey, Taxonomy, and Challenges"* (ACM CSUR) and its proof-of-concept precursor (RE@Next'25). The
taxonomy decomposes any MAD system into three orthogonal dimensions:

1. **Participants** — Personas, Roles, Base Model
2. **Interaction** — Topology, Protocol, Format
3. **Agreement** — Authority, Resolution

A **MAD configuration** is an instantiation of this taxonomy: a declarative, machine-readable
artifact (per the paper's "MAD-as-artifact" vision) that can be documented, version-controlled,
executed, and compared. The paper's formal notation is preserved where possible: topology as a
directed graph `G=(V,E)`, protocol as temporal edge activation `E(t)`, format as message
transformations `m̃=f(m)`, and agreement as an `(authority, resolution)` pair.

The project is delivered as three cleanly separated components:

- **Backend** — Python/FastAPI REST API wrapping a refactored MAD engine, with multi-provider model
  support (closed- and open-weight) via LiteLLM, SQLite persistence, and encrypted credential storage.
- **Frontend** — React/TypeScript management webapp with a visual node/edge debate designer, exhaustive
  taxonomy configuration, and execution history.
- **Website** — A static documentation/landing site explaining the project and the taxonomy dimensions
  with illustrative icons and pattern diagrams.

### Gold test cases
Two configurations serve as development and acceptance anchors throughout:
- **RE binary classification debate**: Functional vs. Non-Functional debaters + Judge (the current framework's capability).
- **ChatEval**: three strategies (One-by-One, Simultaneous-Talk, Simultaneous-Talk + Summarizer) exactly as formalized in Table 3 of the CSUR paper.

### Development-status labelling
Taxonomy values that are configurable and persistable but not yet executable by the engine (e.g.,
embeddings-based syntax, parametric memory, certain dynamic topologies) MUST be clearly marked as
**"under development"** in both backend metadata and the frontend UI, while still being expressible
and savable in a configuration artifact.

---

## Glossary

- **MAD configuration (config)**: A saved, taxonomy-complete template defining a debate. Does not include runtime input.
- **Execution (run)**: A single invocation of a MAD configuration bound to a concrete input (one ad-hoc instance or a dataset batch).
- **Instance**: One unit of input over which exactly one debate occurs (e.g., one CSV row, one requirement, one question).
- **Input template**: A structured text template with placeholders/tags (e.g., `{{requirement}}`) that map instance fields (e.g., CSV columns) into the debate's initial messages.
- **Participant / node**: An agent in the debate (`v ∈ V`), carrying persona, role, and base-model configuration.
- **Edge**: A directed communication path (`(u,v) ∈ E`) between participants, optionally named and coloured.
- **Provider**: A model backend (OpenAI, Anthropic, Gemini, Mistral, DeepSeek, Ollama, vLLM, generic OpenAI-compatible) with credentials and available models.

---

## Requirements

### Requirement 1 — Taxonomy-complete configuration model (Participants dimension)

**User Story:** As a researcher, I want to fully specify the Participants dimension of a MAD
configuration, so that persona, role, and base-model design decisions are explicit and reproducible.

#### Acceptance Criteria

1. THE system SHALL represent each participant as a node `v ∈ V` with an identity, a role, a persona, and a base-model binding.
2. WHERE a persona is defined, THE system SHALL support the three attribute families: **background**, **personality**, and **stance**, each independently specifiable or left unspecified.
3. THE system SHALL support persona **heterogeneity** as `homogeneous` or `heterogeneous` across participants.
4. THE system SHALL support persona **assignment** as `unspecified`, `manually identified`, or `automatically identified`.
5. THE system SHALL support the following **roles**: `debater`, `judge`, `summarizer`, `leader` (moderator), `verifier`, `editor`, AND SHALL allow a single participant to combine multiple roles.
6. THE system SHALL support custom/user-defined roles beyond the predefined set.
7. THE system SHALL support a base-model **family** descriptor (`open-weight` or `closed-weight`) and base-model **heterogeneity** (`homogeneous` or `heterogeneous`).
8. THE system SHALL bind each participant's base model to a configured provider and model key.
9. WHERE the paper provides example persona patterns (e.g., angel/devil, prosecution/defence, faithful/unfaithful, proponent/challenger, Six Thinking Hats, domain-expert panels), THE system SHALL offer them as selectable predefined templates that remain fully editable.
10. THE system SHALL allow full free-form customization of any participant attribute via prompt text in addition to structured fields.

### Requirement 2 — Taxonomy-complete configuration model (Interaction dimension)

**User Story:** As a researcher, I want to fully specify the Interaction dimension, so that topology,
protocol, and message format are explicit and match the paper's formal notation.

#### Acceptance Criteria

1. THE system SHALL represent topology as a directed graph `G=(V,E)` with edges `(u,v) ∈ E` supporting unidirectional and bidirectional links.
2. THE system SHALL support topology **adaptability** as `static` or `dynamic` (`E(t)`), marking dynamic policies that are not yet executable as "under development".
3. THE system SHALL support topology **structure** as `fully connected`, `divided into groups`, or `structured network`.
4. WHERE the structure is a structured network, THE system SHALL offer the canonical patterns described in the paper as predefined, selectable templates: `chain`, `ring`, `star`, `tree`, `layered network`, `sparse`, and `bipartite`.
5. THE system SHALL support protocol **mechanism** as `sequential`, `simultaneous`, or `hybrid`, including a configurable round/iteration cap and turn ordering (fixed, randomized, or coordinator-selected).
6. THE system SHALL support format **syntax** as `natural language` or `embeddings` (the latter marked "under development").
7. THE system SHALL support format **content** as `verbatim`, `summarized`, or `other`, with verbatim supporting attached metadata signals (confidence, uncertainty, verifier/evaluation scores, judge likelihoods, bias/quality scores, guideline/preference weights).
8. THE system SHALL support format **memory access** as `short-term`, `long-term`, `knowledge retrieval`, or `parametric` (long-term, retrieval, and parametric marked "under development" where not executable).
9. THE system SHALL allow naming and colouring of edges, and grouping of participants into named subgroups.

### Requirement 3 — Taxonomy-complete configuration model (Agreement dimension)

**User Story:** As a researcher, I want to fully specify the Agreement dimension, so that how the
debate resolves to a final output is explicit.

#### Acceptance Criteria

1. THE system SHALL represent agreement as an `(authority, resolution)` pair.
2. THE system SHALL support **authority** as `collective`, `judge-based`, `hybrid`, or `other` (user-dependent/undefined/non-standard).
3. THE system SHALL support **resolution** as `argument evaluation`, `majority vote`, `weighted vote`, `scoring`, `average`, or `consensus`.
4. WHERE resolution is `weighted vote` or `scoring`, THE system SHALL allow configuration of the weighting/scoring signals and aggregation logic.
5. THE system SHALL allow a structured output schema (JSON schema) to constrain the final decision, as the current framework does for classification (e.g., `{class: F|NF}`).
6. WHERE a resolution mechanism is not yet executable, THE system SHALL mark it "under development" while keeping it configurable.

### Requirement 4 — Configuration as a machine-readable artifact

**User Story:** As a researcher, I want MAD configurations to be portable, declarative artifacts, so
that they can be exchanged, version-controlled, and compared per the paper's specification vision.

#### Acceptance Criteria

1. THE system SHALL serialize any MAD configuration to a single, well-defined, versioned JSON schema capturing all three dimensions and their formal notation.
2. THE system SHALL validate a configuration artifact against the schema on import and reject invalid artifacts with actionable error messages.
3. THE system SHALL allow export of a configuration to a JSON file and import from a JSON file.
4. THE system SHALL be able to represent the two gold test cases (RE binary debate and all three ChatEval strategies) exactly within this schema.
5. THE system SHALL record a schema/format version in each artifact to support forward migration.

### Requirement 5 — Configuration lifecycle management (CRUD + copy)

**User Story:** As a user, I want to manage all my MAD configurations from a list, so that I can
create, view, edit, duplicate, and delete them easily.

#### Acceptance Criteria

1. THE system SHALL present all saved configurations in a browsable list with name, description, and key summary attributes.
2. THE system SHALL allow creating a new configuration with sensible defaults pre-filled for every taxonomy attribute.
3. THE system SHALL allow viewing and editing an existing configuration.
4. THE system SHALL allow deleting a configuration, with confirmation, and SHALL warn if executions reference it.
5. THE system SHALL allow copying/duplicating a configuration into an independent new configuration.
6. WHEN a configuration is saved, THE system SHALL persist it durably and timestamp created/updated times.
7. THE system SHALL ship with the gold test cases (RE binary debate, ChatEval strategies) as built-in example/template configurations.

### Requirement 6 — Visual debate designer (node/edge canvas)

**User Story:** As a user, I want to design the debate visually by placing participant nodes and
drawing edges, so that configuration is intuitive and the three dimensions are clearly distinguishable.

#### Acceptance Criteria

1. THE system SHALL provide a canvas where participants are nodes and communication paths are directed edges.
2. THE system SHALL allow adding, moving, connecting, and removing nodes and edges directly on the canvas.
3. WHEN a node is clicked, THE system SHALL open an editor exposing all Participants-dimension properties for that participant.
4. WHEN an edge is selected, THE system SHALL allow setting its name, colour, and direction.
5. THE system SHALL let the user apply a predefined topology template (chain, ring, star, tree, layered, sparse, bipartite, fully connected) that auto-generates the corresponding nodes/edges.
6. THE system SHALL visually and distinctly separate the three taxonomy dimensions (Participants, Interaction, Agreement) throughout the UI so a user always knows which dimension they are editing.
7. THE system SHALL display role-specific icons for common roles (debater, judge, summarizer, leader, verifier, editor) and topology diagrams for predefined patterns.
8. THE system SHALL keep the visual graph and the underlying `G=(V,E)` artifact synchronized in both directions.

### Requirement 7 — Default-driven, easy-to-use configuration UX

**User Story:** As a non-expert user, I want every setting to have a good default, so that I can
produce a valid runnable configuration with minimal effort and progressively customize.

#### Acceptance Criteria

1. THE system SHALL pre-populate defaults for every taxonomy attribute so a new configuration is immediately valid and executable.
2. THE system SHALL present configuration in a progressive-disclosure manner (simple defaults first, advanced options on demand).
3. THE system SHALL validate configurations and surface clear, actionable messages for invalid or incomplete settings before execution.
4. THE system SHALL clearly label every taxonomy value with its paper-aligned name and a short description/tooltip.
5. THE system SHALL mark "under development" values distinctly and prevent (or warn before) executing configurations that depend on non-executable values.

### Requirement 8 — Provider and credential management

**User Story:** As a user, I want to add and remove model providers with their API keys and model
keys from the UI, so that I can run debates against any supported model including open-source ones.

#### Acceptance Criteria

1. THE system SHALL allow adding, editing, and removing model providers from the frontend.
2. THE system SHALL support closed-weight providers (OpenAI, Anthropic, Gemini, Mistral, DeepSeek) and open-weight/local backends (Ollama, vLLM, generic OpenAI-compatible endpoints).
3. THE system SHALL allow configuring per-provider API keys, base URLs/endpoints, and the set of available model keys.
4. THE system SHALL store API keys encrypted at rest and SHALL NOT return key plaintext to the frontend after saving.
5. THE system SHALL let a user test provider connectivity with a sample call and report success or a clear error.
6. THE system SHALL make configured provider models selectable when binding a base model to a participant.

### Requirement 9 — Open-source / multi-provider model execution

**User Story:** As a researcher, I want the engine to run debates against open-weight and locally
hosted models, not just OpenAI, so that I can study model-family heterogeneity per the taxonomy.

#### Acceptance Criteria

1. THE system SHALL execute debate agents against any configured provider through a unified model-invocation abstraction.
2. THE system SHALL support heterogeneous base models within a single debate (different participants using different providers/models).
3. THE system SHALL preserve the existing capability to produce structured (JSON-schema-constrained) outputs for judges/classifiers across providers that support it, and SHALL degrade gracefully where a provider does not.
4. THE system SHALL record per-agent and per-run token usage, latency, and cost signals where the provider exposes them.
5. IF a model invocation fails or times out, THEN THE system SHALL retry per a configurable policy and record failures without aborting the whole run.

### Requirement 10 — Execution: input binding and run

**User Story:** As a researcher, I want to execute a saved configuration over a specific input, so
that I can produce debate results for a single instance or a whole dataset.

#### Acceptance Criteria

1. THE system SHALL execute a MAD configuration over either a single ad-hoc instance OR a dataset batch (e.g., CSV) where each row is one debate instance.
2. THE system SHALL provide a structured **input template** using placeholders/tags (e.g., `{{requirement}}`) that map instance fields (CSV columns or ad-hoc form fields) into the debate's initial messages, configurable intuitively in the UI.
3. WHEN a dataset is provided, THE system SHALL let the user map dataset columns to template placeholders and preview the resolved input for a sample row before running.
4. THE system SHALL execute the debate according to the configuration's topology, protocol, format, and agreement, over the bound input.
5. THE system SHALL run batch executions asynchronously with progress reporting and SHALL allow long-running executions without blocking the UI.
6. THE system SHALL persist every execution with its configuration snapshot, input reference, per-instance results, agent transcripts, final decisions, and metrics.
7. THE system SHALL produce, for dataset runs, the same kind of evaluation artifacts the current framework produces (per-instance predictions and aggregate metrics) when ground-truth labels are present.

### Requirement 11 — Execution history and analysis

**User Story:** As a researcher, I want to browse and inspect past executions, so that I can review
results historically and compare runs.

#### Acceptance Criteria

1. THE system SHALL list all executions with their configuration, input, status, timestamps, and summary metrics.
2. THE system SHALL let a user open an execution to inspect per-instance debate transcripts (all rounds, all agents, judge decisions) and metrics.
3. THE system SHALL preserve the exact configuration snapshot used by each execution, independent of later edits to the source configuration.
4. THE system SHALL allow deleting an execution and exporting its results.
5. WHERE ground-truth labels are present, THE system SHALL display classification/evaluation metrics for the run.

### Requirement 12 — Backend REST API and clean architecture

**User Story:** As a developer, I want a clean, documented backend API separating the MAD engine from
transport and persistence, so that the system is maintainable and the engine remains usable headless.

#### Acceptance Criteria

1. THE backend SHALL expose a documented REST API (OpenAPI) covering configurations, providers, executions, datasets, and the taxonomy metadata.
2. THE backend SHALL separate concerns into distinct layers: domain/engine, provider adapters, persistence, and API/transport.
3. THE backend SHALL expose the taxonomy (dimensions, sub-dimensions, attribute values, defaults, descriptions, "under development" flags, predefined templates) via an API so the frontend renders it data-driven rather than hard-coded.
4. THE MAD engine SHALL remain runnable independently of the web layer (preserving a headless/CLI path for batch research runs).
5. THE backend SHALL preserve the existing requirements-classification capability end-to-end through the new engine.

### Requirement 13 — Documentation website

**User Story:** As a visitor, I want a website that summarizes the project and explains the taxonomy,
so that I can understand MAD design dimensions and the platform at a glance.

#### Acceptance Criteria

1. THE website SHALL be a static site deployable independently of backend and frontend.
2. THE website SHALL summarize the project and link to the papers.
3. THE website SHALL document each of the three dimensions with their sub-dimensions and possible values, using icons and pattern illustrations consistent with the frontend.
4. THE website SHALL illustrate common patterns (persona patterns, roles, topologies) with diagrams/icons similar to the designer.
5. THE website SHALL visually and clearly distinguish the three dimensions, consistent with the frontend.

### Requirement 14 — Clean repository architecture and delivery

**User Story:** As the project owner, I want a clean separation of backend, frontend, and website,
so that each can evolve and deploy independently, with contributions committed in reviewable batches.

#### Acceptance Criteria

1. THE repository SHALL separate `backend/`, `frontend/`, and `website/` as top-level components, preserving `data/` research assets and `paper/`.
2. THE existing `code/` research scripts SHALL be refactored into the backend engine while preserving current functionality.
3. THE system SHALL persist configurations, providers, and executions in SQLite, with configurations also exportable as JSON artifacts.
4. Work SHALL be committed in coherent, reviewable batches on the `feature/mad-webapp-platform` branch with the project owner as sole author.
5. Each delivered component SHALL include setup/run instructions.
