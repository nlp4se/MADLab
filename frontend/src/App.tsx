import {
  createBrowserRouter,
  Navigate,
  RouterProvider,
} from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";

import { AppLayout } from "@/components/layout/AppLayout";
import { DesignerPage } from "@/features/designer/DesignerPage";
import { ExecutionDetailPage } from "@/features/executions/ExecutionDetailPage";
import { queryClient } from "@/lib/queryClient";
import { DEFAULT_ROUTE, NAV_ITEMS } from "@/routes";
import { TaxonomyProvider } from "@/taxonomy/TaxonomyContext";

/**
 * Router: all views live under the shared `AppLayout`. The index route
 * redirects to the default view (Configurations). Routes are generated from the
 * central `NAV_ITEMS` table so navigation and routing stay in lockstep.
 */
const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to={DEFAULT_ROUTE} replace /> },
      // NAV_ITEMS includes the designer as `designer/:configId?`: no id opens
      // a new, unsaved configuration (task 11.15), an id opens that config
      // (the Configurations list navigates there on open/create/copy).
      ...NAV_ITEMS.map((item) => ({
        path: (item.routePath ?? item.path).replace(/^\//, ""),
        element: item.element,
      })),
      // `/configs/:id` is kept as an alias resolving to the same editor.
      { path: "configs/:configId", element: <DesignerPage /> },
      // Per-execution detail view + live progress + transcript viewer (task
      // 8.7). `/executions` (the history list) is generated from NAV_ITEMS.
      { path: "executions/:executionId", element: <ExecutionDetailPage /> },
      { path: "*", element: <Navigate to={DEFAULT_ROUTE} replace /> },
    ],
  },
]);

/**
 * App root: wires the server-state cache (React Query) and the taxonomy
 * provider (loaded once, Req 7.4) around the router. Forms mount only after the
 * taxonomy is available.
 */
export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TaxonomyProvider
        fallback={
          <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">
            Loading taxonomy…
          </div>
        }
      >
        <RouterProvider router={router} />
      </TaxonomyProvider>
    </QueryClientProvider>
  );
}

export default App;
