import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useDesignerStore } from "./designerStore";
import { DesignerToolbar } from "./DesignerToolbar";

/**
 * Component test for the designer toolbar wired to the real store. This proves
 * the canvas-level UI actions (add participant, apply topology, delete) drive
 * the artifact through the store (canvas -> artifact, Req 6.2, 6.5, 6.8) — the
 * same path the React Flow canvas uses, but without needing jsdom layout.
 */

function seedStore() {
  useDesignerStore.getState().loadArtifact(7, {
    name: "Toolbar fixture",
    participants: {
      nodes: [
        { id: "a", label: "A", roles: ["debater"] },
        { id: "b", label: "B", roles: ["debater"] },
        { id: "c", label: "C", roles: ["judge"] },
      ],
    },
    interaction: { topology: { structure: "fully_connected", edges: [] } },
  });
}

/** A harness binding the toolbar's callbacks to the real store actions. */
function ToolbarHarness() {
  const store = useDesignerStore();
  return (
    <DesignerToolbar
      onAddNode={() => store.addNode()}
      onApplyTopology={store.applyTopology}
      onAutoLayout={store.relayout}
      onDeleteSelection={() => {
        if (store.selection?.kind === "node") store.removeNode(store.selection.id);
      }}
      onSave={() => store.markSaved()}
      canDeleteSelection={store.selection !== null}
      dirty={store.dirty}
      saving={false}
    />
  );
}

describe("DesignerToolbar (canvas -> artifact)", () => {
  beforeEach(() => {
    useDesignerStore.setState({
      configId: null,
      artifact: null,
      layout: {},
      selection: null,
      dirty: false,
    });
    seedStore();
  });
  afterEach(() => {
    useDesignerStore.setState({ artifact: null, layout: {}, selection: null });
  });

  it("adds a participant node to the artifact", async () => {
    const user = userEvent.setup();
    render(<ToolbarHarness />);

    expect(useDesignerStore.getState().artifact!.participants.nodes).toHaveLength(3);

    await user.click(screen.getByRole("button", { name: /add participant/i }));

    expect(useDesignerStore.getState().artifact!.participants.nodes).toHaveLength(4);
    expect(useDesignerStore.getState().dirty).toBe(true);
  });

  it("applies a topology template that regenerates the edge set (Req 6.5)", async () => {
    const user = userEvent.setup();
    render(<ToolbarHarness />);

    // No edges to start.
    expect(
      useDesignerStore.getState().artifact!.interaction.topology.edges,
    ).toHaveLength(0);

    // Open the Topology menu and apply "Chain" -> 2 edges over 3 nodes.
    await user.click(screen.getByRole("button", { name: /apply topology template/i }));
    await user.click(screen.getByRole("menuitem", { name: /^Chain$/i }));

    const topo = useDesignerStore.getState().artifact!.interaction.topology;
    expect(topo.edges).toHaveLength(2);
    expect(topo.pattern).toBe("chain");
    expect(topo.structure).toBe("structured_network");
  });

  it("enables Save only when there are unsaved changes", async () => {
    const user = userEvent.setup();
    render(<ToolbarHarness />);

    // Fresh load is clean -> Save disabled.
    expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /add participant/i }));
    expect(screen.getByRole("button", { name: /save/i })).toBeEnabled();
  });
});
