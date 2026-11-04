import * as React from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";

/**
 * A minimal, dependency-light dropdown menu.
 *
 * Mirrors the small slice of the shadcn/ui DropdownMenu API the app needs —
 * a trigger that toggles a popover of `DropdownMenuItem`s — without pulling in
 * the full Radix menu primitive (only `@radix-ui/react-slot` is scaffolded).
 *
 * The content is rendered in a PORTAL to `document.body`, positioned next to the
 * trigger. Portalling keeps the menu from being clipped or stacked below
 * sibling layers — notably the React Flow canvas in the designer toolbar, which
 * otherwise painted over (and swallowed clicks on) a menu rendered inline.
 * Closes on outside click, Escape, or after an item is chosen.
 */
interface MenuContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  triggerRef: React.RefObject<HTMLElement>;
  contentRef: React.RefObject<HTMLDivElement>;
}

const MenuContext = React.createContext<MenuContextValue | null>(null);

export function DropdownMenu({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const triggerRef = React.useRef<HTMLElement>(null);
  const contentRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      const t = e.target as Node;
      if (
        !triggerRef.current?.contains(t) &&
        !contentRef.current?.contains(t)
      ) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <MenuContext.Provider value={{ open, setOpen, triggerRef, contentRef }}>
      <div className="relative inline-block text-left">{children}</div>
    </MenuContext.Provider>
  );
}

export function DropdownMenuTrigger({
  children,
}: {
  children: React.ReactElement<React.HTMLAttributes<HTMLElement>>;
}) {
  const ctx = React.useContext(MenuContext);
  return React.cloneElement(children, {
    ref: ctx?.triggerRef as React.Ref<HTMLElement>,
    "aria-haspopup": "menu",
    "aria-expanded": ctx?.open ?? false,
    onClick: (e: React.MouseEvent) => {
      e.stopPropagation();
      children.props.onClick?.(e as React.MouseEvent<HTMLElement>);
      ctx?.setOpen(!ctx.open);
    },
  } as Partial<React.HTMLAttributes<HTMLElement>> & { ref?: React.Ref<HTMLElement> });
}

export function DropdownMenuContent({
  className,
  align = "end",
  children,
}: {
  className?: string;
  align?: "start" | "end";
  children: React.ReactNode;
}) {
  const ctx = React.useContext(MenuContext);
  const [pos, setPos] = React.useState<{ top: number; left: number } | null>(
    null,
  );

  // Position the portalled menu just below the trigger, aligned to its edge.
  React.useLayoutEffect(() => {
    if (!ctx?.open) {
      setPos(null);
      return;
    }
    const rect = ctx.triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const MENU_MIN_WIDTH = 160;
    const left =
      align === "end"
        ? rect.right - MENU_MIN_WIDTH + window.scrollX
        : rect.left + window.scrollX;
    setPos({
      top: rect.bottom + 4 + window.scrollY,
      left: Math.max(8 + window.scrollX, left),
    });
  }, [ctx?.open, align]);

  if (!ctx?.open || pos === null) return null;

  const stop = (e: React.SyntheticEvent) => e.stopPropagation();

  return createPortal(
    <div
      ref={ctx.contentRef}
      role="menu"
      style={{ position: "absolute", top: pos.top, left: pos.left }}
      className={cn(
        "z-[1000] min-w-[10rem] overflow-hidden rounded-md border bg-popover p-1 text-popover-foreground shadow-md",
        className,
      )}
      onMouseDown={stop}
      onPointerDown={stop}
      onClick={stop}
    >
      {children}
    </div>,
    document.body,
  );
}

export interface DropdownMenuItemProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  destructive?: boolean;
}

export const DropdownMenuItem = React.forwardRef<
  HTMLButtonElement,
  DropdownMenuItemProps
>(({ className, destructive, onClick, ...props }, ref) => {
  const ctx = React.useContext(MenuContext);
  return (
    <button
      ref={ref}
      type="button"
      role="menuitem"
      className={cn(
        "flex w-full cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus:bg-accent disabled:pointer-events-none disabled:opacity-50",
        destructive && "text-destructive hover:bg-destructive/10 hover:text-destructive",
        className,
      )}
      onClick={(e) => {
        onClick?.(e);
        ctx?.setOpen(false);
      }}
      {...props}
    />
  );
});
DropdownMenuItem.displayName = "DropdownMenuItem";

export function DropdownMenuSeparator({ className }: { className?: string }) {
  return <div className={cn("-mx-1 my-1 h-px bg-muted", className)} />;
}

export function DropdownMenuLabel({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("px-2 py-1.5 text-xs font-medium text-muted-foreground", className)}>
      {children}
    </div>
  );
}
