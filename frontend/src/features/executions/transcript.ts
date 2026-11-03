import type { JsonObject } from "@/api";
import { roleIconUrl } from "@/assets/icons";
import {
  DIMENSION_THEMES,
  type DimensionKey,
  type DimensionTheme,
} from "@/taxonomy/dimensions";

/**
 * Typed views over the transcript JSON produced by
 * `backend/app/jobs/serialize.py` and the role→dimension colour mapping used to
 * colour-code per-agent messages in the detail view (Req 11.2, 10.6, 13.3).
 *
 * The backend stores transcripts as free-form JSON (`ExecutionInstanceResult
 * .transcript` is a `JsonObject`), so this module narrows that wire shape into
 * the fields the viewer renders, degrading gracefully when a field is absent.
 */

export interface TranscriptUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number | null;
  latency_s: number | null;
}

export interface TranscriptMessage {
  node_id: string;
  round_index: number;
  role: string;
  content: string;
  usage: TranscriptUsage | null;
  metadata: Record<string, unknown>;
  structured: unknown;
}

export interface TranscriptError {
  node_id: string;
  round_index: number;
  message: string;
  attempts: number;
}

export interface TranscriptDecision {
  decision: unknown;
  authority: string | null;
  resolution: string | null;
  detail: Record<string, unknown> | null;
  structured: unknown;
  undecided: boolean;
}

export interface Transcript {
  config_id: number | null;
  config_name: string | null;
  resolved_input: string | null;
  rounds: number;
  messages: TranscriptMessage[];
  usage: TranscriptUsage | null;
  decision: TranscriptDecision | null;
  errors: TranscriptError[];
  notes: string[];
}

/* -------------------------------- parsing -------------------------------- */

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : fallback;
}

function asNullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function parseUsage(value: unknown): TranscriptUsage | null {
  if (!value || typeof value !== "object") return null;
  const u = value as Record<string, unknown>;
  return {
    prompt_tokens: asNumber(u.prompt_tokens),
    completion_tokens: asNumber(u.completion_tokens),
    total_tokens: asNumber(u.total_tokens),
    cost_usd: asNullableNumber(u.cost_usd),
    latency_s: asNullableNumber(u.latency_s),
  };
}

function parseMessage(value: unknown): TranscriptMessage {
  const m = asRecord(value);
  return {
    node_id: asString(m.node_id, "?"),
    round_index: asNumber(m.round_index),
    role: asString(m.role, "debater"),
    content: asString(m.content),
    usage: parseUsage(m.usage),
    metadata: asRecord(m.metadata),
    structured: m.structured ?? null,
  };
}

function parseError(value: unknown): TranscriptError {
  const e = asRecord(value);
  return {
    node_id: asString(e.node_id, "?"),
    round_index: asNumber(e.round_index),
    message: asString(e.message),
    attempts: asNumber(e.attempts),
  };
}

function parseDecision(value: unknown): TranscriptDecision | null {
  if (!value || typeof value !== "object") return null;
  const d = value as Record<string, unknown>;
  return {
    decision: d.decision ?? null,
    authority: typeof d.authority === "string" ? d.authority : null,
    resolution: typeof d.resolution === "string" ? d.resolution : null,
    detail: d.detail ? asRecord(d.detail) : null,
    structured: d.structured ?? null,
    undecided: d.undecided === true,
  };
}

/** Narrow the free-form transcript JSON into the typed view, or `null`. */
export function parseTranscript(value: JsonObject | null): Transcript | null {
  if (!value || typeof value !== "object") return null;
  const t = value as Record<string, unknown>;
  const messages = Array.isArray(t.messages)
    ? t.messages.map(parseMessage)
    : [];
  const errors = Array.isArray(t.errors) ? t.errors.map(parseError) : [];
  const notes = Array.isArray(t.notes)
    ? t.notes.filter((n): n is string => typeof n === "string")
    : [];
  return {
    config_id: asNullableNumber(t.config_id),
    config_name: typeof t.config_name === "string" ? t.config_name : null,
    resolved_input:
      typeof t.resolved_input === "string" ? t.resolved_input : null,
    rounds: asNumber(t.rounds),
    messages,
    usage: parseUsage(t.usage),
    decision: parseDecision(t.decision),
    errors,
    notes,
  };
}

/** Group messages by their round index, ascending. */
export function messagesByRound(
  messages: TranscriptMessage[],
): { round: number; messages: TranscriptMessage[] }[] {
  const map = new Map<number, TranscriptMessage[]>();
  for (const message of messages) {
    const list = map.get(message.round_index) ?? [];
    list.push(message);
    map.set(message.round_index, list);
  }
  return [...map.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([round, msgs]) => ({ round, messages: msgs }));
}

/* ---------------------- role → dimension colour coding ------------------- */

/**
 * Map an agent role to the taxonomy dimension whose colour identity best
 * represents it (Req 13.3, 6.6). Judges/leaders arbitrate the debate, so they
 * take the Agreement identity; summarizers/editors shape the message format, so
 * they take Interaction; everyone else (debaters, verifiers, custom roles) is a
 * participant and takes the Participants identity. This keeps the three
 * dimension colours meaningful when reading a transcript.
 */
export function roleDimension(role: string): DimensionKey {
  const key = role.toLowerCase();
  if (key === "judge" || key === "leader") return "agreement";
  if (key === "summarizer" || key === "editor") return "interaction";
  return "participants";
}

export function roleTheme(role: string): DimensionTheme {
  return DIMENSION_THEMES[roleDimension(role)];
}

/** Resolve the shared SVG icon URL for a role, if one exists. */
export function roleIcon(role: string): string | undefined {
  return roleIconUrl(role);
}
