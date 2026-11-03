import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";

import { TaxonomyProvider } from "@/taxonomy/TaxonomyContext";
import { useDesignerStore } from "../designerStore";
import { AgreementPanel } from "./AgreementPanel";
import { Inspector } from "./Inspector";
import { InteractionPanel } from "./InteractionPanel";
import { ParticipantsPanel } from "./ParticipantsPanel";
import { SAMPLE_PROVIDERS, SAMPLE_TAXONOMY } from "./testFixtures";

/**
 * Component tests for the taxonomy-driven dimension panels (task 8.4).
 *
 * Each test renders a panel wired to the real designer store, then exercises a
 * taxonomy-driven control and asserts the artifact changed accordingly:
 *  - editing a node's roles / persona updates the artifact (Req 1.*)
 *  - changing authority / resolution updates the artifact (Req 3.*)
 *  - a non-executable value shows an "under development" badge (Req 7.5)
 *  - defaults render pre-filled (Req 7.1)
 */

/** Route the stubbed fetch by URL path to the right fixture. */
function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      const payload = url.includes("/providers")
        ? SAMPLE_PROVIDERS
        : SAMPLE_TAXONOMY;
      return Promise.resolve(
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    }),
  );
}

function seedArtifact() {
  useDesignerStore.getState().loadArtifact(1, {
    name: "Panels fixture",
    participants: {
      base_model_heterogeneity: "homogeneous",
      persona_heterogeneity: "homogeneous",
      persona_assignment: "unspecified",
      nodes: [
        {
          id: "a",
          label: "Alpha",
          roles: ["debater"],
          persona: {},
          base_model: { family: "closed_weight" },
        },
        { id: "b", label: "Beta", roles: ["judge"] },
      ],
    },
    interaction: {
      topology: { structure: "fully_connected", edges: [] },
      protocol: { mechanism: "sequential", max_rounds: 1, ordering: "fixed" },
      format: {
        syntax: "natural_language",
        content: { strategy: "verbatim", metadata_signals: [] },
        memory: "short_term",
      },
    },
    agreement: {
      authority: "collective",
      resolution: "majority_vote",
      resolution_params: {},
    },
  });
}

function renderPanel(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TaxonomyProvider fallback={<div>loading</div>}>{ui}</TaxonomyProvider>
    </QueryClientProvider>,
  );
}

function artifact() {
  return useDesignerStore.getState().artifact!;
}

