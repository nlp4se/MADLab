"""Runtime topology graph ``G=(V,E)`` for the MAD engine.

This module turns the *declarative* topology of a
:class:`~mad.taxonomy.schema.MADConfig` (``interaction.topology``) into a
runtime :class:`DebateGraph` with the neighbour queries the protocol scheduler
(task 3.2) consumes. It is a **pure data structure**: it makes no model calls
and imports no web dependencies, so it stays importable from the CLI, the
engine, and tests alike.

Edge resolution
---------------
The configuration artifact can carry an explicit ``topology.edges`` list *and*
a declared ``structure`` / ``pattern``. The visual designer keeps these in
sync (applying a template writes the edges). To avoid re-deriving (and possibly
disagreeing with) what the designer already materialised, the graph uses this
precedence:

* **Explicit edges win.** If ``topology.edges`` is non-empty, that list is the
  authoritative edge set — regardless of ``structure`` / ``pattern``. This is
  the common case for saved configs and for every gold case, whose builders
  pre-compute the edges.
* **Otherwise derive from structure.** With no explicit edges we generate them:

  * ``fully_connected`` → all directed pairs ``(u, v)``, ``u != v``;
  * ``grouped`` → fully-connected *within* each group (via ``node.group`` /
    ``participants.groups``), nothing across groups;
  * ``structured_network`` → the declared ``pattern`` built by the canonical
    :mod:`mad.taxonomy.templates` builders (chain/ring/star/tree/layered/
    sparse/bipartite), so the graph and the designer's "apply template" stay
    consistent. Edge generation is **never** reimplemented here.

Direction
---------
Each :class:`~mad.taxonomy.schema.Edge` carries a ``directed`` flag. A directed
edge ``(u, v)`` contributes a single arc ``u → v``. An **undirected** edge
(``directed=False``) contributes *both* arcs ``u → v`` and ``v → u`` to the
adjacency, so neighbour queries treat it bidirectionally.

Dynamic adaptability
--------------------
A ``dynamic`` topology needs an executable policy to decide ``E(t)`` at run
time. That policy engine is future work, so building a graph for a dynamic
topology **without** a ``dynamic_policy`` raises
:class:`mad.errors.UnderDevelopment`. Static topologies build normally. (A
dynamic topology that *does* carry a policy is out of scope for this task; the
constructor currently treats any dynamic topology as under development because
no policy is executable yet.)
"""

from __future__ import annotations

from mad.errors import UnderDevelopment
from mad.taxonomy import templates
from mad.taxonomy.schema import Edge, MADConfig, Participants, Topology


