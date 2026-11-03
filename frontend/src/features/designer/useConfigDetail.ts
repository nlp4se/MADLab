import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  configsApi,
  type ConfigDetail,
  type ConfigUpdateRequest,
  type JsonObject,
} from "@/api";
import { CONFIGS_QUERY_KEY } from "@/features/configs/useConfigs";

/**
 * React Query hooks for a single configuration used by the designer (task 8.3).
 *
 * `useConfigDetailQuery` loads the full artifact (GET /api/configs/{id}) that
 * seeds the designer store; `useUpdateConfig` persists canvas edits back
 * (PUT /api/configs/{id}, the Save path, Req 6.8). A successful save updates the
 * detail cache and invalidates the list so summary chips stay in sync.
 */
export function configDetailQueryKey(id: number) {
  return ["configs", id] as const;
}

export function useConfigDetailQuery(
  id: number | null,
): UseQueryResult<ConfigDetail> {
  return useQuery({
    queryKey: configDetailQueryKey(id ?? -1),
    queryFn: () => configsApi.get(id as number),
    enabled: id !== null,
  });
}

export function useUpdateConfig(id: number | null) {
  const qc = useQueryClient();
  return useMutation<ConfigDetail, Error, ConfigUpdateRequest>({
    mutationFn: (body) => configsApi.update(id as number, body),
    onSuccess: (updated) => {
      qc.setQueryData(configDetailQueryKey(updated.id), updated);
      void qc.invalidateQueries({ queryKey: CONFIGS_QUERY_KEY });
    },
  });
}

/** Convenience: build a PUT body that only updates the artifact. */
export function artifactUpdateBody(artifact: JsonObject): ConfigUpdateRequest {
  return { artifact };
}
