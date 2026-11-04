/**
 * Colour mappings for designer participant nodes.
 *
 * Two independent visual encodings make a graph readable at a glance:
 *  - ROLE colour tints the node body/border (a debater looks different from a
 *    judge or summarizer);
 *  - PROVIDER colour tints the base-model badge (OpenAI vs Anthropic vs a local
 *    Ollama look distinct).
 *
 * Both use fixed, legible hex palettes (not Tailwind classes) so the colours
 * can be applied as inline styles for arbitrary role/provider values without
 * relying on a safelist. Unknown roles/providers fall back to a stable colour
 * derived from the string, so even custom roles and new providers are visually
 * distinct and consistent across renders.
 */

export interface SwatchColor {
  /** Strong accent (border, text, handle). */
  solid: string;
  /** Faint tint for fills/backgrounds. */
  soft: string;
}

/** Known functional roles → distinct accent colours. */
const ROLE_COLORS: Record<string, SwatchColor> = {
  debater: { solid: "#4f46e5", soft: "rgba(79, 70, 229, 0.12)" }, // indigo
  judge: { solid: "#b45309", soft: "rgba(180, 83, 9, 0.12)" }, // amber-700
  summarizer: { solid: "#0d9488", soft: "rgba(13, 148, 136, 0.12)" }, // teal
  leader: { solid: "#be185d", soft: "rgba(190, 24, 93, 0.12)" }, // pink-700
  verifier: { solid: "#15803d", soft: "rgba(21, 128, 61, 0.12)" }, // green-700
  editor: { solid: "#7c3aed", soft: "rgba(124, 58, 237, 0.12)" }, // violet
};

/** Known provider kinds/names → brand-ish accent colours. */
const PROVIDER_COLORS: Record<string, SwatchColor> = {
  openai: { solid: "#10a37f", soft: "rgba(16, 163, 127, 0.14)" },
  anthropic: { solid: "#d97706", soft: "rgba(217, 119, 6, 0.14)" },
  gemini: { solid: "#4285f4", soft: "rgba(66, 133, 244, 0.14)" },
  google: { solid: "#4285f4", soft: "rgba(66, 133, 244, 0.14)" },
  mistral: { solid: "#ff7000", soft: "rgba(255, 112, 0, 0.14)" },
  deepseek: { solid: "#4d6bfe", soft: "rgba(77, 107, 254, 0.14)" },
  ollama: { solid: "#334155", soft: "rgba(51, 65, 85, 0.14)" },
  vllm: { solid: "#9333ea", soft: "rgba(147, 51, 234, 0.14)" },
  openai_compatible: { solid: "#0891b2", soft: "rgba(8, 145, 178, 0.14)" },
};

/** A stable fallback palette for unknown roles/providers. */
const FALLBACK: SwatchColor[] = [
  { solid: "#6366f1", soft: "rgba(99, 102, 241, 0.12)" },
  { solid: "#14b8a6", soft: "rgba(20, 184, 166, 0.12)" },
  { solid: "#f59e0b", soft: "rgba(245, 158, 11, 0.12)" },
  { solid: "#ec4899", soft: "rgba(236, 72, 153, 0.12)" },
  { solid: "#22c55e", soft: "rgba(34, 197, 94, 0.12)" },
  { solid: "#8b5cf6", soft: "rgba(139, 92, 246, 0.12)" },
  { solid: "#06b6d4", soft: "rgba(6, 182, 212, 0.12)" },
];

/** Deterministic hash → fallback swatch for an arbitrary key. */
function fallbackFor(key: string): SwatchColor {
  let hash = 0;
  for (let i = 0; i < key.length; i += 1) {
    hash = (hash * 31 + key.charCodeAt(i)) | 0;
  }
  return FALLBACK[Math.abs(hash) % FALLBACK.length];
}

/** Colour for a role (custom roles use the `custom:` prefix, stripped here). */
export function roleColor(role: string): SwatchColor {
  const key = role.replace(/^custom:/, "").toLowerCase();
  return ROLE_COLORS[key] ?? fallbackFor(key);
}

/**
 * Colour for a provider, keyed by its kind or name. Accepts either a provider
 * `kind` (openai/anthropic/…) or a display name; the lookup is case-insensitive
 * and falls back to a stable hashed colour for anything unrecognised.
 */
export function providerColor(kindOrName: string): SwatchColor {
  const key = kindOrName.trim().toLowerCase();
  if (PROVIDER_COLORS[key]) return PROVIDER_COLORS[key];
  // Try a loose contains-match so e.g. "OpenAI (prod)" maps to openai.
  for (const known of Object.keys(PROVIDER_COLORS)) {
    if (key.includes(known)) return PROVIDER_COLORS[known];
  }
  return fallbackFor(key);
}
