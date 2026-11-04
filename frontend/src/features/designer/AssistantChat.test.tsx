import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AssistantDesignResponse, ProviderResponse } from "@/api";

import { AssistantChat } from "./AssistantChat";
import { useAssistantChatStore } from "./assistantChatStore";
import { useDesignerStore } from "./designerStore";

/* ------------------------------- fixtures -------------------------------- */

function makeProvider(overrides: Partial<ProviderResponse> = {}): ProviderResponse {
  return {
    id: 1,
    name: "OpenAI (prod)",
    kind: "openai",
    base_url: null,
    models: ["gpt-4o", "gpt-4o-mini"],
    family: "closed_weight",
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
  /** When set, `/assistant/design` waits for it before replying. */
  gate?: Promise<void>;
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
        if (options.gate) await options.gate;
        return json(options.design);
      }
      return json({ detail: `unhandled ${method} ${url}` }, 500);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderChat(props: { configId?: number | null } = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const ui = (p: { configId?: number | null }) => (
    <QueryClientProvider client={client}>
      <AssistantChat {...p} />
    </QueryClientProvider>
  );
  const result = render(ui(props));
  return {
    ...result,
    /** Re-render with a different config id (same QueryClient). */
    rerenderWith: (p: { configId?: number | null }) => result.rerender(ui(p)),
  };
}

const QUESTION: AssistantDesignResponse = {
  mode: "question",
  message: "How many debaters, and who decides the winner?",
  artifact: null,
  under_development: [],
};

/** Open the panel and wait until the provider selector is populated. */
async function openPanel(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByTestId("assistant-open"));
  await waitFor(() => expect(screen.getByLabelText("Provider")).toHaveValue("1"));
}

