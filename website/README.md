# Website — documentation & landing site

The **website** is a static documentation and landing site that explains the project and the
**Multi-Agent Debate (MAD)** taxonomy, built and deployable **independently** of the backend and
frontend (Req 13.1).

It is built with [Astro](https://astro.build) and emits a fully static `dist/` with **no runtime
dependency** on the backend or frontend: the taxonomy catalog is read from a committed build-time
snapshot and the role/topology icons come from the shared icon source.

## Purpose

- Summarize the project and link to the underlying papers.
- Document each of the three taxonomy dimensions (Participants, Interaction, Agreement) with their
  sub-dimensions and possible values, using icons and pattern illustrations consistent with the
  frontend.
- Illustrate common patterns — persona patterns, roles, and topologies — with diagrams/icons drawn
  from the shared icon assets (`shared/icons/`).

The three dimensions are visually and clearly distinguished, consistent with the frontend.

## Project layout

```
website/
├── astro.config.mjs          # static output; @icons / @data aliases
├── package.json
├── tsconfig.json
├── scripts/
│   └── generate-taxonomy-snapshot.py   # regenerates the catalog snapshot
└── src/
    ├── layouts/BaseLayout.astro        # shared shell + dimension colour tokens
    ├── components/Icon.astro           # inlines shared role/topology SVGs
    ├── data/
    │   ├── taxonomy.json               # committed catalog snapshot (generated)
    │   └── taxonomy.ts                 # typed access to the snapshot
    ├── pages/                          # one .astro file per route
    └── styles/tokens.css               # global tokens incl. dimension colours
```

### Dimension colours

The three dimensions share the frontend's signature colours, exposed as CSS tokens in
`src/styles/tokens.css` so themed sections can pick one with `data-dimension="…"`:

| Dimension    | Colour | Token             |
| ------------ | ------ | ----------------- |
| Participants | indigo | `--participants`  |
| Interaction  | teal   | `--interaction`   |
| Agreement    | amber  | `--agreement`     |

### Shared icons

Role and topology SVGs are **not** duplicated here. They are consumed from the single shared source
`../shared/icons` via the `@icons` alias (the same alias the frontend uses — see
`frontend/vite.config.ts`) and inlined at build time by `src/components/Icon.astro`, so the website
and frontend share one icon source (Req 13.4).

## Setup & build

Requires Node.js 18+ and npm.

```bash
cd website
npm install      # install dependencies
npm run dev      # local dev server with hot reload
npm run build    # produce the static site in dist/
npm run preview  # preview the built dist/ locally
```

`npm run build` writes a self-contained static site to `website/dist/` that can be deployed to any
static host (GitHub Pages, Netlify, S3, …) independently of the other components.

## Regenerating the taxonomy snapshot

The site is static and must never call the backend at runtime, so the taxonomy catalog is imported
from a committed snapshot at `src/data/taxonomy.json`. That snapshot is produced from the **same**
source the `GET /api/taxonomy` endpoint serves (`backend/mad/taxonomy/catalog.py` +
`templates.py`, assembled by `app.schemas.taxonomy.TaxonomyResponse.from_engine()`), so the docs
never drift from the product.

Regenerate it whenever the taxonomy catalog or templates change, using the **backend's virtualenv**
Python (so the engine dependencies are importable), then commit the result:

```bash
# from the repository root

# Windows (PowerShell)
backend\.venv\Scripts\python.exe website\scripts\generate-taxonomy-snapshot.py

# macOS / Linux
backend/.venv/bin/python website/scripts/generate-taxonomy-snapshot.py
```

The snapshot contains the full `dimensions → sub-dimensions → values`
(`key`/`label`/`description`/`default`/`executable`/`icon`) tree plus `templates`
(`persona_patterns`, `roles`, `topologies`), `defaults`, and the `under_development` key list.

## Pages

- **Home / Overview** — project summary with links to the underlying papers.
- **Taxonomy** — the three colour-themed dimensions (Participants / Interaction / Agreement) with
  their sub-dimensions and values, rendered from the committed catalog snapshot.
- **Patterns gallery** — persona patterns, roles, and topology diagrams illustrated with the shared
  role/topology SVGs.