describe("designer dimension panels (taxonomy-driven forms)", () => {
  beforeEach(() => {
    stubFetch();
    useDesignerStore.setState({
      configId: null,
      artifact: null,
      layout: {},
      selection: null,
      dirty: false,
      validationErrors: [],
    });
    seedArtifact();
  });
  afterEach(() => vi.restoreAllMocks());

  it("editing a node's roles updates the artifact (Req 1.5)", async () => {
    const user = userEvent.setup();
    renderPanel(<ParticipantsPanel nodeId="a" />);

    // Wait for the taxonomy-driven roles to render.
    const judge = await screen.findByRole("checkbox", { name: "Judge" });
    expect(judge).not.toBeChecked();

    await user.click(judge);

    expect(artifact().participants.nodes[0].roles).toContain("judge");
    expect(useDesignerStore.getState().dirty).toBe(true);
  });

  it("adding a custom role updates the artifact (Req 1.6)", async () => {
    const user = userEvent.setup();
    renderPanel(<ParticipantsPanel nodeId="a" />);

    const input = await screen.findByLabelText("Custom role name");
    await user.type(input, "moderator");
    await user.click(screen.getByRole("button", { name: /^Add$/i }));

    expect(artifact().participants.nodes[0].roles).toContain("custom:moderator");
  });

  it("editing persona stance updates the artifact (Req 1.2)", async () => {
    const user = userEvent.setup();
    renderPanel(<ParticipantsPanel nodeId="a" />);

    const stance = await screen.findByLabelText("Stance");
    await user.type(stance, "pro");

    expect(artifact().participants.nodes[0].persona?.stance).toBe("pro");
  });

  it("applying a persona template prefills the persona fields (Req 1.9)", async () => {
    const user = userEvent.setup();
    renderPanel(<ParticipantsPanel nodeId="a" />);

    const picker = await screen.findByLabelText("Persona template");
    await user.selectOptions(picker, "angel_devil");

    const persona = artifact().participants.nodes[0].persona!;
    expect(persona.template_ref).toBe("angel_devil");
    expect(persona.background).toBe("An optimistic advocate.");
    expect(persona.stance).toBe("Supports the proposal.");
  });

  it("binds a base model to a provider + model (Req 1.8, 8.6)", async () => {
    const user = userEvent.setup();
    renderPanel(<ParticipantsPanel nodeId="a" />);

    // Providers load async; wait for the option to appear.
    const providerSelect = await screen.findByLabelText("Provider");
    await waitFor(() =>
      expect(
        within(providerSelect).queryByRole("option", { name: "OpenAI" }),
      ).toBeInTheDocument(),
    );
    await user.selectOptions(providerSelect, "1");
    expect(artifact().participants.nodes[0].base_model?.provider_id).toBe("1");

    const modelSelect = screen.getByLabelText("Model");
    await user.selectOptions(modelSelect, "gpt-4o");
    expect(artifact().participants.nodes[0].base_model?.model_key).toBe("gpt-4o");
  });

  it("changing authority and resolution updates the artifact (Req 3.1, 3.2, 3.3)", async () => {
    const user = userEvent.setup();
    renderPanel(<AgreementPanel />);

    // Defaults render pre-filled (Req 7.1).
    const authority = await screen.findByLabelText("Authority");
    expect((authority as HTMLSelectElement).value).toBe("collective");

    await user.selectOptions(authority, "judge_based");
    expect(artifact().agreement?.authority).toBe("judge_based");

    const resolution = screen.getByLabelText("Resolution");
    await user.selectOptions(resolution, "argument_evaluation");
    expect(artifact().agreement?.resolution).toBe("argument_evaluation");
  });

  it("shows the resolution-params editor for weighted_vote and commits JSON (Req 3.4)", async () => {
    const user = userEvent.setup();
    renderPanel(<AgreementPanel />);

    const resolution = await screen.findByLabelText("Resolution");
    await user.selectOptions(resolution, "weighted_vote");

    const params = await screen.findByLabelText("Resolution parameters");
    // Set the whole JSON at once (fireEvent avoids userEvent key parsing of
    // `[` / `{` and the char-by-char intermediate invalid states).
    fireEvent.change(params, { target: { value: '{"weights": [1, 2]}' } });

    expect(artifact().agreement?.resolution_params).toEqual({ weights: [1, 2] });
  });

  it("surfaces invalid output-schema JSON as a client error (Req 7.3)", async () => {
    renderPanel(<AgreementPanel />);

    const schema = await screen.findByLabelText("Output schema (JSON)");
    fireEvent.change(schema, { target: { value: "{not json" } });

    expect(await screen.findByText(/invalid json/i)).toBeInTheDocument();
  });

  it("marks a non-executable interaction value under development (Req 7.5)", async () => {
    const user = userEvent.setup();
    renderPanel(<InteractionPanel />);

    const adaptability = await screen.findByLabelText("Topology adaptability");
    await user.selectOptions(adaptability, "dynamic");

    expect(artifact().interaction.topology.adaptability).toBe("dynamic");
    // The selected non-executable value badges "under development".
    expect(screen.getAllByText(/under development/i).length).toBeGreaterThan(0);
  });

  it("toggles format metadata signals (Req 2.7)", async () => {
    const user = userEvent.setup();
    renderPanel(<InteractionPanel />);

    const confidence = await screen.findByRole("checkbox", { name: "Confidence" });
    await user.click(confidence);

    expect(
      artifact().interaction.format?.content?.metadata_signals,
    ).toContain("confidence");
  });

  it("inspector is context-sensitive: node selection shows the Participants panel (Req 6.3)", async () => {
    useDesignerStore.getState().setSelection({ kind: "node", id: "a" });
    renderPanel(<Inspector />);

    // The node's name field (Participants panel) is shown.
    const label = await screen.findByLabelText("Name");
    expect((label as HTMLInputElement).value).toBe("Alpha");
    // The Participants tab is active.
    expect(
      screen.getByRole("tab", { name: /participants/i }),
    ).toHaveAttribute("aria-selected", "true");
  });

  it("inspector shows edge props when an edge is selected (Req 6.4)", async () => {
    useDesignerStore.getState().connectNodes("a", "b");
    useDesignerStore.getState().setSelection({ kind: "edge", id: "a->b" });
    renderPanel(<Inspector />);

    // The edge "Directed" control is shown, and the Interaction tab is active.
    expect(await screen.findByText("a → b")).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: /interaction/i }),
    ).toHaveAttribute("aria-selected", "true");
  });
});

