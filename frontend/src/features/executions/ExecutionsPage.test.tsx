import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  ExecutionDetail,
  ExecutionInstanceResult,
  ExecutionSummary,
} from "@/api";

import { ExecutionsPage } from "./ExecutionsPage";
import { ExecutionDetailPage } from "./ExecutionDetailPage";

/* ------------------------------- fixtures -------------------------------- */

function makeSummary(
  overrides: Partial<ExecutionSummary> = {},
): ExecutionSummary {
  return {
    id: 42,
    config_id: 1,
    config_name: "RE binary debate",
    input_mode: "batch",
    status: "completed",
    progress: 1,
    instance_count: 3,
    completed_count: 3,
    error_count: 0,
    metrics: {
      overall: { accuracy: 0.6667 },
      per_class: {
        F: { precision: 0.5, recall: 1.0, "f1-score": 0.6667, support: 1 },
        NFR: { precision: 1.0, recall: 0.5, "f1-score": 0.6667, support: 2 },
      },
    },
    created_at: "2024-01-01T12:00:00Z",
    updated_at: "2024-01-01T12:05:00Z",
    started_at: "2024-01-01T12:00:01+00:00",
    finished_at: "2024-01-01T12:02:06+00:00",
    summary: {
      wall_time_s: 125.4,
      model_time_s: 98.76,
      input_tokens: 12345,
      output_tokens: 678,
      total_tokens: 13023,
      cost_usd: 0.0123,
      calls: 9,
      instances: { total: 3, completed: 3, failed: 0 },
    },
    ...overrides,
  };
}

function makeInstance(
  overrides: Partial<ExecutionInstanceResult> = {},
): ExecutionInstanceResult {
  return {
    instance_index: 0,
    resolved_input: { resolved_input: "Classify: The system shall be fast" },
    transcript: {
      config_id: 1,
      config_name: "RE binary debate",
      resolved_input: "Classify: The system shall be fast",
      rounds: 1,
      messages: [
        {
          node_id: "debater_a",
          round_index: 0,
          role: "debater",
          content: "I argue this is a performance requirement.",
          usage: {
            prompt_tokens: 10,
            completion_tokens: 8,
            total_tokens: 18,
            cost_usd: 0.0001,
            latency_s: 0.5,
          },
          metadata: {},
          structured: null,
        },
        {
          node_id: "judge_1",
          round_index: 0,
          role: "judge",
          content: "The verdict is NFR.",
          usage: {
            prompt_tokens: 20,
            completion_tokens: 4,
            total_tokens: 24,
            cost_usd: null,
            latency_s: null,
          },
          metadata: {},
          structured: null,
        },
      ],
      usage: {
        prompt_tokens: 30,
        completion_tokens: 12,
        total_tokens: 42,
        cost_usd: 0.0001,
        latency_s: 1.0,
      },
      decision: {
        decision: "NFR",
        authority: "judge_based",
        resolution: "argument_evaluation",
        detail: null,
        structured: null,
        undecided: false,
      },
      errors: [],
      notes: [],
    },
    final_decision: { decision: "NFR" },
    ground_truth: "NFR",
    metrics: { correct: true },
    error: null,
    usage: {
      input_tokens: 30,
      output_tokens: 12,
      total_tokens: 42,
      cost_usd: 0.0001,
      model_time_s: 1.0,
      calls: 2,
    },
    duration_s: 1.42,
    ...overrides,
  };
}

function makeDetail(overrides: Partial<ExecutionDetail> = {}): ExecutionDetail {
  return {
    ...makeSummary(),
    config_snapshot: {
      name: "RE binary debate",
      participants: { nodes: [{ id: "debater_a" }, { id: "judge_1" }] },
      interaction: {
        topology: { structure: "star", pattern: "star" },
        protocol: { mechanism: "sequential" },
      },
      agreement: { authority: "judge_based", resolution: "argument_evaluation" },
    },
    input_ref: {},
    instances: [makeInstance()],
    ...overrides,
  };
}

/* ------------------------------ fetch stub ------------------------------- */

