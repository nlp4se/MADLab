import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Copy,
  Download,
  Loader2,
  MoreVertical,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";

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
import type { ConfigDetail, ConfigSummary } from "@/api";

import { ConfigSummaryChips } from "./ConfigSummaryChips";
import { DeleteConfigDialog } from "./DeleteConfigDialog";
import { ImportConfigDialog } from "./ImportConfigDialog";
import { NewFromTemplateDialog } from "./NewFromTemplateDialog";
import {
  useConfigsQuery,
  useCopyConfig,
  useCreateConfig,
  useExportConfig,
} from "./useConfigs";

/**
 * Configurations list view (Req 5.1-5.7, 4.3).
 *
 * Lists every saved configuration as a card with dimension-themed summary chips
 * derived from `ConfigSummaryAttributes`. Each card opens into the visual
 * designer (`/designer/:id`) and exposes per-config actions — copy, export,
 * delete — via an overflow menu. The toolbar offers "New configuration" (blank,
 * defaults pre-filled), "New from template" (gold cases + taxonomy patterns),
 * and "Import" (from a JSON artifact). All writes go through React Query
 * mutations that invalidate the list cache.
 */
export function ConfigurationsPage() {
  const navigate = useNavigate();
  const { data: configs, isLoading, isError, error } = useConfigsQuery();

  const createConfig = useCreateConfig();
  const copyConfig = useCopyConfig();
  const exportConfig = useExportConfig();

  const [templateOpen, setTemplateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [toDelete, setToDelete] = useState<ConfigSummary | null>(null);
  const [copyingId, setCopyingId] = useState<number | null>(null);
  const [exportingId, setExportingId] = useState<number | null>(null);

  const builtins = useMemo(
    () => (configs ?? []).filter((c) => c.is_builtin),
    [configs],
  );

  const openDesigner = (id: number) => navigate(`/designer/${id}`);

  const handleCreateBlank = () => {
    createConfig.mutate(
      { name: "New configuration" },
      { onSuccess: (created: ConfigDetail) => openDesigner(created.id) },
    );
  };

  const handleCopy = (config: ConfigSummary) => {
    setCopyingId(config.id);
    copyConfig.mutate(
      { id: config.id, body: { name: `Copy of ${config.name}` } },
      { onSettled: () => setCopyingId(null) },
    );
  };

  const handleExport = (config: ConfigSummary) => {
    setExportingId(config.id);
    exportConfig.mutate(
      { id: config.id, name: config.name },
      { onSettled: () => setExportingId(null) },
    );
  };

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Configurations
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Browse, create, copy, import/export, and delete MAD configurations.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={() => setImportOpen(true)}
            disabled={createConfig.isPending}
          >
            <Upload className="size-4" aria-hidden />
            Import
          </Button>
          <Button
            variant="outline"
            onClick={() => setTemplateOpen(true)}
            disabled={createConfig.isPending}
          >
            <Sparkles className="size-4" aria-hidden />
            New from template
          </Button>
          <Button onClick={handleCreateBlank} disabled={createConfig.isPending}>
            {createConfig.isPending ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <Plus className="size-4" aria-hidden />
            )}
            New configuration
          </Button>
        </div>
      </header>

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed p-12 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Loading configurations…
        </div>
      ) : isError ? (
        <div
          role="alert"
          className="rounded-lg border border-destructive/50 bg-destructive/5 p-6 text-sm text-destructive"
        >
          Failed to load configurations: {error?.message}
        </div>
      ) : (configs?.length ?? 0) === 0 ? (
        <EmptyState
          onCreate={handleCreateBlank}
          onTemplate={() => setTemplateOpen(true)}
          onImport={() => setImportOpen(true)}
        />
      ) : (
        <ul className="grid gap-3">
          {configs!.map((config) => (
            <li key={config.id}>
              <ConfigCard
                config={config}
                onOpen={() => openDesigner(config.id)}
                onCopy={() => handleCopy(config)}
                onExport={() => handleExport(config)}
                onDelete={() => setToDelete(config)}
                busy={copyingId === config.id || exportingId === config.id}
              />
            </li>
          ))}
        </ul>
      )}

      {copyConfig.isError ? (
        <p role="alert" className="mt-4 text-sm text-destructive">
          Copy failed: {copyConfig.error.message}
        </p>
      ) : null}
      {exportConfig.isError ? (
        <p role="alert" className="mt-4 text-sm text-destructive">
          Export failed: {exportConfig.error.message}
        </p>
      ) : null}
      {createConfig.isError ? (
        <p role="alert" className="mt-4 text-sm text-destructive">
          Create failed: {createConfig.error.message}
        </p>
      ) : null}

      <NewFromTemplateDialog
        open={templateOpen}
        onOpenChange={setTemplateOpen}
        builtins={builtins}
        onCreated={(created) => openDesigner(created.id)}
      />
      <ImportConfigDialog open={importOpen} onOpenChange={setImportOpen} />
      <DeleteConfigDialog
        config={toDelete}
        open={toDelete !== null}
        onOpenChange={(open) => {
          if (!open) setToDelete(null);
        }}
      />
    </div>
  );
}