/**
 * Defaults pre-filled from the taxonomy (Req 7.1).
 *
 * A fresh config/node that leaves taxonomy-driven fields unspecified must still
 * render the catalog's declared default selections — not an empty control — so
 * a new configuration is immediately valid and runnable. These tests seed a
 * minimal artifact (no explicit dimension values) and assert each
 * data-driven select lands on the taxonomy's `default` value.
 */
describe("taxonomy-driven forms — defaults pre-filled (Req 7.1)", () => {
  beforeEach(() => {
    stubFetch();
    useDesignerStore.setState({
      configId: null,
      artifact: null,
      layout: {},
      selection: null,
      dirty: false,
      validationErrors: [],
    });
    // A deliberately sparse artifact: a single node whose base model, persona,
    // and heterogeneity are all unspecified, and interaction/agreement blocks
    // with no taxonomy values chosen. The forms must fall back to the catalog
    // defaults for every such field.
    useDesignerStore.getState().loadArtifact(99, {
      name: "Fresh config",
      participants: { nodes: [{ id: "a", label: "Alpha", roles: ["debater"] }] },
      interaction: { topology: { edges: [] } },
      agreement: {},
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("Interaction panel lands on the taxonomy default selections", async () => {
    renderPanel(<InteractionPanel />);

    // Topology adaptability default = "static"; structure default =
    // "fully_connected"; protocol mechanism = "sequential"; ordering = "fixed".
    const adaptability = (await screen.findByLabelText(
      "Topology adaptability",
    )) as HTMLSelectElement;
    expect(adaptability.value).toBe("static");

    const structure = screen.getByLabelText(
      "Topology structure",
    ) as HTMLSelectElement;
    expect(structure.value).toBe("fully_connected");

    const mechanism = screen.getByLabelText(
      "Protocol mechanism",
    ) as HTMLSelectElement;
    expect(mechanism.value).toBe("sequential");

    const ordering = screen.getByLabelText(
      "Protocol ordering",
    ) as HTMLSelectElement;
    expect(ordering.value).toBe("fixed");
  });

  it("Agreement panel lands on the taxonomy default selections", async () => {
    renderPanel(<AgreementPanel />);

    const authority = (await screen.findByLabelText(
      "Authority",
    )) as HTMLSelectElement;
    expect(authority.value).toBe("collective");

    const resolution = screen.getByLabelText("Resolution") as HTMLSelectElement;
    expect(resolution.value).toBe("majority_vote");
  });

  it("Participants panel base-model family falls back to the taxonomy default", async () => {
    useDesignerStore.getState().setSelection({ kind: "node", id: "a" });
    renderPanel(<ParticipantsPanel nodeId="a" />);

    // The node declares no base_model.family; the select shows the catalog
    // default ("closed_weight") rather than an empty value.
    const family = (await screen.findByLabelText(
      "Base model family",
    )) as HTMLSelectElement;
    expect(family.value).toBe("closed_weight");

    // Dimension-level heterogeneity/assignment likewise default.
    const personaHet = screen.getByLabelText(
      "Persona heterogeneity",
    ) as HTMLSelectElement;
    expect(personaHet.value).toBe("homogeneous");
  });
});