function installFetch(
  options: {
    executions?: ExecutionSummary[];
    detail?: ExecutionDetail;
    onRequest?: (method: string, url: string) => void;
  } = {},
) {
  const executions = options.executions ?? [makeSummary()];
  const detail = options.detail ?? makeDetail();

  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      options.onRequest?.(method, url);

      const json = (payload: unknown, status = 200) =>
        new Response(JSON.stringify(payload), {
          status,
          headers: { "content-type": "application/json" },
        });

      if (url.endsWith("/executions") && method === "GET")
        return json(executions);
      if (/\/executions\/\d+$/.test(url) && method === "GET")
        return json(detail);
      if (/\/executions\/\d+$/.test(url) && method === "DELETE")
        return json({ id: detail.id, deleted: true });
      return json({ detail: `unhandled ${method} ${url}` }, 500);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/executions"]}>
        <Routes>
          <Route path="/executions" element={<ExecutionsPage />} />
          <Route
            path="/executions/:executionId"
            element={<ExecutionDetailPage />}
          />
          <Route path="/run" element={<div>Run page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderDetail(id = 42) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/executions/${id}`]}>
        <Routes>
          <Route
            path="/executions/:executionId"
            element={<ExecutionDetailPage />}
          />
          <Route path="/executions" element={<div>History list</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/* --------------------------------- tests --------------------------------- */

describe("ExecutionsPage (history list)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders each run with status and summary metrics (Req 11.1)", async () => {
    installFetch({ executions: [makeSummary()] });
    renderList();

    await waitFor(() =>
      expect(screen.getByText("RE binary debate")).toBeInTheDocument(),
    );

    // Status badge + counts.
    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByText(/3 completed/i)).toBeInTheDocument();

    // Aggregate accuracy metric from aggregateMetrics.
    expect(screen.getByText("66.7%")).toBeInTheDocument();
    // A live progress bar is present.
    expect(screen.getByLabelText(/Progress for/i)).toBeInTheDocument();
  });

  it("shows each run's wall time and in/out tokens (task 11.18)", async () => {
    installFetch({
      executions: [
        makeSummary(),
        // An old run: no timestamps -> no wall time; tokens from transcripts.
        makeSummary({
          id: 7,
          config_name: "Old run",
          started_at: null,
          finished_at: null,
          summary: {
            ...makeSummary().summary!,
            wall_time_s: null,
            input_tokens: 3000,
            output_tokens: 12,
          },
        }),
      ],
    });
    renderList();

    await waitFor(() =>
      expect(screen.getAllByTestId("execution-wall-time")).toHaveLength(2),
    );
    const [recent, old] = screen.getAllByTestId("execution-wall-time");
    expect(recent).toHaveTextContent("2 min 05 s");
    expect(old).toHaveTextContent("—");
    const [recentTokens, oldTokens] = screen.getAllByTestId("execution-tokens");
    expect(recentTokens).toHaveTextContent("12,345 in · 678 out tokens");
    expect(oldTokens).toHaveTextContent("3,000 in · 12 out tokens");
  });

  it("shows an empty state when there are no runs", async () => {
    installFetch({ executions: [] });
    renderList();

    await waitFor(() =>
      expect(screen.getByText(/No executions yet/i)).toBeInTheDocument(),
    );
  });

  it("navigates to the detail view on row click", async () => {
    installFetch();
    const user = userEvent.setup();
    renderList();

    await waitFor(() =>
      expect(screen.getByText("RE binary debate")).toBeInTheDocument(),
    );

    // The row title button opens the detail route.
    await user.click(
      screen.getAllByRole("button", { name: /RE binary debate/i })[0],
    );

    await waitFor(() =>
      expect(
        screen.getByText("Configuration snapshot"),
      ).toBeInTheDocument(),
    );
  });
});

describe("ExecutionDetailPage (transcript viewer)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders a colour-coded transcript with the final decision (Req 11.2, 13.3)", async () => {
    installFetch();
    renderDetail();

    // Transcript round + both agents' messages render.
    await waitFor(() =>
      expect(screen.getByText(/Round 1/i)).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/performance requirement/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/The verdict is NFR/i)).toBeInTheDocument();

    // Messages are colour-coded by role → dimension (debater = participants,
    // judge = agreement).
    const debater = document.querySelector('[data-role="debater"]');
    const judge = document.querySelector('[data-role="judge"]');
    expect(debater).toHaveAttribute("data-dimension", "participants");
    expect(judge).toHaveAttribute("data-dimension", "agreement");

    // The final decision block is present with the verdict.
    expect(screen.getByText(/Final decision/i)).toBeInTheDocument();
    const decision = screen.getByTestId("final-decision");
    expect(decision).toHaveAttribute("data-dimension", "agreement");
    expect(within(decision).getByText("NFR")).toBeInTheDocument();

    // Per-class metrics table (Req 11.5).
    expect(screen.getByText("Evaluation metrics")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /Precision/i })).toBeInTheDocument();
  });

  it("shows the run summary bar and per-instance figures (task 11.18)", async () => {
    installFetch();
    renderDetail();

    const bar = await screen.findByTestId("run-summary");
    expect(within(bar).getByText("Wall time")).toBeInTheDocument();
    expect(screen.getByTestId("run-summary-wall-time")).toHaveTextContent("2 min 05 s");
    expect(screen.getByTestId("run-summary-model-time")).toHaveTextContent("1 min 39 s");
    expect(screen.getByTestId("run-summary-input-tokens")).toHaveTextContent("12,345");
    expect(screen.getByTestId("run-summary-output-tokens")).toHaveTextContent("678");
    expect(screen.getByTestId("run-summary-cost")).toHaveTextContent("$0.0123");
    expect(screen.getByTestId("run-summary-calls")).toHaveTextContent("9");
    expect(within(bar).getByText(/Model time adds up the latency/i)).toBeInTheDocument();

    expect(screen.getByTestId("instance-figures")).toHaveTextContent(
      "1.4 s · 30 in / 12 out",
    );
  });

  it("surfaces recoverable errors in the transcript (Req 10.6)", async () => {
    const instance = makeInstance();
    instance.transcript = {
      ...(instance.transcript as Record<string, unknown>),
      errors: [
        {
          node_id: "debater_a",
          round_index: 0,
          message: "rate limited",
          attempts: 3,
        },
      ],
    };
    installFetch({ detail: makeDetail({ instances: [instance] }) });
    renderDetail();

    await waitFor(() =>
      expect(screen.getByText(/Recoverable errors/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/rate limited/i)).toBeInTheDocument();
  });

  it("deletes the run and navigates back to the history (Req 11.4)", async () => {
    const deleted: string[] = [];
    installFetch({
      onRequest: (method, url) => {
        if (method === "DELETE") deleted.push(url);
      },
    });
    const user = userEvent.setup();
    renderDetail();

    await waitFor(() =>
      expect(screen.getByText("Configuration snapshot")).toBeInTheDocument(),
    );

    // Open the delete confirmation and confirm.
    await user.click(screen.getByRole("button", { name: /^Delete$/i }));
    const dialog = await screen.findByRole("dialog");
    await user.click(
      within(dialog).getByRole("button", { name: /^Delete$/i }),
    );

    // After a successful delete we land back on the history list.
    await waitFor(() =>
      expect(screen.getByText("History list")).toBeInTheDocument(),
    );
    expect(deleted.length).toBe(1);
  });
});
