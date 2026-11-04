import {
  LayoutGrid,
  Network,
  PlugZap,
  Play,
  History,
  type LucideIcon,
} from "lucide-react";

import { ConfigurationsPage } from "@/features/configs/ConfigurationsPage";
import { DesignerPage } from "@/features/designer/DesignerPage";
import { ProvidersPage } from "@/features/providers/ProvidersPage";
import { RunLauncherPage } from "@/features/executions/RunLauncherPage";
import { ExecutionsPage } from "@/features/executions/ExecutionsPage";

/**
 * Central route table. Each view is a placeholder here; later tasks (8.2–8.7)
 * flesh them out. The navigation sidebar is generated from `NAV_ITEMS`, so a
 * new view is one entry + one element.
 */
export interface NavItem {
  /** The sidebar link target. */
  path: string;
  /** The route pattern when it differs from `path` (e.g. an optional id). */
  routePath?: string;
  label: string;
  icon: LucideIcon;
  element: JSX.Element;
}

export const NAV_ITEMS: NavItem[] = [
  {
    path: "/configs",
    label: "Configurations",
    icon: LayoutGrid,
    element: <ConfigurationsPage />,
  },
  {
    // `/designer` opens a new, unsaved configuration; `/designer/<id>` an
    // existing one. One route with an optional id, so the first Save's switch
    // from `/designer` to `/designer/<id>` keeps the same page mounted.
    path: "/designer",
    routePath: "/designer/:configId?",
    label: "Designer",
    icon: Network,
    element: <DesignerPage />,
  },
  {
    path: "/providers",
    label: "Providers",
    icon: PlugZap,
    element: <ProvidersPage />,
  },
  {
    path: "/run",
    label: "Run",
    icon: Play,
    element: <RunLauncherPage />,
  },
  {
    path: "/executions",
    label: "Executions",
    icon: History,
    element: <ExecutionsPage />,
  },
];

/** The default landing route. */
export const DEFAULT_ROUTE = "/configs";
