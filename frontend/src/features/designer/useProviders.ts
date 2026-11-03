import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { providersApi, type ProviderResponse } from "@/api";

/**
 * React Query hook for the configured providers (GET /api/providers).
 *
 * The designer's base-model binding (Req 1.8, 8.6) needs the list of
 * configured providers and their model keys so a participant can be bound to a
 * concrete provider + model. Providers rarely change within a designing
 * session, so the query is cached and shared via the standard query key.
 */
export const PROVIDERS_QUERY_KEY = ["providers"] as const;

export function useProvidersQuery(): UseQueryResult<ProviderResponse[]> {
  return useQuery({
    queryKey: PROVIDERS_QUERY_KEY,
    queryFn: () => providersApi.list(),
    staleTime: 30_000,
  });
}
