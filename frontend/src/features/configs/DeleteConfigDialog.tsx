import { useEffect, useState } from "react";
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
import type { ConfigSummary, DeleteResponse } from "@/api";
import { useDeleteConfig } from "./useConfigs";

/**
 * Delete-confirmation dialog with an execution-reference warning (Req 5.4).
 *
 * Because the referencing-execution count is only known server-side, the dialog
 * runs in two phases:
 *  1. **Confirm** — explains the delete is permanent and that any execution
 *     history keeps an immutable snapshot (so history survives).
 *  2. **Acknowledge** — after the delete returns `referencing_executions`, if
 *     any executions referenced the config we surface the count so the user is
 *     warned after the fact; otherwise we close immediately.
 */
export function DeleteConfigDialog({
  config,
  open,
  onOpenChange,
}: {
  config: ConfigSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const del = useDeleteConfig();
  const [result, setResult] = useState<DeleteResponse | null>(null);

  // Reset transient state whenever the dialog is (re)opened for a config.
  useEffect(() => {
    if (open) {
      setResult(null);
      del.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, config?.id]);

  if (!config) return null;

  const handleConfirm = () => {
    del.mutate(config.id, {
      onSuccess: (res) => {
        if (res.referencing_executions > 0) {
          // Keep the dialog open to acknowledge the post-delete warning.
          setResult(res);
        } else {
          onOpenChange(false);
        }
      },
    });
  };

  const acknowledged = result !== null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="size-5 text-destructive" aria-hidden />
            {acknowledged ? "Configuration deleted" : "Delete configuration?"}
          </DialogTitle>
          <DialogDescription>
            {acknowledged ? (
              <>
                <span className="font-medium text-foreground">
                  {config.name}
                </span>{" "}
                was deleted. It was referenced by{" "}
                <span className="font-medium text-foreground">
                  {result.referencing_executions}
                </span>{" "}
                execution
                {result.referencing_executions === 1 ? "" : "s"}. Those
                executions keep an immutable snapshot of the configuration, so
                their history is preserved.
              </>
            ) : (
              <>
                This permanently deletes{" "}
                <span className="font-medium text-foreground">
                  {config.name}
                </span>
                . Any executions that used it keep their own immutable snapshot,
                so run history is preserved — but the configuration itself cannot
                be recovered.
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        {del.isError ? (
          <p role="alert" className="text-sm text-destructive">
            {del.error.message}
          </p>
        ) : null}

        <DialogFooter>
          {acknowledged ? (
            <Button onClick={() => onOpenChange(false)}>Done</Button>
          ) : (
            <>
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
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
