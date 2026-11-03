import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Loader2, Play, Upload } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type {
  ConfigDetail,
  DatasetPreviewResponse,
  DatasetResponse,
  ExecutionCreateRequest,
} from "@/api";

import { ConfigSummaryChips } from "@/features/configs/ConfigSummaryChips";
import { templateFields, type TemplateField } from "./inputSpec";
import {
  useConfigDetailQuery,
  useConfigsQuery,
  useCreateExecution,
  usePreviewDataset,
  useUploadDataset,
} from "./useRunLauncher";

type InputMode = "single" | "batch";

/**
 * Run launcher view (Req 10.1-10.5).
 *
 * Flow: pick a configuration → the config's summary and under-development state
 * are shown; if the config selects any non-executable value the launch is gated
 * with a clear explanation (Req 7.5). Then choose an input mode:
 *
 *  - Single (Req 10.2): a form of template fields derived from the config's
 *    `input_spec` placeholders; collects `{placeholder: value}`.
 *  - Batch (Req 10.1, 10.3): upload a CSV, map its columns to template
 *    placeholders, optionally pick a ground-truth column, and preview the
 *    resolved input for a sample row.
 *
 * Launch posts to `POST /api/executions` (Req 10.4) and, on success, navigates
 * to the executions history where progress is rendered (task 8.7, Req 10.5).
 */
