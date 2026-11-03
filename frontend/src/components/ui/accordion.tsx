import * as React from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Minimal, dependency-free accordion built on the native `<details>`/`<summary>`
 * elements (shadcn/ui style, no Radix dependency).
 *
 * Used by the execution detail view to collapse each per-instance record and
 * each debate round so a large batch stays navigable (Req 11.2). Native
 * `<details>` gives us keyboard + screen-reader support for free; we only style
 * the disclosure marker.
 */

const AccordionItem = React.forwardRef<
  HTMLDetailsElement,
  React.DetailsHTMLAttributes<HTMLDetailsElement>
>(({ className, ...props }, ref) => (
  <details
    ref={ref}
    className={cn("group rounded-md border", className)}
    {...props}
  />
));
AccordionItem.displayName = "AccordionItem";

const AccordionTrigger = React.forwardRef<
  HTMLElement,
  React.HTMLAttributes<HTMLElement>
>(({ className, children, ...props }, ref) => (
  <summary
    ref={ref as React.Ref<HTMLElement>}
    className={cn(
      "flex cursor-pointer list-none items-center justify-between gap-3 rounded-md px-4 py-3 text-sm font-medium outline-none hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden",
      className,
    )}
    {...props}
  >
    {children}
    <ChevronDown
      className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
      aria-hidden
    />
  </summary>
));
AccordionTrigger.displayName = "AccordionTrigger";

const AccordionContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("border-t px-4 py-3 text-sm", className)}
    {...props}
  />
));
AccordionContent.displayName = "AccordionContent";

export { AccordionItem, AccordionTrigger, AccordionContent };
