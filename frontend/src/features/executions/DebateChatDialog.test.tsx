import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  ExecutionDetail,
  ExecutionInstanceResult,
  ProviderResponse,
} from "@/api";

import { STEP_DELAY_MS, TYPING_DELAY_MS } from "./DebateChatDialog";
import { EXEC3_DECISION, EXEC3_SCHEMA } from "./decisionFixtures";
import { ExecutionDetailPage } from "./ExecutionDetailPage";

/* ------------------------------- fixtures -------------------------------- */

const usage = {
  prompt_tokens: 10,
  completion_tokens: 8,
  total_tokens: 18,
  cost_usd: 0.0001,
  latency_s: 0.5,
};

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
          usage,
          metadata: {},
          structured: null,
        },
        {
          // The judge is recorded after the last debate round (round_index = rounds).
          node_id: "judge_1",
          round_index: 1,
          role: "judge",
          content: "The verdict is NFR.",
          usage: null,
          metadata: {},
          structured: { label: "NFR" },
        },
      ],
      usage,
      decision: {
        decision: "NFR",
        authority: "judge_based",
        resolution: "argument_evaluation",
        detail: null,
        structured: null,
        undecided: false,
      },
      errors: [
        {
          node_id: "debater_b",
          round_index: 0,
          message: "rate limited",
          attempts: 3,
        },
      ],
      notes: [],
    },
    final_decision: { decision: "NFR" },
    ground_truth: "NFR",
    metrics: { correct: true },
    error: null,
    ...overrides,
  };
}

function makeDetail(instance = makeInstance()): ExecutionDetail {
  return {
    id: 42,
    config_id: 1,
    config_name: "RE binary debate",
    input_mode: "single",
    status: "completed",
    progress: 1,
    instance_count: 1,
    completed_count: 1,
    error_count: 0,
    metrics: null,
    created_at: "2024-01-01T12:00:00Z",
    updated_at: "2024-01-01T12:05:00Z",
    config_snapshot: {
      name: "RE binary debate",
      participants: {
        nodes: [
          {
            id: "debater_a",
            label: "Debater A",
            roles: ["debater"],
            base_model: { provider_id: "1", model_key: "gpt-4o" },
          },
          {
            id: "debater_b",
            label: "Debater B",
            roles: ["debater"],
            base_model: { provider_id: "1", model_key: "gpt-4o-mini" },
          },
          {
            id: "judge_1",
            label: "Chief Judge",
            roles: ["judge"],
            base_model: { provider_id: "2", model_key: "claude-3-5-sonnet" },
          },
        ],
      },
      interaction: {
        topology: { structure: "star", pattern: "star" },
        protocol: { mechanism: "sequential" },
      },
      agreement: { authority: "judge_based", resolution: "argument_evaluation" },
    },
    input_ref: {},
    instances: [instance],
  } as ExecutionDetail;
}

const providers: ProviderResponse[] = [
  {
    id: 1,
    name: "OpenAI prod",
    kind: "openai",
    base_url: null,
    models: ["gpt-4o"],
    family: "closed_weight",
    has_key: true,
    created_at: null,
    updated_at: null,
  },
  {
    id: 2,
    name: "Anthropic team",
    kind: "anthropic",
    base_url: null,
    models: ["claude-3-5-sonnet"],
    family: "closed_weight",
    has_key: true,
    created_at: null,
    updated_at: null,
  },
];

