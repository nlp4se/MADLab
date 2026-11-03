import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ConfigSummary, TaxonomyResponse } from "@/api";
import { TaxonomyProvider } from "@/taxonomy/TaxonomyContext";
import { ConfigurationsPage } from "./ConfigurationsPage";

/* ------------------------------- fixtures -------------------------------- */

const TAXONOMY: TaxonomyResponse = {
  dimensions: [],
  templates: { persona_patterns: [], roles: [], topologies: [] },
  defaults: {},
  under_development: [],
};

function makeConfig(overrides: Partial<ConfigSummary> = {}): ConfigSummary {
  return {
    id: 1,
    name: "RE binary debate",
    description: "Two debaters argue a binary classification.",
    schema_version: "1.0.0",
    created_at: null,
    updated_at: null,
    is_builtin: true,
    attributes: {
      participant_count: 2,
      topology_structure: "fully_connected",
      topology_pattern: null,
      protocol_mechanism: "sequential",
      authority: "collective",
      resolution: "majority_vote",
      under_development: false,
    },
    ...overrides,
  };
}

const CONFIGS: ConfigSummary[] = [
  makeConfig(),
  makeConfig({
    id: 2,
    name: "My custom config",
    description: null,
    is_builtin: false,
    attributes: {
      participant_count: 3,
      topology_structure: "star",
      topology_pattern: "star",
      protocol_mechanism: "simultaneous",
      authority: "judge_based",
      resolution: "argument_evaluation",
      under_development: true,
    },
  }),
];

/**
 * A fetch stub that routes by method + URL. The taxonomy is loaded once by the
 * provider; the configs list drives the page; DELETE returns the delete
 * response envelope so we can exercise the referencing-executions warning.
 */
function installFetch(options: {
  configs?: ConfigSummary[];
  deleteResponse?: { referencing_executions: number };
}) {
  const configs = options.configs ?? CONFIGS;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();

    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      });

    if (url.endsWith("/taxonomy")) return json(TAXONOMY);
    if (url.endsWith("/configs") && method === "GET") return json(configs);
    const del = /\/configs\/(\d+)$/.exec(url);
    if (del && method === "DELETE") {
      return json({
        id: Number(del[1]),
        deleted: true,
        referencing_executions: options.deleteResponse?.referencing_executions ?? 0,
      });
    }
    return json({ detail: `unhandled ${method} ${url}` }, 500);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TaxonomyProvider fallback={<div>loading-taxonomy</div>}>
        <MemoryRouter initialEntries={["/configs"]}>
          <ConfigurationsPage />
        </MemoryRouter>
      </TaxonomyProvider>
    </QueryClientProvider>,
  );
}

/* --------------------------------- tests --------------------------------- */

describe("ConfigurationsPage", () => {
  beforeEach(() => {
    // jsdom lacks createObjectURL; export isn't exercised here but keep it safe.
    Object.defineProperty(URL, "createObjectURL", {
      value: vi.fn(() => "blob:mock"),
      writable: true,
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("lists configurations with summary chips and a built-in badge", async () => {
    installFetch({});
    renderPage();

    // Both configs render once the list query resolves.
    await waitFor(() =>
      expect(screen.getByText("RE binary debate")).toBeInTheDocument(),
    );
    expect(screen.getByText("My custom config")).toBeInTheDocument();

    // Summary chips derived from ConfigSummaryAttributes.
    expect(screen.getByText("2 agents")).toBeInTheDocument();
    expect(screen.getByText("3 agents")).toBeInTheDocument();
    expect(screen.getByText("Majority Vote")).toBeInTheDocument();
    expect(screen.getByText("Judge Based")).toBeInTheDocument();

    // Built-in badge + under-development warning for the second config.
    expect(screen.getByText("Built-in")).toBeInTheDocument();
    expect(screen.getByText("Under development")).toBeInTheDocument();
  });

  it("confirms delete and surfaces the execution-reference warning", async () => {
    installFetch({ deleteResponse: { referencing_executions: 4 } });
    const user = userEvent.setup();
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("RE binary debate")).toBeInTheDocument(),
    );

    // Open the overflow menu for the first config and choose Delete.
    await user.click(
      screen.getByRole("button", { name: /Actions for RE binary debate/i }),
    );
    await user.click(screen.getByRole("menuitem", { name: /Delete/i }));

    // Confirmation dialog appears.
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/Delete configuration\?/i),
    ).toBeInTheDocument();

    // Confirm the delete.
    await user.click(within(dialog).getByRole("button", { name: /^Delete$/i }));

    // Because referencing_executions > 0, the dialog stays open to warn.
    await waitFor(() =>
      expect(screen.getByText(/Configuration deleted/i)).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/referenced by/i),
    ).toBeInTheDocument();
    // The count is surfaced.
    expect(screen.getByText("4")).toBeInTheDocument();
  });
});
