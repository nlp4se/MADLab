import { useEffect } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import type { ExecutionSummary } from "@/api";

import { useDeleteExecution } from "./useExecutions";

/**
 * Delete-confirmation dialog for an execution (Req 11.4).
 *
 * Deleting a run removes its per-instance transcripts, decisions, and metrics
 * permanently, so the dialog asks for explicit confirmation before calling the
 * backend. On success it closes and fires `onDeleted` so the caller can e.g.
 * navigate away from a detail view.
 */
export function DeleteExecutionDialog({
  execution,
  open,
  onOpenChange,
  onDeleted,
}: {
  execution: Pick<ExecutionSummary, "id" | "config_name"> | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted?: () => void;
}) {
  const del = useDeleteExecution();

  useEffect(() => {
    if (open) del.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, execution?.id]);

  if (!execution) return null;

  const label = execution.config_name ?? `Execution #${execution.id}`;

  const handleConfirm = () => {
    del.mutate(execution.id, {
      onSuccess: () => {
        onOpenChange(false);
        onDeleted?.();
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="size-5 text-destructive" aria-hidden />
            Delete execution?
          </DialogTitle>
          <DialogDescription>
            This permanently deletes the run{" "}
            <span className="font-medium text-foreground">{label}</span> (#
            {execution.id}) along with its transcripts, decisions, and metrics.
            This cannot be undone.
          </DialogDescription>
        </DialogHeader>

        {del.isError ? (
          <p role="alert" className="text-sm text-destructive">
            {del.error.message}
          </p>
        ) : null}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={del.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={del.isPending}
          >
            {del.isPending ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : null}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
