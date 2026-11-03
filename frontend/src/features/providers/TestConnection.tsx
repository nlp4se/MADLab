import { useState } from "react";
import { CheckCircle2, Loader2, PlugZap, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import type { ProviderResponse } from "@/api";

import { useTestProvider } from "./useProviders";

/**
 * Test-connection control with result feedback (Req 8.5).
 *
 * Fires `POST /api/providers/{id}/test` with an optional model (picked from the
 * provider's configured model keys) and renders the success/error message
 * returned by the backend, including the measured latency when present.
 */
export function TestConnection({ provider }: { provider: ProviderResponse }) {
  const test = useTestProvider();
  const [model, setModel] = useState<string>("");

  const handleTest = () => {
    test.mutate({
      id: provider.id,
      body: { model: model.trim() ? model : null },
    });
  };

  const result = test.data;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {provider.models.length > 0 ? (
          <Select
            aria-label={`Test model for ${provider.name}`}
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="h-9 w-auto min-w-40"
          >
            <option value="">Default model</option>
            {provider.models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </Select>
        ) : null}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleTest}
          disabled={test.isPending}
        >
          {test.isPending ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <PlugZap className="size-4" aria-hidden />
          )}
          Test connection
        </Button>
      </div>

      {test.isError ? (
        <TestResult ok={false} message={test.error.message} />
      ) : result ? (
        <TestResult
          ok={result.ok}
          message={result.message}
          model={result.model}
          latencyS={result.latency_s}
        />
      ) : null}
    </div>
  );
}

function TestResult({
  ok,
  message,
  model,
  latencyS,
}: {
  ok: boolean;
  message: string;
  model?: string | null;
  latencyS?: number | null;
}) {
  return (
    <div
      role="status"
      className={
        ok
          ? "flex items-start gap-2 rounded-md border border-emerald-500/40 bg-emerald-500/5 p-2.5 text-sm text-emerald-700 dark:text-emerald-400"
          : "flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-2.5 text-sm text-destructive"
      }
    >
      {ok ? (
        <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden />
      ) : (
        <XCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
      )}
      <span className="min-w-0">
        {message}
        {model ? <span className="text-muted-foreground"> · {model}</span> : null}
        {latencyS != null ? (
          <span className="text-muted-foreground">
            {" "}
            · {formatLatency(latencyS)}
          </span>
        ) : null}
      </span>
    </div>
  );
}

/** Render latency seconds as ms for small values, else seconds. */
export function formatLatency(latencyS: number): string {
  if (latencyS < 1) return `${Math.round(latencyS * 1000)} ms`;
  return `${latencyS.toFixed(2)} s`;
}
