import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { useDesignerStore } from "./designerStore";
import {
  CanvasContextMenu,
  EdgeContextMenu,
  useCanvasContextMenu,
  useEdgeContextMenu,
} from "./EdgeContextMenu";
import {
  toFlowEdges,
  toFlowNodes,
  toStartEndEdges,
  toStartEndNodes,
} from "./flowGraph";

/**
 * Component test for the edge right-click menu (task 11.2).
 *
 * jsdom cannot measure React Flow nodes, so the real canvas never paints its
 * edges here. The harness renders the SAME projected edge list the canvas
 * renders (`toFlowEdges` + `toStartEndEdges`) as plain elements and wires each
 * one's `onContextMenu` to the real `useEdgeContextMenu` handler (exactly what
 * DesignerPage passes to React Flow's `onEdgeContextMenu`), plus the real
 * portalled `EdgeContextMenu` bound to the store.
 */

function seedStore() {
  useDesignerStore.getState().loadArtifact(9, {
    name: "Edge menu fixture",
    participants: {
      nodes: [
        { id: "a", label: "A", roles: ["debater"] },
        { id: "b", label: "B", roles: ["debater"] },
      ],
    },
    interaction: {
      topology: { edges: [{ source: "a", target: "b", directed: true }] },
    },
  });
}

function CanvasEdgesHarness() {
  const artifact = useDesignerStore((s) => s.artifact)!;
  const { menu, onEdgeContextMenu, close } = useEdgeContextMenu();
  const edges = [...toFlowEdges(artifact, null), ...toStartEndEdges(artifact)];
  return (
    <div>
      {edges.map((edge) => (
        <div
          key={edge.id}
          data-testid={`edge-${edge.id}`}
          onContextMenu={(e) => onEdgeContextMenu(e, edge)}
        >
          {edge.id}
        </div>
      ))}
      <EdgeContextMenu menu={menu} onClose={close} />
    </div>
  );
}

const state = () => useDesignerStore.getState();

describe("EdgeContextMenu (right-click -> Delete)", () => {
  beforeEach(() => {
    useDesignerStore.setState({ artifact: null, layout: {}, selection: null, dirty: false });
    seedStore();
  });

  it("right-click on a participant edge shows Delete and removes the edge", async () => {
    const user = userEvent.setup();
    render(<CanvasEdgesHarness />);

    expect(screen.queryByRole("menuitem", { name: "Delete" })).toBeNull();
    // The native context menu is suppressed (default prevented).
    const notPrevented = fireEvent.contextMenu(screen.getByTestId("edge-a->b"), {
      clientX: 120,
      clientY: 80,
    });
    expect(notPrevented).toBe(false);

    const menu = screen.getByTestId("edge-context-menu");
    // Portalled to document.body, positioned at the cursor.
    expect(menu.parentElement).toBe(document.body);
    expect(menu.style.left).toBe("120px");
    expect(menu.style.top).toBe("80px");

    await user.click(screen.getByRole("menuitem", { name: "Delete" }));

    expect(state().artifact!.interaction.topology.edges).toHaveLength(0);
    expect(state().dirty).toBe(true);
    expect(screen.queryByTestId("edge-context-menu")).toBeNull();
    expect(screen.queryByTestId("edge-a->b")).toBeNull();
  });

  it("deletes a Start connector (persists entry_nodes)", async () => {
    const user = userEvent.setup();
    render(<CanvasEdgesHarness />);

    fireEvent.contextMenu(screen.getByTestId("edge-__start__->a"));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));

    expect(state().artifact!.interaction.topology.entry_nodes).toEqual(["b"]);
    expect(screen.queryByTestId("edge-__start__->a")).toBeNull();
    // Participant edges are untouched.
    expect(state().artifact!.interaction.topology.edges).toHaveLength(1);
  });

  it("deletes an End connector (persists exit_nodes)", async () => {
    const user = userEvent.setup();
    render(<CanvasEdgesHarness />);

    fireEvent.contextMenu(screen.getByTestId("edge-b->__end__"));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));

    expect(state().artifact!.interaction.topology.exit_nodes).toEqual(["a"]);
    expect(screen.queryByTestId("edge-b->__end__")).toBeNull();
  });

  it("closes on Escape and on outside click without deleting", async () => {
    const user = userEvent.setup();
    render(<CanvasEdgesHarness />);

    fireEvent.contextMenu(screen.getByTestId("edge-a->b"));
    expect(screen.getByTestId("edge-context-menu")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByTestId("edge-context-menu")).toBeNull();

    fireEvent.contextMenu(screen.getByTestId("edge-a->b"));
    fireEvent.mouseDown(document.body);
    expect(screen.queryByTestId("edge-context-menu")).toBeNull();

    expect(state().artifact!.interaction.topology.edges).toHaveLength(1);
    expect(state().dirty).toBe(false);
  });
});

