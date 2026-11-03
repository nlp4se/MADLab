# Backend — MAD engine + FastAPI API

The **backend** is a Python component that wraps a refactored, headless **Multi-Agent Debate (MAD)
engine** behind a documented **FastAPI** REST API.

## Purpose

- **MAD engine (`mad/`)** — the headless domain core (no web dependencies): the taxonomy catalog and
  machine-readable configuration artifact, topology/protocol/format/agreement execution, a unified
  multi-provider model abstraction (via LiteLLM), input binding, and evaluation.
- **Web layer (`app/`)** — FastAPI routers, request/response schemas, services, SQLite persistence
  (SQLAlchemy), encrypted credential storage (Fernet), and an async execution job runner.
- **CLI (`cli/`)** — headless drivers that call the same services/engine, preserving the existing
  research workflow (configuration creation, batch runs over CSV, evaluation).

The research scripts that used to live under the repository's top-level `code/` have been refactored
into this component, preserving the requirements-classification capability end-to-end through the
`mad` CLI and the REST API (the original `code/` scripts remain in the repo for reference).

## Project layout

```
backend/
├── mad/            # headless engine + domain (no web deps)
│   ├── taxonomy/   # catalog, artifact schema, versioning, templates
│   ├── engine/     # graph / protocol / format / agreement / orchestrator
│   ├── providers/  # unified multi-provider model invocation (LiteLLM)
│   ├── input/      # template resolution + dataset loading
│   ├── evaluation/ # metrics (ported from code/evaluation)
│   └── errors.py   # domain error types
├── app/            # FastAPI web layer
│   ├── main.py     # app factory (create_app): settings, CORS, DB init, gold-config seeding
│   ├── config.py   # typed settings (MAD_* env vars)
│   ├── routers/ schemas/ services/ db/ security/ jobs/
├── cli/            # headless CLI drivers
├── tests/          # pytest suite (engine, web layer, and CLI)
├── pyproject.toml  # dependency manifest + packaging
└── requirements.txt
```

## Setup

Requires **Python >= 3.10**. All commands below are run from this `backend/`
directory.

### 1. Create and activate a virtual environment

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

Editable install with dev + evaluation extras (recommended):

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev,evaluation]"
```

Or, using the pinned-floor requirements file:

```bash
python -m pip install -r requirements.txt
```

### 3. Configure the environment (`.env`)

Settings are read from the environment and an optional `.env` file in this `backend/` directory.
Web-layer settings use the `MAD_` prefix; provider API keys use each provider's own name. The
minimum useful configuration is a server secret (used to derive the Fernet key that encrypts stored
provider credentials) plus the keys for whichever providers you intend to use:

```dotenv
# Server secret for credential encryption. Required before you can store a
# provider API key (the security layer raises a clear error without it).
MAD_SECRET_KEY=change-me-to-a-long-random-string

# Optional web-layer overrides (defaults shown).
# MAD_DATABASE_URL=sqlite:///mad.db
# MAD_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
# MAD_DATASET_STORAGE_PATH=data/datasets

# Provider API keys (add only those you use).
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=...
# GEMINI_API_KEY=...
```

## Running the tests

```bash
pytest
```

This runs the full pytest suite over the engine, web layer, and CLI.

## Running the API (development)

The application factory is `app.main:create_app`. Serve it with Uvicorn:

```bash
uvicorn app.main:create_app --factory --reload
```

By default the API listens on `http://localhost:8000`; every router is mounted under the `/api`
prefix, and interactive OpenAPI docs are at `http://localhost:8000/docs`.

On startup the factory:

- binds a SQLAlchemy engine for `MAD_DATABASE_URL` (default on-disk `sqlite:///mad.db`) and creates
  the schema if it does not yet exist (idempotent — safe on every boot), and
- **seeds the built-in gold/template configurations** (RE binary debate and ChatEval S1/S2/S3) so
  they appear in `GET /api/configs` on first run. Seeding is idempotent.

A `GET /api/health` endpoint responds with the engine version.

## CLI

A `mad` console script is installed with the package. It is the **headless
research path**: every command drives the same services/engine as the REST API,
with no web server, and persists to the same SQLite datastore
(`--database-url`, default `sqlite:///mad.db`).

```bash
mad --version
```

### Commands

- **`create-config`** — create a configuration from defaults, an imported
  artifact JSON file, or a built-in gold case:

  ```bash
  mad create-config --name "My debate"              # from defaults
  mad create-config --artifact my-config.json       # import an artifact
  mad create-config --gold re_binary_debate          # from a gold case
  ```

- **`run`** — run a stored configuration over a CSV batch or a single ad-hoc
  instance (through the engine, persisting an execution):

  ```bash
  # Batch over a CSV: map columns to template placeholders.
  mad run 1 --csv data.csv --map requirement=req --ground-truth type
  # Single ad-hoc instance.
  mad run 1 --input topic="cats vs dogs"
  ```

- **`classify`** — the preserved requirements-classification workflow: binary
  functional/non-functional (F/NF) debate (two opposing debaters + a judge) over
  a requirement CSV, producing a per-instance `judge` class, routed through the
  new engine via the built-in RE binary gold config:

  ```bash
  # path is relative to where you run the command; from backend/ the sample
  # dataset lives one level up under data/
  mad classify ../data/datasets/PROMISE/nfr-small.csv \
      --requirement-column requirement --ground-truth type \
      --provider-id 1 --model gpt-4o
  ```

- **`evaluate`** — print aggregate metrics for a finished execution (when a
  ground-truth column was mapped):

  ```bash
  mad evaluate 1
  ```

`run` and `classify` require a configured provider (added via the API/webapp) so
the debaters/judge can be bound to a model.
