import { NavLink, Outlet } from "react-router-dom";
import { MessagesSquare } from "lucide-react";

import { cn } from "@/lib/utils";
import { NAV_ITEMS } from "@/routes";
import { DIMENSION_ORDER, DIMENSION_THEMES } from "@/taxonomy/dimensions";

/**
 * The base application shell: a fixed sidebar with primary navigation and a
 * scrollable content region fed by the active route (`<Outlet />`). The sidebar
 * also surfaces the three dimension colour identities (Reqs 6.6, 7.4) as a
 * legend so the colour language is visible from the first screen.
 */
export function AppLayout() {
  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      <aside className="flex w-60 shrink-0 flex-col border-r bg-card">
        <div className="flex items-center gap-2 px-5 py-4">
          <MessagesSquare className="size-6 text-primary" />
          <div className="leading-tight">
            <div className="text-sm font-semibold">MAD Platform</div>
            <div className="text-xs text-muted-foreground">
              Multi-Agent Debate
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-1 px-3 py-2">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                )
              }
            >
              <item.icon className="size-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t px-5 py-4">
          <div className="mb-2 text-xs font-medium text-muted-foreground">
            Dimensions
          </div>
          <ul className="space-y-1.5">
            {DIMENSION_ORDER.map((key) => {
              const dim = DIMENSION_THEMES[key];
              return (
                <li key={key} className="flex items-center gap-2 text-xs">
                  <span
                    className={cn("inline-block size-2.5 rounded-full", dim.classes.bg)}
                    aria-hidden
                  />
                  <dim.icon className={cn("size-3.5", dim.classes.text)} />
                  <span>{dim.label}</span>
                </li>
              );
            })}
          </ul>
        </div>
      </aside>

      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
