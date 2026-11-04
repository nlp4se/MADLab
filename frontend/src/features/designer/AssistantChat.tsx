import { useEffect, useMemo, useRef, useState } from "react";
import {
  Loader2,
  MessageSquare,
  MessageSquarePlus,
  Send,
  Sparkles,
  Wrench,
  X,
} from "lucide-react";

import type { JsonObject, ProviderResponse } from "@/api";
import { Markdown } from "@/components/Markdown";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn, WRAP_TEXT } from "@/lib/utils";

import {
  EMPTY_SESSION,
  chatKey,
  historyFor,
  useAssistantChatStore,
  type ChatTurn,
} from "./assistantChatStore";
import { useDesignerStore } from "./designerStore";
import { useProvidersQuery } from "./useProviders";
import { useAssistantChatSend } from "./useAssistant";

/**
 * AI design assistant chat panel (task 11.1).
 *
 * A floating button pinned to the bottom-right of the designer canvas opens a
 * popup panel where the user describes a MAD setup in natural language. Each
 * turn is sent to `POST /api/assistant/design` (via {@link useAssistantDesign})
 * together with the running `history` and the CURRENT artifact read live from
 * the designer store — the model is always called on the backend through the
 * configured provider layer, never from the browser.
 *
 * Replies are either a clarifying `question` (rendered as an assistant turn) or
 * a `proposal`: a short explanation plus a clearly-marked card with an **Apply
 * to canvas** button that loads the proposed artifact into the store
 * (`setArtifactFromAssistant`, which marks the store dirty so the user reviews
 * on the canvas and then clicks the existing Save). Provider + model are chosen
 * per request in the panel header; provider errors come back as assistant turns.
 *
 * Task 11.5: the conversation, provider/model choice, and unsent draft live in
 * the in-memory {@link useAssistantChatStore}, keyed by config id, so closing
 * and reopening the panel (or navigating within the app) keeps them; a page
 * reload clears them. "New chat" clears the current config's history.
 */
export function AssistantChat({ configId }: { configId?: number | null }) {
  const [open, setOpen] = useState(false);
  // Fall back to the config loaded in the designer store.
  const storeConfigId = useDesignerStore((s) => s.configId);
  // A new, unsaved config (task 11.15) has its own draft session, which moves
  // to the config id on the first Save.
  const draftKey = useDesignerStore((s) => s.draftKey);
  const id = configId !== undefined ? configId : storeConfigId;
  const key = id == null && draftKey ? draftKey : chatKey(id);

  return (
    <div className="pointer-events-none absolute inset-0 z-10">
      {open ? (
        <ChatPanel chatKey={key} onClose={() => setOpen(false)} />
      ) : (
        <Button
          type="button"
          size="icon"
          onClick={() => setOpen(true)}
          aria-label="Open the AI design assistant"
          data-testid="assistant-open"
          className="pointer-events-auto absolute bottom-4 right-4 size-12 rounded-full shadow-lg"
        >
          <Sparkles className="size-5" aria-hidden />
        </Button>
      )}
    </div>
  );
}

