import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ReactFlow, { ReactFlowProvider } from "reactflow";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";

import { TaxonomyProvider } from "@/taxonomy/TaxonomyContext";
import { DesignerToolbar } from "../DesignerToolbar";
import { useDesignerStore } from "../designerStore";
import { toFlowNodes } from "../flowGraph";
import { topologyStatus } from "../interactionScope";
import { ParticipantNode } from "../ParticipantNode";
import { buildTopologyEdges } from "../topology";
import { AgreementPanel } from "./AgreementPanel";
import { Inspector } from "./Inspector";
import { InteractionPanel } from "./InteractionPanel";
import { SAMPLE_PROVIDERS, SAMPLE_TAXONOMY } from "./testFixtures";

/**
 * Panel behaviour for the debate-level Interaction / Agreement scope (task
 * 11.7): dependent-field visibility, turn order + canvas badges, the phases
 * editor, drift detection + Re-apply, the resolution compatibility matrix,
 * and the judge notices with "Add judge".
 */

function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      const payload = url.includes("/providers") ? SAMPLE_PROVIDERS : SAMPLE_TAXONOMY;
      return Promise.resolve(
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    }),
  );
}

const NODES = [
  { id: "a", label: "Alpha", roles: ["debater"] },
  { id: "b", label: "Beta", roles: ["debater"] },
  { id: "c", label: "Gamma", roles: ["debater"] },
];

function seed(raw: Record<string, unknown> = {}, nodes: unknown[] = NODES) {
  useDesignerStore.getState().loadArtifact(1, {
    name: "Interaction panels",
    participants: { nodes },
    interaction: { topology: { edges: [] } },
    ...raw,
  });
}

function renderUi(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TaxonomyProvider fallback={<div>loading</div>}>{ui}</TaxonomyProvider>
    </QueryClientProvider>,
  );
}

const state = () => useDesignerStore.getState();
const protocol = () => state().artifact!.interaction.protocol!;

beforeEach(() => {
  stubFetch();
  useDesignerStore.setState({
    artifact: null,
    layout: {},
    edgeBends: {},
    selection: null,
    dirty: false,
    validationErrors: [],
  });
});
afterEach(() => vi.restoreAllMocks());

