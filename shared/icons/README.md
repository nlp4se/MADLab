# Shared icons

Single source of truth for the MAD role and topology SVG icons, consumed by
**both** the frontend app and the documentation website. Keeping them here
avoids duplicating assets and keeps the catalog icon references valid for every
consumer.

## Icon reference keys

The taxonomy catalog (`backend/mad/taxonomy/catalog.py`) and templates
(`backend/mad/taxonomy/templates.py`) reference each icon by a `group/name` key
that maps directly onto the file layout here:

| Catalog `icon` ref | File |
| --- | --- |
| `role/debater` | `role/debater.svg` |
| `role/judge` | `role/judge.svg` |
| `role/summarizer` | `role/summarizer.svg` |
| `role/leader` | `role/leader.svg` |
| `role/verifier` | `role/verifier.svg` |
| `role/editor` | `role/editor.svg` |
| `topology/chain` | `topology/chain.svg` |
| `topology/ring` | `topology/ring.svg` |
| `topology/star` | `topology/star.svg` |
| `topology/tree` | `topology/tree.svg` |
| `topology/layered` | `topology/layered.svg` |
| `topology/sparse` | `topology/sparse.svg` |
| `topology/bipartite` | `topology/bipartite.svg` |
| `topology/fully_connected` | `topology/fully_connected.svg` |

Resolve a catalog `icon` ref to a path with `shared/icons/{ref}.svg`.

> Note: `fully_connected` is a `topology_structure` value in the catalog rather
> than a `topology_pattern`, so it carries no `icon` ref there. Its diagram is
> included here anyway because the structure selector in the UI/website needs a
> visual for the default fully-connected structure.

## Naming convention

- Two groups: `role/` and `topology/`.
- File name is the catalog value `key` (snake_case) plus `.svg`
  (e.g. `topology/fully_connected.svg`).
- One glyph per file, no external references, no embedded raster data.

## Theming with `currentColor`

Every SVG uses `currentColor` for all strokes and fills and declares **no**
hard-coded colours. The icon therefore inherits the CSS `color` of its
container, which lets a single asset theme cleanly in both consumers:

- **Frontend** — set `color` to the relevant taxonomy dimension colour (e.g.
  the participants/interaction/agreement accent) on the wrapping element.
- **Website** — set `color` to the current text/theme colour so icons track
  light/dark mode automatically.

```html
<span style="color: var(--dimension-interaction)">
  <!-- inline the SVG, or <img>/<use> it -->
</span>
```

Filled regions use `fill="currentColor"` with a low `fill-opacity` so the fill
reads as a tint of the same themed colour rather than a separate hue.

## Geometry

- Role icons use a `0 0 24 24` viewBox (UI glyph scale).
- Topology diagrams use a `0 0 64 64` viewBox (node/edge diagrams) drawn as
  circles (nodes) and lines (edges) matching each canonical graph structure:
  chain (line), ring (cycle), star (central hub), tree (hierarchy), layered
  (stacked layers), sparse (few edges), bipartite (two groups across a
  partition), fully_connected (complete graph).
