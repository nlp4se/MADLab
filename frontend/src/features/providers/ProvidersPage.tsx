import { useState } from "react";
import { Loader2, MoreVertical, Pencil, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { ProviderResponse } from "@/api";

import { providerKindLabel } from "./kinds";
import { ProviderFormDialog } from "./ProviderFormDialog";
import { DeleteProviderDialog } from "./DeleteProviderDialog";
import { TestConnection } from "./TestConnection";
import { useProvidersQuery } from "./useProviders";

/**
 * Providers management view (Req 8.1-8.6).
 *
 * Lists every configured provider as a card showing its name, kind, base URL,
 * model keys, and the `has_key` state (the API never returns the key itself —
 * Req 8.4 — so the card shows "Configured" / "Not set"). The toolbar adds a
 * provider; each card edits, removes, and tests connectivity (Req 8.5).
 *
 * All writes go through React Query mutations that invalidate the list cache.
 */
export function ProvidersPage() {
  const { data: providers, isLoading, isError, error } = useProvidersQuery();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ProviderResponse | null>(null);
  const [toDelete, setToDelete] = useState<ProviderResponse | null>(null);

  const openAdd = () => {
    setEditing(null);
    setFormOpen(true);
  };

  const openEdit = (provider: ProviderResponse) => {
    setEditing(provider);
    setFormOpen(true);
  };

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Providers</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage model providers and write-only API credentials, then test
            connectivity.
          </p>
        </div>
        <Button onClick={openAdd}>
          <Plus className="size-4" aria-hidden />
          Add provider
        </Button>
      </header>

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed p-12 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Loading providers…
        </div>
      ) : isError ? (
        <div
          role="alert"
          className="rounded-lg border border-destructive/50 bg-destructive/5 p-6 text-sm text-destructive"
        >
          Failed to load providers: {error?.message}
        </div>
      ) : (providers?.length ?? 0) === 0 ? (
        <EmptyState onAdd={openAdd} />
      ) : (
        <ul className="grid gap-3">
          {providers!.map((provider) => (
            <li key={provider.id}>
              <ProviderCard
                provider={provider}
                onEdit={() => openEdit(provider)}
                onDelete={() => setToDelete(provider)}
              />
            </li>
          ))}
        </ul>
      )}

      <ProviderFormDialog
        provider={editing}
        open={formOpen}
        onOpenChange={setFormOpen}
      />
      <DeleteProviderDialog
        provider={toDelete}
        open={toDelete !== null}
        onOpenChange={(open) => {
          if (!open) setToDelete(null);
        }}
      />
    </div>
  );
}

function ProviderCard({
  provider,
  onEdit,
  onDelete,
}: {
  provider: ProviderResponse;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0 pb-3">
        <div className="min-w-0">
          <CardTitle className="flex flex-wrap items-center gap-2 text-base">
            {provider.name}
            <Badge variant="outline">{providerKindLabel(provider.kind)}</Badge>
            <Badge
              variant={provider.has_key ? "secondary" : "outline"}
              aria-label={
                provider.has_key ? "API key configured" : "API key not set"
              }
            >
              {provider.has_key ? "Key configured" : "Key not set"}
            </Badge>
          </CardTitle>
          {provider.base_url ? (
            <CardDescription className="mt-1 truncate font-mono text-xs">
              {provider.base_url}
            </CardDescription>
          ) : (
            <CardDescription className="mt-1 text-xs italic">
              Default endpoint
            </CardDescription>
          )}
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger>
            <Button
              variant="ghost"
              size="icon"
              aria-label={`Actions for ${provider.name}`}
            >
              <MoreVertical className="size-4" aria-hidden />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem onClick={onEdit}>
              <Pencil className="size-4" aria-hidden />
              Edit
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem destructive onClick={onDelete}>
              <Trash2 className="size-4" aria-hidden />
              Remove
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </CardHeader>
      <CardContent className="space-y-3 pb-4">
        <div>
          <p className="mb-1.5 text-xs font-medium text-muted-foreground">
            Models
          </p>
          {provider.models.length > 0 ? (
            <ul className="flex flex-wrap gap-1.5" aria-label="Model keys">
              {provider.models.map((model) => (
                <li key={model}>
                  <span className="inline-flex items-center rounded-full border bg-secondary px-2.5 py-0.5 text-xs font-medium text-secondary-foreground">
                    {model}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs italic text-muted-foreground">
              No model keys configured.
            </p>
          )}
        </div>
        <TestConnection provider={provider} />
      </CardContent>
    </Card>
  );
}

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="rounded-lg border border-dashed p-12 text-center">
      <h2 className="text-lg font-medium">No providers yet</h2>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
        Add a provider to run debates against OpenAI, Anthropic, Gemini,
        Mistral, DeepSeek, or a local Ollama / vLLM / OpenAI-compatible backend.
      </p>
      <div className="mt-5 flex justify-center">
        <Button onClick={onAdd}>
          <Plus className="size-4" aria-hidden />
          Add provider
        </Button>
      </div>
    </div>
  );
}
