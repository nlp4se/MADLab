import { useMemo, useState } from "react";
import { Loader2, Sparkles, Star } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useTaxonomy } from "@/taxonomy/TaxonomyContext";
import type { ConfigDetail, ConfigSummary } from "@/api";
import { useCopyConfig } from "./useConfigs";
import { ConfigSummaryChips } from "./ConfigSummaryChips";

/**
 * "New from template" (Req 5.7).
 *
 * Two kinds of starting points:
 *  - **Gold cases** — the seeded built-in configurations (`is_builtin`). These
 *    are fully-formed, validated artifacts (RE binary debate, ChatEval S1/S2/
 *    S3); picking one creates an independent, editable copy via the copy
 *    endpoint (the cleanest way to "start from" a gold case).
 *  - **Patterns** — persona patterns and topologies from the taxonomy context.
 *    These are shown as reference starting points the designer (task 8.3/8.4)
 *    applies to a configuration; here they surface the available vocabulary and
 *    link into a fresh design.
 */
export function NewFromTemplateDialog({
  open,
  onOpenChange,
  builtins,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  builtins: ConfigSummary[];
  onCreated: (created: ConfigDetail) => void;
}) {
  const { taxonomy } = useTaxonomy();
  const copy = useCopyConfig();
  const [pendingId, setPendingId] = useState<number | null>(null);

  const personaPatterns = taxonomy.templates.persona_patterns;
  const topologies = taxonomy.templates.topologies;

  const sortedBuiltins = useMemo(
    () => [...builtins].sort((a, b) => a.name.localeCompare(b.name)),
    [builtins],
  );

  const handlePickGold = (config: ConfigSummary) => {
    setPendingId(config.id);
    copy.mutate(
      { id: config.id, body: { name: `${config.name} (copy)` } },
      {
        onSuccess: (created) => {
          onCreated(created);
          onOpenChange(false);
        },
        onSettled: () => setPendingId(null),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New from template</DialogTitle>
          <DialogDescription>
            Start from a built-in gold case, or explore the persona and topology
            patterns available in the taxonomy.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          <section>
            <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <Star className="size-4 text-amber-500" aria-hidden />
              Gold cases
            </h3>
            {sortedBuiltins.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No built-in configurations are available yet.
              </p>
            ) : (
              <ul className="space-y-2">
                {sortedBuiltins.map((config) => (
                  <li key={config.id}>
                    <button
                      type="button"
                      disabled={copy.isPending}
                      onClick={() => handlePickGold(config)}
                      className={cn(
                        "flex w-full items-center justify-between gap-3 rounded-md border p-3 text-left transition-colors hover:bg-accent/60 disabled:pointer-events-none disabled:opacity-60",
                      )}
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium">
                          {config.name}
                        </span>
                        {config.description ? (
                          <span className="block truncate text-xs text-muted-foreground">
                            {config.description}
                          </span>
                        ) : null}
                        <ConfigSummaryChips
                          attributes={config.attributes}
                          className="mt-1.5"
                        />
                      </span>
                      {pendingId === config.id ? (
                        <Loader2 className="size-4 shrink-0 animate-spin" aria-hidden />
                      ) : (
                        <span className="shrink-0 text-xs font-medium text-primary">
                          Use
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <Sparkles className="size-4 text-participants" aria-hidden />
              Persona patterns
            </h3>
            {personaPatterns.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No persona patterns in the taxonomy.
              </p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {personaPatterns.map((p) => (
                  <Badge
                    key={p.key}
                    variant="participants"
                    title={p.description}
                  >
                    {p.label}
                  </Badge>
                ))}
              </div>
            )}
            <p className="mt-2 text-xs text-muted-foreground">
              Apply persona patterns to participants in the visual designer after
              creating a configuration.
            </p>
          </section>

          <section>
            <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <Sparkles className="size-4 text-interaction" aria-hidden />
              Topologies
            </h3>
            {topologies.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No topology patterns in the taxonomy.
              </p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {topologies.map((t) => (
                  <Badge key={t.key} variant="interaction" title={t.description}>
                    {t.label}
                  </Badge>
                ))}
              </div>
            )}
            <p className="mt-2 text-xs text-muted-foreground">
              Topology patterns generate the agent graph in the visual designer.
            </p>
          </section>

          {copy.isError ? (
            <p role="alert" className="text-sm text-destructive">
              {copy.error.message}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
