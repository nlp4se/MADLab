import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { useDesignerStore } from "./designerStore";
import { EdgeContextMenu, useEdgeContextMenu } from "./EdgeContextMenu";
import { toFlowEdges, toStartEndEdges } from "./flowGraph";

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
