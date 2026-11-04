import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AssistantDesignResponse, ProviderResponse } from "@/api";

import { AssistantChat } from "./AssistantChat";
import { useDesignerStore } from "./designerStore";

/* ------------------------------- fixtures -------------------------------- */

function makeProvider(overrides: Partial<ProviderResponse> = {}): ProviderResponse {
  return {
    id: 1,
    name: "OpenAI (prod)",
    kind: "openai",
    base_url: null,
    models: ["gpt-4o", "gpt-4o-mini"],
    has_key: true,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function validArtifact() {
  return {
    schema_version: "1.0",
    name: "Two-debater majority vote",
    participants: {
      nodes: [
        { id: "alice", label: "Alice", roles: ["debater"] },
        { id: "bob", label: "Bob", roles: ["debater"] },
      ],
    },
    interaction: {
      topology: { adaptability: "static", structure: "fully_connected", edges: [] },
      protocol: {
        mechanism: "sequential",
        max_rounds: 2,
        ordering: "fixed",
        order: ["alice", "bob"],
      },
      format: { syntax: "natural_language", memory: "short_term" },
    },
    agreement: { authority: "collective", resolution: "majority_vote" },
    input_spec: { template: "Debate: {{topic}}", placeholders: ["topic"] },
  };
}

/**
 * A fetch stub routing by method + URL. `/providers` drives the header
 * selectors; `/assistant/design` returns a scripted envelope (question or
 * proposal) captured from `options.design`.
 */
function installFetch(options: {
  providers?: ProviderResponse[];
  design: AssistantDesignResponse;
  onDesign?: (body: unknown) => void;
}) {
  const providers = options.providers ?? [makeProvider()];
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;

      const json = (payload: unknown, status = 200) =>
        new Response(JSON.stringify(payload), {
          status,
          headers: { "content-type": "application/json" },
        });

      if (url.endsWith("/providers") && method === "GET") return json(providers);
      if (url.endsWith("/assistant/design") && method === "POST") {
        options.onDesign?.(body);
        return json(options.design);
      }
      return json({ detail: `unhandled ${method} ${url}` }, 500);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderChat() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AssistantChat />
    </QueryClientProvider>,
  );
}

/* --------------------------------- tests --------------------------------- */

describe("AssistantChat", () => {
  beforeEach(() => {
    // Reset the shared designer store between tests.
    useDesignerStore.setState({
      configId: null,
      artifact: null,
      layout: {},
      selection: null,
      dirty: false,
      validationErrors: [],
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("sends a message and shows the assistant's clarifying question", async () => {
    installFetch({
      design: {
        mode: "question",
        message: "How many debaters, and who decides the winner?",
        artifact: null,
        under_development: [],
      },
    });
    const user = userEvent.setup();
    renderChat();

    // Open the panel from the floating button.
    await user.click(screen.getByTestId("assistant-open"));
    // Providers load and populate the selectors.
    await waitFor(() =>
      expect(screen.getByLabelText("Provider")).toHaveValue("1"),
    );

    await user.type(
      screen.getByLabelText(/Message the design assistant/i),
      "I want a debate",
    );
    await user.click(screen.getByTestId("assistant-send"));

    // The user turn and the assistant's question both render.
    expect(await screen.findByText("I want a debate")).toBeInTheDocument();
    expect(
      await screen.findByText(/How many debaters, and who decides/i),
    ).toBeInTheDocument();
  });

  it("shows an Apply button for a proposal and applies it to the store", async () => {
    const design: AssistantDesignResponse = {
      mode: "proposal",
      message: "Two debaters over two rounds, decided by majority vote.",
      artifact: validArtifact(),
      under_development: [],
    };
    installFetch({ design });
    const user = userEvent.setup();
    renderChat();

    await user.click(screen.getByTestId("assistant-open"));
    await waitFor(() =>
      expect(screen.getByLabelText("Provider")).toHaveValue("1"),
    );

    await user.type(
      screen.getByLabelText(/Message the design assistant/i),
      "Design two debaters, majority vote",
    );
    await user.click(screen.getByTestId("assistant-send"));

    // The proposal card + Apply button appear.
    const apply = await screen.findByTestId("assistant-apply");
    expect(screen.getByTestId("assistant-proposal")).toBeInTheDocument();

    // Nothing in the store yet.
    expect(useDesignerStore.getState().artifact).toBeNull();

    await user.click(apply);

    // Apply loads the proposed artifact into the designer store and marks it
    // dirty (so the user can review on the canvas and then Save).
    await waitFor(() => {
      const state = useDesignerStore.getState();
      expect(state.artifact?.name).toBe("Two-debater majority vote");
      expect(state.artifact?.participants.nodes).toHaveLength(2);
      expect(state.dirty).toBe(true);
    });
  });

  it("sends the chosen provider + model and the current artifact", async () => {
    // Seed a current artifact in the store so it is sent with the request.
    useDesignerStore.getState().loadArtifact(7, validArtifact());

    let sent: Record<string, unknown> | undefined;
    installFetch({
      design: {
        mode: "question",
        message: "Got it.",
        artifact: null,
        under_development: [],
      },
      onDesign: (body) => {
        sent = body as Record<string, unknown>;
      },
    });
    const user = userEvent.setup();
    renderChat();

    await user.click(screen.getByTestId("assistant-open"));
    await waitFor(() =>
      expect(screen.getByLabelText("Provider")).toHaveValue("1"),
    );

    await user.type(
      screen.getByLabelText(/Message the design assistant/i),
      "Make it three rounds",
    );
    await user.click(screen.getByTestId("assistant-send"));

    await waitFor(() => expect(sent).toBeDefined());
    expect(sent).toMatchObject({
      provider_id: 1,
      model: "gpt-4o",
      message: "Make it three rounds",
    });
    // The current artifact is forwarded for in-place editing.
    expect((sent!.artifact as Record<string, unknown>).name).toBe(
      "Two-debater majority vote",
    );
  });
});
