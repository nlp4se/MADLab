import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  configsApi,
  type ConfigCopyRequest,
  type ConfigCreateRequest,
  type ConfigDetail,
  type ConfigImportRequest,
  type ConfigSummary,
  type DeleteResponse,
} from "@/api";

/**
 * React Query hooks for the configurations resource (Req 5.1-5.7, 4.3).
 *
 * The list is the single cached source for the Configurations view; every
 * mutation (create, copy, import, delete) invalidates it so the UI reflects the
 * server after a successful write. Export is a one-shot action (file download)
 * rather than cached state, so it is a plain mutation with no invalidation.
 */
export const CONFIGS_QUERY_KEY = ["configs"] as const;

export function useConfigsQuery(): UseQueryResult<ConfigSummary[]> {
  return useQuery({
    queryKey: CONFIGS_QUERY_KEY,
    queryFn: () => configsApi.list(),
  });
}

/** Create a new configuration (defaults when no artifact supplied, Req 5.2). */
export function useCreateConfig() {
  const qc = useQueryClient();
  return useMutation<ConfigDetail, Error, ConfigCreateRequest>({
    mutationFn: (body) => configsApi.create(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: CONFIGS_QUERY_KEY });
    },
  });
}

/** Duplicate a configuration into an independent one (Req 5.5). */
export function useCopyConfig() {
  const qc = useQueryClient();
  return useMutation<
    ConfigDetail,
    Error,
    { id: number; body?: ConfigCopyRequest }
  >({
    mutationFn: ({ id, body }) => configsApi.copy(id, body ?? {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: CONFIGS_QUERY_KEY });
    },
  });
}

/** Delete a configuration; the response carries referencing_executions (Req 5.4). */
export function useDeleteConfig() {
  const qc = useQueryClient();
  return useMutation<DeleteResponse, Error, number>({
    mutationFn: (id) => configsApi.remove(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: CONFIGS_QUERY_KEY });
    },
  });
}

/** Import a configuration artifact from JSON (Req 4.3). */
export function useImportConfig() {
  const qc = useQueryClient();
  return useMutation<ConfigDetail, Error, ConfigImportRequest>({
    mutationFn: (body) => configsApi.import(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: CONFIGS_QUERY_KEY });
    },
  });
}

/**
 * Export a configuration's artifact and trigger a client-side JSON download
 * (Req 4.3). The backend returns the raw artifact with a filename; we turn it
 * into a Blob and click a transient anchor.
 */
export function useExportConfig() {
  return useMutation<void, Error, { id: number; name: string }>({
    mutationFn: async ({ id, name }) => {
      const { text, filename } = await configsApi.export(id);
      downloadTextFile(
        text,
        filename ?? `${slugify(name) || `config-${id}`}.json`,
      );
    },
  });
}

/** Turn a config name into a filesystem-friendly slug for the export filename. */
export function slugify(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Trigger a browser download of `text` as `filename` (JSON). */
export function downloadTextFile(text: string, filename: string): void {
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
