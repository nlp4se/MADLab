import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Gavel,
  ListChecks,
  Pause,
  Play,
  StepBack,
  StepForward,
} from "lucide-react";

import type {
  ExecutionInstanceResult,
  JsonObject,
  ProviderResponse,
} from "@/api";
import { roleIconUrl } from "@/assets/icons";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { roleColor } from "@/features/designer/nodeStyle";
import { useProvidersQuery } from "@/features/designer/useProviders";
import { cn, SCROLL_PRE, WRAP_TEXT } from "@/lib/utils";
import { DIMENSION_THEMES } from "@/taxonomy/dimensions";

import {
  buildChatTimeline,
  debateRoundCount,
  modelBadge,
  participantsFromSnapshot,
  type ChatItem,
} from "./chatTimeline";
import { outputSchemaFromSnapshot, structuredMessageBody } from "./decisionDisplay";
import { DecisionContent, DisplayValueView } from "./DecisionView";
import { parseTranscript, roleTheme, type TranscriptUsage } from "./transcript";

/**
 * Chat-style replay of one execution instance's debate (task 11.3, Req 11.2,
 * 13.3).
 *
 * Renders the stored transcript as a group chat: the task input, round
 * dividers, every agent turn attributed to its participant (label, role
 * colour, provider-name model badge from the config snapshot), recoverable
 * errors inline, the verdict phase and the final decision. Opens fully
 * revealed; playback controls re-reveal the items one at a time with a typing
 * indicator so the user can watch the discussion unfold.
 */
export interface DebateChatDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  instance: ExecutionInstanceResult;
  configSnapshot: JsonObject;
  configName: string | null;
}

/** Base delays (ms at 1x): typing indicator before a turn, and other items. */
export const TYPING_DELAY_MS = 900;
export const STEP_DELAY_MS = 600;
const SPEEDS = [0.5, 1, 2] as const;

