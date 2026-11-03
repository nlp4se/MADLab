import {
  useMutation,
  useQuery,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  configsApi,
  datasetsApi,
  executionsApi,
  type ConfigDetail,
  type ConfigSummary,
  type DatasetPreviewRequest,
  type DatasetPreviewResponse,
  type DatasetResponse,
  type ExecutionCreateRequest,
  type ExecutionSummary,
} from "@/api";
import { configDetailQueryKey } from "@/features/designer/useConfigDetail";
import { CONFIGS_QUERY_KEY } from "@/features/configs/useConfigs";

/**
 * React Query hooks for the Run launcher view (Req 10.1-10.5).
 *
 * The launcher composes four backend resources:
 *   - the configuration list + a single config's full artifact (to derive the
 *     input template placeholders and the under-development gate, Req 7.5);
 *   - the datasets upload + sample-row preview (batch mode, Req 10.1, 10.3);
 *   - the executions create endpoint (launch, Req 10.4).
 *
 * Reads are cached queries; the writes (upload, preview, launch) are one-shot
 * actions the UI drives imperatively, so they are plain mutations with no cache
 * invalidation of their own.
 */

export function useConfigsQuery(): UseQueryResult<ConfigSummary[]> {
  return useQuery({
    queryKey: CONFIGS_QUERY_KEY,
    queryFn: () => configsApi.list(),
  });
}

/** Load the full artifact for the picked config (placeholders + gate). */
export function useConfigDetailQuery(
  id: number | null,
): UseQueryResult<ConfigDetail> {
  return useQuery({
    queryKey: configDetailQueryKey(id ?? -1),
    queryFn: () => configsApi.get(id as number),
    enabled: id !== null,
  });
}

/** Upload a CSV dataset (Req 10.1). */
export function useUploadDataset() {
  return useMutation<DatasetResponse, Error, { file: File; name?: string }>({
    mutationFn: ({ file, name }) => datasetsApi.upload(file, name),
  });
}

/** Resolve a sample-row input preview for the picked config (Req 10.3). */
export function usePreviewDataset() {
  return useMutation<
    DatasetPreviewResponse,
    Error,
    { datasetId: number; body: DatasetPreviewRequest }
  >({
    mutationFn: ({ datasetId, body }) => datasetsApi.preview(datasetId, body),
  });
}

/** Launch an execution — single ad-hoc input or dataset batch (Req 10.4). */
export function useCreateExecution() {
  return useMutation<ExecutionSummary, Error, ExecutionCreateRequest>({
    mutationFn: (body) => executionsApi.create(body),
  });
}
