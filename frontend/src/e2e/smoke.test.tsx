import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  MemoryRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ConfigDetail,
  ConfigSummary,
  ExecutionDetail,
  JsonObject,
} from "@/api";
import { TaxonomyProvider } from "@/taxonomy/TaxonomyContext";
import { SAMPLE_TAXONOMY } from "@/features/designer/panels/testFixtures";

import { ConfigurationsPage } from "@/features/configs/ConfigurationsPage";
import { DesignerPage } from "@/features/designer/DesignerPage";
import { RunLauncherPage } from "@/features/executions/RunLauncherPage";
import { ExecutionsPage } from "@/features/executions/ExecutionsPage";
import { ExecutionDetailPage } from "@/features/executions/ExecutionDetailPage";

/**
 * Smoke end-to-end test (task 8.8) exercising the full product loop —
 * create → save → run → inspect — against a single in-memory fetch stub that
 * emulates the backend. No real network and no real provider: the "run" uses a
 * mock/local provider at the stub level, so the execution the stub returns is
 * already completed with a transcript and a final decision (mirroring the
 * ExecutionsPage fixtures).
 *
 * The real page components are composed across their real route paths under a
 * single MemoryRouter + shared QueryClient + the TaxonomyProvider, driven by a
 * single fetch mock that routes by method + URL (the same stubbing style the
 * per-page tests use). jsdom has no EventSource, so the live-progress SSE hooks
 * no-op and the flow stays deterministic and offline.
 */

/* ----------------------------- in-memory backend ------------------------- */

/**
 * A tiny stateful backend. It holds a configs table keyed by id and records the
 * launched execution so the inspect step can read back a completed run. State
 * flows across the whole loop: the PUT in the save step mutates the same config
 * the run step later reads.
 */
interface BackendState {
  nextConfigId: number;
  configs: Map<number, ConfigDetail>;
  lastExecution: ExecutionDetail | null;
  /** Captured request log for assertions (method + url + parsed body). */
  requests: { method: string; url: string; body: unknown }[];
}

const DEFAULT_ARTIFACT: JsonObject = {
  name: "New configuration",
  participants: {
    nodes: [
      { id: "a", label: "Debater A", roles: ["debater"] },
      { id: "b", label: "Debater B", roles: ["debater"] },
    ],
  },
  interaction: {
    topology: { structure: "fully_connected", edges: [] },
    protocol: { mechanism: "sequential", max_rounds: 1, ordering: "fixed" },
  },
  agreement: { authority: "collective", resolution: "majority_vote" },
  input_spec: {
    template: "Classify: {{requirement}}",
    placeholders: ["requirement"],
    ad_hoc_fields: [{ key: "requirement", label: "Requirement text" }],
  },
};

function summaryFromDetail(detail: ConfigDetail): ConfigSummary {
  const artifact = detail.artifact as Record<string, unknown>;
  const participants = (artifact.participants ?? {}) as Record<string, unknown>;
  const nodes = Array.isArray(participants.nodes) ? participants.nodes : [];
  return {
    id: detail.id,
    name: detail.name,
    description: detail.description,
    schema_version: detail.schema_version,
    created_at: detail.created_at,
    updated_at: detail.updated_at,
    is_builtin: detail.is_builtin,
    attributes: {
      participant_count: nodes.length,
      topology_structure: "fully_connected",
      topology_pattern: null,
      protocol_mechanism: "sequential",
      authority: "collective",
      resolution: "majority_vote",
      under_development: false,
    },
  };
}

/** A completed execution carrying a transcript + a final decision (inspect). */
function completedExecution(
  id: number,
  config: ConfigDetail,
  resolvedInput: string,
): ExecutionDetail {
  return {
    id,
    config_id: config.id,
    config_name: config.name,
    input_mode: "single",
    status: "completed",
    progress: 1,
    instance_count: 1,
    completed_count: 1,
    error_count: 0,
    metrics: null,
    created_at: "2024-01-01T12:00:00Z",
    updated_at: "2024-01-01T12:00:05Z",
    config_snapshot: config.artifact,
    input_ref: {},
    instances: [
      {
        instance_index: 0,
        resolved_input: { resolved_input: resolvedInput },
        transcript: {
          config_id: config.id,
          config_name: config.name,
          resolved_input: resolvedInput,
          rounds: 1,
          messages: [
            {
              node_id: "debater_a",
              round_index: 0,
              role: "debater",
              content: "I argue this is a non-functional requirement.",
              usage: {
                prompt_tokens: 10,
                completion_tokens: 8,
                total_tokens: 18,
                cost_usd: null,
                latency_s: null,
              },
              metadata: {},
              structured: null,
            },
            {
              node_id: "debater_b",
              round_index: 0,
              role: "debater",
              content: "I concur — it is non-functional.",
              usage: {
                prompt_tokens: 12,
                completion_tokens: 6,
                total_tokens: 18,
                cost_usd: null,
                latency_s: null,
              },
              metadata: {},
              structured: null,
            },
          ],
          usage: {
            prompt_tokens: 22,
            completion_tokens: 14,
            total_tokens: 36,
            cost_usd: null,
            latency_s: null,
          },
          decision: {
            decision: "NFR",
            authority: "collective",
            resolution: "majority_vote",
            detail: null,
            structured: null,
            undecided: false,
          },
          errors: [],
          notes: [],
        },
        final_decision: { decision: "NFR" },
        ground_truth: null,
        metrics: null,
        error: null,
      },
    ],
  };
}

