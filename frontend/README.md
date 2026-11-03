# Frontend — MAD management webapp

The **frontend** is a React + TypeScript (Vite) single-page application for designing, configuring,
executing, and analysing **Multi-Agent Debate (MAD)** configurations.

## Purpose

- A **visual debate designer** (node/edge canvas) where participants are nodes and communication
  paths are directed edges, kept in sync with the underlying `G=(V,E)` configuration artifact.
- **Exhaustive taxonomy configuration** across the three dimensions — Participants, Interaction,
  Agreement — rendered data-driven from the backend taxonomy API, with sensible defaults and
  progressive disclosure.
- **Provider and credential management**, with write-only API keys.
- **Execution** launching (single ad-hoc instance or dataset batch) and **execution history** with
  per-instance transcript inspection and metrics.

The three taxonomy dimensions are visually and distinctly separated throughout the UI.

## Tech stack

- **Build / dev server:** [Vite](https://vite.dev) 6 + React 18 + TypeScript.
- **Server state:** [TanStack React Query](https://tanstack.com/query) — caches
  API responses (the taxonomy catalog, configs, providers, executions).
- **Client state:** [Zustand](https://zustand-demo.pmnd.rs/) — backs the visual
  designer/canvas state.
- **UI:** [Tailwind CSS](https://tailwindcss.com) + [shadcn/ui](https://ui.shadcn.com)
  conventions (CSS-variable design tokens, `cn()` helper, variant-driven
  components in `src/components/ui/`).
- **Routing:** [React Router](https://reactrouter.com) with a shared app
  layout (sidebar nav) and one route per view.
- **Icons:** [lucide-react](https://lucide.dev) for UI chrome, plus the shared
  role/topology SVGs from `../shared/icons` (see below).
- **Tests:** [Vitest](https://vitest.dev) + React Testing Library (jsdom).

## Prerequisites

- Node.js ≥ 20 (developed against Node 24) and npm ≥ 10.
- The backend running locally (default `http://localhost:8000`), or point the
  client at another instance via `VITE_API_BASE_URL`.

## Setup

```bash
cd frontend
npm install

# configure the API base URL (optional; the default below is assumed)
cp .env.example .env
```

> Note: npm may report that esbuild has an install script "not yet covered by
> allowScripts". Vite/Vitest still build and run in this environment; if you hit
> an esbuild binary error, run `npm rebuild esbuild` (or approve the script with
> `npm install-scripts approve esbuild`).

## Commands

| Command             | What it does                                         |
| ------------------- | ---------------------------------------------------- |
| `npm run dev`       | Start the Vite dev server on `http://localhost:5173` |
| `npm run build`     | Type-check (`tsc -b`) and produce a production build |
| `npm run preview`   | Preview the production build locally                 |
| `npm run typecheck` | Type-check without emitting                          |
| `npm test`          | Run the Vitest suite once                            |
| `npm run test:watch`| Run Vitest in watch mode                             |

## Configuration

The API base URL is read from the Vite env var **`VITE_API_BASE_URL`**
(default **`http://localhost:8000/api`**). The backend mounts every router under
the `/api` prefix, so the default already includes it. Override it in `.env`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000/api
```

## Project layout

```
frontend/
├── index.html
├── vite.config.ts            # app build (aliases: @ -> src, @icons -> ../shared/icons)
├── vitest.config.ts          # test harness (jsdom + RTL)
├── tailwind.config.js        # design tokens incl. dimension colours
├── components.json           # shadcn/ui config
└── src/
    ├── api/                  # typed fetch client + DTO types + endpoints
    ├── taxonomy/             # catalog loader (React Query), context, dimension theming
    ├── components/
    │   ├── ui/               # shadcn/ui primitives (Button, Badge, …)
    │   └── layout/           # AppLayout (sidebar) + page scaffolding
    ├── features/             # configs, designer, providers, executions (views)
    ├── assets/icons.ts       # consumes shared role/topology SVGs via @icons
    ├── lib/                  # cn() helper, React Query client
    ├── routes.tsx            # central route + nav table
    ├── App.tsx               # providers (React Query, Taxonomy) + router
    └── main.tsx              # entry
```

## Typed API client

`src/api/` is a hand-written, typed fetch client:

- `types.ts` mirrors the backend Pydantic DTOs (`backend/app/schemas/*.py`) for
  taxonomy, configs, providers, datasets, and executions.
- `client.ts` is the fetch core: base-URL resolution, JSON handling, query
  strings, and a normalized `ApiError`.
- `endpoints.ts` groups typed functions per resource
  (`taxonomyApi`, `configsApi`, `providersApi`, `datasetsApi`, `executionsApi`).

## Taxonomy context (data-driven forms)

`GET /api/taxonomy` is fetched **once** via React Query
(`src/taxonomy/useTaxonomyQuery.ts`) and provided through a React context
(`TaxonomyProvider` / `useTaxonomy`). Forms render data-driven from the catalog
(dimensions → sub-dimensions → values, defaults, and "under development" flags).

## Dimension theming

Each taxonomy dimension has a fixed colour + icon identity, defined once and
reused everywhere (panels, badges, tabs, the designer inspector):

- **Participants** — indigo
- **Interaction** — teal
- **Agreement** — amber

Colours live as CSS variables in `src/index.css`, are exposed to Tailwind in
`tailwind.config.js`, and the full theme (colour classes + lucide icon) is in
`src/taxonomy/dimensions.ts`.

## Shared icons

Role and topology SVGs are **not** duplicated here — they are consumed from the
single source at `../shared/icons` through the `@icons` Vite alias.
`src/assets/icons.ts` eagerly collects them (`import.meta.glob`) and exposes
`roleIconUrl(name)` / `topologyIconUrl(name)`.