class DebateGraph:
    """Directed runtime graph ``G=(V,E)`` with neighbour queries.

    Construct via :meth:`from_config` (or :meth:`from_parts`). Nodes preserve
    participant declaration order; the adjacency maps every node to its ordered
    successors / predecessors, de-duplicated.
    """

    def __init__(self, nodes: list[str], edges: list[tuple[str, str]]):
        # Preserve declaration order of nodes.
        self._nodes: list[str] = list(nodes)
        node_set = set(self._nodes)

        # Adjacency: successors (outgoing) and predecessors (incoming). Values
        # are ordered, de-duplicated lists.
        self._succ: dict[str, list[str]] = {n: [] for n in self._nodes}
        self._pred: dict[str, list[str]] = {n: [] for n in self._nodes}
        self._edge_set: set[tuple[str, str]] = set()
        self._edges: list[tuple[str, str]] = []

        for src, dst in edges:
            if src not in node_set:
                raise ValueError(
                    f"edge source '{src}' does not reference an existing node"
                )
            if dst not in node_set:
                raise ValueError(
                    f"edge target '{dst}' does not reference an existing node"
                )
            if (src, dst) in self._edge_set:
                continue
            self._edge_set.add((src, dst))
            self._edges.append((src, dst))
            self._succ[src].append(dst)
            self._pred[dst].append(src)

    # -- construction ------------------------------------------------------

    @classmethod
    def from_config(cls, config: MADConfig) -> "DebateGraph":
        """Build the runtime graph from a full :class:`MADConfig`."""
        return cls.from_parts(config.participants, config.interaction.topology)

    @classmethod
    def from_parts(
        cls, participants: Participants, topology: Topology
    ) -> "DebateGraph":
        """Build the runtime graph from ``Participants`` + ``Topology``.

        Applies the dynamic-adaptability gate and the explicit-edges-win
        precedence described in the module docstring.
        """
        if topology.adaptability == "dynamic":
            # No executable dynamic policy engine exists yet; gate the run.
            raise UnderDevelopment(
                "Dynamic topology adaptability is not yet executable: no runtime "
                "policy engine exists to compute E(t). Use a static topology to "
                "run this configuration (the dynamic selection can still be saved)."
            )

        nodes = [node.id for node in participants.nodes]
        edges = cls._resolve_edges(participants, topology)
        arcs = cls._to_arcs(edges)
        return cls(nodes, arcs)

    # -- edge resolution ---------------------------------------------------

    @staticmethod
    def _resolve_edges(participants: Participants, topology: Topology) -> list[Edge]:
        """Return the authoritative :class:`Edge` list for ``topology``.

        Explicit edges win; otherwise derive from structure/pattern using the
        canonical :mod:`mad.taxonomy.templates` builders.
        """
        if topology.edges:
            # Explicit edges are authoritative (designer-synced source of truth).
            return list(topology.edges)

        node_ids = [node.id for node in participants.nodes]

        if topology.structure == "fully_connected":
            return templates.fully_connected(node_ids)

        if topology.structure == "grouped":
            return DebateGraph._grouped_edges(participants)

        if topology.structure == "structured_network":
            pattern = topology.pattern
            if pattern is None:
                raise ValueError(
                    "structured_network topology requires a 'pattern' to derive "
                    "edges when no explicit edges are provided"
                )
            built = templates.build_topology(pattern, node_ids)
            return list(built.edges)

        # Should be unreachable given the schema's Literal typing.
        raise ValueError(f"unknown topology structure '{topology.structure}'")

    @staticmethod
    def _grouped_edges(participants: Participants) -> list[Edge]:
        """Fully-connected edges *within* each group (nothing across groups).

        Grouping comes from each node's ``group`` assignment. Nodes without a
        group are isolated (contribute no edges).
        """
        members: dict[str, list[str]] = {}
        for node in participants.nodes:
            if node.group is None:
                continue
            members.setdefault(node.group, []).append(node.id)

        edges: list[Edge] = []
        for group_members in members.values():
            # Reuse the canonical fully-connected builder per group.
            edges.extend(templates.fully_connected(group_members))
        return edges

    @staticmethod
    def _to_arcs(edges: list[Edge]) -> list[tuple[str, str]]:
        """Expand edges into directed arcs, honouring ``directed=False``.

        A directed edge yields one arc; an undirected edge yields both.
        """
        arcs: list[tuple[str, str]] = []
        for edge in edges:
            arcs.append((edge.source, edge.target))
            if not edge.directed:
                arcs.append((edge.target, edge.source))
        return arcs

    # -- neighbour queries (used by the protocol scheduler) ----------------

    def successors(self, node_id: str) -> list[str]:
        """Nodes ``node_id`` can send to (outgoing edges), in order."""
        self._require_node(node_id)
        return list(self._succ[node_id])

    def predecessors(self, node_id: str) -> list[str]:
        """Nodes that can send to ``node_id`` (incoming edges), in order."""
        self._require_node(node_id)
        return list(self._pred[node_id])

    def nodes(self) -> list[str]:
        """All node ids, in declaration order."""
        return list(self._nodes)

    def edges(self) -> list[tuple[str, str]]:
        """All directed arcs ``(src, dst)``, in insertion order."""
        return list(self._edges)

    def has_edge(self, u: str, v: str) -> bool:
        """``True`` if the directed arc ``u → v`` is present."""
        return (u, v) in self._edge_set

    def has_node(self, node_id: str) -> bool:
        """``True`` if ``node_id`` is a node of the graph."""
        return node_id in self._succ

    # -- helpers -----------------------------------------------------------

    def _require_node(self, node_id: str) -> None:
        if node_id not in self._succ:
            raise KeyError(f"node '{node_id}' is not in the graph")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"DebateGraph(nodes={len(self._nodes)}, "
            f"edges={len(self._edges)})"
        )


__all__ = ["DebateGraph"]
