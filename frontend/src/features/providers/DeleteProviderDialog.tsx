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
import type { ProviderResponse } from "@/api";

import { useDeleteProvider } from "./useProviders";

/**
 * Delete-confirmation dialog for a provider (Req 8.1).
 *
 * Removing a provider also removes its encrypted key, so the action is
 * permanent; the dialog makes that explicit and closes on success.
 */
export function DeleteProviderDialog({
  provider,
  open,
  onOpenChange,
}: {
  provider: ProviderResponse | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const del = useDeleteProvider();

  useEffect(() => {
    if (open) del.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, provider?.id]);

  if (!provider) return null;

  const handleConfirm = () => {
    del.mutate(provider.id, { onSuccess: () => onOpenChange(false) });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="size-5 text-destructive" aria-hidden />
            Remove provider?
          </DialogTitle>
          <DialogDescription>
            This permanently removes{" "}
            <span className="font-medium text-foreground">{provider.name}</span>{" "}
            and its stored API key. Configurations that bind models to this
            provider will no longer be runnable until re-pointed.
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
            Remove
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