export function DebateChatDialog({
  open,
  onOpenChange,
  instance,
  configSnapshot,
  configName,
}: DebateChatDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="flex h-[85vh] max-w-3xl flex-col p-0"
      >
        {/* The body only mounts while open, so closing unmounts it and its
            playback timers are cleared by the effect cleanup. */}
        <DebateChatBody
          instance={instance}
          configSnapshot={configSnapshot}
          configName={configName}
          titleId={titleId}
          descriptionId={descriptionId}
        />
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------- playback -------------------------------- */

function usePrefersReducedMotion(): boolean {
  const query = "(prefers-reduced-motion: reduce)";
  const supported =
    typeof window !== "undefined" && typeof window.matchMedia === "function";
  const [reduced, setReduced] = useState(
    () => supported && window.matchMedia(query).matches,
  );
  useEffect(() => {
    if (!supported) return;
    const mq = window.matchMedia(query);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, [supported]);
  return reduced;
}

/**
 * Reveal state for the timeline. `revealed === null` means "show everything"
 * (the static review the dialog opens in, which also follows new items).
 */
function usePlayback(items: ChatItem[], reducedMotion: boolean) {
  const total = items.length;
  const [revealed, setRevealed] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [typing, setTyping] = useState(false);
  const [speed, setSpeed] = useState<number>(1);
  const shown = revealed == null ? total : Math.min(revealed, total);

  useEffect(() => {
    if (!playing) return;
    if (shown >= total) {
      setPlaying(false);
      setTyping(false);
      return;
    }
    const showTyping = items[shown]?.kind === "message" && !reducedMotion;
    setTyping(showTyping);
    const delay = (showTyping ? TYPING_DELAY_MS : STEP_DELAY_MS) / speed;
    const timer = window.setTimeout(() => {
      setTyping(false);
      setRevealed(shown + 1);
    }, delay);
    return () => window.clearTimeout(timer);
  }, [playing, shown, total, items, speed, reducedMotion]);

  const pause = useCallback(() => {
    setPlaying(false);
    setTyping(false);
  }, []);

  const togglePlay = useCallback(() => {
    if (playing) {
      pause();
      return;
    }
    // From the fully revealed state, restart at the first item.
    if (shown >= total) setRevealed(Math.min(1, total));
    else setRevealed(shown);
    setPlaying(true);
  }, [playing, pause, shown, total]);

  const stepForward = useCallback(() => {
    pause();
    setRevealed(Math.min(total, shown + 1));
  }, [pause, shown, total]);

  const stepBack = useCallback(() => {
    pause();
    setRevealed(Math.max(0, shown - 1));
  }, [pause, shown]);

  const showAll = useCallback(() => {
    pause();
    setRevealed(null);
  }, [pause]);

  return {
    shown,
    total,
    playing,
    typing,
    speed,
    setSpeed,
    togglePlay,
    stepForward,
    stepBack,
    showAll,
  };
}

/* --------------------------------- body ---------------------------------- */

function DebateChatBody({
  instance,
  configSnapshot,
  configName,
  titleId,
  descriptionId,
}: Omit<DebateChatDialogProps, "open" | "onOpenChange"> & {
  titleId: string;
  descriptionId: string;
}) {
  const transcript = useMemo(
    () => parseTranscript(instance.transcript),
    [instance.transcript],
  );
  const participants = useMemo(
    () => participantsFromSnapshot(configSnapshot),
    [configSnapshot],
  );
  const outputSchema = useMemo(
    () => outputSchemaFromSnapshot(configSnapshot),
    [configSnapshot],
  );
  const fallbackInput = useMemo(() => {
    const input = instance.resolved_input as Record<string, unknown> | null;
    const text = input?.["resolved_input"];
    return typeof text === "string" ? text : null;
  }, [instance.resolved_input]);
  const items = useMemo(
    () => buildChatTimeline(transcript, participants, fallbackInput),
    [transcript, participants, fallbackInput],
  );
  const providers = useProvidersQuery().data ?? [];
  const reducedMotion = usePrefersReducedMotion();
  const playback = usePlayback(items, reducedMotion);

  const visible = items.slice(0, playback.shown);
  const nextItem = items[playback.shown];
  const typingLabel =
    playback.typing && nextItem?.kind === "message"
      ? nextItem.participant.label
      : null;

  // Keep the newest revealed item in view, but leave the initial static
  // review at the top (guard for jsdom, which has no scrollTo).
  const scrollRef = useRef<HTMLDivElement>(null);
  const firstRender = useRef(true);
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    const el = scrollRef.current;
    if (el && typeof el.scrollTo === "function") {
      el.scrollTo({
        top: el.scrollHeight,
        behavior: reducedMotion ? "auto" : "smooth",
      });
    }
  }, [playback.shown, typingLabel, reducedMotion]);

  const messageCount = transcript?.messages.length ?? 0;
  const rounds = transcript ? debateRoundCount(transcript) : 0;
  const name = configName ?? transcript?.config_name ?? "Execution";

  return (
    <>
      <header className="border-b px-6 pb-3 pt-5">
        <div className="pr-8">
          <DialogTitle id={titleId} className="truncate">
            {name} · Instance #{instance.instance_index}
          </DialogTitle>
          <DialogDescription id={descriptionId} className="mt-1">
            Debate replay · {participants.size || "?"} participants · {rounds}{" "}
            {rounds === 1 ? "round" : "rounds"} · {messageCount}{" "}
            {messageCount === 1 ? "turn" : "turns"}
          </DialogDescription>
        </div>

        {items.length > 0 ? (
          <div
            className="mt-3 flex flex-wrap items-center gap-2"
            role="toolbar"
            aria-label="Playback controls"
          >
            <Button
              size="sm"
              variant="outline"
              onClick={playback.stepBack}
              disabled={playback.shown === 0}
              aria-label="Step back"
            >
              <StepBack aria-hidden />
            </Button>
            <Button
              size="sm"
              onClick={playback.togglePlay}
              aria-label={playback.playing ? "Pause" : "Play"}
            >
              {playback.playing ? <Pause aria-hidden /> : <Play aria-hidden />}
              {playback.playing ? "Pause" : "Play"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={playback.stepForward}
              disabled={playback.shown >= playback.total}
              aria-label="Step forward"
            >
              <StepForward aria-hidden />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={playback.showAll}
              aria-label="Show all"
            >
              <ListChecks aria-hidden />
              Show all
            </Button>
            <Select
              aria-label="Playback speed"
              className="h-9 w-20"
              value={String(playback.speed)}
              onChange={(e) => playback.setSpeed(Number(e.target.value))}
            >
              {SPEEDS.map((s) => (
                <option key={s} value={String(s)}>
                  {s}x
                </option>
              ))}
            </Select>
            <span
              className="ml-auto text-xs tabular-nums text-muted-foreground"
              data-testid="playback-progress"
              aria-label="Playback progress"
            >
              {playback.shown} / {playback.total}
            </span>
          </div>
        ) : null}
      </header>

      <div
        ref={scrollRef}
        className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden bg-muted/20 px-6 py-4"
        data-testid="chat-scroll"
      >
        {items.length === 0 && !instance.error ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No transcript was recorded for this instance.
          </p>
        ) : null}

        <ol className="space-y-0" aria-label="Debate timeline">
          {visible.map((item) => (
            <ChatItemView
              key={item.key}
              item={item}
              providers={providers}
              outputSchema={outputSchema}
            />
          ))}
        </ol>

        {transcript && messageCount === 0 && playback.shown >= playback.total ? (
          <p className="mt-4 text-center text-sm text-muted-foreground">
            No agent messages were recorded for this instance.
          </p>
        ) : null}

        {typingLabel ? (
          <p
            className="mt-3 flex items-center gap-2 pl-12 text-xs italic text-muted-foreground"
            role="status"
            data-testid="typing-indicator"
          >
            <span className="flex gap-0.5" aria-hidden>
              <span className="size-1.5 rounded-full bg-muted-foreground/60 motion-safe:animate-bounce" />
              <span className="size-1.5 rounded-full bg-muted-foreground/60 motion-safe:animate-bounce [animation-delay:150ms]" />
              <span className="size-1.5 rounded-full bg-muted-foreground/60 motion-safe:animate-bounce [animation-delay:300ms]" />
            </span>
            {typingLabel} is typing…
          </p>
        ) : null}

        {instance.error && playback.shown >= playback.total ? (
          <div
            role="alert"
            className="mt-4 rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive"
          >
            <p className="font-medium">Instance failed</p>
            <p className={cn("mt-1", WRAP_TEXT)}>{instance.error}</p>
          </div>
        ) : null}
      </div>
    </>
  );
}

