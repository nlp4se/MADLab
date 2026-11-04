import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * shadcn/ui's class-name helper: merge conditional class lists (clsx) and
 * de-duplicate conflicting Tailwind utilities (tailwind-merge).
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Long-content helpers (task 11.15) for transcript text, error messages and
 * JSON blocks, so nothing escapes its card:
 *  - `WRAP_TEXT`: keep line breaks, wrap words, and break unbroken strings
 *    (one-line JSON, URLs, ids) anywhere. `overflow-wrap: anywhere` (unlike
 *    `break-word`) also lowers the min-content width, so flex/grid parents
 *    don't grow to the longest token.
 *  - `SCROLL_PRE`: a `<pre>` keeps its formatting and scrolls horizontally
 *    inside its card instead of widening it.
 */
export const WRAP_TEXT = "whitespace-pre-wrap break-words [overflow-wrap:anywhere]";
export const SCROLL_PRE = "max-w-full overflow-x-auto";
