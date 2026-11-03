import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ProviderResponse } from "@/api";
import { ProvidersPage } from "./ProvidersPage";

/* ------------------------------- fixtures -------------------------------- */

function makeProvider(
  overrides: Partial<ProviderResponse> = {},
): ProviderResponse {
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

/**
 * A fetch stub that routes by method + URL. The providers list drives the page;
 * PUT echoes the (never-returned) key-free provider; the test endpoint returns
 * a connectivity result with a latency we assert on.
 */
function installFetch(options: {
  providers?: ProviderResponse[];
  testResponse?: {
    ok: boolean;
    message: string;
    model: string | null;
    latency_s: number | null;
  };
  onRequest?: (method: string, url: string, body: unknown) => void;
}) {
  const providers = options.providers ?? [makeProvider()];
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      options.onRequest?.(method, url, body);

      const json = (payload: unknown, status = 200) =>
        new Response(JSON.stringify(payload), {
          status,
          headers: { "content-type": "application/json" },
        });

      if (url.endsWith("/providers") && method === "GET") return json(providers);

      const test = /\/providers\/(\d+)\/test$/.exec(url);
      if (test && method === "POST") {
        return json(
          options.testResponse ?? {
            ok: true,
            message: "Connection succeeded",
            model: "gpt-4o",
            latency_s: 0.123,
          },
        );
      }

      const put = /\/providers\/(\d+)$/.exec(url);
      if (put && method === "PUT") {
        // The API never echoes the key — respond with the key-free provider.
        return json(makeProvider({ id: Number(put[1]), ...body, has_key: true }));
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
      <ProvidersPage />
    </QueryClientProvider>,
  );
}

/* --------------------------------- tests --------------------------------- */

describe("ProvidersPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists providers with kind, models, and the configured-key state", async () => {
    installFetch({
      providers: [
        makeProvider(),
        makeProvider({
          id: 2,
          name: "Local Ollama",
          kind: "ollama",
          base_url: "http://localhost:11434",
          models: ["llama3"],
          has_key: false,
        }),
      ],
    });
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("OpenAI (prod)")).toBeInTheDocument(),
    );
    expect(screen.getByText("Local Ollama")).toBeInTheDocument();

    // Kind labels and model keys are surfaced. Model keys are scoped to the
    // card's "Model keys" list (they also appear in the test-model select).
    expect(screen.getByText("OpenAI")).toBeInTheDocument();
    expect(screen.getByText("Ollama")).toBeInTheDocument();
    const modelLists = screen.getAllByRole("list", { name: "Model keys" });
    expect(
      within(modelLists[0]).getByText("gpt-4o-mini"),
    ).toBeInTheDocument();
    expect(within(modelLists[1]).getByText("llama3")).toBeInTheDocument();

    // The has_key state is shown as a badge — not the key value (Req 8.4).
    expect(screen.getByText("Key configured")).toBeInTheDocument();
    expect(screen.getByText("Key not set")).toBeInTheDocument();
  });

  it("never shows the key in the edit form and keeps it by default (Req 8.4)", async () => {
    const requests: { method: string; url: string; body: unknown }[] = [];
    installFetch({
      onRequest: (method, url, body) => requests.push({ method, url, body }),
    });
    const user = userEvent.setup();
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("OpenAI (prod)")).toBeInTheDocument(),
    );

    // Open the edit form.
    await user.click(
      screen.getByRole("button", { name: /Actions for OpenAI \(prod\)/i }),
    );
    await user.click(screen.getByRole("menuitem", { name: /Edit/i }));

    const dialog = await screen.findByRole("dialog");

    // The stored key state is shown as a badge ("Configured"), never the value.
    expect(within(dialog).getByText("Configured")).toBeInTheDocument();
    expect(
      within(dialog).getByLabelText(/API key configured/i),
    ).toBeInTheDocument();

    // No password input is rendered while "Keep existing" is active — the key
    // is write-only and cannot be read back.
    expect(
      within(dialog).queryByPlaceholderText(/new API key/i),
    ).not.toBeInTheDocument();

    // Save with the key left untouched → the request omits api_key entirely,
    // so the stored key is preserved.
    await user.click(
      within(dialog).getByRole("button", { name: /Save changes/i }),
    );

    await waitFor(() => {
      const put = requests.find((r) => r.method === "PUT");
      expect(put).toBeTruthy();
      expect(put!.body as Record<string, unknown>).not.toHaveProperty(
        "api_key",
      );
    });
  });

  it("sends api_key=null when the stored key is explicitly cleared (Req 8.4)", async () => {
    const requests: { method: string; url: string; body: unknown }[] = [];
    installFetch({
      onRequest: (method, url, body) => requests.push({ method, url, body }),
    });
    const user = userEvent.setup();
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("OpenAI (prod)")).toBeInTheDocument(),
    );
    await user.click(
      screen.getByRole("button", { name: /Actions for OpenAI \(prod\)/i }),
    );
    await user.click(screen.getByRole("menuitem", { name: /Edit/i }));

    const dialog = await screen.findByRole("dialog");
    await user.click(
      within(dialog).getByRole("button", { name: /Clear stored key/i }),
    );
    await user.click(
      within(dialog).getByRole("button", { name: /Save changes/i }),
    );

    await waitFor(() => {
      const put = requests.find((r) => r.method === "PUT");
      expect(put).toBeTruthy();
      expect((put!.body as Record<string, unknown>).api_key).toBeNull();
    });
  });

  it("tests connectivity and reports success with latency (Req 8.5)", async () => {
    installFetch({
      testResponse: {
        ok: true,
        message: "Connection succeeded",
        model: "gpt-4o",
        latency_s: 0.42,
      },
    });
    const user = userEvent.setup();
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("OpenAI (prod)")).toBeInTheDocument(),
    );

    await user.click(
      screen.getByRole("button", { name: /Test connection/i }),
    );

    await waitFor(() =>
      expect(screen.getByText(/Connection succeeded/i)).toBeInTheDocument(),
    );
    // Latency is surfaced (0.42 s < 1 → still seconds here via toFixed path).
    expect(screen.getByText(/420 ms/i)).toBeInTheDocument();
  });

  it("never surfaces the stored key value anywhere in the UI or responses (Req 8.4)", async () => {
    // A sentinel secret that must NEVER leak into the page. The list response
    // only carries `has_key` (no key field), so if this string ever shows up
    // in the DOM it would be a real write-only-key regression.
    const SECRET = "sk-super-secret-value-DO-NOT-LEAK";

    const responses: unknown[] = [];
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        const json = (payload: unknown, status = 200) => {
          responses.push(payload);
          return new Response(JSON.stringify(payload), {
            status,
            headers: { "content-type": "application/json" },
          });
        };
        if (url.endsWith("/providers") && method === "GET")
          return json([makeProvider({ has_key: true })]);
        if (/\/providers\/(\d+)$/.test(url) && method === "PUT") {
          const body = init?.body ? JSON.parse(String(init.body)) : {};
          // The real backend NEVER echoes the key back — strip it from the
          // response exactly as the write-only contract requires (Req 8.4).
          const { api_key: _omitted, ...keyFree } = body as Record<
            string,
            unknown
          >;
          void _omitted;
          return json(makeProvider({ ...keyFree, has_key: true }));
        }
        return json({ detail: `unhandled ${method} ${url}` }, 500);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("OpenAI (prod)")).toBeInTheDocument(),
    );

    // The configured-key state is a badge, not the value.
    expect(screen.getByText("Key configured")).toBeInTheDocument();

    // Open the edit form; type a replacement key into the write-only field.
    await user.click(
      screen.getByRole("button", { name: /Actions for OpenAI \(prod\)/i }),
    );
    await user.click(screen.getByRole("menuitem", { name: /Edit/i }));
    const dialog = await screen.findByRole("dialog");

    // Reveal the write-only key input (the "Replace" action) and type the secret.
    await user.click(
      within(dialog).getByRole("button", { name: /^Replace$/i }),
    );
    const keyInput = within(dialog).getByPlaceholderText(/new API key/i);
    // The key field is a password input so the value is never shown in cleartext.
    expect(keyInput).toHaveAttribute("type", "password");
    await user.type(keyInput, SECRET);
    await user.click(
      within(dialog).getByRole("button", { name: /Save changes/i }),
    );

    // The PUT carried the secret to the server…
    await waitFor(() => {
      const put = fetchMock.mock.calls.find(
        ([, init]) => (init?.method ?? "GET").toUpperCase() === "PUT",
      );
      expect(put).toBeTruthy();
      expect(String(put![1]?.body)).toContain(SECRET);
    });

    // …but no server RESPONSE ever echoes the key back.
    for (const payload of responses) {
      expect(JSON.stringify(payload)).not.toContain(SECRET);
    }

    // …and the secret value is nowhere in the rendered document.
    expect(document.body.textContent ?? "").not.toContain(SECRET);
    expect(
      (document.body.innerHTML ?? "").includes(SECRET),
    ).toBe(false);
  });

  it("reports a clear error when connectivity fails (Req 8.5)", async () => {
    installFetch({
      testResponse: {
        ok: false,
        message: "Invalid API key",
        model: null,
        latency_s: null,
      },
    });
    const user = userEvent.setup();
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("OpenAI (prod)")).toBeInTheDocument(),
    );
    await user.click(
      screen.getByRole("button", { name: /Test connection/i }),
    );

    await waitFor(() =>
      expect(screen.getByText(/Invalid API key/i)).toBeInTheDocument(),
    );
  });
});