describe("protocol: dependent fields per mechanism / ordering", () => {
  it("sequential + fixed: Turn order in declaration order, reorder, reset", async () => {
    const user = userEvent.setup();
    seed();
    renderUi(<InteractionPanel />);

    expect(await screen.findByLabelText("Protocol ordering")).toBeInTheDocument();
    expect(screen.getByTestId("turn-order-declaration")).toBeInTheDocument();
    const items = () =>
      within(screen.getByTestId("turn-order"))
        .getAllByTestId("turn-order-item")
        .map((li) => li.textContent);
    expect(items()).toEqual(["1Alpha", "2Beta", "3Gamma"]);
    expect(screen.getByRole("button", { name: "Move Alpha up" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Move Beta up" }));
    expect(protocol().order).toEqual(["b", "a", "c"]);
    expect(items()).toEqual(["1Beta", "2Alpha", "3Gamma"]);

    await user.click(screen.getByRole("button", { name: "Reset to declaration order" }));
    expect(protocol().order).toEqual([]);
    expect(screen.getByTestId("turn-order-declaration")).toBeInTheDocument();
  });

  it("a partial order flags participants that never speak, with Add", async () => {
    const user = userEvent.setup();
    seed({ interaction: { topology: { edges: [] }, protocol: { order: ["c", "a"] } } });
    renderUi(<InteractionPanel />);
    const notice = await screen.findByTestId("turn-order-missing");
    expect(notice).toHaveTextContent("Beta");
    await user.click(within(notice).getByRole("button", { name: "Add Beta" }));
    expect(protocol().order).toEqual(["c", "a", "b"]);
  });

  it("randomized: a note, no turn list", async () => {
    seed({ interaction: { topology: { edges: [] }, protocol: { ordering: "randomized" } } });
    renderUi(<InteractionPanel />);
    expect(await screen.findByTestId("proto-randomized-note")).toBeInTheDocument();
    expect(screen.queryByTestId("turn-order")).toBeNull();
  });

  it("simultaneous: ordering hidden, all-act note", async () => {
    seed({ interaction: { topology: { edges: [] }, protocol: { mechanism: "simultaneous" } } });
    renderUi(<InteractionPanel />);
    expect(await screen.findByTestId("proto-simultaneous-note")).toBeInTheDocument();
    expect(screen.queryByLabelText("Protocol ordering")).toBeNull();
    expect(screen.queryByTestId("turn-order")).toBeNull();
    expect(screen.queryByTestId("phases")).toBeNull();
  });

  it("hybrid: phases editor with the no-phase error, add / edit / reorder / remove", async () => {
    const user = userEvent.setup();
    seed({ interaction: { topology: { edges: [] }, protocol: { mechanism: "hybrid" } } });
    renderUi(<InteractionPanel />);

    expect(await screen.findByTestId("hybrid-phases-error")).toBeInTheDocument();
    expect(screen.queryByLabelText("Protocol ordering")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Add phase" }));
    expect(screen.queryByTestId("hybrid-phases-error")).toBeNull();
    await user.selectOptions(screen.getByLabelText("Phase 1 mechanism"), "simultaneous");
    await user.click(screen.getByRole("checkbox", { name: "Phase 1: Gamma" }));
    await user.click(screen.getByRole("checkbox", { name: "Phase 1: Alpha" }));
    expect(protocol().phases).toEqual([{ mechanism: "simultaneous", participants: ["a", "c"] }]);

    await user.click(screen.getByRole("button", { name: "Add phase" }));
    await user.click(screen.getByRole("button", { name: "Move phase 2 up" }));
    expect(protocol().phases).toEqual([
      { mechanism: "sequential", participants: [] },
      { mechanism: "simultaneous", participants: ["a", "c"] },
    ]);

    await user.click(screen.getByRole("button", { name: "Remove phase 1" }));
    await user.click(screen.getByRole("button", { name: "Remove phase 1" }));
    expect(protocol().phases).toEqual([]);
    expect(screen.getByTestId("hybrid-phases-error")).toBeInTheDocument();
  });
});

describe("turn-number badges on the canvas", () => {
  function renderCanvas() {
    const flowNodes = toFlowNodes(
      state().artifact!,
      { a: { x: 0, y: 0 }, b: { x: 300, y: 0 }, c: { x: 600, y: 0 } },
      null,
    );
    return renderUi(
      <div style={{ width: 900, height: 600 }}>
        <ReactFlowProvider>
          <ReactFlow nodes={flowNodes} edges={[]} nodeTypes={{ participant: ParticipantNode }} />
        </ReactFlowProvider>
      </div>,
    );
  }

  it("numbers follow the fixed order", async () => {
    seed({ interaction: { topology: { edges: [] }, protocol: { order: ["c", "a", "b"] } } });
    renderCanvas();
    await screen.findAllByTestId("participant-turn-badge");
    const byLabel = Object.fromEntries(
      screen.getAllByTestId("participant-node").map((n) => [
        n.querySelector("p[title]")?.getAttribute("title"),
        within(n).getByTestId("participant-turn-badge").textContent,
      ]),
    );
    expect(byLabel).toEqual({ Alpha: "2", Beta: "3", Gamma: "1" });
  });

  it("no numbers when randomized", async () => {
    seed({ interaction: { topology: { edges: [] }, protocol: { ordering: "randomized" } } });
    renderCanvas();
    await screen.findAllByTestId("participant-node");
    expect(screen.queryByTestId("participant-turn-badge")).toBeNull();
  });
});

describe("topology: adaptability + drift detection", () => {
  const chain = () => ({
    interaction: {
      topology: {
        structure: "structured_network",
        pattern: "chain",
        edges: buildTopologyEdges("chain", ["a", "b", "c"]),
      },
    },
  });

  it("summary says Custom (edited from Chain) and Re-apply confirms first", async () => {
    const user = userEvent.setup();
    seed(chain());
    renderUi(<InteractionPanel />);
    expect(await screen.findByTestId("topology-status")).toHaveTextContent("Chain");
    expect(screen.getByLabelText("Topology adaptability")).toBeInTheDocument();

    state().removeEdge("a->b");
    expect(await screen.findByText("Custom (edited from Chain)")).toBeInTheDocument();

    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    const reapply = screen.getByRole("button", { name: "Re-apply Chain" });
    await user.click(reapply);
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(state().artifact!.interaction.topology.edges).toHaveLength(1);
    await user.click(reapply);
    expect(state().artifact!.interaction.topology.edges).toHaveLength(2);
    expect(screen.getByTestId("topology-status")).toHaveTextContent(/^Chain$/);
  });

  it("toolbar shows the status, offers Re-apply, and no longer offers Grouped", async () => {
    const user = userEvent.setup();
    seed(chain());
    state().removeEdge("a->b");
    const onApply = vi.fn();
    render(
      <DesignerToolbar
        onAddNode={() => undefined}
        onApplyTopology={onApply}
        onAutoLayout={() => undefined}
        onDeleteSelection={() => undefined}
        onSave={() => undefined}
        canDeleteSelection={false}
        dirty
        saving={false}
        topologyStatus={topologyStatus(state().artifact!)}
      />,
    );
    expect(screen.getByTestId("toolbar-topology-status")).toHaveTextContent(
      "Custom (edited from Chain)",
    );
    await user.click(screen.getByRole("button", { name: /apply topology template/i }));
    expect(screen.queryByRole("menuitem", { name: /grouped/i })).toBeNull();
    await user.click(screen.getByRole("menuitem", { name: /re-apply chain/i }));
    expect(onApply).toHaveBeenCalledWith("chain");
  });
});

describe("format: summarized needs a summarizer", () => {
  it("warns without one and Add summarizer adds the role node", async () => {
    const user = userEvent.setup();
    seed({ interaction: { topology: { edges: [] }, format: { content: { strategy: "summarized" } } } });
    renderUi(<InteractionPanel />);
    const notice = await screen.findByTestId("fmt-no-summarizer");
    await user.click(within(notice).getByRole("button", { name: "Add summarizer" }));
    const nodes = state().artifact!.participants.nodes;
    expect(nodes[nodes.length - 1].roles).toEqual(["summarizer"]);
    expect(screen.getByTestId("fmt-summarizer")).toBeInTheDocument();
  });
});

describe("agreement: compatibility matrix and judge notices", () => {
  const option = (select: HTMLElement, value: string) =>
    within(select).getAllByRole("option").find((o) => (o as HTMLOptionElement).value === value) as HTMLOptionElement;

  it("collective disables argument_evaluation with the reason", async () => {
    seed({ agreement: { authority: "collective", resolution: "majority_vote" } });
    renderUi(<AgreementPanel />);
    const resolution = await screen.findByLabelText("Resolution");
    expect(option(resolution, "argument_evaluation").disabled).toBe(true);
    expect(option(resolution, "argument_evaluation").textContent).toMatch(/needs a judge/);
    expect(option(resolution, "consensus").disabled).toBe(false);
  });

  it("switching to judge-based switches the resolution and says so; Add judge fixes the missing judge", async () => {
    const user = userEvent.setup();
    seed({ agreement: { authority: "collective", resolution: "majority_vote" } });
    renderUi(<AgreementPanel />);
    await user.selectOptions(await screen.findByLabelText("Authority"), "judge_based");
    expect(state().artifact!.agreement).toMatchObject({
      authority: "judge_based",
      resolution: "argument_evaluation",
    });
    expect(screen.getByTestId("agr-resolution-switched")).toHaveTextContent(
      "Resolution switched from Majority vote to Argument evaluation",
    );
    const resolution = screen.getByLabelText("Resolution");
    expect(option(resolution, "majority_vote").disabled).toBe(true);

    const notice = screen.getByTestId("agr-no-judge");
    await user.click(within(notice).getByRole("button", { name: "Add judge" }));
    expect(state().artifact!.participants.nodes.some((n) => n.roles.includes("judge"))).toBe(true);
    expect(screen.queryByTestId("agr-no-judge")).toBeNull();
  });

  it("collective with a judge: judges do not decide", async () => {
    seed({ agreement: { authority: "collective" } }, [
      ...NODES,
      { id: "j", label: "Judy", roles: ["judge"] },
    ]);
    renderUi(<AgreementPanel />);
    expect(await screen.findByTestId("agr-judges-ignored")).toHaveTextContent("Judy");
  });

  it("an incompatible loaded pair offers the fix; params only when applied", async () => {
    const user = userEvent.setup();
    seed({
      participants: { nodes: [...NODES, { id: "j", label: "Judy", roles: ["judge"] }] },
      agreement: { authority: "judge_based", resolution: "weighted_vote", resolution_params: { w: 1 } },
    });
    renderUi(<AgreementPanel />);
    const notice = await screen.findByTestId("agr-resolution-incompatible");
    expect(screen.queryByLabelText("Resolution parameters")).toBeNull();
    await user.click(within(notice).getByRole("button", { name: "Switch to Argument evaluation" }));
    expect(state().artifact!.agreement?.resolution).toBe("argument_evaluation");
  });
});

describe("edge level", () => {
  it("edits only label/colour/direction and links back to debate settings", async () => {
    const user = userEvent.setup();
    seed();
    state().connectNodes("a", "b");
    state().setSelection({ kind: "edge", id: "a->b" });
    renderUi(<Inspector />);
    const link = await screen.findByTestId("edge-debate-level");
    expect(screen.queryByLabelText("Protocol mechanism")).toBeNull();
    await user.click(within(link).getByRole("button"));
    expect(state().selection).toBeNull();
    expect(await screen.findByLabelText("Protocol mechanism")).toBeInTheDocument();
  });
});
