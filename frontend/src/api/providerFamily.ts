import type { ProviderFamily, ProviderKind, ProviderResponse } from "./types";

/**
 * Provider kind -> base-model family (task 11.9). Mirrors the backend's single
 * source of truth (`backend/app/provider_family.py`): the family is a property
 * of the provider, not a free participant parameter.
 *
 *  - Fixed kinds always have one family.
 *  - Mixed kinds (mistral, openai_compatible) take the stored choice, falling
 *    back to a per-kind default.
 */
export const FIXED_KIND_FAMILY: Partial<Record<ProviderKind, ProviderFamily>> = {
  openai: "closed_weight",
  anthropic: "closed_weight",
  gemini: "closed_weight",
  ollama: "open_weight",
  vllm: "open_weight",
  deepseek: "open_weight",
};

export const MIXED_KIND_DEFAULT_FAMILY: Partial<Record<ProviderKind, ProviderFamily>> = {
  mistral: "closed_weight",
  openai_compatible: "open_weight",
};

export const PROVIDER_FAMILY_LABELS: Record<ProviderFamily, string> = {
  open_weight: "Open-weight",
  closed_weight: "Closed-weight",
};

/** Whether the user may choose the family for this kind. */
export function isMixedKind(kind: ProviderKind): boolean {
  return kind in MIXED_KIND_DEFAULT_FAMILY;
}

/** The family a provider of `kind` has when no choice is stored. */
export function defaultFamily(kind: ProviderKind): ProviderFamily {
  return FIXED_KIND_FAMILY[kind] ?? MIXED_KIND_DEFAULT_FAMILY[kind] ?? "closed_weight";
}

/** Effective family for a kind + (optional) stored choice. */
export function effectiveFamily(
  kind: ProviderKind,
  stored?: ProviderFamily | null,
): ProviderFamily {
  return FIXED_KIND_FAMILY[kind] ?? stored ?? defaultFamily(kind);
}

/** The family of a loaded provider (the API already returns the effective one). */
export function providerFamily(provider: Pick<ProviderResponse, "kind" | "family">) {
  return effectiveFamily(provider.kind, provider.family);
}
