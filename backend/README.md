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

The existing research scripts under the repository's top-level `code/` are refactored into this
component in later tasks, preserving the current requirements-classification capability end-to-end.

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
│   ├── main.py     # app factory (minimal placeholder; full bootstrap in task 6.1)
│   ├── routers/ schemas/ services/ db/ security/ jobs/
├── cli/            # headless CLI drivers
├── tests/          # pytest suite (scaffold smoke test lives here)
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

## Running the tests

```bash
pytest
```

This runs the scaffold smoke test, which verifies the `mad`, `app`, and `cli`
packages import cleanly.

## Running the API (development)

The API bootstrap is a minimal placeholder until task 6.1. Once FastAPI and
Uvicorn are installed you can serve the placeholder app with:

```bash
uvicorn app.main:create_app --factory --reload
```

A `GET /health` endpoint responds with the engine version.

## CLI

A `mad` console script is installed with the package (full commands land in
task 6.7):

```bash
mad --version
```

> Engine, provider, persistence, and full API/CLI functionality are added in
> later tasks; this component currently provides the scaffold only.
