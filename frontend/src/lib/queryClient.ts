import { QueryClient } from "@tanstack/react-query";

/**
 * The shared React Query client (server-state cache). Defaults are tuned for a
 * management UI: a modest stale time to avoid chatty refetches, one retry, and
 * no refetch-on-focus storms. Individual queries (e.g. the taxonomy catalog)
 * override these where they want different semantics.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
