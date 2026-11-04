import { useContext, useEffect } from "react";
import { UNSAFE_DataRouterContext, useBlocker } from "react-router-dom";

import { useDesignerStore } from "./designerStore";

/** The confirmation shown before leaving the designer with unsaved changes. */
export const LEAVE_DESIGNER_MESSAGE =
  "You have unsaved changes in this configuration.\n\n" +
  "Leave the designer and discard them?";

/**
 * Asks before leaving the designer with unsaved changes (task 11.15), for new
 * and existing configs alike:
 *   - closing / reloading the tab: the browser's `beforeunload` prompt;
 *   - in-app navigation to another path: a `useBlocker` confirmation (only
 *     available under a data router, i.e. the app's `createBrowserRouter`;
 *     plain `<MemoryRouter>` test harnesses get the `beforeunload` part only).
 *
 * The dirty flag is read live from the store when a navigation starts, so the
 * first Save's switch to `/designer/<id>` (made right after the store is
 * marked saved) is never blocked. Query-string-only changes are not blocked.
 */
export function UnsavedChangesGuard() {
  const dirty = useDesignerStore((s) => s.dirty);

  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // Legacy browsers need a returnValue to show the prompt.
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  const dataRouter = useContext(UNSAFE_DataRouterContext);
  return dataRouter ? <NavigationBlocker /> : null;
}

function NavigationBlocker() {
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      useDesignerStore.getState().dirty &&
      currentLocation.pathname !== nextLocation.pathname,
  );

  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm(LEAVE_DESIGNER_MESSAGE)) blocker.proceed();
    else blocker.reset();
  }, [blocker]);

  return null;
}
