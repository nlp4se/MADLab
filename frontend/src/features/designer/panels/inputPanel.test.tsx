import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TaxonomyProvider } from "@/taxonomy/TaxonomyContext";
import { useDesignerStore } from "../designerStore";
import { Inspector } from "./Inspector";
import { SAMPLE_PROVIDERS, SAMPLE_TAXONOMY } from "./testFixtures";

/**
 * Task 11.10: the inspector's Input tab / panel — template editing with
 * auto-detected placeholders and labels, the live preview, who receives the
 * input, and the empty-template warning.
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

function seed(template: string) {
  useDesignerStore.getState().loadArtifact(8, {
    name: "Input fixture",
    participants: {
      nodes: [
        { id: "p1", label: "Pro", roles: ["debater"] },
        { id: "p2", label: "Con", roles: ["debater"] },
        { id: "j", label: "Judge", roles: ["judge"] },
      ],
    },
    interaction: {
      topology: { structure: "fully_connected", edges: [], entry_nodes: ["p1", "p2"] },
    },
    agreement: { authority: "judge_based", resolution: "argument_evaluation" },
    input_spec: { template, placeholders: [], ad_hoc_fields: [] },
  });
}

function renderInspector() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TaxonomyProvider fallback={<div>loading</div>}>
        <Inspector />
      </TaxonomyProvider>
    </QueryClientProvider>,
  );
}

const spec = () => useDesignerStore.getState().artifact!.input_spec!;

describe("Input panel", () => {
  beforeEach(() => {
    stubFetch();
    useDesignerStore.setState({ selection: null, dirty: false, validationErrors: [] });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    useDesignerStore.setState({ artifact: null, layout: {}, selection: null });
  });

  it("opens on the Start-node selection and warns about an empty template", async () => {
    seed("");
    renderInspector();
    await screen.findByRole("tab", { name: /participants/i });
    // The Input tab carries the empty-template marker before it is opened.
    expect(screen.getByTestId("input-tab-warning")).toBeInTheDocument();

    useDesignerStore.getState().setSelection({ kind: "input" });
    await screen.findByTestId("input-panel");
    expect(screen.getByRole("tab", { name: /input/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    const warning = screen.getByTestId("input-empty-warning");
    expect(warning).toHaveTextContent(/no input template/i);
    // Who receives it: the Start connectors, and the deciding judge.
    expect(screen.getByTestId("input-receivers")).toHaveTextContent("Pro, Con receive it");
    expect(screen.getByTestId("input-judges")).toHaveTextContent("Judge sees it");

    // The quick fix sets the starter input.
    await userEvent.setup().click(
      within(warning).getByRole("button", { name: "Use {{input}}" }),
    );
    expect(spec()).toMatchObject({
      template: "{{input}}",
      placeholders: ["input"],
      ad_hoc_fields: [{ key: "input", label: "Input" }],
    });
    expect(screen.queryByTestId("input-empty-warning")).not.toBeInTheDocument();
    expect(screen.queryByTestId("input-tab-warning")).not.toBeInTheDocument();
  });

  it("detects placeholders, syncs labels, and previews with sample values", async () => {
    seed("");
    useDesignerStore.getState().setSelection({ kind: "input" });
    renderInspector();
    const template = await screen.findByLabelText("Template");

    // `{` is a userEvent key-descriptor character, so set the value directly.
    fireEvent.change(template, {
      target: { value: "Classify {{ requirement }} for {{stakeholder}}" },
    });
    expect(spec().placeholders).toEqual(["requirement", "stakeholder"]);
    expect(useDesignerStore.getState().dirty).toBe(true);

    const rows = within(screen.getByTestId("input-placeholders"));
    expect(rows.getByLabelText("Label for requirement")).toHaveValue("requirement");
    fireEvent.change(rows.getByLabelText("Label for requirement"), {
      target: { value: "Requirement text" },
    });
    expect(spec().ad_hoc_fields).toEqual([
      { key: "requirement", label: "Requirement text" },
      { key: "stakeholder", label: "stakeholder" },
    ]);

    // Unfilled samples stay visible as their tag.
    expect(screen.getByTestId("input-preview")).toHaveTextContent(
      "Task: Classify {{ requirement }} for {{stakeholder}}",
    );
    fireEvent.change(screen.getByLabelText("Sample value for requirement"), {
      target: { value: "The app shall be fast" },
    });
    expect(screen.getByTestId("input-preview")).toHaveTextContent(
      "Task: Classify The app shall be fast for {{stakeholder}}",
    );

    // Removing a placeholder drops its label.
    fireEvent.change(template, { target: { value: "Classify {{stakeholder}}" } });
    expect(spec().ad_hoc_fields).toEqual([{ key: "stakeholder", label: "stakeholder" }]);
    await waitFor(() =>
      expect(screen.queryByLabelText("Label for requirement")).not.toBeInTheDocument(),
    );
  });

  it("notes a fixed task when the template has no placeholders", async () => {
    seed("Debate whether remote work is better.");
    useDesignerStore.getState().setSelection({ kind: "input" });
    renderInspector();
    expect(await screen.findByTestId("input-static-note")).toBeInTheDocument();
    expect(screen.queryByTestId("input-empty-warning")).not.toBeInTheDocument();
  });
});