function installFetch(detail: ExecutionDetail) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    const json = (payload: unknown, status = 200) =>
      new Response(JSON.stringify(payload), {
        status,
        headers: { "content-type": "application/json" },
      });
    if (/\/executions\/\d+$/.test(url) && method === "GET") return json(detail);
    if (url.endsWith("/providers") && method === "GET") return json(providers);
    return json({ detail: `unhandled ${method} ${url}` }, 500);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function renderDetail() {
  // gcTime: Infinity keeps React Query from scheduling GC timers, so the timer
  // count after closing reflects only the dialog's own playback timers.
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/executions/42"]}>
        <Routes>
          <Route path="/executions/:executionId" element={<ExecutionDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function openChat(detail = makeDetail()) {
  installFetch(detail);
  const user = userEvent.setup();
  renderDetail();
  const opener = await screen.findByRole("button", {
    name: /open instance #0 as chat/i,
  });
  await user.click(opener);
  return screen.findByRole("dialog", { name: /RE binary debate · Instance #0/ });
}

const items = (dialog: HTMLElement) => within(dialog).queryAllByTestId("chat-item");

/* --------------------------------- tests --------------------------------- */

describe("DebateChatDialog (chat replay, task 11.3)", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("opens from the instance and renders the timeline in order", async () => {
    const dialog = await openChat();

    const order = items(dialog).map((el) =>
      el.dataset.kind === "divider"
        ? `divider:${el.dataset.variant}`
        : el.dataset.kind === "message"
          ? `message:${el.dataset.nodeId}`
          : el.dataset.kind,
    );
    expect(order).toEqual([
      "task",
      "divider:round",
      "message:debater_a",
      "error",
      "divider:verdict",
      "message:judge_1",
      "decision",
    ]);

    expect(within(dialog).getByText("Round 1")).toBeInTheDocument();
    expect(within(dialog).getByText("Verdict")).toBeInTheDocument();
    const decision = within(dialog).getByTestId("chat-final-decision");
    expect(within(decision).getByText("NFR")).toBeInTheDocument();
    // Opens fully revealed.
    expect(within(dialog).getByTestId("playback-progress")).toHaveTextContent("7 / 7");
  });

  it("attributes turns with participant labels and provider names", async () => {
    const dialog = await openChat();

    expect(
      within(dialog).getAllByTestId("chat-author").map((el) => el.textContent),
    ).toEqual(["Debater A", "Chief Judge"]);

    await waitFor(() =>
      expect(
        within(dialog).getAllByTestId("chat-model-badge").map((el) => el.textContent),
      ).toEqual(["OpenAI prod · gpt-4o", "Anthropic team · claude-3-5-sonnet"]),
    );
    expect(within(dialog).queryByText(/#1/)).not.toBeInTheDocument();
  });

  it("shows an inline line for a recoverable error", async () => {
    const dialog = await openChat();
    const error = items(dialog).find((el) => el.dataset.kind === "error")!;
    expect(error).toHaveTextContent("Debater B's call failed after 3 attempts");
    expect(error).toHaveTextContent("rate limited");
  });

  it("shows the instance error when there is no transcript", async () => {
    const dialog = await openChat(
      makeDetail(makeInstance({ transcript: null, error: "provider exploded" })),
    );
    expect(within(dialog).getByRole("alert")).toHaveTextContent("provider exploded");
    // The task input still comes from the instance's resolved input.
    expect(items(dialog).map((el) => el.dataset.kind)).toEqual(["task"]);
  });

  it("plays back progressively, pauses, shows all, and clears timers on close", async () => {
    const dialog = await openChat();
    await waitFor(() =>
      expect(within(dialog).getAllByTestId("chat-model-badge")).toHaveLength(2),
    );

    vi.useFakeTimers();
    const progress = () => within(dialog).getByTestId("playback-progress");

    // Play restarts from the first item.
    fireEvent.click(within(dialog).getByRole("button", { name: "Play" }));
    expect(items(dialog)).toHaveLength(1);
    expect(progress()).toHaveTextContent("1 / 7");

    // Round divider after a step delay.
    act(() => vi.advanceTimersByTime(STEP_DELAY_MS));
    expect(items(dialog)).toHaveLength(2);

    // A typing indicator precedes the agent turn.
    expect(within(dialog).getByTestId("typing-indicator")).toHaveTextContent(
      "Debater A is typing…",
    );
    act(() => vi.advanceTimersByTime(TYPING_DELAY_MS));
    expect(items(dialog)).toHaveLength(3);
    expect(within(dialog).getByText(/performance requirement/)).toBeInTheDocument();

    // Pause stops the reveal.
    fireEvent.click(within(dialog).getByRole("button", { name: "Pause" }));
    act(() => vi.advanceTimersByTime(10_000));
    expect(items(dialog)).toHaveLength(3);
    expect(within(dialog).queryByTestId("typing-indicator")).not.toBeInTheDocument();

    // Step forward / back.
    fireEvent.click(within(dialog).getByRole("button", { name: "Step forward" }));
    expect(items(dialog)).toHaveLength(4);
    fireEvent.click(within(dialog).getByRole("button", { name: "Step back" }));
    expect(items(dialog)).toHaveLength(3);

    // Show all reveals everything.
    fireEvent.click(within(dialog).getByRole("button", { name: "Show all" }));
    expect(items(dialog)).toHaveLength(7);

    // Faster speed halves the delay.
    fireEvent.change(within(dialog).getByLabelText("Playback speed"), {
      target: { value: "2" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Play" }));
    act(() => vi.advanceTimersByTime(STEP_DELAY_MS / 2));
    expect(items(dialog)).toHaveLength(2);

    // Closing mid-playback unmounts the body and clears its timer.
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(vi.getTimerCount()).toBe(0);
    act(() => vi.advanceTimersByTime(10_000));

    // Reopening starts fully revealed again.
    fireEvent.click(screen.getByRole("button", { name: /open instance #0 as chat/i }));
    const reopened = screen.getByRole("dialog");
    expect(items(reopened)).toHaveLength(7);
  });
});

/* ------------------- final decision display (task 11.12) ------------------ */

interface DecisionCase {
  name: string;
  decision: unknown;
  undecided?: boolean;
  schema?: unknown;
  /** Expected pill text, or null for no label pill. */
  label: string | null;
  /** Text expected in the readable body block, or null for no body. */
  body: string | null;
  /** Undecided: the raw reply's label (default "MAYBE"). */
  reply?: string;
  /** The engine's `detail` string (shown for undecided decisions). */
  reason?: string;
}

const LONG_TEXT =
  "The requirement constrains how the system behaves rather than what it does, so it is non-functional.";

const DECISION_CASES: DecisionCase[] = [
  { name: "string", decision: "NFR", label: "NFR", body: null },
  {
    name: "enum object (execution 3)",
    decision: EXEC3_DECISION,
    schema: EXEC3_SCHEMA,
    label: "Functional",
    body: "Moderator evaluation",
  },
  { name: "enum object {class: F}", decision: { class: "F" }, schema: EXEC3_SCHEMA, label: "F", body: null },
  {
    name: "multi-field object without enum",
    decision: { summary: "Both sides agree it is a usability constraint.", risks: ["scope", "cost"] },
    label: null,
    body: "Both sides agree it is a usability constraint.",
  },
  { name: "long text", decision: LONG_TEXT, label: null, body: LONG_TEXT },
  { name: "undecided", decision: "MAYBE", undecided: true, schema: EXEC3_SCHEMA, label: null, body: null },
  {
    // Task 11.13: execution 3's off-schema reply is now rejected; the reason shows.
    name: "undecided off-schema reply (execution 3) with reason",
    decision: EXEC3_DECISION,
    undecided: true,
    schema: EXEC3_SCHEMA,
    label: null,
    body: "Moderator evaluation",
    reply: "Functional",
    reason:
      "judge decision failed schema parsing/validation: reply has none of the schema's properties ['class']",
  },
];

function decisionDetail(c: DecisionCase): ExecutionDetail {
  const base = makeInstance();
  const transcript = base.transcript as Record<string, unknown>;
  const structured =
    c.decision && typeof c.decision === "object" && !c.undecided ? c.decision : null;
  const instance = makeInstance({
    transcript: {
      ...transcript,
      decision: {
        decision: c.decision,
        authority: "judge_based",
        resolution: "argument_evaluation",
        detail: c.reason ?? null,
        structured,
        undecided: c.undecided === true,
      },
    } as ExecutionInstanceResult["transcript"],
  });
  const detail = makeDetail(instance);
  const snapshot = detail.config_snapshot as Record<string, unknown>;
  detail.config_snapshot = {
    ...snapshot,
    agreement: {
      authority: "judge_based",
      resolution: "argument_evaluation",
      output_schema: c.schema ?? null,
    },
  } as ExecutionDetail["config_snapshot"];
  return detail;
}

function expectDecisionCard(card: HTMLElement, c: DecisionCase) {
  const pill = within(card).queryByTestId("decision-label");
  if (c.label == null) expect(pill).toBeNull();
  else expect(pill).toHaveTextContent(new RegExp(`^${c.label}$`));
  // The pill never carries JSON.
  expect(pill?.textContent ?? "").not.toMatch(/[{}]/);

  const body = within(card).queryByTestId("decision-body");
  if (c.body == null) expect(body).toBeNull();
  else expect(body).toHaveTextContent(c.body);
  expect(body?.className ?? "").not.toMatch(/rounded-full/);

  if (c.undecided) {
    expect(within(card).getByText("Undecided")).toBeInTheDocument();
    expect(within(card).getByTestId("decision-reply")).toHaveTextContent(c.reply ?? "MAYBE");
  }
  const reason = within(card).queryByTestId("decision-reason");
  if (c.reason) expect(reason).toHaveTextContent(c.reason);
  else expect(reason).toBeNull();
  const structured = within(card).queryByText("Structured decision");
  if (c.decision && typeof c.decision === "object" && !c.undecided) {
    expect(structured).toBeInTheDocument();
  } else {
    expect(structured).toBeNull();
  }
}

describe("final decision display (task 11.12)", () => {
  afterEach(() => vi.restoreAllMocks());

  it.each(DECISION_CASES)("$name: detail view and chat replay", async (c) => {
    const dialog = await openChat(decisionDetail(c));
    expectDecisionCard(within(dialog).getByTestId("chat-final-decision"), c);

    const detailCard = screen
      .getAllByTestId("final-decision")
      .find((el) => !dialog.contains(el))!;
    expectDecisionCard(detailCard, c);
  });

  it("execution 3: lists the debaters' arguments as bullets", async () => {
    const c = DECISION_CASES[1];
    const dialog = await openChat(decisionDetail(c));
    const body = within(within(dialog).getByTestId("chat-final-decision")).getByTestId(
      "decision-body",
    );
    expect(within(body).getAllByRole("listitem")).toHaveLength(2);
    expect(within(body).queryByText("final_classification")).toBeNull();
  });

  it("renders a JSON-only judge reply as a readable list, keeping the raw text", async () => {
    const base = makeInstance();
    const transcript = base.transcript as Record<string, unknown>;
    const messages = transcript.messages as Record<string, unknown>[];
    const raw = JSON.stringify(EXEC3_DECISION);
    const detail = makeDetail(
      makeInstance({
        transcript: {
          ...transcript,
          messages: [
            messages[0],
            { ...messages[1], content: raw, structured: EXEC3_DECISION },
          ],
        } as ExecutionInstanceResult["transcript"],
      }),
    );
    const dialog = await openChat(detail);
    const judge = items(dialog).find((el) => el.dataset.nodeId === "judge_1")!;
    const body = within(judge).getByTestId("message-structured-body");
    expect(body).toHaveTextContent("Final classification");
    expect(body).toHaveTextContent("Functional");
    expect(within(body).getAllByRole("listitem")).toHaveLength(2);
    expect(within(judge).getByText("Raw reply")).toBeInTheDocument();
    expect(within(judge).getByText(raw)).toBeInTheDocument();
  });
});

/* --------------------- long content stays in its card (task 11.15) -------- */

const LONG_TOKEN = `{"final_classification":"${"x".repeat(400)}"}`;
const LONG_ERROR = `litellm.BadRequestError: ${"y".repeat(400)}`;

function longContentDetail(): ExecutionDetail {
  const base = makeInstance();
  const transcript = base.transcript as Record<string, unknown>;
  const messages = transcript.messages as Record<string, unknown>[];
  return makeDetail(
    makeInstance({
      transcript: {
        ...transcript,
        messages: [
          { ...messages[0], content: LONG_TOKEN },
          {
            ...messages[1],
            content: "Long structured verdict",
            structured: { label: "NFR", rationale: "z".repeat(400) },
          },
        ],
        errors: [{ node_id: "debater_b", round_index: 0, message: LONG_ERROR, attempts: 3 }],
      } as ExecutionInstanceResult["transcript"],
    }),
  );
}

/** The classes that keep long text / pre blocks inside their card. */
function expectWraps(el: HTMLElement) {
  expect(el).toHaveClass("whitespace-pre-wrap", "break-words", "[overflow-wrap:anywhere]");
}
/**
 * Markdown-rendered text (task 11.16): the root is a block container, so it
 * wraps without `whitespace-pre-wrap` (newlines become <br>).
 */
function expectMarkdownWraps(el: HTMLElement) {
  expect(el).toHaveClass("min-w-0", "break-words", "[overflow-wrap:anywhere]");
}
function expectScrollsInCard(el: HTMLElement) {
  expect(el).toHaveClass("max-w-full");
  expect(el.className).toMatch(/overflow-(x-)?auto/);
}

describe("long content stays inside its card (task 11.15)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("detail view: wraps message text and errors, scrolls JSON inside the card", async () => {
    installFetch(longContentDetail());
    renderDetail();
    const list = await screen.findByTestId("instance-list");
    // The instance grid can't grow to its widest child.
    expect(list).toHaveClass("grid-cols-1");
    for (const li of within(list).getAllByRole("listitem").filter((el) => el.parentElement === list)) {
      expect(li).toHaveClass("min-w-0");
    }

    const messages = within(list).getAllByTestId("transcript-message");
    expect(messages).toHaveLength(2);
    for (const m of messages) expect(m).toHaveClass("min-w-0");

    const text = within(messages[0]).getByTestId("message-text");
    expect(text).toHaveTextContent(LONG_TOKEN);
    expectMarkdownWraps(text);

    const structured = within(messages[1]).getByTestId("message-structured");
    expect(structured.tagName).toBe("PRE");
    expectScrollsInCard(structured);

    const errors = within(list).getByTestId("recoverable-errors");
    const errorItem = within(errors).getByText(new RegExp(LONG_ERROR.slice(0, 40)));
    expectWraps(errorItem);
  });

  it("chat replay: wraps message text and errors, scrolls JSON inside the bubble", async () => {
    const dialog = await openChat(longContentDetail());

    const text = within(dialog).getAllByTestId("chat-message-text")[0];
    expect(text).toHaveTextContent(LONG_TOKEN);
    expectMarkdownWraps(text);

    const structured = within(dialog).getByTestId("chat-message-structured");
    expectScrollsInCard(structured);

    const error = within(dialog).getByTestId("chat-error-text");
    expect(error).toHaveTextContent(LONG_ERROR);
    expect(error).toHaveClass("min-w-0");
    expectWraps(error);
  });
});

/* ------------- failed instance keeps its call errors (task 11.17) --------- */

const QUOTA_ERROR =
  "model call for node 'judge_1' failed after 1 attempt(s): [rate limit, HTTP 429] " +
  "You exceeded your current quota, please check your plan and billing details. " +
  "q".repeat(300);

function failedJudgeDetail(): ExecutionDetail {
  const base = makeInstance();
  const transcript = base.transcript as Record<string, unknown>;
  const messages = transcript.messages as Record<string, unknown>[];
  const detail = makeDetail(
    makeInstance({
      // The runner now persists the partial transcript of a failed instance.
      transcript: {
        ...transcript,
        messages: [messages[0]],
        decision: null,
        errors: [{ node_id: "judge_1", round_index: 1, message: QUOTA_ERROR, attempts: 1 }],
      } as ExecutionInstanceResult["transcript"],
      final_decision: null,
      metrics: null,
      error:
        "ExecutionError: judge node 'judge_1' failed to produce a decision after 1 attempt(s): " +
        "[rate limit, HTTP 429] You exceeded your current quota (details in the transcript errors)",
    }),
  );
  return { ...detail, status: "failed", error_count: 1 } as ExecutionDetail;
}

describe("failed instance shows its call errors (task 11.17)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("detail view: lists the call errors next to the instance error", async () => {
    installFetch(failedJudgeDetail());
    renderDetail();
    const alert = await screen.findByTestId("instance-failed");
    expect(alert).toHaveTextContent(/Instance failed/);
    expect(alert).toHaveTextContent(/exceeded your current quota/);

    const callErrors = within(alert).getByTestId("instance-call-errors");
    const item = within(callErrors).getByRole("listitem");
    expect(item).toHaveTextContent(/judge_1 · verdict · 1 attempt:/);
    expect(item).toHaveTextContent(QUOTA_ERROR);
    expectWraps(item);
    // Listed once: the transcript's own error panel is folded into the alert.
    expect(screen.queryByTestId("recoverable-errors")).not.toBeInTheDocument();
    // The partial debate is still shown.
    expect(screen.getAllByTestId("transcript-message")).toHaveLength(1);
  });

  it("chat replay: the failure alert names the participant and the provider error", async () => {
    const dialog = await openChat(failedJudgeDetail());
    const alert = within(dialog).getByTestId("instance-failed");
    const item = within(within(alert).getByTestId("instance-call-errors")).getByRole("listitem");
    expect(item).toHaveTextContent(/Chief Judge · verdict · 1 attempt:/);
    expect(item).toHaveTextContent(QUOTA_ERROR);
    expectWraps(item);
  });
});

/* ------------------ Markdown in model-generated text (task 11.16) --------- */

const BOLD_REPLY =
  "**Functional (F).** The requirement specifies *what* the system does.\n\n- input\n- output";

function markdownDetail(): ExecutionDetail {
  const base = makeInstance();
  const transcript = base.transcript as Record<string, unknown>;
  const messages = transcript.messages as Record<string, unknown>[];
  return makeDetail(
    makeInstance({
      transcript: {
        ...transcript,
        messages: [
          { ...messages[0], content: BOLD_REPLY },
          // JSON-only judge reply: stays raw in the detail view.
          { ...messages[1], content: '{"label": "**NFR**"}', structured: { label: "**NFR**" } },
        ],
        decision: {
          decision: "The debaters **agree**: it constrains *how* the system behaves, so it is NFR.",
          authority: "judge_based",
          resolution: "argument_evaluation",
          detail: null,
          structured: null,
          undecided: false,
        },
      } as ExecutionInstanceResult["transcript"],
    }),
  );
}

function expectBoldDebater(text: HTMLElement) {
  expect(text.querySelector("strong")).toHaveTextContent("Functional (F).");
  expect(text.querySelector("em")).toHaveTextContent("what");
  expect(text.querySelectorAll("li")).toHaveLength(2);
  expect(text.textContent).not.toContain("**");
}

describe("Markdown in model-generated text (task 11.16)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("detail view: a **bold** debater message renders <strong>; JSON-only replies stay raw", async () => {
    installFetch(markdownDetail());
    renderDetail();
    const list = await screen.findByTestId("instance-list");
    const [debater, judge] = within(list).getAllByTestId("transcript-message");

    expectBoldDebater(within(debater).getByTestId("message-text"));

    const judgeText = within(judge).getByTestId("message-text");
    expect(judgeText).toHaveTextContent('{"label": "**NFR**"}');
    expect(judgeText.querySelector("strong")).toBeNull();

    const body = within(list).getByTestId("decision-body");
    expect(body.querySelector("strong")).toHaveTextContent("agree");
    expect(body.querySelector("em")).toHaveTextContent("how");
  });

  it("chat replay: a **bold** debater message renders <strong>", async () => {
    const dialog = await openChat(markdownDetail());
    const debater = items(dialog).find((el) => el.dataset.nodeId === "debater_a")!;
    expectBoldDebater(within(debater).getByTestId("chat-message-text"));

    // The JSON-only reply keeps the 11.12 readable view and its raw text.
    const judge = items(dialog).find((el) => el.dataset.nodeId === "judge_1")!;
    const structured = within(judge).getByTestId("message-structured-body");
    expect(structured.querySelector("strong")).toHaveTextContent("NFR");
    expect(within(judge).getByText('{"label": "**NFR**"}')).toBeInTheDocument();

    const decision = within(dialog).getByTestId("chat-final-decision");
    expect(within(decision).getByTestId("decision-body").querySelector("strong")).toHaveTextContent(
      "agree",
    );
  });
});