/**
 * Node right-click menu (task 11.5). Same approach: render the projected node
 * list (participants + synthetic Start/End) as plain elements wired to the real
 * `onNodeContextMenu` handler and the real portalled menu.
 */
function CanvasNodesHarness() {
  const artifact = useDesignerStore((s) => s.artifact)!;
  const layout = useDesignerStore((s) => s.layout);
  const { menu, onEdgeContextMenu, onNodeContextMenu, close } =
    useCanvasContextMenu();
  const nodes = [
    ...toFlowNodes(artifact, layout, null),
    ...toStartEndNodes(artifact, layout),
  ];
  const edges = [...toFlowEdges(artifact, null), ...toStartEndEdges(artifact)];
  return (
    <div>
      {nodes.map((node) => (
        <div
          key={node.id}
          data-testid={`node-${node.id}`}
          onContextMenu={(e) => onNodeContextMenu(e, node)}
        >
          {node.id}
        </div>
      ))}
      {edges.map((edge) => (
        <div
          key={edge.id}
          data-testid={`edge-${edge.id}`}
          onContextMenu={(e) => onEdgeContextMenu(e, edge)}
        >
          {edge.id}
        </div>
      ))}
      <CanvasContextMenu menu={menu} onClose={close} />
    </div>
  );
}

describe("Node context menu (right-click -> Delete)", () => {
  beforeEach(() => {
    useDesignerStore.setState({ artifact: null, layout: {}, selection: null, dirty: false });
    seedStore();
  });

  it("deletes the node, its edges and its Start/End connectors", async () => {
    const user = userEvent.setup();
    render(<CanvasNodesHarness />);

    const notPrevented = fireEvent.contextMenu(screen.getByTestId("node-a"), {
      clientX: 40,
      clientY: 30,
    });
    expect(notPrevented).toBe(false);

    const menu = screen.getByTestId("node-context-menu");
    expect(menu).toHaveAttribute("aria-label", "Node actions");
    expect(menu.parentElement).toBe(document.body);
    expect(screen.queryByTestId("edge-context-menu")).toBeNull();

    await user.click(screen.getByRole("menuitem", { name: "Delete" }));

    const s = state();
    expect(s.artifact!.participants.nodes.map((n) => n.id)).toEqual(["b"]);
    expect(s.artifact!.interaction.topology.edges).toHaveLength(0);
    expect(s.layout.a).toBeUndefined();
    expect(s.dirty).toBe(true);
    expect(screen.queryByTestId("node-context-menu")).toBeNull();
    // Canvas: the node, its participant edge and its Start connector are gone.
    expect(screen.queryByTestId("node-a")).toBeNull();
    expect(screen.queryByTestId("edge-a->b")).toBeNull();
    expect(screen.queryByTestId("edge-__start__->a")).toBeNull();
    expect(screen.getByTestId("edge-__start__->b")).toBeInTheDocument();
  });

  it("also drops the node from explicit entry/exit lists", async () => {
    const user = userEvent.setup();
    render(<CanvasNodesHarness />);
    // Materialize explicit IO lists first (Start -> a only).
    act(() => state().removeEntryNode("b"));
    expect(state().artifact!.interaction.topology.entry_nodes).toEqual(["a"]);

    fireEvent.contextMenu(screen.getByTestId("node-a"));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));

    // Emptied by the deletion -> falls back to the default (null).
    expect(state().artifact!.interaction.topology.entry_nodes ?? null).toBeNull();
    expect(state().artifact!.interaction.topology.exit_nodes ?? []).not.toContain("a");
  });

  it("shows no menu for the synthetic Start/End nodes", () => {
    render(<CanvasNodesHarness />);

    for (const id of ["__start__", "__end__"]) {
      const notPrevented = fireEvent.contextMenu(screen.getByTestId(`node-${id}`));
      // Native menu still suppressed, but no custom menu opens.
      expect(notPrevented).toBe(false);
      expect(screen.queryByTestId("node-context-menu")).toBeNull();
      expect(screen.queryByRole("menu")).toBeNull();
    }
    expect(state().artifact!.participants.nodes).toHaveLength(2);
  });

  it("keeps a single menu open: a node right-click replaces an edge menu", () => {
    render(<CanvasNodesHarness />);

    fireEvent.contextMenu(screen.getByTestId("edge-a->b"));
    expect(screen.getByTestId("edge-context-menu")).toBeInTheDocument();
    fireEvent.contextMenu(screen.getByTestId("node-b"));
    expect(screen.queryByTestId("edge-context-menu")).toBeNull();
    expect(screen.getAllByRole("menu")).toHaveLength(1);
    expect(screen.getByTestId("node-context-menu")).toBeInTheDocument();
  });
});
