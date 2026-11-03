import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  Loader2,
  MoreVertical,
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Progress } from "@/components/ui/progress";
import type { ExecutionSummary } from "@/api";

import { DeleteExecutionDialog } from "./DeleteExecutionDialog";
import {
  aggregateMetrics,
  formatPercent,
  formatTimestamp,
  StatusBadge,
} from "./format";
import {
  isRunningStatus,
  useExecutionsListProgress,
  useExecutionsQuery,
  useExportExecution,
} from "./useExecutions";

/**
 * Executions history view (Req 11.1, 11.4, 10.5).
 *
 * Lists every execution as a row showing status, a live progress bar,
 * instance/completed/error counts, the source configuration name, timestamps,
 * and summary metrics. Running executions subscribe to the SSE progress stream
 * (Req 10.5) so their bar + status advance live; a React Query polling fallback
 * covers environments without `EventSource`. Clicking a row opens the detail
 * view. Per-row actions export the results as JSON or delete the run (Req 11.4).
 */
export function ExecutionsPage() {
  const navigate = useNavigate();
  const { data: executions, isLoading, isError, error } = useExecutionsQuery();
  useExecutionsListProgress(executions);

  const exportExecution = useExportExecution();
  const [toDelete, setToDelete] = useState<ExecutionSummary | null>(null);
  const [exportingId, setExportingId] = useState<number | null>(null);

  const openDetail = (id: number) => navigate(`/executions/${id}`);

  const handleExport = (execution: ExecutionSummary) => {
    setExportingId(execution.id);
    exportExecution.mutate(
      { id: execution.id, name: execution.config_name },
      { onSettled: () => setExportingId(null) },
    );
  };

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Executions</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Run history with live progress, per-instance transcripts, decisions,
          and metrics.
        </p>
      </header>

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed p-12 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Loading executions…
        </div>
      ) : isError ? (
        <div
          role="alert"
          className="rounded-lg border border-destructive/50 bg-destructive/5 p-6 text-sm text-destructive"
        >
          Failed to load executions: {error?.message}
        </div>
      ) : (executions?.length ?? 0) === 0 ? (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <h2 className="text-lg font-medium">No executions yet</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Launch a configuration from the Run view to see its history,
            transcripts, and metrics here.
          </p>
          <Button className="mt-5" onClick={() => navigate("/run")}>
            Go to Run
          </Button>
        </div>
      ) : (
        <ul className="grid gap-3">
          {executions!.map((execution) => (
            <li key={execution.id}>
              <ExecutionRow
                execution={execution}
                onOpen={() => openDetail(execution.id)}
                onExport={() => handleExport(execution)}
                onDelete={() => setToDelete(execution)}
                busy={exportingId === execution.id}
              />
            </li>
          ))}
        </ul>
      )}

      {exportExecution.isError ? (
        <p role="alert" className="mt-4 text-sm text-destructive">
          Export failed: {exportExecution.error.message}
        </p>
      ) : null}

      <DeleteExecutionDialog
        execution={toDelete}
        open={toDelete !== null}
        onOpenChange={(open) => {
          if (!open) setToDelete(null);
        }}
      />
    </div>
  );
}

function ExecutionRow({
  execution,
  onOpen,
  onExport,
  onDelete,
  busy,
}: {
  execution: ExecutionSummary;
  onOpen: () => void;
  onExport: () => void;
  onDelete: () => void;
  busy: boolean;
}) {
  const metrics = aggregateMetrics(execution.metrics);
  const running = isRunningStatus(execution.status);
  const title = execution.config_name ?? `Execution #${execution.id}`;

  return (
    <Card className="transition-colors hover:border-primary/40">
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0 pb-3">
        <div className="min-w-0">
          <button
            type="button"
            onClick={onOpen}
            className="text-left focus:outline-none focus-visible:underline"
          >
            <CardTitle className="flex flex-wrap items-center gap-2 text-base">
              <span className="truncate">{title}</span>
              <StatusBadge status={execution.status} />
              <Badge variant="outline" className="font-normal capitalize">
                {execution.input_mode}
              </Badge>
            </CardTitle>
          </button>
          <p className="mt-1 text-xs text-muted-foreground">
            #{execution.id}
            {execution.created_at
              ? ` · ${formatTimestamp(execution.created_at)}`
              : ""}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {busy ? (
            <Loader2
              className="size-4 animate-spin text-muted-foreground"
              aria-hidden
            />
          ) : null}
          <DropdownMenu>
            <DropdownMenuTrigger>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Actions for ${title}`}
              >
                <MoreVertical className="size-4" aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem onClick={onOpen}>Open</DropdownMenuItem>
              <DropdownMenuItem onClick={onExport}>
                <Download className="size-4" aria-hidden />
                Export JSON
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem destructive onClick={onDelete}>
                <Trash2 className="size-4" aria-hidden />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </CardHeader>

      <CardContent className="space-y-3 pb-4">
        {/* Progress bar — live for running runs (Req 10.5, 11.1). */}
        <div className="flex items-center gap-3">
          <Progress
            value={execution.progress * 100}
            className="flex-1"
            aria-label={`Progress for ${title}`}
          />
          <span className="w-10 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
            {formatPercent(execution.progress)}
          </span>
        </div>

        {/* Counts + metrics (Req 11.1). */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>
            <span className="font-medium text-foreground">
              {execution.instance_count}
            </span>{" "}
            {execution.instance_count === 1 ? "instance" : "instances"}
          </span>
          <span className="inline-flex items-center gap-1">
            <CheckCircle2 className="size-3.5 text-emerald-600" aria-hidden />
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
          {metrics.map((m) => (
            <span key={m.label}>
              <span className="font-medium text-foreground">{m.value}</span>{" "}
              {m.label.toLowerCase()}
            </span>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
