import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { taxonomyApi, type TaxonomyResponse } from "@/api";

/** Query key for the taxonomy catalog — stable so it is cached once. */
export const TAXONOMY_QUERY_KEY = ["taxonomy"] as const;

/**
 * Load `GET /api/taxonomy` through React Query (Req 7.4). The catalog is
 * effectively static for a session, so it is cached indefinitely (`staleTime:
 * Infinity`) and never refetched on focus — one fetch provides every
 * data-driven form.
 */
export function useTaxonomyQuery(): UseQueryResult<TaxonomyResponse> {
  return useQuery({
    queryKey: TAXONOMY_QUERY_KEY,
    queryFn: () => taxonomyApi.get(),
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
  });
}
