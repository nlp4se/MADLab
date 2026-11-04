import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Download,
  Gavel,
  Loader2,
  MessagesSquare,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { ConfigSummaryChips } from "@/features/configs/ConfigSummaryChips";
import type {
  ConfigSummaryAttributes,
  ExecutionInstanceResult,
  JsonObject,
} from "@/api";

import { DebateChatDialog } from "./DebateChatDialog";
import { DeleteExecutionDialog } from "./DeleteExecutionDialog";
import {
  aggregateMetrics,
  formatPercent,
  formatTimestamp,
  perClassRows,
  StatusBadge,
} from "./format";
import {
  parseTranscript,
  messagesByRound,
  roleIcon,
  roleTheme,
  type Transcript,
  type TranscriptMessage,
  type TranscriptUsage,
} from "./transcript";
import {
  isRunningStatus,
  useExecutionDetailQuery,
  useExecutionProgressStream,
  useExportExecution,
} from "./useExecutions";

/**
 * Execution detail + transcript viewer (Req 11.2, 11.3, 11.5, 10.5, 10.6).
 *
 * Loads one execution, subscribes to its live SSE progress stream while the
 * run is still going (Req 10.5), and renders:
 *  - the immutable configuration snapshot summary (Req 11.3),
 *  - the aggregate metrics incl. the per-class table when ground truth is
 *    present (Req 11.5),
 *  - every per-instance record: the parsed transcript grouped into rounds, each
 *    agent message colour-coded by its dimension/role identity (Req 11.2,
 *    13.3), message metadata + usage, the final decision, and any recoverable
 *    errors (Req 10.6), plus the instance's resolved input, ground truth,
 *    metrics, and hard error.
 * Delete (navigates back to the history on success) + export round out the
 * per-run actions (Req 11.4).
 */