async function sendMessage(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(screen.getByLabelText(/Message the design assistant/i), text);
  await user.click(screen.getByTestId("assistant-send"));
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
    // The chat store is in-memory module state: reset it between tests.
    useAssistantChatStore.getState().resetAll();
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

describe("AssistantChat session persistence (task 11.5)", () => {
  beforeEach(() => {
    useDesignerStore.setState({
      configId: null,
      artifact: null,
      layout: {},
      selection: null,
      dirty: false,
      validationErrors: [],
    });
    useAssistantChatStore.getState().resetAll();
  });
  afterEach(() => vi.restoreAllMocks());

  it("keeps history, model choice and draft across close/reopen and continues", async () => {
    const bodies: Array<Record<string, unknown>> = [];
    installFetch({
      design: QUESTION,
      onDesign: (b) => bodies.push(b as Record<string, unknown>),
    });
    const user = userEvent.setup();
    renderChat({ configId: 5 });

    await openPanel(user);
    await user.selectOptions(screen.getByLabelText("Model"), "gpt-4o-mini");
    await sendMessage(user, "I want a debate");
    expect(await screen.findByText(/How many debaters/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Message the design assistant/i), "half-typed");

    // Close: the panel (and its component state) unmounts.
    await user.click(screen.getByRole("button", { name: "Close the assistant" }));
    expect(screen.queryByTestId("assistant-panel")).toBeNull();

    // Reopen: the conversation, model choice and draft are still there.
    await user.click(screen.getByTestId("assistant-open"));
    expect(screen.getByText("I want a debate")).toBeInTheDocument();
    expect(screen.getByText(/How many debaters/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Model")).toHaveValue("gpt-4o-mini");
    expect(screen.getByLabelText(/Message the design assistant/i)).toHaveValue("half-typed");

    // Continue: the earlier turns are sent as history.
    await user.clear(screen.getByLabelText(/Message the design assistant/i));
    await sendMessage(user, "Two debaters");
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toMatchObject({
      model: "gpt-4o-mini",
      message: "Two debaters",
      history: [
        { role: "user", content: "I want a debate" },
        { role: "assistant", content: QUESTION.message },
      ],
    });
  });

  it("lands a pending reply even if the panel was closed", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => {
      release = r;
    });
    installFetch({ design: QUESTION, gate });
    const user = userEvent.setup();
    renderChat({ configId: 5 });

    await openPanel(user);
    await sendMessage(user, "I want a debate");
    expect(await screen.findByText(/Thinking/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Close the assistant" }));
    release();
    await waitFor(() =>
      expect(useAssistantChatStore.getState().sessions["5"]?.turns).toHaveLength(2),
    );

    await user.click(screen.getByTestId("assistant-open"));
    expect(screen.getByText(/How many debaters/i)).toBeInTheDocument();
    expect(screen.queryByText(/Thinking/)).toBeNull();
  });

  it("keeps a separate conversation per config", async () => {
    installFetch({ design: QUESTION });
    const user = userEvent.setup();
    const { rerenderWith } = renderChat({ configId: 1 });

    await openPanel(user);
    await sendMessage(user, "Config one chat");
    expect(await screen.findByText(/How many debaters/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close the assistant" }));

    // Another config: empty conversation.
    rerenderWith({ configId: 2 });
    await openPanel(user);
    expect(screen.queryByText("Config one chat")).toBeNull();
    expect(screen.queryAllByTestId("assistant-turn-user")).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Close the assistant" }));

    // Back to the first config: its history is intact.
    rerenderWith({ configId: 1 });
    await user.click(screen.getByTestId("assistant-open"));
    expect(screen.getByText("Config one chat")).toBeInTheDocument();
  });

  it("New chat clears the current config's history only", async () => {
    installFetch({ design: QUESTION });
    const user = userEvent.setup();
    const { rerenderWith } = renderChat({ configId: 1 });

    await openPanel(user);
    await sendMessage(user, "Config one chat");
    expect(await screen.findByText(/How many debaters/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close the assistant" }));

    rerenderWith({ configId: 2 });
    await openPanel(user);
    await sendMessage(user, "Config two chat");
    expect(await screen.findByText(/How many debaters/i)).toBeInTheDocument();

    const newChat = screen.getByRole("button", { name: "New chat" });
    expect(newChat).toHaveAttribute("title");
    await user.click(newChat);
    expect(screen.queryByText("Config two chat")).toBeNull();
    expect(screen.queryAllByTestId("assistant-turn-assistant")).toHaveLength(0);
    // The provider/model choice is kept.
    expect(screen.getByLabelText("Provider")).toHaveValue("1");
    await user.click(screen.getByRole("button", { name: "Close the assistant" }));

    rerenderWith({ configId: 1 });
    await user.click(screen.getByTestId("assistant-open"));
    expect(screen.getByText("Config one chat")).toBeInTheDocument();
  });

  it("keeps a proposal's Applied state across close/reopen", async () => {
    installFetch({
      design: {
        mode: "proposal",
        message: "Here you go.",
        artifact: validArtifact(),
        under_development: [],
      },
    });
    const user = userEvent.setup();
    renderChat({ configId: 3 });

    await openPanel(user);
    await sendMessage(user, "Design it");
    await user.click(await screen.findByTestId("assistant-apply"));
    expect(screen.getByTestId("assistant-apply")).toHaveTextContent(/Applied/);

    await user.click(screen.getByRole("button", { name: "Close the assistant" }));
    await user.click(screen.getByTestId("assistant-open"));
    expect(screen.getByTestId("assistant-apply")).toHaveTextContent(/Applied/);
  });
});

describe("AssistantChat Markdown (task 11.16)", () => {
  beforeEach(() => {
    useDesignerStore.setState({
      configId: null,
      artifact: null,
      layout: {},
      selection: null,
      dirty: false,
      validationErrors: [],
    });
    useAssistantChatStore.getState().resetAll();
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders the assistant's reply as Markdown while the user's turn stays literal", async () => {
    installFetch({
      design: {
        mode: "question",
        message: "**How many** debaters?\n\n- two\n- three",
        artifact: null,
        under_development: [],
      },
    });
    const user = userEvent.setup();
    renderChat({ configId: 5 });

    await openPanel(user);
    await sendMessage(user, "I want **bold** and <b>tags</b>");

    const reply = await screen.findByTestId("assistant-turn-assistant");
    expect(reply.querySelector("strong")).toHaveTextContent("How many");
    expect(reply.querySelectorAll("li")).toHaveLength(2);
    expect(reply.textContent).not.toContain("**");

    const mine = screen.getByTestId("assistant-turn-user");
    expect(mine).toHaveTextContent("I want **bold** and <b>tags</b>");
    expect(mine.querySelector("strong, b")).toBeNull();
  });

  it("renders a proposal's message as Markdown", async () => {
    installFetch({
      design: {
        mode: "proposal",
        message: "Two debaters, decided by **majority vote**.",
        artifact: validArtifact(),
        under_development: [],
      },
    });
    const user = userEvent.setup();
    renderChat({ configId: 5 });

    await openPanel(user);
    await sendMessage(user, "Design it");
    const message = await screen.findByTestId("assistant-proposal-message");
    expect(message.querySelector("strong")).toHaveTextContent("majority vote");
  });

  it("keeps request errors as plain text", async () => {
    installFetch({ design: QUESTION });
    useAssistantChatStore.getState().patchSession("5", {
      turns: [
        { kind: "message", role: "user", content: "hi" },
        {
          kind: "message",
          role: "assistant",
          content: "The assistant request failed: **boom**",
          error: true,
        },
      ],
    });
    const user = userEvent.setup();
    renderChat({ configId: 5 });

    await openPanel(user);
    const error = screen.getByTestId("assistant-turn-assistant");
    expect(error).toHaveTextContent("The assistant request failed: **boom**");
    expect(error.querySelector("strong")).toBeNull();
  });
});