/* --------------------------------- items --------------------------------- */

function ChatItemView({
  item,
  providers,
  outputSchema,
}: {
  item: ChatItem;
  providers: ProviderResponse[];
  outputSchema: unknown;
}) {
  switch (item.kind) {
    case "task":
      return (
        <li className="mb-2 flex justify-center" data-testid="chat-item" data-kind="task">
          <div className="w-full max-w-xl rounded-xl border-2 border-emerald-500 bg-emerald-500/10 px-4 py-3 shadow-sm">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-400">
              Task
            </p>
            <p className={cn("text-sm", WRAP_TEXT)}>{item.text}</p>
          </div>
        </li>
      );
    case "divider":
      return (
        <li
          className="my-4 flex items-center gap-3"
          data-testid="chat-item"
          data-kind="divider"
          data-variant={item.variant}
        >
          <span className="h-px flex-1 bg-border" aria-hidden />
          <span
            className={cn(
              "inline-flex items-center gap-1 text-xs font-medium uppercase tracking-wide",
              item.variant === "verdict"
                ? "text-amber-700 dark:text-amber-400"
                : "text-muted-foreground",
            )}
          >
            {item.variant === "verdict" ? (
              <Gavel className="size-3.5" aria-hidden />
            ) : null}
            {item.label}
          </span>
          <span className="h-px flex-1 bg-border" aria-hidden />
        </li>
      );
    case "message":
      return <MessageBubble item={item} providers={providers} />;
    case "error":
      return (
        <li
          className="my-2 ml-12 flex items-start gap-2 rounded-md border border-amber-500/50 bg-amber-500/5 px-3 py-2 text-xs"
          data-testid="chat-item"
          data-kind="error"
        >
          <AlertTriangle
            className="mt-0.5 size-3.5 shrink-0 text-amber-600 dark:text-amber-400"
            aria-hidden
          />
          <span className={cn("min-w-0", WRAP_TEXT)} data-testid="chat-error-text">
            <span className="font-medium text-amber-700 dark:text-amber-400">
              {item.participant.label}'s call failed after {item.error.attempts}{" "}
              {item.error.attempts === 1 ? "attempt" : "attempts"}
            </span>
            {item.error.message ? (
              <span className="text-muted-foreground">: {item.error.message}</span>
            ) : null}
          </span>
        </li>
      );
    case "decision":
      return <DecisionBubble item={item} outputSchema={outputSchema} />;
    case "note":
      return (
        <li
          className={cn("mt-2 text-center text-xs text-muted-foreground", WRAP_TEXT)}
          data-testid="chat-item"
          data-kind="note"
        >
          {item.text}
        </li>
      );
  }
}

function Avatar({ role }: { role: string }) {
  const color = roleColor(role);
  const icon = roleIconUrl(role);
  const Fallback = DIMENSION_THEMES.participants.icon;
  return (
    <span
      className="flex size-9 items-center justify-center rounded-full border-2"
      style={{ borderColor: color.solid, background: color.soft, color: color.solid }}
      aria-hidden
    >
      {icon ? (
        <img src={icon} alt="" className="size-5" />
      ) : (
        <Fallback className="size-5" />
      )}
    </span>
  );
}