export function RunLauncherPage() {
  const navigate = useNavigate();
  const configsQuery = useConfigsQuery();

  const [configId, setConfigId] = useState<number | null>(null);
  const [mode, setMode] = useState<InputMode>("single");

  const detailQuery = useConfigDetailQuery(configId);
  const createExecution = useCreateExecution();

  // Single-mode field values keyed by placeholder.
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});

  // Batch-mode state.
  const [dataset, setDataset] = useState<DatasetResponse | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [groundTruthColumn, setGroundTruthColumn] = useState<string>("");

  const config = detailQuery.data ?? null;
  const gated = (config?.under_development.length ?? 0) > 0;

  const fields = useMemo<TemplateField[]>(
    () => (config ? templateFields(config) : []),
    [config],
  );

  function handlePickConfig(value: string) {
    const id = value === "" ? null : Number(value);
    setConfigId(id);
    // Reset per-config input state when switching configs.
    setFieldValues({});
    setDataset(null);
    setMapping({});
    setGroundTruthColumn("");
    createExecution.reset();
  }

  function buildRequest(): ExecutionCreateRequest | null {
    if (configId === null) return null;
    if (mode === "single") {
      const input: Record<string, string> = {};
      for (const field of fields) {
        input[field.key] = fieldValues[field.key] ?? "";
      }
      return { config_id: configId, input };
    }
    if (!dataset) return null;
    return {
      config_id: configId,
      batch: {
        dataset_id: dataset.id,
        mapping,
        ground_truth_column:
          groundTruthColumn === "" ? null : groundTruthColumn,
      },
    };
  }

  const canLaunch =
    configId !== null &&
    !gated &&
    (mode === "single"
      ? fields.length > 0
      : dataset !== null && Object.keys(mapping).length > 0) &&
    !createExecution.isPending;

  async function handleLaunch() {
    const body = buildRequest();
    if (!body) return;
    const execution = await createExecution.mutateAsync(body);
    navigate(`/executions/${execution.id}`);
  }

  return (
    <div className="mx-auto max-w-4xl px-8 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Run</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Launch a configuration over a single ad-hoc input or a dataset batch.
        </p>
      </header>

      <div className="space-y-5">
        {/* --- Step 1: pick a configuration --- */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Configuration</CardTitle>
            <CardDescription>
              Pick the configuration to run.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-1.5">
              <Label htmlFor="config-select">Configuration</Label>
              {configsQuery.isLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                  Loading configurations…
                </div>
              ) : configsQuery.isError ? (
                <p role="alert" className="text-sm text-destructive">
                  Failed to load configurations:{" "}
                  {configsQuery.error?.message}
                </p>
              ) : (
                <Select
                  id="config-select"
                  aria-label="Configuration"
                  value={configId === null ? "" : String(configId)}
                  onChange={(e) => handlePickConfig(e.target.value)}
                >
                  <option value="">Select a configuration…</option>
                  {configsQuery.data?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </Select>
              )}
            </div>

            {configId !== null && detailQuery.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden />
                Loading configuration…
              </div>
            ) : config ? (
              <ConfigSummaryFromDetail config={config} />
            ) : null}

            {gated && config ? (
              <UnderDevelopmentGate config={config} />
            ) : null}
          </CardContent>
        </Card>

        {/* --- Step 2: input mode (only once a config is picked) --- */}
        {config ? (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Input</CardTitle>
              <CardDescription>
                Run a single ad-hoc input or a dataset batch.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div
                role="radiogroup"
                aria-label="Input mode"
                className="inline-flex rounded-md border p-0.5"
              >
                <ModeToggle
                  active={mode === "single"}
                  onClick={() => setMode("single")}
                  label="Single input"
                />
                <ModeToggle
                  active={mode === "batch"}
                  onClick={() => setMode("batch")}
                  label="Batch (CSV)"
                />
              </div>

              {mode === "single" ? (
                <SingleInputForm
                  fields={fields}
                  values={fieldValues}
                  onChange={(key, value) =>
                    setFieldValues((prev) => ({ ...prev, [key]: value }))
                  }
                />
              ) : (
                <BatchInputForm
                  config={config}
                  dataset={dataset}
                  onDataset={(d) => {
                    setDataset(d);
                    setMapping({});
                    setGroundTruthColumn("");
                  }}
                  mapping={mapping}
                  onMappingChange={(column, placeholder) =>
                    setMapping((prev) => {
                      const next = { ...prev };
                      if (placeholder === "") delete next[column];
                      else next[column] = placeholder;
                      return next;
                    })
                  }
                  placeholders={fields}
                  groundTruthColumn={groundTruthColumn}
                  onGroundTruthChange={setGroundTruthColumn}
                />
              )}
            </CardContent>
          </Card>
        ) : null}

        {/* --- Launch --- */}
        {config ? (
          <div className="flex flex-col items-end gap-2">
            {createExecution.isError ? (
              <p role="alert" className="text-sm text-destructive">
                Failed to launch: {createExecution.error?.message}
              </p>
            ) : null}
            <Button
              size="lg"
              disabled={!canLaunch}
              onClick={() => void handleLaunch()}
            >
              {createExecution.isPending ? (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              ) : (
                <Play className="size-4" aria-hidden />
              )}
              Launch
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/* ----------------------------- sub-components ---------------------------- */

function ConfigSummaryFromDetail({ config }: { config: ConfigDetail }) {
  return (
    <div className="rounded-md border bg-muted/30 p-3">
      <p className="text-sm font-medium">{config.name}</p>
      {config.description ? (
        <p className="mt-0.5 text-xs text-muted-foreground">
          {config.description}
        </p>
      ) : null}
      <ConfigSummaryChips
        attributes={summaryAttributesFromArtifact(config)}
        className="mt-2"
      />
    </div>
  );
}

/**
 * The under-development gate (Req 7.5): the config selects values the engine
 * cannot yet execute, so launching is blocked with an explanation listing what
 * must change.
 */
function UnderDevelopmentGate({ config }: { config: ConfigDetail }) {
  return (
    <div
      role="alert"
      className="rounded-md border border-amber-500/60 bg-amber-500/10 p-3 text-sm"
    >
      <p className="flex items-center gap-2 font-medium text-amber-700 dark:text-amber-400">
        <AlertTriangle className="size-4" aria-hidden />
        This configuration can't be run yet
      </p>
      <p className="mt-1 text-muted-foreground">
        It selects {config.under_development.length}{" "}
        {config.under_development.length === 1 ? "value" : "values"} that are
        under development and not yet executable. Change the following in the
        designer before running:
      </p>
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {config.under_development.map((key) => (
          <li key={key}>
            <Badge
              variant="outline"
              className="border-amber-500 font-mono text-amber-700 dark:text-amber-400"
            >
              {key}
            </Badge>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ModeToggle({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      onClick={onClick}
      className={
        "rounded px-3 py-1.5 text-sm font-medium transition-colors " +
        (active
          ? "bg-primary text-primary-foreground"
          : "text-muted-foreground hover:text-foreground")
      }
    >
      {label}
    </button>
  );
}

function SingleInputForm({
  fields,
  values,
  onChange,
}: {
  fields: TemplateField[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
}) {
  if (fields.length === 0) {
    return (
      <p className="text-sm italic text-muted-foreground">
        This configuration's template declares no input fields.
      </p>
    );
  }
  return (
    <div className="grid gap-4">
      {fields.map((field) => (
        <div key={field.key} className="grid gap-1.5">
          <Label htmlFor={`field-${field.key}`}>
            {field.label}
            <span className="ml-1.5 font-mono text-xs text-muted-foreground">
              {`{{${field.key}}}`}
            </span>
          </Label>
          <Textarea
            id={`field-${field.key}`}
            rows={2}
            value={values[field.key] ?? ""}
            onChange={(e) => onChange(field.key, e.target.value)}
          />
        </div>
      ))}
    </div>
  );
}

function BatchInputForm({
  config,
  dataset,
  onDataset,
  mapping,
  onMappingChange,
  placeholders,
  groundTruthColumn,
  onGroundTruthChange,
}: {
  config: ConfigDetail;
  dataset: DatasetResponse | null;
  onDataset: (d: DatasetResponse) => void;
  mapping: Record<string, string>;
  onMappingChange: (column: string, placeholder: string) => void;
  placeholders: TemplateField[];
  groundTruthColumn: string;
  onGroundTruthChange: (column: string) => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadDataset();
  const preview = usePreviewDataset();
  const [previewData, setPreviewData] = useState<DatasetPreviewResponse | null>(
    null,
  );

  async function handleFile(file: File | undefined) {
    if (!file) return;
    const d = await upload.mutateAsync({ file });
    onDataset(d);
    setPreviewData(null);
  }

  async function handlePreview() {
    if (!dataset) return;
    const data = await preview.mutateAsync({
      datasetId: dataset.id,
      body: { mapping, config_id: config.id, row_index: 0 },
    });
    setPreviewData(data);
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-1.5">
        <Label>Dataset (CSV)</Label>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          aria-label="Upload CSV"
          onChange={(e) => void handleFile(e.target.files?.[0])}
        />
        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="outline"
            disabled={upload.isPending}
            onClick={() => fileInputRef.current?.click()}
          >
            {upload.isPending ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <Upload className="size-4" aria-hidden />
            )}
            {dataset ? "Replace CSV" : "Upload CSV"}
          </Button>
          {dataset ? (
            <span className="text-sm text-muted-foreground">
              {dataset.original_filename} · {dataset.row_count}{" "}
              {dataset.row_count === 1 ? "row" : "rows"}
            </span>
          ) : null}
        </div>
        {upload.isError ? (
          <p role="alert" className="text-sm text-destructive">
            Upload failed: {upload.error?.message}
          </p>
        ) : null}
      </div>

      {dataset ? (
        <>
          <div className="grid gap-2">
            <Label>Map columns to placeholders</Label>
            <p className="text-xs text-muted-foreground">
              Assign each template placeholder to a dataset column.
            </p>
            <ul className="grid gap-2">
              {dataset.columns.map((column) => (
                <li
                  key={column}
                  className="grid grid-cols-[1fr_auto_1fr] items-center gap-2"
                >
                  <span className="truncate font-mono text-sm">{column}</span>
                  <span className="text-muted-foreground">→</span>
                  <Select
                    aria-label={`Placeholder for ${column}`}
                    value={mapping[column] ?? ""}
                    onChange={(e) => onMappingChange(column, e.target.value)}
                  >
                    <option value="">(ignore)</option>
                    {placeholders.map((field) => (
                      <option key={field.key} value={field.key}>
                        {field.label} ({`{{${field.key}}}`})
                      </option>
                    ))}
                  </Select>
                </li>
              ))}
            </ul>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="ground-truth-select">
              Ground-truth column (optional)
            </Label>
            <Select
              id="ground-truth-select"
              aria-label="Ground-truth column"
              value={groundTruthColumn}
              onChange={(e) => onGroundTruthChange(e.target.value)}
            >
              <option value="">(none)</option>
              {dataset.columns.map((column) => (
                <option key={column} value={column}>
                  {column}
                </option>
              ))}
            </Select>
          </div>

          <div className="grid gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-fit"
              disabled={
                Object.keys(mapping).length === 0 || preview.isPending
              }
              onClick={() => void handlePreview()}
            >
              {preview.isPending ? (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              ) : null}
              Preview sample row
            </Button>
            {preview.isError ? (
              <p role="alert" className="text-sm text-destructive">
                Preview failed: {preview.error?.message}
              </p>
            ) : null}
            {previewData ? (
              <div className="rounded-md border bg-muted/30 p-3">
                <p className="mb-1 text-xs font-medium text-muted-foreground">
                  Resolved input · row {previewData.row_index}
                </p>
                <pre className="whitespace-pre-wrap break-words text-sm">
                  {previewData.resolved_input}
                </pre>
              </div>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  );
}

/* -------------------------------- helpers -------------------------------- */

/**
 * The config detail carries the full artifact but not the pre-computed summary
 * attributes (those live on `ConfigSummary`). Reconstruct the subset the chips
 * need from the artifact so the launcher can show a summary without a second
 * request. Missing values degrade gracefully to placeholders.
 */
function summaryAttributesFromArtifact(config: ConfigDetail) {
  const artifact = config.artifact as Record<string, unknown>;
  const rec = (v: unknown): Record<string, unknown> =>
    v && typeof v === "object" ? (v as Record<string, unknown>) : {};
  const participants = rec(artifact["participants"]);
  const interaction = rec(artifact["interaction"]);
  const topology = rec(interaction["topology"]);
  const protocol = rec(interaction["protocol"]);
  const agreement = rec(artifact["agreement"]);
  const nodes = participants["nodes"];
  const str = (v: unknown, fallback = ""): string =>
    typeof v === "string" ? v : fallback;

  return {
    participant_count: Array.isArray(nodes) ? nodes.length : 0,
    topology_structure: str(topology["structure"], "—"),
    topology_pattern: str(topology["pattern"]) || null,
    protocol_mechanism: str(protocol["mechanism"], "—"),
    authority: str(agreement["authority"], "—"),
    resolution: str(agreement["resolution"], "—"),
    under_development: config.under_development.length > 0,
  };
}
