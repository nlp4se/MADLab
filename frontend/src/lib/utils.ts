import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * shadcn/ui's class-name helper: merge conditional class lists (clsx) and
 * de-duplicate conflicting Tailwind utilities (tailwind-merge).
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
