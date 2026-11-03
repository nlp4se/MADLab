import { useEffect, useRef, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  executionsApi,
  getApiBaseUrl,
  type ExecutionDeleteResponse,
  type ExecutionDetail,
  type ExecutionSummary,
} from "@/api";
import { downloadTextFile, slugify } from "@/features/configs/useConfigs";

/**
 * React Query hooks for the executions history + detail views (Req 11.1, 11.2,
 * 11.4, 11.5) plus the live SSE progress subscription (Req 10.5).
 *
 * The list is the cached source for the history view; the detail query is the
 * per-run source for the transcript viewer. Delete invalidates both. Export is
 * a one-shot file download. Live progress is layered on top: running executions
 * subscribe to the backend SSE stream and, when an event changes a run's
 * status/progress, the cached list + detail are patched in place so the UI
 * updates without a refetch. A polling fallback keeps progress moving if the
 * stream is unavailable.
 */

export const EXECUTIONS_QUERY_KEY = ["executions"] as const;

export function executionDetailQueryKey(id: number) {
  return ["executions", id] as const;
}

/** Statuses that mean the run is still producing progress events. */
const RUNNING_STATUSES = new Set(["pending", "queued", "running"]);
/** Statuses that end the SSE stream (mirrors the backend's terminal set). */
const TERMINAL_STATUSES = new Set(["completed", "failed", "partial", "cancelled"]);

export function isRunningStatus(status: string): boolean {
  return RUNNING_STATUSES.has(status);
}

export function isTerminalStatus(status: string): boolean {
  return TERMINAL_STATUSES.has(status);
}

export function useExecutionsQuery(): UseQueryResult<ExecutionSummary[]> {
  return useQuery({
    queryKey: EXECUTIONS_QUERY_KEY,
    queryFn: () => executionsApi.list(),
    // Poll while anything is running; stop once everything is terminal. This is
    // the fallback for environments where the SSE stream is unavailable.
    refetchInterval: (query) => {
      const data = query.state.data as ExecutionSummary[] | undefined;
      const anyRunning = (data ?? []).some((e) => isRunningStatus(e.status));
      return anyRunning ? 2000 : false;
    },
  });
}

export function useExecutionDetailQuery(
  id: number | null,
): UseQueryResult<ExecutionDetail> {
  return useQuery({
    queryKey: executionDetailQueryKey(id ?? -1),
    queryFn: () => executionsApi.get(id as number),
    enabled: id !== null,
    refetchInterval: (query) => {
      const data = query.state.data as ExecutionDetail | undefined;
      return data && isRunningStatus(data.status) ? 2000 : false;
    },
  });
}

/** Delete an execution; invalidates the list and the detail cache (Req 11.4). */
export function useDeleteExecution() {
  const qc = useQueryClient();
  return useMutation<ExecutionDeleteResponse, Error, number>({
    mutationFn: (id) => executionsApi.remove(id),
    onSuccess: (_res, id) => {
      void qc.invalidateQueries({ queryKey: EXECUTIONS_QUERY_KEY });
      qc.removeQueries({ queryKey: executionDetailQueryKey(id) });
    },
  });
}

/**
 * Export an execution's full results payload and trigger a client-side JSON
 * download (Req 11.4), mirroring the config export pattern.
 */
export function useExportExecution() {
  return useMutation<void, Error, { id: number; name?: string | null }>({
    mutationFn: async ({ id, name }) => {
      const { text, filename } = await executionsApi.export(id);
      const fallback = `${slugify(name ?? "") || `execution-${id}`}.json`;
      downloadTextFile(text, filename ?? fallback);
    },
  });
}

/* ------------------------------ SSE progress ----------------------------- */

interface ProgressEvent {
  execution_id: number;
  status: string;
  progress: number;
}

/** Build the absolute SSE URL from the API base + the relative stream path. */
export function executionStreamUrl(id: number): string {
  return `${getApiBaseUrl()}${executionsApi.streamUrl(id)}`;
}

