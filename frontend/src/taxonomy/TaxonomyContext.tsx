import { createContext, useContext, useMemo, type ReactNode } from "react";

import type {
  DimensionDTO,
  SubDimensionDTO,
  TaxonomyResponse,
  ValueDTO,
} from "@/api";
import { useTaxonomyQuery } from "./useTaxonomyQuery";

/**
 * Taxonomy context (Req 7.4).
 *
 * The taxonomy catalog is loaded once (via React Query in `useTaxonomyQuery`)
 * and provided through this context so every data-driven form renders from a
 * single source without each component re-fetching. Alongside the raw payload
 * the context exposes cheap lookup helpers (dimension / sub-dimension / value
 * by key, defaults, and an under-development set) that forms repeatedly need.
 */
export interface TaxonomyContextValue {
  taxonomy: TaxonomyResponse;
  /** Keys of all non-executable values, as a Set for O(1) membership checks. */
  underDevelopment: Set<string>;
  getDimension: (key: string) => DimensionDTO | undefined;
  getSubDimension: (
    dimensionKey: string,
    subKey: string,
  ) => SubDimensionDTO | undefined;
  getValue: (
    dimensionKey: string,
    subKey: string,
    valueKey: string,
  ) => ValueDTO | undefined;
  /** Default value key for a sub-dimension, if the catalog declares one. */
  getDefault: (dimensionKey: string, subKey: string) => string | undefined;
  /** Whether a value key is flagged "under development" (non-executable). */
  isUnderDevelopment: (valueKey: string) => boolean;
}

const TaxonomyContext = createContext<TaxonomyContextValue | null>(null);

function buildValue(
  taxonomy: TaxonomyResponse,
): TaxonomyContextValue {
  const dimensionsByKey = new Map<string, DimensionDTO>();
  for (const dim of taxonomy.dimensions) dimensionsByKey.set(dim.key, dim);
  const underDevelopment = new Set(taxonomy.under_development);

  const getDimension = (key: string) => dimensionsByKey.get(key);

  const getSubDimension = (dimensionKey: string, subKey: string) =>
    getDimension(dimensionKey)?.subdimensions.find((s) => s.key === subKey);

  const getValue = (
    dimensionKey: string,
    subKey: string,
    valueKey: string,
  ) =>
    getSubDimension(dimensionKey, subKey)?.values.find(
      (v) => v.key === valueKey,
    );

  const getDefault = (dimensionKey: string, subKey: string) =>
    taxonomy.defaults[dimensionKey]?.[subKey];

  const isUnderDevelopment = (valueKey: string) =>
    underDevelopment.has(valueKey);

  return {
    taxonomy,
    underDevelopment,
    getDimension,
    getSubDimension,
    getValue,
    getDefault,
    isUnderDevelopment,
  };
}

export interface TaxonomyProviderProps {
  children: ReactNode;
  /** Rendered while the catalog loads. */
  fallback?: ReactNode;
  /** Rendered on load error, given the error and a retry callback. */
  renderError?: (error: unknown, retry: () => void) => ReactNode;
}

/**
 * Loads the taxonomy once and provides it to the subtree. While loading it
 * renders `fallback`; on error it renders `renderError` (or a minimal default).
 * Children only mount once the catalog is available, so consumers can assume a
 * non-null taxonomy via `useTaxonomy()`.
 */
export function TaxonomyProvider({
  children,
  fallback = null,
  renderError,
}: TaxonomyProviderProps) {
  const query = useTaxonomyQuery();

  const value = useMemo(
    () => (query.data ? buildValue(query.data) : null),
    [query.data],
  );

  if (query.isError) {
    if (renderError) return <>{renderError(query.error, () => query.refetch())}</>;
    return (
      <div role="alert" className="p-6 text-sm text-destructive">
        Failed to load the taxonomy catalog.
        <button
          type="button"
          className="ml-2 underline"
          onClick={() => query.refetch()}
        >
          Retry
        </button>
      </div>
    );
  }

  if (!value) return <>{fallback}</>;

  return (
    <TaxonomyContext.Provider value={value}>
      {children}
    </TaxonomyContext.Provider>
  );
}

/**
 * Access the loaded taxonomy. Throws if used outside a `TaxonomyProvider` (or
 * before the catalog has loaded), which keeps consumers honest.
 */
export function useTaxonomy(): TaxonomyContextValue {
  const ctx = useContext(TaxonomyContext);
  if (!ctx) {
    throw new Error("useTaxonomy must be used within a <TaxonomyProvider>.");
  }
  return ctx;
}
