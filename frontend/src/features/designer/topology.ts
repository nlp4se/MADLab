/**
 * Client-side topology builders (Req 6.5).
 *
 * These mirror the backend builders in `backend/mad/taxonomy/templates.py`
 * (CSUR §5.1). Applying a topology template on the canvas regenerates the edge
 * set over the current participant nodes without a server round-trip, keeping
 * the "apply template" action instant and the canvas the source of truth until
 * the user saves (PUT /api/configs/{id}).
 *
 * Each builder is a pure function mapping an ordered list of node ids to a list
 * of directed `EdgeArtifact`s. The edge counts match the backend's for parity:
 *   - fully_connected: n(n-1)
 *   - grouped:         fully-connected within each group (no cross-group edges)
 *   - chain:           n-1
 *   - ring:            n (n >= 2)
 *   - star:            n-1 (every node -> center)
 *   - tree:            n-1 (binary parent -> child)
 *   - layered:         sum over consecutive layers of |L_i|*|L_{i+1}|
 *   - sparse:          n (each node -> next successor, wrapping; == ring)
 *   - bipartite:       |A|*|B|
 */
import {
  APPLICABLE_TOPOLOGIES,
  type ApplicableTopology,
  type EdgeArtifact,
  type TopologyArtifact,
  type TopologyPattern,
} from "./artifact";

export { APPLICABLE_TOPOLOGIES };
export type { ApplicableTopology };

/** The three topology *structures* the toolbar groups templates under. */
export const TOPOLOGY_STRUCTURES = [
  "fully_connected",
  "grouped",
  "structured_network",
] as const;

function edge(source: string, target: string): EdgeArtifact {
  return { source, target, directed: true };
}

export function fullyConnected(nodes: string[]): EdgeArtifact[] {
  const edges: EdgeArtifact[] = [];
  for (const u of nodes) {
    for (const v of nodes) {
      if (u !== v) edges.push(edge(u, v));
    }
  }
  return edges;
}

/**
 * Divided into groups: fully-connected within each group, no edges across
 * groups. With no explicit group assignment yet, split the nodes into roughly
 * two even groups — a sensible default the user can then edit by hand.
 */
export function grouped(nodes: string[], groupCount = 2): EdgeArtifact[] {
  const count = Math.max(1, Math.min(groupCount, nodes.length || 1));
  const groups = splitInto(nodes, count);
  const edges: EdgeArtifact[] = [];
  for (const group of groups) {
    edges.push(...fullyConnected(group));
  }
  return edges;
}

export function chain(nodes: string[]): EdgeArtifact[] {
  const edges: EdgeArtifact[] = [];
  for (let i = 0; i < nodes.length - 1; i += 1) {
    edges.push(edge(nodes[i], nodes[i + 1]));
  }
  return edges;
}

export function ring(nodes: string[]): EdgeArtifact[] {
  const edges = chain(nodes);
  if (nodes.length >= 2) edges.push(edge(nodes[nodes.length - 1], nodes[0]));
  return edges;
}

/** Centralized star: every other node -> center. Defaults to the first node. */
export function star(nodes: string[], center?: string): EdgeArtifact[] {
  if (nodes.length === 0) return [];
  const hub = center && nodes.includes(center) ? center : nodes[0];
  return nodes.filter((n) => n !== hub).map((n) => edge(n, hub));
}

/** Hierarchical parent -> child edges for a `branching`-ary tree. */
export function tree(nodes: string[], branching = 2): EdgeArtifact[] {
  const edges: EdgeArtifact[] = [];
  const n = nodes.length;
  for (let i = 0; i < n; i += 1) {
    for (let k = 1; k <= branching; k += 1) {
      const child = branching * i + k;
      if (child < n) edges.push(edge(nodes[i], nodes[child]));
    }
  }
  return edges;
}

/** Every node in each layer -> every node in the next layer. */
export function layered(layers: string[][]): EdgeArtifact[] {
  const edges: EdgeArtifact[] = [];
  for (let i = 0; i < layers.length - 1; i += 1) {
    for (const src of layers[i]) {
      for (const dst of layers[i + 1]) {
        edges.push(edge(src, dst));
      }
    }
  }
  return edges;
}

/** Low-density: each node -> its next `neighbors` successors (wrapping). */
export function sparse(nodes: string[], neighbors = 1): EdgeArtifact[] {
  const n = nodes.length;
  const edges: EdgeArtifact[] = [];
  if (n < 2) return edges;
  const reach = Math.min(neighbors, n - 1);
  for (let i = 0; i < n; i += 1) {
    for (let k = 1; k <= reach; k += 1) {
      edges.push(edge(nodes[i], nodes[(i + k) % n]));
    }
  }
  return edges;
}

/** Directed edges from every node in `setA` to every node in `setB`. */
export function bipartite(setA: string[], setB: string[]): EdgeArtifact[] {
  const edges: EdgeArtifact[] = [];
  for (const a of setA) {
    for (const b of setB) {
      edges.push(edge(a, b));
    }
  }
  return edges;
}

/** Split a node list into `count` roughly-equal, order-preserving slices. */
function splitInto(nodes: string[], count: number): string[][] {
  const groups: string[][] = Array.from({ length: count }, () => []);
  nodes.forEach((id, index) => {
    groups[index % count].push(id);
  });
  return groups;
}

/**
 * Build the edge set for an applicable topology over the given (ordered) node
 * ids. For `layered` the nodes are split into three roughly-equal layers and
 * for `bipartite` into two sets, since the canvas has no explicit layer/set
 * assignment yet — a reasonable default the user can then edit by hand.
 */
export function buildTopologyEdges(
  topology: ApplicableTopology,
  nodeIds: string[],
): EdgeArtifact[] {
  switch (topology) {
    case "fully_connected":
      return fullyConnected(nodeIds);
    case "grouped":
      return grouped(nodeIds);
    case "chain":
      return chain(nodeIds);
    case "ring":
      return ring(nodeIds);
    case "star":
      return star(nodeIds);
    case "tree":
      return tree(nodeIds);
    case "layered": {
      const layerCount = Math.min(3, Math.max(1, nodeIds.length));
      return layered(splitInto(nodeIds, layerCount));
    }
    case "sparse":
      return sparse(nodeIds);
    case "bipartite": {
      const [setA, setB] = splitInto(nodeIds, 2);
      return bipartite(setA, setB ?? []);
    }
    default:
      return [];
  }
}

/**
 * Produce the `structure` / `pattern` metadata that accompanies an applied
 * topology so the artifact's `interaction.topology` stays schema-valid
 * (structured_network requires a pattern; fully_connected / grouped forbid one).
 */
export function topologyMeta(topology: ApplicableTopology): {
  structure: TopologyArtifact["structure"];
  pattern: TopologyPattern | null;
} {
  if (topology === "fully_connected") {
    return { structure: "fully_connected", pattern: null };
  }
  if (topology === "grouped") {
    return { structure: "grouped", pattern: null };
  }
  return { structure: "structured_network", pattern: topology };
}

/** Human-readable label for a topology key, for toolbar menus. */
export function topologyLabel(topology: string): string {
  return topology
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
