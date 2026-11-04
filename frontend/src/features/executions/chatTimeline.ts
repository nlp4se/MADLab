import type { JsonObject, ProviderResponse } from "@/api";
import { providerColor, type SwatchColor } from "@/features/designer/nodeStyle";

import type {
  Transcript,
  TranscriptDecision,
  TranscriptError,
  TranscriptMessage,
} from "./transcript";

/**
 * Pure helpers behind the chat-style debate replay (task 11.3, Req 11.2, 13.3).
 *
 * `buildChatTimeline` flattens a parsed transcript into the ordered list of
 * chat items the replay dialog reveals one at a time:
 *
 *   1. the task input (always first when present),
 *   2. for every debate round, a "Round N" divider followed by that round's
 *      agent turns in recorded order, then that round's recoverable errors,
 *   3. a "Verdict" divider, the post-debate turns (the judge, recorded with
 *      `round_index >= rounds`) and their errors,
 *   4. the final decision as the closing message,
 *   5. any run notes.
 *
 * Messages are attributed to participants via the immutable config snapshot so
 * the chat shows labels, roles and models instead of opaque node ids.
 */

export interface ChatParticipant {
  id: string;
  label: string;
  roles: string[];
  providerId: string | null;
  modelKey: string | null;
}

export type ChatItem =
  | { kind: "task"; key: string; text: string }
  | { kind: "divider"; key: string; variant: "round" | "verdict"; label: string }
  | {
      kind: "message";
      key: string;
      message: TranscriptMessage;
      participant: ChatParticipant;
      /** True when the previous item is a message from the same node. */
      grouped: boolean;
    }
  | {
      kind: "error";
      key: string;
      error: TranscriptError;
      participant: ChatParticipant;
    }
  | { kind: "decision"; key: string; decision: TranscriptDecision }
  | { kind: "note"; key: string; text: string };