function ChatPanel({
  chatKey: key,
  onClose,
}: {
  chatKey: string;
  onClose: () => void;
}) {
  const artifact = useDesignerStore((s) => s.artifact);
  const setArtifactFromAssistant = useDesignerStore(
    (s) => s.setArtifactFromAssistant,
  );

  const providersQuery = useProvidersQuery();
  const providers = useMemo(
    () => providersQuery.data ?? [],
    [providersQuery.data],
  );

  // Session state (survives the panel unmounting; see assistantChatStore).
  const session = useAssistantChatStore((s) => s.sessions[key] ?? EMPTY_SESSION);
  const patchSession = useAssistantChatStore((s) => s.patchSession);
  const beginTurn = useAssistantChatStore((s) => s.beginTurn);
  const markApplied = useAssistantChatStore((s) => s.markApplied);
  const clearChat = useAssistantChatStore((s) => s.clearChat);
  const { turns, providerId, model, draft: input, pending } = session;

  const mutation = useAssistantChatSend();

  // Default the provider/model selection to the first configured provider
  // when nothing is chosen yet (or the stored provider no longer exists).
  useEffect(() => {
    if (providers.length === 0) return;
    if (providerId !== null && providers.some((p) => p.id === providerId)) return;
    const first = providers[0];
    patchSession(key, { providerId: first.id, model: first.models[0] ?? "" });
  }, [providers, providerId, key, patchSession]);

  const selectedProvider: ProviderResponse | undefined = providers.find(
    (p) => p.id === providerId,
  );
  const modelOptions = selectedProvider?.models ?? [];

  const transcriptRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Keep the newest turn in view (guard for jsdom, which has no scrollTo).
    const el = transcriptRef.current;
    if (el && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight });
    }
  }, [turns, pending]);

  const canSend =
    providerId !== null &&
    model.trim().length > 0 &&
    input.trim().length > 0 &&
    !pending;

  const handleSend = () => {
    if (providerId === null || !model || !input.trim() || pending) return;
    const message = input.trim();
    // History = the turns BEFORE this message (plain messages only; a
    // proposal's artifact is state, not something to replay as chat text).
    const history = historyFor(turns);
    const generation = session.generation;
    beginTurn(key, message);

    // Replies are appended by the mutation-level handlers, keyed by the
    // session captured here, so they land even if the panel is closed.
    mutation.mutate({
      chatKey: key,
      generation,
      body: {
        provider_id: providerId,
        model,
        message,
        history,
        artifact: artifact as unknown as JsonObject | null,
      },
    });
  };

  return (
    <div
      role="dialog"
      aria-label="AI design assistant"
      data-testid="assistant-panel"
      className="pointer-events-auto absolute bottom-4 right-4 flex h-[32rem] w-96 max-w-[calc(100%-2rem)] flex-col overflow-hidden rounded-xl border bg-background shadow-2xl"
    >
      {/* Header: title + provider/model selectors. */}
      <div className="flex flex-col gap-2 border-b bg-muted/40 p-3">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="size-4 text-primary" aria-hidden />
            Design assistant
          </span>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="size-7"
              aria-label="New chat"
              title="New chat — clear this configuration's conversation"
              data-testid="assistant-new-chat"
              disabled={turns.length === 0 && !pending && input.length === 0}
              onClick={() => clearChat(key)}
            >
              <MessageSquarePlus className="size-4" aria-hidden />
            </Button>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="size-7"
              aria-label="Close the assistant"
              title="Close — the conversation is kept until you reload the page"
              onClick={onClose}
            >
              <X className="size-4" aria-hidden />
            </Button>
          </div>
        </div>
        <div className="flex gap-2">
          <label className="flex-1 text-xs">
            <span className="sr-only">Provider</span>
            <Select
              aria-label="Provider"
              className="h-8 text-xs"
              value={providerId ?? ""}
              onChange={(e) => {
                const id = Number(e.target.value);
                const p = providers.find((x) => x.id === id);
                patchSession(key, { providerId: id, model: p?.models[0] ?? "" });
              }}
            >
              {providers.length === 0 ? (
                <option value="">No providers configured</option>
              ) : null}
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </label>
          <label className="flex-1 text-xs">
            <span className="sr-only">Model</span>
            <Select
              aria-label="Model"
              className="h-8 text-xs"
              value={model}
              onChange={(e) => patchSession(key, { model: e.target.value })}
              disabled={modelOptions.length === 0}
            >
              {modelOptions.length === 0 ? (
                <option value="">No models</option>
              ) : null}
              {modelOptions.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Select>
          </label>
        </div>
      </div>

      {/* Transcript. */}
      <div
        ref={transcriptRef}
        data-testid="assistant-transcript"
        className="flex-1 space-y-3 overflow-y-auto p-3"
      >
        {turns.length === 0 ? (
          <p className="flex items-start gap-2 text-xs text-muted-foreground">
            <MessageSquare className="mt-0.5 size-4 shrink-0" aria-hidden />
            Describe the debate you want — number of debaters, roles, rounds, and
            how a decision is reached. I’ll ask follow-ups, then propose a
            configuration you can review and apply.
          </p>
        ) : null}

        {turns.map((turn, i) =>
          turn.kind === "proposal" ? (
            <ProposalCard
              key={i}
              turn={turn}
              onApply={() => {
                setArtifactFromAssistant(turn.artifact);
                markApplied(key, i);
              }}
            />
          ) : (
            <MessageBubble
              key={i}
              role={turn.role}
              content={turn.content}
              error={turn.error === true}
            />
          ),
        )}

        {pending ? (
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
            Thinking…
          </p>
        ) : null}
      </div>

      {/* Composer. */}
      <div className="border-t p-3">
        <Textarea
          aria-label="Message the design assistant"
          placeholder="e.g. Two debaters arguing for and against, three rounds, a judge decides."
          rows={2}
          value={input}
          onChange={(e) => patchSession(key, { draft: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (canSend) handleSend();
            }
          }}
          className="mb-2 resize-none text-sm"
        />
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-muted-foreground">
            Enter to send · Shift+Enter for a new line
          </span>
          <Button
            type="button"
            size="sm"
            onClick={handleSend}
            disabled={!canSend}
            data-testid="assistant-send"
          >
            <Send className="size-3.5" aria-hidden />
            Send
          </Button>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({
  role,
  content,
  error = false,
}: {
  role: "user" | "assistant";
  content: string;
  /** A request failure: shown as plain text, never as Markdown. */
  error?: boolean;
}) {
  const isUser = role === "user";
  // Only the model's own replies render Markdown (task 11.16); the user's
  // turns and error text stay literal.
  const markdown = !isUser && !error;
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      {markdown ? (
        <Markdown
          data-testid={`assistant-turn-${role}`}
          className="max-w-[85%] rounded-lg bg-muted px-3 py-2 text-sm text-foreground"
        >
          {content}
        </Markdown>
      ) : (
        <div
          data-testid={`assistant-turn-${role}`}
          className={cn(
            "max-w-[85%] rounded-lg px-3 py-2 text-sm",
            WRAP_TEXT,
            isUser
              ? "bg-primary text-primary-foreground"
              : "bg-muted text-foreground",
          )}
        >
          {content}
        </div>
      )}
    </div>
  );
}

function ProposalCard({
  turn,
  onApply,
}: {
  turn: Extract<ChatTurn, { kind: "proposal" }>;
  onApply: () => void;
}) {
  const applied = turn.applied === true;
  const name =
    typeof turn.artifact.name === "string" ? turn.artifact.name : "Configuration";

  return (
    <div
      data-testid="assistant-proposal"
      className="rounded-lg border border-primary/40 bg-primary/5 p-3"
    >
      <div className="mb-1 flex items-center gap-2">
        <Badge variant="default" className="gap-1">
          <Sparkles className="size-3" aria-hidden />
          Proposal
        </Badge>
        <span className="truncate text-xs font-medium">{name}</span>
      </div>

      {turn.message ? (
        <Markdown
          className="mb-2 text-sm text-foreground"
          data-testid="assistant-proposal-message"
        >
          {turn.message}
        </Markdown>
      ) : null}

      {turn.underDevelopment.length > 0 ? (
        <div className="mb-2 flex flex-wrap items-center gap-1">
          <span className="flex items-center gap-1 text-[10px] text-amber-700 dark:text-amber-400">
            <Wrench className="size-3" aria-hidden />
            Under development:
          </span>
          {turn.underDevelopment.map((key) => (
            <span
              key={key}
              className="rounded-full border border-amber-500/50 px-1.5 py-0.5 text-[10px]"
            >
              {key}
            </span>
          ))}
        </div>
      ) : null}

      <Button
        type="button"
        size="sm"
        data-testid="assistant-apply"
        onClick={onApply}
      >
        {applied ? "Applied — review on canvas" : "Apply to canvas"}
      </Button>
    </div>
  );
}
