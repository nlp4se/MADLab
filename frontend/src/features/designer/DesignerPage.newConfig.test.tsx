import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TaxonomyProvider } from "@/taxonomy/TaxonomyContext";
import { blankArtifact, NEW_CONFIG_NAME } from "./artifact";
import { useAssistantChatStore } from "./assistantChatStore";
import { DesignerPage } from "./DesignerPage";
import { useDesignerStore } from "./designerStore";
import { STARTER_INPUT_SPEC } from "./inputEditor";
import { SAMPLE_PROVIDERS, SAMPLE_TAXONOMY } from "./panels/testFixtures";
import { LEAVE_DESIGNER_MESSAGE } from "./UnsavedChangesGuard";

/**
 * Task 11.15: `/designer` (the sidebar's Designer link) opens a new, unsaved
 * configuration; the first Save POSTs it and switches the URL to its id
 * (keeping the canvas, its layout, and the assistant chat); leaving with
 * unsaved changes asks first. Uses a data router (as the app does) so the
 * navigation blocker is active.
 */

const EXISTING = {
  name: "Existing config",
  description: "",
  participants: {
    nodes: [{ id: "participant-1", label: "Participant 1", roles: ["debater"] }],
  },
  interaction: { topology: { structure: "fully_connected", edges: [] } },
  agreement: { authority: "collective", resolution: "majority_vote" },
  input_spec: { ...STARTER_INPUT_SPEC },
};

function detail(id: number, artifact: Record<string, unknown>) {
  return {
    id,
    name: artifact.name,
    description: null,
    schema_version: "1.0",
    created_at: null,
    updated_at: null,
    is_builtin: false,
    artifact,
    under_development: [],
  };
}

function installBackend() {
  const calls: Array<{ method: string; url: string; body?: Record<string, any> }> = [];
  let created: Record<string, unknown> | null = null;
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
      if (url.includes("/taxonomy")) return json(SAMPLE_TAXONOMY);
      if (url.includes("/providers")) return json(SAMPLE_PROVIDERS);
      if (url.endsWith("/configs/validate")) {
        return json({ valid: true, errors: [], under_development: [] });
      }
      calls.push({ method, url, body });
      if (url.endsWith("/configs") && method === "POST") {
        const artifact: Record<string, unknown> = { ...body!.artifact, id: "uuid-21" };
        created = artifact;
        return json(detail(21, artifact));
      }
      if (url.endsWith("/configs/21") && created) return json(detail(21, created));
      if (url.endsWith("/configs/8") && method === "PUT") return json(detail(8, body!.artifact));
      if (url.endsWith("/configs/8")) return json(detail(8, EXISTING));
      return json([]);
    }),
  );
  return calls;
}

function renderApp(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/designer/:configId?", element: <DesignerPage /> },
      { path: "/configs", element: <div>Configurations list</div> },
    ],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={client}>
      <TaxonomyProvider fallback={<div>loading</div>}>
        <RouterProvider router={router} />
      </TaxonomyProvider>
    </QueryClientProvider>,
  );
  return router;
}

const saveButton = () => screen.getByRole("button", { name: /^Save$/ });

/**
 * Data-router navigations build a `Request` with an AbortSignal; under jsdom
 * the signal comes from jsdom while `Request` is Node's, which rejects it.
 * Drop the signal (no loaders/actions here, so nothing aborts).
 */
const NodeRequest = globalThis.Request;
class JsdomSafeRequest extends NodeRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    const { signal: _signal, ...rest } = init ?? {};
    void _signal;
    super(input, rest);
  }
}

describe("blankArtifact (task 11.15)", () => {
  it("matches the backend blank create: name, starter input, no participants, no id", () => {
    const a = blankArtifact();
    expect(a.name).toBe(NEW_CONFIG_NAME);
    expect(a.name).toBe("New configuration");
    expect(a.input_spec).toEqual({
      template: "{{input}}",
      placeholders: ["input"],
      ad_hoc_fields: [{ key: "input", label: "Input" }],
    });
    expect(a.participants.nodes).toEqual([]);
    expect(a.interaction.topology.edges).toEqual([]);
    expect(a.agreement).toMatchObject({ authority: "collective", resolution: "majority_vote" });
    expect(a.id).toBeUndefined();
    expect(a.ui).toBeNull();
    // Fresh copies: editing one never leaks into the next.
    a.input_spec!.placeholders!.push("other");
    expect(blankArtifact().input_spec!.placeholders).toEqual(["input"]);
  });
});

