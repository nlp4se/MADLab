import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TaxonomyProvider } from "@/taxonomy/TaxonomyContext";
import { DesignerPage } from "./DesignerPage";
import { useDesignerStore } from "./designerStore";
import { SAMPLE_PROVIDERS, SAMPLE_TAXONOMY } from "./panels/testFixtures";

/**
 * Task 11.10 on the real designer page: the inline-editable name (validation,
 * dirty, saved with Save), the Start node opening the Input panel, its
 * empty-template marker, and the Run view's `?panel=input` deep link.
 */

const ARTIFACT = {
  name: "New configuration",
  description: "",
  participants: {
    nodes: [
      { id: "participant-1", label: "Participant 1", roles: ["debater"] },
      { id: "participant-2", label: "Participant 2", roles: ["debater"] },
    ],
  },
  interaction: { topology: { structure: "fully_connected", edges: [] } },
  agreement: { authority: "collective", resolution: "majority_vote" },
  input_spec: { template: "", placeholders: [], ad_hoc_fields: [] },
};

function installBackend() {
  const puts: Array<Record<string, unknown>> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      const json = (payload: unknown) =>
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      const detail = (artifact: Record<string, unknown>) => ({
        id: 8,
        name: artifact.name,
        description: artifact.description || null,
        schema_version: "1.0",
        created_at: null,
        updated_at: null,
        is_builtin: false,
        artifact,
        under_development: [],
      });
      if (url.includes("/taxonomy")) return json(SAMPLE_TAXONOMY);
      if (url.includes("/providers")) return json(SAMPLE_PROVIDERS);
      if (url.endsWith("/configs/validate")) return json({ valid: true, errors: [], under_development: [] });
      if (url.endsWith("/configs/8") && method === "PUT") {
        puts.push(body);
        return json(detail(body.artifact));
      }
      if (url.endsWith("/configs/8")) return json(detail(ARTIFACT));
      return json([]);
    }),
  );
  return puts;
}

function renderDesigner(path = "/designer/8") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TaxonomyProvider fallback={<div>loading</div>}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/designer/:configId" element={<DesignerPage />} />
          </Routes>
        </MemoryRouter>
      </TaxonomyProvider>
    </QueryClientProvider>,
  );
}

describe("DesignerPage — name and input (task 11.10)", () => {
  beforeEach(() => {
    useDesignerStore.setState({
      configId: null,
      artifact: null,
      layout: {},
      edgeBends: {},
      selection: null,
      dirty: false,
      validationErrors: [],
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("edits the name inline (empty rejected, Escape cancels) and saves it", async () => {
    const puts = installBackend();
    const user = userEvent.setup();
    renderDesigner();

    const title = await screen.findByRole("button", { name: /New configuration/ });
    await user.click(title);
    const input = screen.getByRole("textbox", { name: "Configuration name" });

    // Empty name: rejected inline, nothing changes.
    await user.clear(input);
    await user.keyboard("{Enter}");
    expect(screen.getByText("The name can't be empty.")).toHaveAttribute("role", "alert");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(useDesignerStore.getState().artifact!.name).toBe("New configuration");
    expect(useDesignerStore.getState().dirty).toBe(false);

    // Escape cancels the edit.
    await user.type(input, "Discarded");
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: /New configuration/ })).toBeInTheDocument();
    expect(useDesignerStore.getState().dirty).toBe(false);

    // Enter commits and marks dirty; Save PUTs the renamed artifact.
    await user.click(screen.getByRole("button", { name: /New configuration/ }));
    const again = screen.getByRole("textbox", { name: "Configuration name" });
    await user.clear(again);
    await user.type(again, "NFR debate{Enter}");
    expect(screen.getByRole("button", { name: /NFR debate/ })).toBeInTheDocument();
    expect(useDesignerStore.getState().dirty).toBe(true);

    // Description: blur commits.
    await user.click(screen.getByRole("button", { name: /Add a description/ }));
    await user.type(
      screen.getByRole("textbox", { name: "Configuration description" }),
      "Two debaters",
    );
    await user.tab();
    expect(screen.getByRole("button", { name: /Two debaters/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Save$/ }));
    await waitFor(() => expect(puts).toHaveLength(1));
    const saved = puts[0].artifact as Record<string, unknown>;
    expect(saved.name).toBe("NFR debate");
    expect(saved.description).toBe("Two debaters");
  });

  it("clicking the Start node opens the Input panel; Start flags the empty template", async () => {
    installBackend();
    renderDesigner();

    const start = await screen.findByTestId("start-node");
    expect(screen.getByTestId("start-node-input-missing")).toBeInTheDocument();
    // A plain click: user-event's mousedown has no `view`, which React Flow's
    // drag handler (d3-drag) dereferences in jsdom.
    fireEvent.click(start);

    await screen.findByTestId("input-panel");
    expect(useDesignerStore.getState().selection).toEqual({ kind: "input" });
    // The Start selection cannot be deleted from the toolbar.
    expect(screen.getByRole("button", { name: /^Delete$/ })).toBeDisabled();
  });

  it("?panel=input (the Run view's link) opens the Input panel", async () => {
    installBackend();
    renderDesigner("/designer/8?panel=input");
    expect(await screen.findByTestId("input-panel")).toBeInTheDocument();
    expect(screen.getByTestId("input-empty-warning")).toBeInTheDocument();
  });
});