/* ----------------------------- participants ------------------------------ */

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function idString(value: unknown): string | null {
  if (typeof value === "string" && value) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

/** Index the snapshot's `participants.nodes[]` by node id. */
export function participantsFromSnapshot(
  snapshot: JsonObject | null | undefined,
): Map<string, ChatParticipant> {
  const map = new Map<string, ChatParticipant>();
  const nodes = asRecord(asRecord(snapshot)["participants"])["nodes"];
  if (!Array.isArray(nodes)) return map;
  for (const raw of nodes) {
    const node = asRecord(raw);
    const id = idString(node["id"]);
    if (!id) continue;
    const baseModel = asRecord(node["base_model"]);
    const roles = Array.isArray(node["roles"])
      ? (node["roles"] as unknown[]).filter((r): r is string => typeof r === "string")
      : [];
    map.set(id, {
      id,
      label: typeof node["label"] === "string" && node["label"] ? (node["label"] as string) : id,
      roles,
      providerId: idString(baseModel["provider_id"]),
      modelKey:
        typeof baseModel["model_key"] === "string" && baseModel["model_key"]
          ? (baseModel["model_key"] as string)
          : null,
    });
  }
  return map;
}

/** Resolve a node id to its participant, falling back to the bare id. */
export function resolveParticipant(
  participants: Map<string, ChatParticipant>,
  nodeId: string,
  role?: string,
): ChatParticipant {
  return (
    participants.get(nodeId) ?? {
      id: nodeId,
      label: nodeId,
      roles: role ? [role] : [],
      providerId: null,
      modelKey: null,
    }
  );
}

export interface ModelBadge {
  /** e.g. "OpenAI prod · gpt-4o"; null when the node has no model binding. */
  text: string | null;
  color: SwatchColor | null;
}

/**
 * Build the "ProviderName · model_key" badge. The provider is shown by NAME;
 * an unresolved provider falls back to `#id` (never the raw id alone).
 */
export function modelBadge(
  participant: ChatParticipant,
  providers: ProviderResponse[],
): ModelBadge {
  const provider = participant.providerId
    ? providers.find((p) => String(p.id) === participant.providerId)
    : undefined;
  const providerName =
    provider?.name ?? (participant.providerId ? `#${participant.providerId}` : null);
  if (!providerName && !participant.modelKey) return { text: null, color: null };
  const text = [providerName, participant.modelKey ?? "no model"]
    .filter(Boolean)
    .join(" · ");
  const color = provider
    ? providerColor(provider.kind || provider.name)
    : participant.providerId
      ? providerColor(participant.providerId)
      : null;
  return { text, color };
}

/* -------------------------------- timeline -------------------------------- */

/**
 * Number of debate rounds; messages at or past it belong to the verdict
 * phase. Falls back to the highest non-judge round when `rounds` is missing.
 */
export function debateRoundCount(transcript: Transcript): number {
  if (transcript.rounds > 0) return transcript.rounds;
  const debate = transcript.messages.filter((m) => m.role.toLowerCase() !== "judge");
  if (debate.length === 0) return 0;
  return Math.max(...debate.map((m) => m.round_index)) + 1;
}

export function buildChatTimeline(
  transcript: Transcript | null,
  participants: Map<string, ChatParticipant>,
  fallbackInput: string | null = null,
): ChatItem[] {
  const items: ChatItem[] = [];
  const taskText = transcript?.resolved_input ?? fallbackInput;
  if (taskText) items.push({ kind: "task", key: "task", text: taskText });
  if (!transcript) return items;

  const rounds = debateRoundCount(transcript);
  let lastNode: string | null = null;

  const pushMessage = (message: TranscriptMessage, index: number) => {
    items.push({
      kind: "message",
      key: `msg-${index}`,
      message,
      participant: resolveParticipant(participants, message.node_id, message.role),
      grouped: lastNode === message.node_id,
    });
    lastNode = message.node_id;
  };
  const pushError = (error: TranscriptError, index: number) => {
    items.push({
      kind: "error",
      key: `err-${index}`,
      error,
      participant: resolveParticipant(participants, error.node_id),
    });
    lastNode = null;
  };
  const pushDivider = (variant: "round" | "verdict", label: string, key: string) => {
    items.push({ kind: "divider", key, variant, label });
    lastNode = null;
  };

  const indexedMessages = transcript.messages.map((m, i) => ({ m, i }));
  const indexedErrors = transcript.errors.map((e, i) => ({ e, i }));

  // Debate rounds: every round that has a message or an error, ascending.
  const debateRounds = new Set<number>();
  for (const { m } of indexedMessages) if (m.round_index < rounds) debateRounds.add(m.round_index);
  for (const { e } of indexedErrors) if (e.round_index < rounds) debateRounds.add(e.round_index);
  for (const round of [...debateRounds].sort((a, b) => a - b)) {
    pushDivider("round", `Round ${round + 1}`, `round-${round}`);
    for (const { m, i } of indexedMessages) if (m.round_index === round) pushMessage(m, i);
    for (const { e, i } of indexedErrors) if (e.round_index === round) pushError(e, i);
  }

  // Verdict phase: post-debate turns (judge), their errors, then the decision.
  const verdictMessages = indexedMessages.filter(({ m }) => m.round_index >= rounds);
  const verdictErrors = indexedErrors.filter(({ e }) => e.round_index >= rounds);
  if (verdictMessages.length > 0 || verdictErrors.length > 0 || transcript.decision) {
    pushDivider("verdict", "Verdict", "verdict");
    for (const { m, i } of verdictMessages) pushMessage(m, i);
    for (const { e, i } of verdictErrors) pushError(e, i);
  }
  if (transcript.decision) {
    items.push({ kind: "decision", key: "decision", decision: transcript.decision });
  }

  transcript.notes.forEach((text, i) => items.push({ kind: "note", key: `note-${i}`, text }));
  return items;
}
