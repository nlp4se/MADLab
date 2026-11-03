import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  providersApi,
  type ProviderCreateRequest,
  type ProviderDeleteResponse,
  type ProviderResponse,
  type ProviderTestRequest,
  type ProviderTestResponse,
  type ProviderUpdateRequest,
} from "@/api";

/**
 * React Query hooks for the providers resource (Req 8.1-8.6).
 *
 * The list is the single cached source for the Providers view. Every mutation
 * that changes stored state (create, update, delete) invalidates the list so
 * the UI reflects the server after a successful write — including the
 * `has_key` signal, since the API never returns the key itself (Req 8.4).
 *
 * The connectivity test (Req 8.5) is a one-shot action with no cached state, so
 * it is a plain mutation with no invalidation; callers consume the returned
 * `ProviderTestResponse` directly for success/error feedback.
 */
export const PROVIDERS_QUERY_KEY = ["providers"] as const;

export function useProvidersQuery(): UseQueryResult<ProviderResponse[]> {
  return useQuery({
    queryKey: PROVIDERS_QUERY_KEY,
    queryFn: () => providersApi.list(),
  });
}

/** Add a provider (Req 8.1). `api_key` is write-only (Req 8.4). */
export function useCreateProvider() {
  const qc = useQueryClient();
  return useMutation<ProviderResponse, Error, ProviderCreateRequest>({
    mutationFn: (body) => providersApi.create(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: PROVIDERS_QUERY_KEY });
    },
  });
}

/**
 * Edit a provider (Req 8.1). The `api_key` field is tri-state (Req 8.4):
 * omit to keep the stored key, send a string to replace it, send `null` to
 * clear it.
 */
export function useUpdateProvider() {
  const qc = useQueryClient();
  return useMutation<
    ProviderResponse,
    Error,
    { id: number; body: ProviderUpdateRequest }
  >({
    mutationFn: ({ id, body }) => providersApi.update(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: PROVIDERS_QUERY_KEY });
    },
  });
}

/** Remove a provider (Req 8.1). */
export function useDeleteProvider() {
  const qc = useQueryClient();
  return useMutation<ProviderDeleteResponse, Error, number>({
    mutationFn: (id) => providersApi.remove(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: PROVIDERS_QUERY_KEY });
    },
  });
}

/** Test provider connectivity with an optional model (Req 8.5). */
export function useTestProvider() {
  return useMutation<
    ProviderTestResponse,
    Error,
    { id: number; body: ProviderTestRequest }
  >({
    mutationFn: ({ id, body }) => providersApi.test(id, body),
  });
}