function installBackend(): BackendState {
  const state: BackendState = {
    nextConfigId: 1,
    configs: new Map(),
    lastExecution: null,
    requests: [],
  };

  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      const isForm =
        typeof FormData !== "undefined" && init?.body instanceof FormData;
      const body =
        init?.body && !isForm ? JSON.parse(String(init.body)) : undefined;
      state.requests.push({ method, url, body });

      const json = (payload: unknown, status = 200) =>
        new Response(JSON.stringify(payload), {
          status,
          headers: { "content-type": "application/json" },
        });

      // --- taxonomy + providers (read-once context / designer bindings) ---
      if (url.endsWith("/taxonomy")) return json(SAMPLE_TAXONOMY);
      if (url.endsWith("/providers") && method === "GET") return json([]);

      // --- configs ---
      if (url.endsWith("/configs") && method === "GET") {
        return json([...state.configs.values()].map(summaryFromDetail));
      }
      if (url.endsWith("/configs") && method === "POST") {
        const id = state.nextConfigId++;
        const detail: ConfigDetail = {
          id,
          name: (body?.name as string) ?? "New configuration",
          description: (body?.description as string) ?? null,
          schema_version: "1.0",
          created_at: null,
          updated_at: null,
          is_builtin: false,
          artifact: (body?.artifact as JsonObject) ?? {
            ...DEFAULT_ARTIFACT,
            name: (body?.name as string) ?? "New configuration",
          },
          under_development: [],
        };
        state.configs.set(id, detail);
        return json(detail);
      }
      const idMatch = /\/configs\/(\d+)$/.exec(url);
      if (idMatch && method === "GET") {
        const detail = state.configs.get(Number(idMatch[1]));
        return detail
          ? json(detail)
          : json({ detail: "not found" }, 404);
      }
      if (idMatch && method === "PUT") {
        const id = Number(idMatch[1]);
        const prev = state.configs.get(id)!;
        const updated: ConfigDetail = {
          ...prev,
          ...(body?.name ? { name: body.name as string } : {}),
          artifact: (body?.artifact as JsonObject) ?? prev.artifact,
        };
        state.configs.set(id, updated);
        return json(updated);
      }
      if (url.endsWith("/configs/validate") && method === "POST") {
        return json({ valid: true, errors: [], under_development: [] });
      }

      // --- executions (the "run" uses the mock provider at the stub level) ---
      if (url.endsWith("/executions") && method === "POST") {
        const configId = body?.config_id as number;
        const config = state.configs.get(configId)!;
        const input = (body?.input ?? {}) as Record<string, unknown>;
        const resolved = `Classify: ${String(input.requirement ?? "")}`;
        const execution = completedExecution(99, config, resolved);
        state.lastExecution = execution;
        // POST returns the summary shape; the detail is fetched on inspect.
        const { config_snapshot, input_ref, instances, ...summary } =
          execution;
        void config_snapshot;
        void input_ref;
        void instances;
        return json(summary);
      }
      if (url.endsWith("/executions") && method === "GET") {
        if (!state.lastExecution) return json([]);
        const { config_snapshot, input_ref, instances, ...summary } =
          state.lastExecution;
        void config_snapshot;
        void input_ref;
        void instances;
        return json([summary]);
      }
      const execMatch = /\/executions\/(\d+)$/.exec(url);
      if (execMatch && method === "GET") {
        return state.lastExecution
          ? json(state.lastExecution)
          : json({ detail: "not found" }, 404);
      }

      return json({ detail: `unhandled ${method} ${url}` }, 500);
    },
  );

  vi.stubGlobal("fetch", fetchMock);
  return state;
}

/* ------------------------------- test harness ---------------------------- */

/**
 * Compose the real pages across their real route paths. The Configurations
 * list, the designer (`/designer/:configId`), the Run launcher (`/run`), and
 * the executions history + detail (`/executions`, `/executions/:executionId`)
 * are all wired so navigation between them is driven by the pages themselves —
 * the same way the production router (App.tsx) wires them.
 */
