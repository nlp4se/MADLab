import type { ReactNode } from "react";

/**
 * A simple page scaffold used by the view placeholders until later tasks
 * (8.2–8.7) implement them. Provides a consistent header + body region.
 */
export function PagePlaceholder({
  title,
  description,
  taskRef,
  children,
}: {
  title: string;
  description: string;
  taskRef?: string;
  children?: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </header>
      {children ?? (
        <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
          This view is scaffolded and will be implemented
          {taskRef ? ` in task ${taskRef}` : " in a later task"}.
        </div>
      )}
    </div>
  );
}
