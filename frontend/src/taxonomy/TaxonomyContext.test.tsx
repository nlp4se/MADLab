import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TaxonomyResponse } from "@/api";
import { TaxonomyProvider, useTaxonomy } from "./TaxonomyContext";

const SAMPLE: TaxonomyResponse = {
  dimensions: [
    {
      key: "participants",
      label: "Participants",
      description: "who debates",
      subdimensions: [
        {
          key: "roles",
          label: "Roles",
          description: "functional roles",
          selection: "multi",
          values: [
            {
              key: "debater",
              label: "Debater",
              description: "argues a position",
              default: true,
              executable: true,
              icon: "role/debater",
            },
            {
              key: "verifier",
              label: "Verifier",
              description: "checks claims",
              default: false,
              executable: false,
              icon: "role/verifier",
            },
          ],
        },
      ],
    },
  ],
  templates: { persona_patterns: [], roles: [], topologies: [] },
  defaults: { participants: { roles: "debater" } },
  under_development: ["verifier"],
};

function Probe() {
  const { getValue, getDefault, isUnderDevelopment } = useTaxonomy();
  const debater = getValue("participants", "roles", "debater");
  return (
    <div>
      <span>label:{debater?.label}</span>
      <span>default:{getDefault("participants", "roles")}</span>
      <span>underdev:{String(isUnderDevelopment("verifier"))}</span>
    </div>
  );
}

function renderWithProvider() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TaxonomyProvider fallback={<div>loading</div>}>
        <Probe />
      </TaxonomyProvider>
    </QueryClientProvider>,
  );
}

describe("TaxonomyProvider", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the catalog once and exposes lookup helpers", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(SAMPLE), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    renderWithProvider();

    await waitFor(() =>
      expect(screen.getByText("label:Debater")).toBeInTheDocument(),
    );
    expect(screen.getByText("default:debater")).toBeInTheDocument();
    expect(screen.getByText("underdev:true")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
