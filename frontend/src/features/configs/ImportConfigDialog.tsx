import { useEffect, useRef, useState } from "react";
import { Loader2, Upload } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, type FieldError, type JsonObject } from "@/api";
import { useImportConfig } from "./useConfigs";

/**
 * Import a configuration from a JSON artifact (Req 4.3).
 *
 * Accepts either a pasted JSON blob or an uploaded `.json` file. The pasted/
 * loaded text is parsed client-side (so malformed JSON is caught before any
 * request), then sent to `POST /api/configs/import`. Server-side validation
 * failures (the backend's structured field errors) are surfaced inline so the
 * user can see exactly which part of the artifact is invalid.
 */
export function ImportConfigDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const importMut = useImportConfig();
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [parseError, setParseError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setName("");
      setText("");
      setParseError(null);
      importMut.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleFile = async (file: File) => {
    const content = await file.text();
    setText(content);
    setParseError(null);
    if (!name) setName(file.name.replace(/\.json$/i, ""));
  };

  const handleSubmit = () => {
    setParseError(null);
    let artifact: JsonObject;
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        throw new Error("The artifact must be a JSON object.");
      }
      artifact = parsed as JsonObject;
    } catch (e) {
      setParseError(
        e instanceof Error ? `Invalid JSON: ${e.message}` : "Invalid JSON.",
      );
      return;
    }

    importMut.mutate(
      { artifact, name: name.trim() || null },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  // Surface backend validation field errors when present.
  const fieldErrors: FieldError[] =
    importMut.error instanceof ApiError &&
    importMut.error.payload &&
    typeof importMut.error.payload === "object"
      ? extractFieldErrors(importMut.error.payload)
      : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import configuration</DialogTitle>
          <DialogDescription>
            Paste a configuration artifact, or load one from a JSON file. The
            artifact is validated before it is saved.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="import-name">Name (optional)</Label>
            <Input
              id="import-name"
              placeholder="Override the artifact's name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="import-json">Artifact JSON</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => fileRef.current?.click()}
              >
                <Upload className="size-4" aria-hidden />
                Load file
              </Button>
              <input
                ref={fileRef}
                type="file"
                accept="application/json,.json"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void handleFile(file);
                  e.target.value = "";
                }}
              />
            </div>
            <Textarea
              id="import-json"
              className="min-h-[220px] font-mono text-xs"
              placeholder='{ "schema_version": "…", "participants": { … }, … }'
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </div>

          {parseError ? (
            <p role="alert" className="text-sm text-destructive">
              {parseError}
            </p>
          ) : null}

          {fieldErrors.length > 0 ? (
            <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/5 p-3">
              <p className="mb-1 text-sm font-medium text-destructive">
                The artifact failed validation:
              </p>
              <ul className="list-disc space-y-0.5 pl-5 text-sm text-destructive">
                {fieldErrors.map((err, i) => (
                  <li key={`${err.field}-${i}`}>
                    {err.field ? <code className="font-mono">{err.field}</code> : null}
                    {err.field ? ": " : ""}
                    {err.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : importMut.isError && fieldErrors.length === 0 ? (
            <p role="alert" className="text-sm text-destructive">
              {importMut.error.message}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={importMut.isPending}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={importMut.isPending || text.trim().length === 0}
          >
            {importMut.isPending ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : null}
            Import
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Pull `FieldError[]` out of the backend's structured error envelope. The
 * validation errors live under `detail.errors` (or `detail.fields`) depending
 * on the error path; we probe both defensively.
 */
function extractFieldErrors(payload: object): FieldError[] {
  const obj = payload as Record<string, unknown>;
  const detail = (obj.detail ?? obj) as Record<string, unknown>;
  const raw =
    (detail.errors as unknown) ??
    (detail.fields as unknown) ??
    (obj.errors as unknown) ??
    (obj.fields as unknown);
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((e): e is Record<string, unknown> => typeof e === "object" && e !== null)
    .map((e) => ({
      field: typeof e.field === "string" ? e.field : "",
      message: typeof e.message === "string" ? e.message : String(e.message ?? ""),
    }));
}
