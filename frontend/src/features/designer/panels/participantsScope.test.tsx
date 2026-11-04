import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ReactFlow, { ReactFlowProvider } from "reactflow";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";

import { TaxonomyProvider } from "@/taxonomy/TaxonomyContext";
import type { ParticipantsArtifact } from "../artifact";
import { useDesignerStore } from "../designerStore";
import { toFlowNodes } from "../flowGraph";
import { ParticipantNode } from "../ParticipantNode";
import { Inspector } from "./Inspector";
import { ParticipantsDimensionPanel } from "./ParticipantsDimensionPanel";
import { ParticipantsPanel } from "./ParticipantsPanel";
import { SAMPLE_PROVIDERS, SAMPLE_TAXONOMY } from "./testFixtures";

/**
 * Panel behaviour for the debate-level vs node-level Participants scope
 * (task 11.6): visibility / disabled states per mode, confirmations, conflict
 * banners + fixes, and the canvas conflict marker.
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

function seed(p: Partial<ParticipantsArtifact>, nodes?: ParticipantsArtifact["nodes"]) {
  useDesignerStore.getState().loadArtifact(1, {
    name: "Scope panels",
    participants: {
      persona_assignment: "manual",
      persona_heterogeneity: "homogeneous",
      base_model_heterogeneity: "homogeneous",
      ...p,
      nodes: nodes ?? [
        { id: "a", label: "Alpha", roles: ["debater"], persona: { stance: "Pro" } },
        { id: "b", label: "Beta", roles: ["debater"], persona: { stance: "Pro" } },
        { id: "j", label: "Judge", roles: ["judge"], persona: { stance: "Neutral" } },
      ],
    },
    interaction: { topology: { edges: [] } },
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
const node = (id: string) => state().artifact!.participants.nodes.find((n) => n.id === id)!;

beforeEach(() => {
  stubFetch();
  useDesignerStore.setState({
    artifact: null,
    layout: {},
    selection: null,
    dirty: false,
    validationErrors: [],
  });
});
afterEach(() => vi.restoreAllMocks());

describe("debate-level Participants panel", () => {
  it("orders persona assignment first and drops the old descriptive hint", async () => {
    seed({});
    renderUi(<ParticipantsDimensionPanel />);
    const assign = await screen.findByLabelText("Persona assignment");
    const het = screen.getByLabelText("Persona heterogeneity");
    const model = screen.getByLabelText("Base model heterogeneity");
    // DOCUMENT_POSITION_FOLLOWING = 4
    expect(assign.compareDocumentPosition(het) & 4).toBeTruthy();
    expect(het.compareDocumentPosition(model) & 4).toBeTruthy();
    expect(screen.queryByText(/documents intent/i)).toBeNull();
  });

  it("unspecified: heterogeneity disabled with a hint, no shared persona editor", async () => {
    seed({ persona_assignment: "unspecified" }, [
      { id: "a", label: "Alpha", roles: ["debater"] },
    ]);
    renderUi(<ParticipantsDimensionPanel />);
    expect(await screen.findByLabelText("Persona heterogeneity")).toBeDisabled();
    expect(screen.getByTestId("dim-persona-het-hint")).toBeInTheDocument();
    expect(screen.getByTestId("dim-persona-unspecified-note")).toBeInTheDocument();
    expect(screen.queryByTestId("dim-shared-persona")).toBeNull();
  });

  it("automatic: under-development note, persona editor hidden", async () => {
    seed({ persona_assignment: "automatic" }, [
      { id: "a", label: "Alpha", roles: ["debater"] },
    ]);
    renderUi(<ParticipantsDimensionPanel />);
    expect(await screen.findByTestId("dim-persona-automatic-note")).toBeInTheDocument();
    expect(screen.getByLabelText("Persona heterogeneity")).toBeDisabled();
    expect(screen.queryByTestId("dim-shared-persona")).toBeNull();
  });

  it("manual + homogeneous: the shared persona editor broadcasts to debaters", async () => {
    const user = userEvent.setup();
    seed({});
    renderUi(<ParticipantsDimensionPanel />);
    const shared = await screen.findByTestId("dim-shared-persona");
    const stance = within(shared).getByLabelText("Stance");
    expect(stance).toHaveValue("Pro");
    await user.type(stance, "!");
    expect(node("a").persona?.stance).toBe("Pro!");
    expect(node("b").persona?.stance).toBe("Pro!");
    expect(node("j").persona?.stance).toBe("Neutral");
  });

  it("heterogeneous modes show per-participant messages instead of editors", async () => {
    seed({ persona_heterogeneity: "heterogeneous", base_model_heterogeneity: "heterogeneous" });
    renderUi(<ParticipantsDimensionPanel />);
    expect(await screen.findByTestId("dim-persona-per-node")).toBeInTheDocument();
    expect(screen.getByTestId("dim-model-per-node")).toBeInTheDocument();
    expect(screen.queryByTestId("dim-shared-model")).toBeNull();
  });

  it("the shared model editor applies to every node", async () => {
    const user = userEvent.setup();
    seed({});
    renderUi(<ParticipantsDimensionPanel />);
    const shared = await screen.findByTestId("dim-shared-model");
    const provider = within(shared).getByLabelText("Provider");
    await waitFor(() =>
      expect(within(provider).queryByRole("option", { name: "OpenAI" })).toBeInTheDocument(),
    );
    await user.selectOptions(provider, "1");
    await user.selectOptions(within(shared).getByLabelText("Model"), "gpt-4o");
    for (const id of ["a", "b", "j"]) {
      expect(node(id).base_model).toMatchObject({ provider_id: "1", model_key: "gpt-4o" });
    }
  });

  it("switching to unspecified with personas asks first; cancel keeps them", async () => {
    const user = userEvent.setup();
    seed({});
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderUi(<ParticipantsDimensionPanel />);
    const assign = await screen.findByLabelText("Persona assignment");

    await user.selectOptions(assign, "unspecified");
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(state().artifact!.participants.persona_assignment).toBe("manual");
    expect(node("a").persona?.stance).toBe("Pro");

    await user.selectOptions(assign, "unspecified");
    expect(state().artifact!.participants.persona_assignment).toBe("unspecified");
    expect(node("a").persona?.stance ?? null).toBeNull();
    expect(node("j").persona?.stance ?? null).toBeNull();
  });

  it("heterogeneous -> homogeneous confirms only when personas diverge", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    seed({ persona_heterogeneity: "heterogeneous" });
    const { unmount } = renderUi(<ParticipantsDimensionPanel />);
    await user.selectOptions(await screen.findByLabelText("Persona heterogeneity"), "homogeneous");
    expect(confirm).not.toHaveBeenCalled(); // already agree
    unmount();

    seed({ persona_heterogeneity: "heterogeneous" }, [
      { id: "a", label: "Alpha", roles: ["debater"], persona: { stance: "Pro" } },
      { id: "b", label: "Beta", roles: ["debater"], persona: { stance: "Con" } },
    ]);
    renderUi(<ParticipantsDimensionPanel />);
    await user.selectOptions(await screen.findByLabelText("Persona heterogeneity"), "homogeneous");
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(node("b").persona?.stance).toBe("Pro");
  });
});

describe("conflict banners and fixes", () => {
  const divergent = [
    { id: "a", label: "Alpha", roles: ["debater"], persona: { stance: "Pro" } },
    { id: "b", label: "Beta", roles: ["debater"], persona: { stance: "Con" } },
  ];

  it("homogeneous-but-divergent personas: Make all match <first>", async () => {
    const user = userEvent.setup();
    seed({}, divergent);
    renderUi(<ParticipantsDimensionPanel />);
    const banner = await screen.findByTestId("participant-conflict-persona_divergent");
    // Shared editor is locked until the conflict is resolved.
    expect(within(screen.getByTestId("dim-shared-persona")).getByLabelText("Stance")).toBeDisabled();
    await user.click(within(banner).getByRole("button", { name: "Make all match Alpha" }));
    expect(node("b").persona?.stance).toBe("Pro");
    expect(screen.queryByTestId("participant-conflict-persona_divergent")).toBeNull();
  });

  it("homogeneous-but-divergent personas: Switch to heterogeneous keeps data", async () => {
    const user = userEvent.setup();
    seed({}, divergent);
    renderUi(<ParticipantsDimensionPanel />);
    const banner = await screen.findByTestId("participant-conflict-persona_divergent");
    await user.click(within(banner).getByRole("button", { name: "Switch to heterogeneous" }));
    expect(state().artifact!.participants.persona_heterogeneity).toBe("heterogeneous");
    expect(node("b").persona?.stance).toBe("Con");
  });

  it("unspecified-but-has-personas: Switch to Manual / Clear personas", async () => {
    const user = userEvent.setup();
    seed({ persona_assignment: "unspecified", persona_heterogeneity: "heterogeneous" }, divergent);
    const { unmount } = renderUi(<ParticipantsDimensionPanel />);
    let banner = await screen.findByTestId("participant-conflict-personas_without_manual");
    await user.click(within(banner).getByRole("button", { name: "Switch to Manual" }));
    expect(state().artifact!.participants.persona_assignment).toBe("manual");
    expect(node("b").persona?.stance).toBe("Con");
    unmount();

    seed({ persona_assignment: "unspecified" }, divergent);
    renderUi(<ParticipantsDimensionPanel />);
    banner = await screen.findByTestId("participant-conflict-personas_without_manual");
    await user.click(within(banner).getByRole("button", { name: "Clear personas" }));
    expect(state().artifact!.participants.persona_assignment).toBe("unspecified");
    expect(node("a").persona?.stance ?? null).toBeNull();
  });

  it("homogeneous-but-divergent models: Make all match <first bound>", async () => {
    const user = userEvent.setup();
    seed({ persona_assignment: "unspecified" }, [
      { id: "a", label: "Alpha", roles: ["debater"] },
      { id: "b", label: "Beta", roles: ["debater"], base_model: { provider_id: "2", model_key: "llama3" } },
    ]);
    renderUi(<ParticipantsDimensionPanel />);
    const banner = await screen.findByTestId("participant-conflict-model_divergent");
    await user.click(within(banner).getByRole("button", { name: "Make all match Beta" }));
    expect(node("a").base_model).toMatchObject({ provider_id: "2", model_key: "llama3" });
  });

  it("marks affected canvas nodes in amber", async () => {
    seed({}, divergent);
    const flowNodes = toFlowNodes(state().artifact!, { a: { x: 0, y: 0 }, b: { x: 300, y: 0 } }, null);
    renderUi(
      <div style={{ width: 800, height: 600 }}>
        <ReactFlowProvider>
          <ReactFlow nodes={flowNodes} edges={[]} nodeTypes={{ participant: ParticipantNode }} />
        </ReactFlowProvider>
      </div>,
    );
    const markers = await screen.findAllByTestId("participant-conflict-marker");
    expect(markers).toHaveLength(1);
    expect(markers[0].closest("[data-testid='participant-node']")).toHaveTextContent("Beta");
  });
});

describe("node-level Participants panel", () => {
  it("shared values are read-only with a link back to debate settings", async () => {
    const user = userEvent.setup();
    seed({});
    state().setSelection({ kind: "node", id: "a" });
    renderUi(<Inspector />);

    expect(await screen.findByLabelText("Stance")).toBeDisabled();
    expect(screen.getByLabelText("Provider")).toBeDisabled();
    expect(screen.getByTestId("node-persona-shared")).toBeInTheDocument();
    // System prompt stays editable in its own Instructions group.
    expect(screen.getByRole("heading", { name: "Instructions" })).toBeInTheDocument();
    expect(screen.getByLabelText("System prompt")).toBeEnabled();

    await user.click(screen.getByTestId("node-persona-shared").querySelector("button")!);
    expect(state().selection).toBeNull();
    expect(await screen.findByLabelText("Persona assignment")).toBeInTheDocument();
  });

  it("a judge keeps its own persona under a shared persona", async () => {
    seed({});
    renderUi(<ParticipantsPanel nodeId="j" />);
    expect(await screen.findByLabelText("Stance")).toBeEnabled();
    expect(screen.queryByTestId("node-persona-shared")).toBeNull();
  });

  it("unspecified disables persona fields on the node", async () => {
    seed({ persona_assignment: "unspecified" }, [{ id: "a", label: "Alpha", roles: ["debater"] }]);
    renderUi(<ParticipantsPanel nodeId="a" />);
    expect(await screen.findByLabelText("Stance")).toBeDisabled();
    expect(screen.getByLabelText("Persona template")).toBeDisabled();
    expect(screen.getByTestId("node-persona-disabled")).toBeInTheDocument();
  });

  it("gaining the debater role on the node inherits the shared persona", async () => {
    const user = userEvent.setup();
    seed({});
    renderUi(<ParticipantsPanel nodeId="j" />);
    await user.click(await screen.findByRole("checkbox", { name: "Debater" }));
    expect(node("j").persona?.stance).toBe("Pro");
    expect(screen.getByLabelText("Stance")).toBeDisabled();
  });
});
