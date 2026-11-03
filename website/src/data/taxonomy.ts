/**
 * Typed access to the committed taxonomy-catalog snapshot.
 *
 * The website is static and must not call the backend at runtime (Req 13.1), so
 * the catalog is imported from `taxonomy.json` — a build-time snapshot produced
 * by `scripts/generate-taxonomy-snapshot.py` from the same source the
 * `GET /api/taxonomy` endpoint serves. The overview/taxonomy pages (task 9.2)
 * and the patterns gallery (task 9.3) consume this module.
 *
 * The types below mirror `backend/app/schemas/taxonomy.py`.
 */
import snapshot from "./taxonomy.json";

export interface TaxonomyValue {
  key: string;
  label: string;
  description: string;
  default: boolean;
  executable: boolean;
  icon: string | null;
}

export interface SubDimension {
  key: string;
  label: string;
  description: string;
  selection: "single" | "multi" | "attributes";
  values: TaxonomyValue[];
}

export interface Dimension {
  key: string;
  label: string;
  description: string;
  subdimensions: SubDimension[];
}

export interface PersonaFieldSet {
  name: string;
  background: string | null;
  personality: string | null;
  stance: string | null;
}

export interface PersonaPattern {
  key: string;
  label: string;
  description: string;
  pair_with: string | null;
  is_set: boolean;
  personas: PersonaFieldSet[];
}

export interface Role {
  key: string;
  label: string;
  description: string;
  icon: string | null;
}

export interface TopologyPattern {
  key: string;
  label: string;
  description: string;
  icon: string | null;
}

export interface Templates {
  persona_patterns: PersonaPattern[];
  roles: Role[];
  topologies: TopologyPattern[];
}

export interface Taxonomy {
  dimensions: Dimension[];
  templates: Templates;
  defaults: Record<string, Record<string, string>>;
  under_development: string[];
}

export const taxonomy = snapshot as unknown as Taxonomy;

/** The canonical dimension keys in presentation order. */
export const DIMENSION_KEYS = ["participants", "interaction", "agreement"] as const;
export type DimensionKey = (typeof DIMENSION_KEYS)[number];

/** Look up a dimension by key (undefined if absent from the snapshot). */
export function getDimension(key: DimensionKey): Dimension | undefined {
  return taxonomy.dimensions.find((d) => d.key === key);
}

/** True when a value key is marked "under development" (non-executable). */
export function isUnderDevelopment(key: string): boolean {
  return taxonomy.under_development.includes(key);
}