function usageText(usage: TranscriptUsage): string {
  const parts = [`${usage.total_tokens} tok`];
  if (usage.latency_s != null) parts.push(`${usage.latency_s.toFixed(2)}s`);
  if (usage.cost_usd != null) parts.push(`$${usage.cost_usd.toFixed(4)}`);
  return parts.join(" · ");
}

function MessageBubble({
  item,
  providers,
}: {
  item: Extract<ChatItem, { kind: "message" }>;
  providers: ProviderResponse[];
}) {
  const { message, participant, grouped } = item;
  const color = roleColor(message.role);
  const badge = modelBadge(participant, providers);
  // A reply that is just its structured JSON reads as a key/value list; the
  // raw text stays one click away.
  const structuredBody = structuredMessageBody(message.content, message.structured);

  return (
    <li
      className={cn("flex gap-3", grouped ? "mt-1" : "mt-4")}
      data-testid="chat-item"
      data-kind="message"
      data-node-id={message.node_id}
      data-role={message.role}
      data-dimension={roleTheme(message.role).key}
    >
      <div className="w-9 shrink-0">{grouped ? null : <Avatar role={message.role} />}</div>
      <div className="min-w-0 flex-1">
        {grouped ? null : (
          <div className="mb-1 flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-semibold" data-testid="chat-author">
              {participant.label}
            </span>
            <span
              className="rounded-full px-2 py-0.5 text-[11px] font-medium capitalize"
              style={{ background: color.soft, color: color.solid }}
            >
              {message.role}
            </span>
            {badge.text ? (
              <span
                className="max-w-full truncate rounded-full border px-2 py-0.5 text-[11px] font-medium"
                style={
                  badge.color
                    ? {
                        borderColor: badge.color.solid,
                        background: badge.color.soft,
                        color: badge.color.solid,
                      }
                    : undefined
                }
                data-testid="chat-model-badge"
                title={badge.text}
              >
                {badge.text}
              </span>
            ) : null}
          </div>
        )}
        <div
          className="rounded-2xl rounded-tl-sm border border-l-4 bg-card px-3.5 py-2.5 text-sm shadow-sm"
          style={{ borderLeftColor: color.solid }}
        >
          {structuredBody ? (
            <>
              <div data-testid="message-structured-body">
                <DisplayValueView value={structuredBody} />
              </div>
              <details className="mt-2 text-xs">
                <summary className="cursor-pointer text-muted-foreground">
                  Raw reply
                </summary>
                <pre
                  className={cn(
                    "mt-1 max-h-60 overflow-auto rounded bg-muted/40 p-2",
                    SCROLL_PRE,
                    WRAP_TEXT,
                  )}
                >
                  {message.content}
                </pre>
              </details>
            </>
          ) : (
            <p className={WRAP_TEXT} data-testid="chat-message-text">
              {message.content}
            </p>
          )}
          {message.structured != null ? (
            <details className="mt-2 text-xs">
              <summary className="cursor-pointer text-muted-foreground">
                Structured output
              </summary>
              <pre
                className={cn("mt-1 max-h-60 overflow-auto rounded bg-muted/40 p-2", SCROLL_PRE)}
                data-testid="chat-message-structured"
              >
                {JSON.stringify(message.structured, null, 2)}
              </pre>
            </details>
          ) : null}
        </div>
        {message.usage ? (
          <p className="mt-0.5 pl-1 text-[11px] text-muted-foreground">
            {usageText(message.usage)}
          </p>
        ) : null}
      </div>
    </li>
  );
}

function DecisionBubble({
  item,
  outputSchema,
}: {
  item: Extract<ChatItem, { kind: "decision" }>;
  outputSchema: unknown;
}) {
  const { decision } = item;
  const theme = roleTheme("judge");
  return (
    <li
      className="mt-4 flex justify-center"
      data-testid="chat-item"
      data-kind="decision"
    >
      <div
        className={cn(
          "w-full max-w-xl rounded-xl border-2 px-4 py-3 shadow-sm",
          theme.classes.border,
          theme.classes.bgMuted,
        )}
        data-testid="chat-final-decision"
        data-dimension="agreement"
      >
        <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <Gavel className="size-3.5" aria-hidden />
          Final decision
        </p>
        <DecisionContent decision={decision} outputSchema={outputSchema} />
      </div>
    </li>
  );
}
