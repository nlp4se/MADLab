import { describe, expect, it } from "vitest";

import type { ProviderResponse } from "@/api";

import {
  buildChatTimeline,
  debateRoundCount,
  modelBadge,
  participantsFromSnapshot,
  type ChatItem,
} from "./chatTimeline";
import { parseTranscript } from "./transcript";

const snapshot = {
  participants: {
    nodes: [
      {
        id: "debater_a",
        label: "Debater A",
        roles: ["debater"],
        base_model: { provider_id: "1", model_key: "gpt-4o" },
      },
      {
        id: "judge_1",
        label: "Chief Judge",
        roles: ["judge"],
        base_model: { provider_id: "9", model_key: "claude-3" },
      },
    ],
  },
};

const msg = (node_id: string, round_index: number, role = "debater") => ({
  node_id,
  round_index,
  role,
  content: `${node_id}@${round_index}`,
  usage: null,
  metadata: {},
  structured: null,
});

function transcript(extra: Record<string, unknown> = {}) {
  return parseTranscript({
    resolved_input: "Classify X",
    rounds: 2,
    messages: [
      msg("debater_a", 0),
      msg("debater_b", 0),
      msg("debater_a", 1),
      msg("judge_1", 2, "judge"),
    ],
    errors: [
      { node_id: "debater_b", round_index: 1, message: "rate limited", attempts: 3 },
    ],
    decision: { decision: "NFR", authority: "judge_based", undecided: false },
    notes: [],
    ...extra,
  });
}

/** Compact signature of a timeline for order assertions. */
function signature(items: ChatItem[]): string[] {
  return items.map((item) => {
    switch (item.kind) {
      case "task":
        return "task";
      case "divider":
        return `divider:${item.label}`;
      case "message":
        return `msg:${item.message.node_id}@${item.message.round_index}`;
      case "error":
        return `error:${item.error.node_id}@${item.error.round_index}`;
      case "decision":
        return "decision";
      case "note":
        return "note";
    }
  });
}

describe("buildChatTimeline", () => {
  it("orders task, rounds, inline errors, verdict, judge and decision", () => {
    const items = buildChatTimeline(transcript(), participantsFromSnapshot(snapshot));
    expect(signature(items)).toEqual([
      "task",
      "divider:Round 1",
      "msg:debater_a@0",
      "msg:debater_b@0",
      "divider:Round 2",
      "msg:debater_a@1",
      "error:debater_b@1",
      "divider:Verdict",
      "msg:judge_1@2",
      "decision",
    ]);
  });

  it("attributes messages from the snapshot and falls back to the node id", () => {
    const items = buildChatTimeline(transcript(), participantsFromSnapshot(snapshot));
    const messages = items.filter(
      (i): i is Extract<ChatItem, { kind: "message" }> => i.kind === "message",
    );
    expect(messages[0].participant.label).toBe("Debater A");
    expect(messages[0].participant.modelKey).toBe("gpt-4o");
    // debater_b isn't in the snapshot.
    expect(messages[1].participant.label).toBe("debater_b");
    expect(messages[3].participant.label).toBe("Chief Judge");
  });

  it("groups consecutive turns from the same participant", () => {
    const t = parseTranscript({
      rounds: 1,
      messages: [msg("debater_a", 0), msg("debater_a", 0), msg("debater_b", 0)],
    });
    const grouped = buildChatTimeline(t, new Map())
      .filter((i): i is Extract<ChatItem, { kind: "message" }> => i.kind === "message")
      .map((i) => i.grouped);
    expect(grouped).toEqual([false, true, false]);
  });

  it("uses the fallback input when the transcript has none", () => {
    expect(signature(buildChatTimeline(null, new Map(), "Raw input"))).toEqual(["task"]);
    expect(buildChatTimeline(null, new Map())).toEqual([]);
  });

  it("derives the debate round count when `rounds` is missing", () => {
    const t = transcript({ rounds: 0 });
    expect(debateRoundCount(t!)).toBe(2);
  });
});

describe("modelBadge", () => {
  const providers = [
    { id: 1, name: "OpenAI prod", kind: "openai" },
  ] as ProviderResponse[];
  const participants = participantsFromSnapshot(snapshot);

  it("shows the provider name, not the id", () => {
    const badge = modelBadge(participants.get("debater_a")!, providers);
    expect(badge.text).toBe("OpenAI prod · gpt-4o");
    expect(badge.color).not.toBeNull();
  });

  it("falls back to #id for an unresolved provider", () => {
    expect(modelBadge(participants.get("judge_1")!, providers).text).toBe("#9 · claude-3");
  });
});
