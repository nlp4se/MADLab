import { NavLink, Outlet } from "react-router-dom";
import { MessagesSquare } from "lucide-react";

import { cn } from "@/lib/utils";
import { NAV_ITEMS } from "@/routes";

/**
 * The base application shell: a fixed sidebar with primary navigation and a
 * scrollable content region fed by the active route (`<Outlet />`). The
 * Designer link opens a new, unsaved configuration (`/designer`, task 11.15).
 */
export function AppLayout() {
  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      <aside className="flex w-60 shrink-0 flex-col border-r bg-card">
        <div className="flex items-center gap-2 px-5 py-4">
          <MessagesSquare className="size-6 text-primary" />
          <div className="leading-tight">
            <div className="text-sm font-semibold">MADLab</div>
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
      </aside>

      {/* `min-w-0`: as a flex item the content column would otherwise grow to
          its widest child (long transcript lines, JSON blocks) and push the
          page past the viewport; with it, wide content wraps or scrolls
          inside its own card (task 11.15). */}
      <main className="min-w-0 flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
