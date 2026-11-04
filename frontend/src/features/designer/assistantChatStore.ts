import { create } from "zustand";

import type { AssistantDesignResponse, AssistantMessage, JsonObject } from "@/api";

/**
 * Session-scoped AI design assistant chat state (task 11.5).
 *
 * A plain zustand store with NO persist middleware: it lives in memory for the
 * lifetime of the page, so closing/reopening the assistant panel or navigating
 * inside the app keeps the conversation (and the provider/model choice), while
 * a page reload or closing the window clears it.
 *
 * Sessions are keyed by config id ({@link chatKey}), so each configuration has
 * its own conversation. Replies are appended by key from mutation-level
 * callbacks (see `useAssistantChatSend`), so a reply that arrives after the
 * panel was closed still lands in the right conversation.
 */

/** A rendered chat turn: a plain message, or an assistant proposal card. */
export type ChatTurn =
  | {
      kind: "message";
      role: "user" | "assistant";
      content: string;
      /** A request failure shown as an assistant turn (rendered as plain text). */
      error?: boolean;
    }
  | {
      kind: "proposal";
      message: string;
      artifact: JsonObject;
      underDevelopment: string[];
      /** Set once the user clicked "Apply to canvas" for this proposal. */
      applied?: boolean;
    };

export interface ChatSession {
  turns: ChatTurn[];
  /** Selected provider/model; null/"" = not chosen yet (panel picks a default). */
  providerId: number | null;
  model: string;
  /** Unsent composer text. */
  draft: string;
  /** A request is in flight for this conversation. */
  pending: boolean;
  /**
   * Bumped by "New chat"; a reply only lands if the generation it was sent in
   * is still current (so a late reply never leaks into a fresh conversation).
   */
  generation: number;
}

export const EMPTY_SESSION: ChatSession = Object.freeze({
  turns: [],
  providerId: null,
  model: "",
  draft: "",
  pending: false,
  generation: 0,
}) as ChatSession;

/** The session key for a config id (null = a not-yet-loaded/unsaved config). */
export function chatKey(configId: number | null | undefined): string {
  return configId == null ? "unsaved" : String(configId);
}

interface AssistantChatState {
  sessions: Record<string, ChatSession>;

  /** Shallow-merge fields into a session (creating it if needed). */
  patchSession: (key: string, patch: Partial<ChatSession>) => void;
  /** Append the user's turn and mark the conversation pending. */
  beginTurn: (key: string, content: string) => void;
  /** Append the assistant's reply (if `generation` is still current). */
  receiveReply: (key: string, generation: number, res: AssistantDesignResponse) => void;
  /** Append a failure as an assistant turn (if `generation` is still current). */
  receiveError: (key: string, generation: number, err: Error) => void;
  /** Flag a proposal turn as applied to the canvas. */
  markApplied: (key: string, index: number) => void;
  /** "New chat": drop the history (keeps the provider/model choice). */
  clearChat: (key: string) => void;
  /**
   * Move a session to another key (task 11.15: a new config's draft session
   * moves to its id on the first Save). Replies still in flight for `from`
   * land in `to` (draft keys are unique, so the alias never misroutes).
   */
  moveSession: (from: string, to: string) => void;
  /** Drop every session (tests). */
  resetAll: () => void;
}

export const useAssistantChatStore = create<AssistantChatState>((set, get) => {
  const session = (key: string) => get().sessions[key] ?? EMPTY_SESSION;
  const write = (key: string, next: ChatSession) =>
    set((s) => ({ sessions: { ...s.sessions, [key]: next } }));

  /** Moved sessions: old key -> new key (see `moveSession`). */
  const aliases: Record<string, string> = {};
  const resolve = (key: string): string => {
    let k = key;
    const seen = new Set<string>();
    while (aliases[k] !== undefined && !seen.has(k)) {
      seen.add(k);
      k = aliases[k];
    }
    return k;
  };

  /** Append a reply turn unless "New chat" happened since it was sent. */
  const land = (sentKey: string, generation: number, turn: ChatTurn) => {
    const key = resolve(sentKey);
    const cur = session(key);
    if (cur.generation !== generation) return;
    write(key, { ...cur, turns: [...cur.turns, turn], pending: false });
  };

  return {
    sessions: {},

    patchSession: (key, patch) => write(key, { ...session(key), ...patch }),

    beginTurn: (key, content) => {
      const cur = session(key);
      write(key, {
        ...cur,
        turns: [...cur.turns, { kind: "message", role: "user", content }],
        draft: "",
        pending: true,
      });
    },

    receiveReply: (key, generation, res) =>
      land(
        key,
        generation,
        res.mode === "proposal" && res.artifact
          ? {
              kind: "proposal",
              message: res.message,
              artifact: res.artifact,
              underDevelopment: res.under_development,
            }
          : { kind: "message", role: "assistant", content: res.message },
      ),

    receiveError: (key, generation, err) =>
      land(key, generation, {
        kind: "message",
        role: "assistant",
        content: `The assistant request failed: ${err.message}`,
        error: true,
      }),

    markApplied: (key, index) => {
      const cur = session(key);
      const turn = cur.turns[index];
      if (turn?.kind !== "proposal") return;
      const turns = cur.turns.slice();
      turns[index] = { ...turn, applied: true };
      write(key, { ...cur, turns });
    },

    clearChat: (key) => {
      const cur = session(key);
      write(key, {
        ...cur,
        turns: [],
        draft: "",
        pending: false,
        generation: cur.generation + 1,
      });
    },

    moveSession: (from, to) => {
      if (from === to) return;
      aliases[from] = to;
      const moved = get().sessions[from];
      if (!moved) return;
      set((s) => {
        const { [from]: _removed, ...rest } = s.sessions;
        void _removed;
        return { sessions: { ...rest, [to]: moved } };
      });
    },

    resetAll: () => {
      for (const k of Object.keys(aliases)) delete aliases[k];
      set({ sessions: {} });
    },
  };
});

/** The conversation history sent to the backend: plain message turns only. */
export function historyFor(turns: ChatTurn[]): AssistantMessage[] {
  return turns
    .filter((t): t is Extract<ChatTurn, { kind: "message" }> => t.kind === "message")
    .map((t) => ({ role: t.role, content: t.content }));
}