function ConfigCard({
  config,
  onOpen,
  onCopy,
  onExport,
  onDelete,
  busy,
}: {
  config: ConfigSummary;
  onOpen: () => void;
  onCopy: () => void;
  onExport: () => void;
  onDelete: () => void;
  busy: boolean;
}) {
  return (
    <Card className="transition-colors hover:border-primary/40">
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0 pb-3">
        <div className="min-w-0">
          <button
            type="button"
            onClick={onOpen}
            className="text-left focus:outline-none focus-visible:underline"
          >
            <CardTitle className="flex items-center gap-2 truncate text-base">
              {config.name}
              {config.is_builtin ? (
                <Badge variant="secondary" className="shrink-0">
                  Built-in
                </Badge>
              ) : null}
            </CardTitle>
          </button>
          {config.description ? (
            <CardDescription className="mt-1 line-clamp-2">
              {config.description}
            </CardDescription>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {busy ? (
            <Loader2 className="size-4 animate-spin text-muted-foreground" aria-hidden />
          ) : null}
          <DropdownMenu>
            <DropdownMenuTrigger>
              <Button variant="ghost" size="icon" aria-label={`Actions for ${config.name}`}>
                <MoreVertical className="size-4" aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem onClick={onOpen}>
                <Pencil className="size-4" aria-hidden />
                Open
              </DropdownMenuItem>
              <DropdownMenuItem onClick={onCopy}>
                <Copy className="size-4" aria-hidden />
                Copy
              </DropdownMenuItem>
              <DropdownMenuItem onClick={onExport}>
                <Download className="size-4" aria-hidden />
                Export
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem destructive onClick={onDelete}>
                <Trash2 className="size-4" aria-hidden />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </CardHeader>
      <CardContent className="pb-4">
        <ConfigSummaryChips attributes={config.attributes} />
      </CardContent>
    </Card>
  );
}

function EmptyState({
  onCreate,
  onTemplate,
  onImport,
}: {
  onCreate: () => void;
  onTemplate: () => void;
  onImport: () => void;
}) {
  return (
    <div className="rounded-lg border border-dashed p-12 text-center">
      <h2 className="text-lg font-medium">No configurations yet</h2>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
        Create a configuration from scratch, start from a built-in gold case, or
        import an existing artifact.
      </p>
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        <Button onClick={onCreate}>
          <Plus className="size-4" aria-hidden />
          New configuration
        </Button>
        <Button variant="outline" onClick={onTemplate}>
          <Sparkles className="size-4" aria-hidden />
          New from template
        </Button>
        <Button variant="outline" onClick={onImport}>
          <Upload className="size-4" aria-hidden />
          Import
        </Button>
      </div>
    </div>
  );
}