/**
 * Subscribe to the live SSE progress stream for one running execution and patch
 * the cached list + detail with each event (Req 10.5). The subscription opens
 * only while `enabled` is true (i.e. the run is not yet terminal) and is torn
 * down on a terminal event, on error (falling back to the query polling above),
 * or on unmount. On a terminal event we also invalidate the detail so the final
 * per-instance records + metrics are fetched.
 */
export function useExecutionProgressStream(
  id: number,
  enabled: boolean,
): void {
  const qc = useQueryClient();
  // Keep the latest qc without resubscribing on every render.
  const qcRef = useRef(qc);
  qcRef.current = qc;

  useEffect(() => {
    if (!enabled) return;
    if (typeof EventSource === "undefined") return; // graceful no-op fallback.

    const source = new EventSource(executionStreamUrl(id));

    const applyProgress = (event: ProgressEvent) => {
      const client = qcRef.current;
      // Patch the list entry in place.
      client.setQueryData<ExecutionSummary[]>(
        EXECUTIONS_QUERY_KEY,
        (prev) =>
          prev?.map((e) =>
            e.id === event.execution_id
              ? { ...e, status: event.status, progress: event.progress }
              : e,
          ),
      );
      // Patch the detail entry in place.
      client.setQueryData<ExecutionDetail>(
        executionDetailQueryKey(event.execution_id),
        (prev) =>
          prev
            ? { ...prev, status: event.status, progress: event.progress }
            : prev,
      );
    };

    source.onmessage = (message) => {
      try {
        const data = JSON.parse(message.data) as ProgressEvent & {
          error?: string;
        };
        if (data.error) {
          source.close();
          return;
        }
        applyProgress(data);
        if (isTerminalStatus(data.status)) {
          source.close();
          // Fetch the final records + metrics now the run is done.
          void qcRef.current.invalidateQueries({
            queryKey: executionDetailQueryKey(id),
          });
          void qcRef.current.invalidateQueries({
            queryKey: EXECUTIONS_QUERY_KEY,
          });
        }
      } catch {
        /* ignore malformed events; polling fallback covers us. */
      }
    };

    source.onerror = () => {
      // The stream failed (or the server closed it); rely on query polling.
      source.close();
    };

    return () => source.close();
  }, [id, enabled]);
}

/**
 * Open a progress stream for every currently-running execution in the list so
 * the history view updates live (Req 10.5). Returns nothing; its effect is the
 * cache patching done by the per-id subscriptions.
 */
export function useExecutionsListProgress(
  executions: ExecutionSummary[] | undefined,
): void {
  const qc = useQueryClient();
  const qcRef = useRef(qc);
  qcRef.current = qc;
  // Track open sources by id so we subscribe once per running run.
  const [runningIds, setRunningIds] = useState<number[]>([]);

  useEffect(() => {
    const ids = (executions ?? [])
      .filter((e) => isRunningStatus(e.status))
      .map((e) => e.id)
      .sort((a, b) => a - b);
    setRunningIds((prev) =>
      prev.length === ids.length && prev.every((v, i) => v === ids[i])
        ? prev
        : ids,
    );
  }, [executions]);

  useEffect(() => {
    if (runningIds.length === 0) return;
    if (typeof EventSource === "undefined") return;

    const sources = runningIds.map((id) => {
      const source = new EventSource(executionStreamUrl(id));
      source.onmessage = (message) => {
        try {
          const data = JSON.parse(message.data) as ProgressEvent & {
            error?: string;
          };
          if (data.error) {
            source.close();
            return;
          }
          qcRef.current.setQueryData<ExecutionSummary[]>(
            EXECUTIONS_QUERY_KEY,
            (prev) =>
              prev?.map((e) =>
                e.id === data.execution_id
                  ? { ...e, status: data.status, progress: data.progress }
                  : e,
              ),
          );
          if (isTerminalStatus(data.status)) {
            source.close();
            void qcRef.current.invalidateQueries({
              queryKey: EXECUTIONS_QUERY_KEY,
            });
          }
        } catch {
          /* ignore malformed events. */
        }
      };
      source.onerror = () => source.close();
      return source;
    });

    return () => sources.forEach((s) => s.close());
  }, [runningIds]);
}