export function ExecutionDetailPage() {
  const params = useParams();
  const navigate = useNavigate();
  const idParam = params.executionId;
  const id = idParam != null && /^\d+$/.test(idParam) ? Number(idParam) : null;

  const { data: execution, isLoading, isError, error } =
    useExecutionDetailQuery(id);
  const running = execution ? isRunningStatus(execution.status) : false;
  // Subscribe to the live stream only while the run is in flight (Req 10.5).
  useExecutionProgressStream(id ?? -1, id !== null && running);

  const exportExecution = useExportExecution();
  const [deleteOpen, setDeleteOpen] = useState(false);

  const classRows = useMemo(
    () => perClassRows(execution?.metrics),
    [execution?.metrics],
  );
  const metrics = useMemo(
    () => aggregateMetrics(execution?.metrics),
    [execution?.metrics],
  );

  const title = execution?.config_name ?? (id != null ? `Execution #${id}` : "Execution");

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <button
        type="button"
        onClick={() => navigate("/executions")}
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground focus:outline-none focus-visible:underline"
      >
        <ArrowLeft className="size-4" aria-hidden />
        Back to executions
      </button>

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed p-12 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Loading execution…
        </div>
      ) : isError ? (
        <div
          role="alert"
          className="rounded-lg border border-destructive/50 bg-destructive/5 p-6 text-sm text-destructive"
        >
          Failed to load execution: {error?.message}
        </div>
      ) : !execution ? (
        <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
          Execution not found.
        </div>
      ) : (
        <>
          <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="flex flex-wrap items-center gap-2 text-2xl font-semibold tracking-tight">
                <span className="truncate">{title}</span>
                <StatusBadge status={execution.status} />
                <Badge variant="outline" className="font-normal capitalize">
                  {execution.input_mode}
                </Badge>
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">
                #{execution.id}
                {execution.created_at
                  ? ` · created ${formatTimestamp(execution.created_at)}`
                  : ""}
                {execution.updated_at
                  ? ` · updated ${formatTimestamp(execution.updated_at)}`
                  : ""}
              </p>
            </div>

            <div className="flex shrink-0 items-center gap-2">
              <Button
                variant="outline"
                onClick={() =>
                  exportExecution.mutate({
                    id: execution.id,
                    name: execution.config_name,
                  })
                }
                disabled={exportExecution.isPending}
              >
                {exportExecution.isPending ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                ) : (
                  <Download className="size-4" aria-hidden />
                )}
                Export
              </Button>
              <Button
                variant="destructive"
                onClick={() => setDeleteOpen(true)}
              >
                <Trash2 className="size-4" aria-hidden />
                Delete
              </Button>
            </div>
          </header>

          {exportExecution.isError ? (
            <p role="alert" className="mb-4 text-sm text-destructive">
              Export failed: {exportExecution.error.message}
            </p>
          ) : null}

          {/* Progress + counts (live while running, Req 10.5, 11.1). */}
          <Card className="mb-4">
            <CardContent className="space-y-3 py-4">
              <div className="flex items-center gap-3">
                <Progress
                  value={execution.progress * 100}
                  className="flex-1"
                  aria-label="Execution progress"
                />
                <span className="w-10 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
                  {formatPercent(execution.progress)}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span>
                  <span className="font-medium text-foreground">
                    {execution.instance_count}
                  </span>{" "}
                  {execution.instance_count === 1 ? "instance" : "instances"}
                </span>
                <span className="inline-flex items-center gap-1">
                  <CheckCircle2
                    className="size-3.5 text-emerald-600"
                    aria-hidden
                  />
                  {execution.completed_count} completed
                </span>
                {execution.error_count > 0 ? (
                  <span className="inline-flex items-center gap-1 text-destructive">
                    <AlertTriangle className="size-3.5" aria-hidden />
                    {execution.error_count}{" "}
                    {execution.error_count === 1 ? "error" : "errors"}
                  </span>
                ) : null}
                {running ? (
                  <span className="inline-flex items-center gap-1">
                    <Loader2 className="size-3.5 animate-spin" aria-hidden />
                    running
                  </span>
                ) : null}
              </div>
            </CardContent>
          </Card>

          {/* Configuration snapshot (immutable, Req 11.3). */}
          <ConfigSnapshotCard snapshot={execution.config_snapshot} />

          {/* Aggregate metrics + per-class table (Req 11.5). */}
          <MetricsCard
            metrics={metrics}
            classRows={classRows}
          />

          {/* Per-instance records + transcripts (Req 11.2). */}
          <section className="mt-6">
            <h2 className="mb-3 text-lg font-medium">
              Instances{" "}
              <span className="text-sm font-normal text-muted-foreground">
                ({execution.instances.length})
              </span>
            </h2>
            {execution.instances.length === 0 ? (
              <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
                {running
                  ? "No results yet — the run is still in progress."
                  : "This execution produced no instance records."}
              </p>
            ) : (
              <ul className="grid gap-2">
                {execution.instances.map((instance) => (
                  <li key={instance.instance_index}>
                    <InstanceAccordion
                      instance={instance}
                      defaultOpen={execution.instances.length === 1}
                      configSnapshot={execution.config_snapshot}
                      configName={execution.config_name}
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}

      <DeleteExecutionDialog
        execution={execution ?? null}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onDeleted={() => navigate("/executions")}
      />
    </div>
  );
}

/* --------------------------- configuration snapshot ---------------------- */

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/**
 * Reconstruct the `ConfigSummaryAttributes` the chips need from the immutable
 * snapshot artifact (mirrors `summaryAttributesFromArtifact` in the launcher).
 */
function summaryAttributesFromSnapshot(
  snapshot: JsonObject,
): ConfigSummaryAttributes {
  const artifact = asRecord(snapshot);
  const participants = asRecord(artifact["participants"]);
  const interaction = asRecord(artifact["interaction"]);
  const topology = asRecord(interaction["topology"]);
  const protocol = asRecord(interaction["protocol"]);
  const agreement = asRecord(artifact["agreement"]);
  const nodes = participants["nodes"];
  const str = (v: unknown, fallback = "—"): string =>
    typeof v === "string" && v ? v : fallback;

  return {
    participant_count: Array.isArray(nodes) ? nodes.length : 0,
    topology_structure: str(topology["structure"]),
    topology_pattern:
      typeof topology["pattern"] === "string" && topology["pattern"]
        ? (topology["pattern"] as string)
        : null,
    protocol_mechanism: str(protocol["mechanism"]),
    authority: str(agreement["authority"]),
    resolution: str(agreement["resolution"]),
    under_development: false,
  };
}

function ConfigSnapshotCard({ snapshot }: { snapshot: JsonObject }) {
  const attrs = useMemo(
    () => summaryAttributesFromSnapshot(snapshot),
    [snapshot],
  );
  const name =
    typeof snapshot?.["name"] === "string"
      ? (snapshot["name"] as string)
      : null;

  return (
    <Card className="mb-4">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Configuration snapshot</CardTitle>
        <p className="text-xs text-muted-foreground">
          The exact configuration used by this run, preserved independently of
          later edits.
        </p>
      </CardHeader>
      <CardContent className="space-y-2">
        {name ? (
          <p className="text-sm font-medium">{name}</p>
        ) : null}
        <ConfigSummaryChips attributes={attrs} />
      </CardContent>
    </Card>
  );
}

/* -------------------------------- metrics -------------------------------- */

function MetricsCard({
  metrics,
  classRows,
}: {
  metrics: { label: string; value: string }[];
  classRows: ReturnType<typeof perClassRows>;
}) {
  if (metrics.length === 0 && classRows.length === 0) return null;

  const fmt = (v: number | null) => (v == null ? "—" : v.toFixed(3));

  return (
    <Card className="mb-4">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Evaluation metrics</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {metrics.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {metrics.map((m) => (
              <Badge key={m.label} variant="secondary" className="gap-1">
                <span className="text-muted-foreground">{m.label}</span>
                <span className="font-medium">{m.value}</span>
              </Badge>
            ))}
          </div>
        ) : null}

        {classRows.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="py-1.5 pr-4 font-medium">Class</th>
                  <th className="py-1.5 pr-4 font-medium">Precision</th>
                  <th className="py-1.5 pr-4 font-medium">Recall</th>
                  <th className="py-1.5 pr-4 font-medium">F1</th>
                  <th className="py-1.5 font-medium">Support</th>
                </tr>
              </thead>
              <tbody>
                {classRows.map((row) => (
                  <tr key={row.label} className="border-b last:border-0">
                    <td className="py-1.5 pr-4 font-medium">{row.label}</td>
                    <td className="py-1.5 pr-4 tabular-nums">
                      {fmt(row.precision)}
                    </td>
                    <td className="py-1.5 pr-4 tabular-nums">
                      {fmt(row.recall)}
                    </td>
                    <td className="py-1.5 pr-4 tabular-nums">{fmt(row.f1)}</td>
                    <td className="py-1.5 tabular-nums">
                      {row.support == null ? "—" : row.support}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

/* ------------------------------- instances ------------------------------- */

function instancePreview(instance: ExecutionInstanceResult): string {
  const input = asRecord(instance.resolved_input);
  const text =
    typeof input["resolved_input"] === "string"
      ? (input["resolved_input"] as string)
      : JSON.stringify(instance.resolved_input);
  const trimmed = (text ?? "").trim();
  return trimmed.length > 90 ? `${trimmed.slice(0, 90)}…` : trimmed || "(empty)";
}

function InstanceAccordion({
  instance,
  defaultOpen,
  configSnapshot,
  configName,
}: {
  instance: ExecutionInstanceResult;
  defaultOpen: boolean;
  configSnapshot: JsonObject;
  configName: string | null;
}) {
  const transcript = useMemo(
    () => parseTranscript(instance.transcript),
    [instance.transcript],
  );
  const hasError = Boolean(instance.error);
  const [chatOpen, setChatOpen] = useState(false);

  return (
    <div className="relative">
      {/* Chat replay entry point (task 11.3). Positioned over the trigger row as
          a sibling (not inside <summary>) so it never toggles the accordion. */}
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="absolute right-10 top-1.5 z-10 h-8 gap-1.5 px-2.5 text-xs"
        onClick={() => setChatOpen(true)}
        aria-label={`Open instance #${instance.instance_index} as chat`}
      >
        <MessagesSquare aria-hidden />
        Open as chat
      </Button>
      <DebateChatDialog
        open={chatOpen}
        onOpenChange={setChatOpen}
        instance={instance}
        configSnapshot={configSnapshot}
        configName={configName}
      />
      <AccordionItem open={defaultOpen || undefined}>
        <AccordionTrigger>
          <span className="mr-32 flex min-w-0 items-center gap-2">
            <span className="shrink-0 font-mono text-xs text-muted-foreground">
              #{instance.instance_index}
            </span>
            <span className="truncate font-normal text-muted-foreground">
              {instancePreview(instance)}
            </span>
            {hasError ? (
              <Badge variant="destructive" className="shrink-0 gap-1">
                <AlertTriangle className="size-3" aria-hidden />
                error
              </Badge>
            ) : null}
            {instance.ground_truth != null ? (
              <Badge variant="outline" className="shrink-0 font-normal">
                truth: {instance.ground_truth}
              </Badge>
            ) : null}
          </span>
        </AccordionTrigger>
        <AccordionContent className="space-y-4">
          {/* Resolved input (Req 11.2). */}
          <ResolvedInput instance={instance} transcript={transcript} />
  
          {/* Hard, instance-level error. */}
          {hasError ? (
            <div
              role="alert"
              className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive"
            >
              <p className="font-medium">Instance failed</p>
              <p className="mt-1 whitespace-pre-wrap">{instance.error}</p>
            </div>
          ) : null}
  
          {transcript ? (
            <TranscriptView transcript={transcript} />
          ) : !hasError ? (
            <p className="text-sm text-muted-foreground">
              No transcript recorded for this instance.
            </p>
          ) : null}
  
          {/* Per-instance metrics. */}
          {instance.metrics ? (
            <InstanceMetrics metrics={instance.metrics} />
          ) : null}
        </AccordionContent>
      </AccordionItem>
    </div>
  );
}

function ResolvedInput({
  instance,
  transcript,
}: {
  instance: ExecutionInstanceResult;
  transcript: Transcript | null;
}) {
  const fromTranscript = transcript?.resolved_input ?? null;
  const input = asRecord(instance.resolved_input);
  const fromInstance =
    typeof input["resolved_input"] === "string"
      ? (input["resolved_input"] as string)
      : null;
  const text = fromTranscript ?? fromInstance;

  return (
    <div>
      <h4 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Resolved input
      </h4>
      {text ? (
        <p className="whitespace-pre-wrap rounded-md bg-muted/40 p-3 text-sm">
          {text}
        </p>
      ) : (
        <pre className="overflow-x-auto rounded-md bg-muted/40 p-3 text-xs">
          {JSON.stringify(instance.resolved_input, null, 2)}
        </pre>
      )}
    </div>
  );
}

function InstanceMetrics({ metrics }: { metrics: JsonObject }) {
  const entries = Object.entries(asRecord(metrics)).filter(
    ([, v]) => typeof v === "string" || typeof v === "number" || typeof v === "boolean",
  );
  if (entries.length === 0) return null;
  return (
    <div>
      <h4 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Instance metrics
      </h4>
      <div className="flex flex-wrap gap-2">
        {entries.map(([k, v]) => (
          <Badge key={k} variant="secondary" className="gap-1">
            <span className="text-muted-foreground">{k}</span>
            <span className="font-medium">{String(v)}</span>
          </Badge>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------- transcript ------------------------------ */

function TranscriptView({ transcript }: { transcript: Transcript }) {
  const rounds = useMemo(
    () => messagesByRound(transcript.messages),
    [transcript.messages],
  );

  return (
    <div className="space-y-4">
      {/* Rounds × agents, colour-coded by role/dimension (Req 11.2, 13.3). */}
      {rounds.length > 0 ? (
        <div className="space-y-4">
          {rounds.map(({ round, messages }) => (
            <div key={round}>
              <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Round {round + 1}
              </h4>
              <div className="space-y-2">
                {messages.map((message, i) => (
                  <MessageCard key={`${message.node_id}-${i}`} message={message} />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No messages recorded.</p>
      )}

      {/* Recoverable per-call errors (Req 10.6). */}
      {transcript.errors.length > 0 ? (
        <div className="rounded-md border border-amber-500/50 bg-amber-500/5 p-3">
          <h4 className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-amber-600 dark:text-amber-400">
            <AlertTriangle className="size-3.5" aria-hidden />
            Recoverable errors ({transcript.errors.length})
          </h4>
          <ul className="mt-2 space-y-1 text-sm">
            {transcript.errors.map((err, i) => (
              <li key={i} className="text-muted-foreground">
                <span className="font-mono text-xs">{err.node_id}</span> · round{" "}
                {err.round_index + 1} · {err.attempts}{" "}
                {err.attempts === 1 ? "attempt" : "attempts"}: {err.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Final decision (Req 11.2). */}
      {transcript.decision ? (
        <DecisionCard decision={transcript.decision} />
      ) : null}

      {/* Notes bubbled up during the run. */}
      {transcript.notes.length > 0 ? (
        <div className="text-xs text-muted-foreground">
          {transcript.notes.map((note, i) => (
            <p key={i}>{note}</p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function MessageCard({ message }: { message: TranscriptMessage }) {
  const theme = roleTheme(message.role);
  const icon = roleIcon(message.role);

  return (
    <div
      className={cn(
        "rounded-md border-l-4 bg-card p-3",
        theme.classes.border,
      )}
      data-role={message.role}
      data-dimension={theme.key}
    >
      <div className="mb-1 flex flex-wrap items-center gap-2">
        {icon ? (
          <img src={icon} alt="" aria-hidden className="size-4" />
        ) : null}
        <span className="font-mono text-xs text-muted-foreground">
          {message.node_id}
        </span>
        <Badge variant={theme.badgeVariant} className="gap-1 capitalize">
          {message.role}
        </Badge>
        {message.usage ? <UsageChips usage={message.usage} /> : null}
      </div>

      <p className="whitespace-pre-wrap text-sm">{message.content}</p>

      {message.structured != null ? (
        <pre className="mt-2 overflow-x-auto rounded bg-muted/40 p-2 text-xs">
          {JSON.stringify(message.structured, null, 2)}
        </pre>
      ) : null}

      {Object.keys(message.metadata).length > 0 ? (
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer text-muted-foreground">
            Metadata
          </summary>
          <pre className="mt-1 overflow-x-auto rounded bg-muted/40 p-2">
            {JSON.stringify(message.metadata, null, 2)}
          </pre>
        </details>
      ) : null}
    </div>
  );
}

function UsageChips({ usage }: { usage: TranscriptUsage }) {
  const parts: string[] = [`${usage.total_tokens} tok`];
  if (usage.cost_usd != null) parts.push(`$${usage.cost_usd.toFixed(4)}`);
  if (usage.latency_s != null) parts.push(`${usage.latency_s.toFixed(2)}s`);
  return (
    <span className="text-xs text-muted-foreground">{parts.join(" · ")}</span>
  );
}

function DecisionCard({
  decision,
}: {
  decision: NonNullable<Transcript["decision"]>;
}) {
  const theme = roleTheme("judge");
  const value =
    decision.decision == null
      ? null
      : typeof decision.decision === "string" ||
          typeof decision.decision === "number"
        ? String(decision.decision)
        : JSON.stringify(decision.decision);

  return (
    <div
      className={cn(
        "rounded-md border-l-4 p-3",
        theme.classes.border,
        theme.classes.bgMuted,
      )}
      data-testid="final-decision"
      data-dimension="agreement"
    >
      <h4 className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Gavel className="size-3.5" aria-hidden />
        Final decision
      </h4>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {decision.undecided ? (
          <Badge variant="outline">Undecided</Badge>
        ) : value != null ? (
          <Badge variant="agreement" className="text-sm">
            {value}
          </Badge>
        ) : (
          <span className="text-sm text-muted-foreground">—</span>
        )}
        {decision.authority ? (
          <span className="text-xs text-muted-foreground">
            authority: {decision.authority}
          </span>
        ) : null}
        {decision.resolution ? (
          <span className="text-xs text-muted-foreground">
            resolution: {decision.resolution}
          </span>
        ) : null}
      </div>

      {decision.structured != null ? (
        <pre className="mt-2 overflow-x-auto rounded bg-background/60 p-2 text-xs">
          {JSON.stringify(decision.structured, null, 2)}
        </pre>
      ) : null}

      {decision.detail && Object.keys(decision.detail).length > 0 ? (
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer text-muted-foreground">
            Resolution detail
          </summary>
          <pre className="mt-1 overflow-x-auto rounded bg-background/60 p-2">
            {JSON.stringify(decision.detail, null, 2)}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