describe("DesignerPage — new configuration (task 11.15)", () => {
  beforeEach(() => {
    useDesignerStore.setState({
      configId: null,
      artifact: null,
      layout: {},
      edgeBends: {},
      selection: null,
      dirty: false,
      validationErrors: [],
      draftKey: null,
    });
    useAssistantChatStore.getState().resetAll();
    vi.stubGlobal("Request", JsdomSafeRequest);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("opens a blank, dirty draft at /designer; first Save POSTs then routes to /designer/<id>", async () => {
    const calls = installBackend();
    const user = userEvent.setup();
    const router = renderApp("/designer");

    expect(await screen.findByRole("button", { name: /New configuration/ })).toBeInTheDocument();
    expect(screen.getByTestId("designer-not-saved")).toBeInTheDocument();
    const state = useDesignerStore.getState();
    expect(state.configId).toBeNull();
    expect(state.dirty).toBe(true);
    expect(state.draftKey).toMatch(/^unsaved:/);
    expect(state.artifact!.input_spec!.template).toBe("{{input}}");
    expect(saveButton()).toBeEnabled();

    // Edit: add a participant, and start an assistant conversation.
    await user.click(screen.getByRole("button", { name: /Add participant/ }));
    expect(useDesignerStore.getState().artifact!.participants.nodes).toHaveLength(1);
    const draftKey = useDesignerStore.getState().draftKey!;
    useAssistantChatStore.getState().patchSession(draftKey, { draft: "make it a chain" });
    const layoutBefore = { ...useDesignerStore.getState().layout };
    const canvasBefore = screen.getByTestId("designer-canvas");

    await user.click(saveButton());

    await waitFor(() => expect(router.state.location.pathname).toBe("/designer/21"));
    expect(router.state.historyAction).toBe("REPLACE");

    // One POST with the full artifact (starter input + the canvas layout); no PUT.
    const posts = calls.filter((c) => c.method === "POST");
    expect(posts).toHaveLength(1);
    expect(posts[0].url).toMatch(/\/configs$/);
    const sent = posts[0].body!.artifact as Record<string, any>;
    expect(sent.name).toBe("New configuration");
    expect(sent.input_spec.template).toBe("{{input}}");
    expect(sent.participants.nodes).toHaveLength(1);
    expect(sent.ui.nodes["participant-1"]).toEqual(layoutBefore["participant-1"]);
    expect(calls.some((c) => c.method === "PUT")).toBe(false);

    // The store now holds the created config, saved, with the same layout.
    await waitFor(() => expect(useDesignerStore.getState().draftKey).toBeNull());
    const after = useDesignerStore.getState();
    expect(after.configId).toBe(21);
    expect(after.dirty).toBe(false);
    expect(after.layout["participant-1"]).toEqual(layoutBefore["participant-1"]);
    expect(saveButton()).toBeDisabled();
    expect(screen.queryByTestId("designer-not-saved")).not.toBeInTheDocument();
    // The canvas stayed mounted across the URL switch.
    expect(screen.getByTestId("designer-canvas")).toBe(canvasBefore);

    // The draft's assistant chat moved to the new id.
    const sessions = useAssistantChatStore.getState().sessions;
    expect(sessions["21"]?.draft).toBe("make it a chain");
    expect(sessions[draftKey]).toBeUndefined();

    // Later saves update it (PUT), and navigating away is no longer guarded.
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await act(() => router.navigate("/configs"));
    expect(router.state.location.pathname).toBe("/configs");
    expect(confirm).not.toHaveBeenCalled();
  });

  it("asks before leaving a new config: cancel keeps you, confirm leaves", async () => {
    installBackend();
    const router = renderApp("/designer");
    await screen.findByRole("button", { name: /New configuration/ });
    // Let the blocker finish registering (useBlocker sets its key in an effect).
    await act(async () => {});

    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    await act(() => router.navigate("/configs"));
    expect(confirm).toHaveBeenCalledWith(LEAVE_DESIGNER_MESSAGE);
    expect(router.state.location.pathname).toBe("/designer");
    expect(screen.getByTestId("designer-canvas")).toBeInTheDocument();

    confirm.mockReturnValueOnce(true);
    await act(() => router.navigate("/configs"));
    await waitFor(() => expect(router.state.location.pathname).toBe("/configs"));
    expect(await screen.findByText("Configurations list")).toBeInTheDocument();
    expect(confirm).toHaveBeenCalledTimes(2);
  });

  it("guards an existing config only while it has unsaved changes (incl. tab close)", async () => {
    installBackend();
    const user = userEvent.setup();
    const router = renderApp("/designer/8");
    await screen.findByRole("button", { name: /Existing config/ });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);

    // Clean: no beforeunload prompt.
    const clean = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);

    // Dirty: the tab-close prompt and the in-app confirmation both kick in.
    await user.click(screen.getByRole("button", { name: /Add participant/ }));
    const dirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);

    await act(() => router.navigate("/configs"));
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(router.state.location.pathname).toBe("/designer/8");

    // Query-string-only changes (e.g. ?panel=input) are not blocked.
    await act(() => router.navigate("/designer/8?panel=input"));
    expect(router.state.location.search).toBe("?panel=input");
    expect(confirm).toHaveBeenCalledTimes(1);

    confirm.mockReturnValue(true);
    await act(() => router.navigate("/configs"));
    await waitFor(() => expect(router.state.location.pathname).toBe("/configs"));
  });
});
