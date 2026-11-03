import { Users, Workflow, Gavel, type LucideIcon } from "lucide-react";

/**
 * Dimension theming tokens (Reqs 6.6, 7.4).
 *
 * The three taxonomy dimensions — Participants, Interaction, Agreement — each
 * carry a fixed colour + icon identity that is reused everywhere (panels,
 * badges, tabs, the designer inspector) so the active dimension is always
 * unmistakable. Colours are defined once as CSS variables in `index.css` and
 * surfaced to Tailwind via `tailwind.config.js`; this module is the single
 * source for the dimension keys, labels, Badge variant, Tailwind class
 * fragments, and the lucide icon identity.
 */
export type DimensionKey = "participants" | "interaction" | "agreement";

export interface DimensionTheme {
  key: DimensionKey;
  label: string;
  /** Short tagline describing what the dimension governs. */
  blurb: string;
  /** lucide-react icon used as the dimension's visual identity. */
  icon: LucideIcon;
  /** Badge variant name (see `components/ui/badge.tsx`). */
  badgeVariant: DimensionKey;
  /** Tailwind class fragments keyed off the dimension CSS variables. */
  classes: {
    text: string;
    bg: string;
    bgMuted: string;
    border: string;
    ring: string;
  };
}

export const DIMENSION_THEMES: Record<DimensionKey, DimensionTheme> = {
  participants: {
    key: "participants",
    label: "Participants",
    blurb: "Who debates — roles, personas, and base models.",
    icon: Users,
    badgeVariant: "participants",
    classes: {
      text: "text-participants",
      bg: "bg-participants text-participants-foreground",
      bgMuted: "bg-participants-muted",
      border: "border-participants",
      ring: "ring-participants",
    },
  },
  interaction: {
    key: "interaction",
    label: "Interaction",
    blurb: "How they talk — topology, protocol, and format.",
    icon: Workflow,
    badgeVariant: "interaction",
    classes: {
      text: "text-interaction",
      bg: "bg-interaction text-interaction-foreground",
      bgMuted: "bg-interaction-muted",
      border: "border-interaction",
      ring: "ring-interaction",
    },
  },
  agreement: {
    key: "agreement",
    label: "Agreement",
    blurb: "How they decide — authority and resolution.",
    icon: Gavel,
    badgeVariant: "agreement",
    classes: {
      text: "text-agreement",
      bg: "bg-agreement text-agreement-foreground",
      bgMuted: "bg-agreement-muted",
      border: "border-agreement",
      ring: "ring-agreement",
    },
  },
};

export const DIMENSION_ORDER: DimensionKey[] = [
  "participants",
  "interaction",
  "agreement",
];

export function getDimensionTheme(key: DimensionKey): DimensionTheme {
  return DIMENSION_THEMES[key];
}
