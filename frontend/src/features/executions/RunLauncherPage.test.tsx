import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  ConfigDetail,
  ConfigSummary,
  DatasetResponse,
} from "@/api";
import { RunLauncherPage } from "./RunLauncherPage";

/* ------------------------------- fixtures -------------------------------- */

function makeSummary(overrides: Partial<ConfigSummary> = {}): ConfigSummary {
  return {
    id: 1,
    name: "RE binary debate",
    description: "Debate a requirement class",
    schema_version: "1.0",
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

function makeDetail(overrides: Partial<ConfigDetail> = {}): ConfigDetail {
  return {
    id: 1,
    name: "RE binary debate",
    description: "Debate a requirement class",
    schema_version: "1.0",
    created_at: null,
    updated_at: null,
    is_builtin: true,
    artifact: {
      participants: { nodes: [{ id: "a" }, { id: "b" }] },
      interaction: {
        topology: { structure: "fully_connected", pattern: null },
        protocol: { mechanism: "sequential" },
      },
      agreement: { authority: "collective", resolution: "majority_vote" },
      input_spec: {
        template: "Classify: {{requirement}}",
        placeholders: ["requirement"],
        ad_hoc_fields: [{ key: "requirement", label: "Requirement text" }],
      },
    },
    under_development: [],
    ...overrides,
  };
}

function makeDataset(overrides: Partial<DatasetResponse> = {}): DatasetResponse {
  return {
    id: 7,
    name: "nfr-small",
    original_filename: "nfr-small.csv",
    columns: ["RequirementText", "Label"],
    row_count: 3,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

/**
 * Route the typed client's fetch calls by method + URL. `onRequest` captures
 * the launch/preview bodies so the tests can assert the exact posted shape.
 */
function installFetch(options: {
  configs?: ConfigSummary[];
  detail?: ConfigDetail;
  dataset?: DatasetResponse;
  onRequest?: (method: string, url: string, body: unknown) => void;
}) {
  const configs = options.configs ?? [makeSummary()];
  const detail = options.detail ?? makeDetail();
  const dataset = options.dataset ?? makeDataset();

  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      const isForm =
        typeof FormData !== "undefined" && init?.body instanceof FormData;
      const body =
        init?.body && !isForm ? JSON.parse(String(init.body)) : undefined;
      options.onRequest?.(method, url, body);

      const json = (payload: unknown, status = 200) =>
        new Response(JSON.stringify(payload), {
          status,
          headers: { "content-type": "application/json" },
        });

      if (url.endsWith("/configs") && method === "GET") return json(configs);
      if (/\/configs\/\d+$/.test(url) && method === "GET") return json(detail);
      if (url.endsWith("/datasets") && method === "POST") return json(dataset);
      if (/\/datasets\/\d+\/preview$/.test(url) && method === "POST") {
        return json({
          row_index: 0,
          resolved_input: "Classify: The system shall be fast",
          instance: { requirement: "The system shall be fast" },
        });
      }
      if (url.endsWith("/executions") && method === "POST") {
        return json({
          id: 99,
          config_id: detail.id,
          config_name: detail.name,
          input_mode: body?.batch ? "batch" : "single",
          status: "pending",
          progress: 0,
          instance_count: 0,
          completed_count: 0,
          error_count: 0,
          metrics: null,
          created_at: null,
          updated_at: null,
        });
      }
      return json({ detail: `unhandled ${method} ${url}` }, 500);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/run"]}>
        <Routes>
          <Route path="/run" element={<RunLauncherPage />} />
          <Route
            path="/executions/:id"
            element={<div>Execution detail</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function pickConfig(user: ReturnType<typeof userEvent.setup>) {
  await waitFor(() =>
    expect(screen.getByLabelText("Configuration")).toBeInTheDocument(),
  );
  await user.selectOptions(screen.getByLabelText("Configuration"), "1");
}

/* --------------------------------- tests --------------------------------- */

describe("RunLauncherPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("gates launch when the config selects under-development values (Req 7.5)", async () => {
    installFetch({
      detail: makeDetail({
        under_development: ["interaction.format.syntax.embeddings"],
      }),
    });
    const user = userEvent.setup();
    renderPage();

    await pickConfig(user);

    // The gate explanation and the offending value are shown.
    await waitFor(() =>
      expect(
        screen.getByText(/can't be run yet/i),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByText("interaction.format.syntax.embeddings"),
    ).toBeInTheDocument();

    // Launch is disabled.
    expect(screen.getByRole("button", { name: /Launch/i })).toBeDisabled();
  });

  it("explains an empty input template and links to the designer's Input panel (task 11.10)", async () => {
    const base = makeDetail();
    installFetch({
      detail: makeDetail({
        artifact: {
          ...base.artifact,
          input_spec: { template: "", placeholders: [], ad_hoc_fields: [] },
        },
      }),
    });
    const user = userEvent.setup();
    renderPage();

    await pickConfig(user);

    const gate = await screen.findByTestId("missing-input-gate");
    expect(gate).toHaveTextContent(/has no input yet/i);
    expect(
      screen.getByRole("link", { name: /Define the input in the designer/i }),
    ).toHaveAttribute("href", "/designer/1?panel=input");
    expect(screen.getByRole("button", { name: /Launch/i })).toBeDisabled();
  });

  it("launches a fixed task (template without placeholders) with an empty input", async () => {
    const requests: { method: string; url: string; body: unknown }[] = [];
    const base = makeDetail();
    installFetch({
      detail: makeDetail({
        artifact: {
          ...base.artifact,
          input_spec: { template: "Debate remote work.", placeholders: [], ad_hoc_fields: [] },
        },
      }),
      onRequest: (method, url, body) => requests.push({ method, url, body }),
    });
    const user = userEvent.setup();
    renderPage();

    await pickConfig(user);
    expect(await screen.findByText(/same fixed task/i)).toBeInTheDocument();
    expect(screen.queryByTestId("missing-input-gate")).not.toBeInTheDocument();

    const launch = screen.getByRole("button", { name: /Launch/i });
    await waitFor(() => expect(launch).toBeEnabled());
    await user.click(launch);
    await waitFor(() =>
      expect(screen.getByText("Execution detail")).toBeInTheDocument(),
    );
    const post = requests.find((r) => r.method === "POST" && r.url.endsWith("/executions"));
    expect(post!.body).toEqual({ config_id: 1, input: {} });
  });

  it("single mode collects template fields and posts { config_id, input } (Req 10.2, 10.4)", async () => {
    const requests: { method: string; url: string; body: unknown }[] = [];
    installFetch({
      onRequest: (method, url, body) => requests.push({ method, url, body }),
    });
    const user = userEvent.setup();
    renderPage();

    await pickConfig(user);

    // The single-input form renders a field derived from the template.
    const field = await screen.findByLabelText(/Requirement text/i);
    await user.type(field, "The system shall be fast");

    const launch = screen.getByRole("button", { name: /Launch/i });
    await waitFor(() => expect(launch).toBeEnabled());
    await user.click(launch);

    // Posts the single-input body and navigates to the execution detail.
    await waitFor(() =>
      expect(screen.getByText("Execution detail")).toBeInTheDocument(),
    );
    const post = requests.find(
      (r) => r.method === "POST" && r.url.endsWith("/executions"),
    );
    expect(post).toBeTruthy();
    expect(post!.body).toEqual({
      config_id: 1,
      input: { requirement: "The system shall be fast" },
    });
  });

  it("batch mode maps columns, previews a sample row, and posts a batch body (Req 10.3, 10.4)", async () => {
    const requests: { method: string; url: string; body: unknown }[] = [];
    const fetchMock = installFetch({
      onRequest: (method, url, body) => requests.push({ method, url, body }),
    });
    const user = userEvent.setup();
    renderPage();

    await pickConfig(user);

    // Switch to batch mode.
    await user.click(screen.getByRole("radio", { name: /Batch \(CSV\)/i }));

    // Upload a CSV via the hidden file input.
    const file = new File(["RequirementText,Label\nfoo,F\n"], "nfr-small.csv", {
      type: "text/csv",
    });
    const fileInput = screen.getByLabelText("Upload CSV") as HTMLInputElement;
    await user.upload(fileInput, file);

    // Columns appear; map RequirementText → the requirement placeholder.
    await waitFor(() =>
      expect(
        screen.getByLabelText("Placeholder for RequirementText"),
      ).toBeInTheDocument(),
    );
    await user.selectOptions(
      screen.getByLabelText("Placeholder for RequirementText"),
      "requirement",
    );

    // Optionally pick a ground-truth column.
    await user.selectOptions(
      screen.getByLabelText("Ground-truth column"),
      "Label",
    );

    // Preview resolves the sample row.
    await user.click(
      screen.getByRole("button", { name: /Preview sample row/i }),
    );
    await waitFor(() =>
      expect(
        screen.getByText(/Classify: The system shall be fast/i),
      ).toBeInTheDocument(),
    );
    const previewReq = requests.find(
      (r) => r.method === "POST" && /\/datasets\/7\/preview$/.test(r.url),
    );
    expect(previewReq!.body).toEqual({
      mapping: { RequirementText: "requirement" },
      config_id: 1,
      row_index: 0,
    });

    // Launch posts the batch body.
    const launch = screen.getByRole("button", { name: /Launch/i });
    await waitFor(() => expect(launch).toBeEnabled());
    await user.click(launch);

    await waitFor(() =>
      expect(screen.getByText("Execution detail")).toBeInTheDocument(),
    );
    const post = requests.find(
      (r) => r.method === "POST" && r.url.endsWith("/executions"),
    );
    expect(post!.body).toEqual({
      config_id: 1,
      batch: {
        dataset_id: 7,
        mapping: { RequirementText: "requirement" },
        ground_truth_column: "Label",
      },
    });

    expect(fetchMock).toHaveBeenCalled();
  });
});