function renderApp(initialPath = "/configs") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TaxonomyProvider fallback={<div>loading-taxonomy</div>}>
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route path="/" element={<Navigate to="/configs" replace />} />
            <Route path="/configs" element={<ConfigurationsPage />} />
            <Route path="/designer/:configId" element={<DesignerPage />} />
            <Route path="/run" element={<RunLauncherPage />} />
            <Route path="/executions" element={<ExecutionsPage />} />
            <Route
              path="/executions/:executionId"
              element={<ExecutionDetailPage />}
            />
          </Routes>
        </MemoryRouter>
      </TaxonomyProvider>
    </QueryClientProvider>,
  );
}

/* --------------------------------- test ---------------------------------- */

describe("smoke e2e: create → save → run → inspect", () => {
  beforeEach(() => {
    // jsdom lacks createObjectURL (used by config export menus on the page).
    Object.defineProperty(URL, "createObjectURL", {
      value: vi.fn(() => "blob:mock"),
      writable: true,
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("runs the full loop against a single mocked backend", async () => {
    const backend = installBackend();
    const user = userEvent.setup();
    renderApp("/configs");

    /* --- 1. CREATE: a new configuration from the list --- */
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /New configuration/i }),
      ).toBeInTheDocument(),
    );
    await user.click(
      screen.getByRole("button", { name: /New configuration/i }),
    );

    // Creating posts to /configs and navigates into the designer.
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Add participant/i }),
      ).toBeInTheDocument(),
    );
    const created = backend.requests.find(
      (r) => r.method === "POST" && r.url.endsWith("/configs"),
    );
    expect(created).toBeTruthy();
    expect(backend.configs.size).toBe(1);
    const configId = [...backend.configs.keys()][0];

    /* --- 2. SAVE: edit on the canvas, then persist --- */
    // Add a participant (canvas → artifact), which marks the designer dirty.
    const nodesBefore =
      (backend.configs.get(configId)!.artifact as any).participants.nodes
        .length;
    await user.click(
      screen.getByRole("button", { name: /Add participant/i }),
    );

    // Save is enabled once there are unsaved changes; click it.
    const saveBtn = screen.getByRole("button", { name: /^Save$/i });
    await waitFor(() => expect(saveBtn).toBeEnabled());
    await user.click(saveBtn);

    // Save validates then PUTs the artifact; the backend state reflects the edit.
    await waitFor(() => {
      const put = backend.requests.find(
        (r) => r.method === "PUT" && /\/configs\/\d+$/.test(r.url),
      );
      expect(put).toBeTruthy();
    });
    const savedNodes = (
      backend.configs.get(configId)!.artifact as any
    ).participants.nodes.length;
    expect(savedNodes).toBe(nodesBefore + 1);

    /* --- 3. RUN: launch the config in single-input mode --- */
    renderApp("/run");

    // Pick the just-created configuration.
    await waitFor(() =>
      expect(screen.getByLabelText("Configuration")).toBeInTheDocument(),
    );
    await user.selectOptions(
      screen.getByLabelText("Configuration"),
      String(configId),
    );

    // Fill the single-input field derived from the config's template.
    const field = await screen.findByLabelText(/Requirement text/i);
    await user.type(field, "The system shall respond within 100 ms");

    const launch = screen.getByRole("button", { name: /Launch/i });
    await waitFor(() => expect(launch).toBeEnabled());
    await user.click(launch);

    // Launch posts to /executions with the single-input body.
    await waitFor(() => {
      const post = backend.requests.find(
        (r) => r.method === "POST" && r.url.endsWith("/executions"),
      );
      expect(post).toBeTruthy();
      expect(post!.body).toEqual({
        config_id: configId,
        input: { requirement: "The system shall respond within 100 ms" },
      });
    });
    expect(backend.lastExecution).not.toBeNull();

    /* --- 4. INSPECT: open the completed execution's detail --- */
    renderApp(`/executions/${backend.lastExecution!.id}`);

    // The transcript renders (round + both debater messages)…
    await waitFor(() =>
      expect(screen.getByText(/Round 1/i)).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/non-functional requirement/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/I concur/i)).toBeInTheDocument();

    // …and the final decision is surfaced in the agreement-coloured block.
    expect(screen.getByText(/Final decision/i)).toBeInTheDocument();
    const decision = screen.getByTestId("final-decision");
    expect(within(decision).getByText("NFR")).toBeInTheDocument();

    // The resolved input the run was launched with is shown (inspect closes
    // the loop back to the launcher input). It appears both in the instance
    // preview and the resolved-input block, so assert at least one match.
    expect(
      screen.getAllByText(/The system shall respond within 100 ms/i).length,
    ).toBeGreaterThan(0);
  });
});
