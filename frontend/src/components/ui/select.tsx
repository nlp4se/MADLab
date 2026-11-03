import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Native `<select>` wrapper styled to match the other shadcn/ui form controls.
 *
 * The taxonomy-driven dimension panels (task 8.4) render many single-choice
 * selectors from catalog values; a native select keeps them accessible and
 * fully controllable without pulling in a Radix popover dependency. Consumers
 * pass `<option>` children (or an `Select`-adjacent helper) and the standard
 * `value` / `onChange` props.
 */
const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
      className,
    )}
    {...props}
  >
    {children}
  </select>
));
Select.displayName = "Select";

export { Select };
