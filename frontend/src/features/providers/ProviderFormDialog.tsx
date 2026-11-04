import { useEffect, useState } from "react";
import { Loader2, Plus, X } from "lucide-react";

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
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  PROVIDER_FAMILY_LABELS,
  PROVIDER_KINDS,
  defaultFamily,
  isMixedKind,
  type ProviderCreateRequest,
  type ProviderFamily,
  type ProviderKind,
  type ProviderResponse,
  type ProviderUpdateRequest,
} from "@/api";

import { providerKindLabel } from "./kinds";
import { useCreateProvider, useUpdateProvider } from "./useProviders";

/**
 * Add / edit provider dialog (Req 8.1-8.4).
 *
 * Collects the provider name, a kind selector over the eight supported kinds
 * (Req 8.2), an optional base URL, a model-keys list editor (Req 8.3), and a
 * write-only API key field (Req 8.4).
 *
 * The API key is **write-only** and never returned by the API, so the field is
 * always empty on open and its treatment is tri-state on save:
 *  - create: send the typed key (or omit when blank).
 *  - edit: leave blank to keep the stored key; type a value to replace it; use
 *    the explicit "Clear stored key" control to remove it (sends `null`).
 * The current state is shown as a "configured" / "not set" badge rather than
 * the key value.
 */
type KeyAction = "keep" | "set" | "clear";

export function ProviderFormDialog({
  provider,
  open,
  onOpenChange,
}: {
  /** The provider being edited, or `null`/`undefined` to add a new one. */
  provider?: ProviderResponse | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const isEdit = provider != null;
  const create = useCreateProvider();
  const update = useUpdateProvider();
  const pending = create.isPending || update.isPending;
  const mutationError = isEdit ? update.error : create.error;

  const [name, setName] = useState("");
  const [kind, setKind] = useState<ProviderKind>("openai");
  // Base-model family (task 11.9): pre-filled from the kind; only editable for
  // mixed kinds (fixed kinds always show their derived family).
  const [family, setFamily] = useState<ProviderFamily>(defaultFamily("openai"));
  const [baseUrl, setBaseUrl] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [modelDraft, setModelDraft] = useState("");
  // Tri-state write-only key handling (Req 8.4).
  const [keyAction, setKeyAction] = useState<KeyAction>("keep");
  const [apiKey, setApiKey] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  // (Re)seed the form whenever the dialog opens for a given provider.
  useEffect(() => {
    if (!open) return;
    setName(provider?.name ?? "");
    setKind(provider?.kind ?? "openai");
    setFamily(provider?.family ?? defaultFamily(provider?.kind ?? "openai"));
    setBaseUrl(provider?.base_url ?? "");
    setModels(provider?.models ?? []);
    setModelDraft("");
    // New providers start in "set" (their only option); edits default to "keep".
    setKeyAction(isEdit ? "keep" : "set");
    setApiKey("");
    setFormError(null);
    create.reset();
    update.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, provider?.id]);

  const addModel = () => {
    const value = modelDraft.trim();
    if (!value || models.includes(value)) {
      setModelDraft("");
      return;
    }
    setModels((prev) => [...prev, value]);
    setModelDraft("");
  };

  const removeModel = (value: string) =>
    setModels((prev) => prev.filter((m) => m !== value));

  const handleModelKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addModel();
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      setFormError("Name is required.");
      return;
    }
    setFormError(null);

    const base = baseUrl.trim() ? baseUrl.trim() : null;

    if (isEdit) {
      const body: ProviderUpdateRequest = {
        name: trimmedName,
        kind,
        base_url: base,
        models,
      };
      // Family is sent only for mixed kinds; fixed kinds derive it.
      if (isMixedKind(kind)) body.family = family;
      // Tri-state key (Req 8.4): omit=keep, string=set, null=clear.
      if (keyAction === "set") body.api_key = apiKey;
      else if (keyAction === "clear") body.api_key = null;
      update.mutate(
        { id: provider!.id, body },
        { onSuccess: () => onOpenChange(false) },
      );
      return;
    }

    const body: ProviderCreateRequest = {
      name: trimmedName,
      kind,
      base_url: base,
      models,
    };
    if (isMixedKind(kind)) body.family = family;
    if (apiKey.trim()) body.api_key = apiKey;
    create.mutate(body, { onSuccess: () => onOpenChange(false) });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit provider" : "Add provider"}</DialogTitle>
          <DialogDescription>
            Configure the provider kind, endpoint, available models, and API
            key. The key is stored encrypted and never shown again.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="provider-name">Name</Label>
            <Input
              id="provider-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. OpenAI (prod)"
              autoFocus
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="provider-kind">Kind</Label>
            <Select
              id="provider-kind"
              value={kind}
              onChange={(e) => {
                const next = e.target.value as ProviderKind;
                setKind(next);
                // Re-derive from the new kind (mirrors the backend on update).
                setFamily(defaultFamily(next));
              }}
            >
              {PROVIDER_KINDS.map((k) => (
                <option key={k} value={k}>
                  {providerKindLabel(k)}
                </option>
              ))}
            </Select>
          </div>

          <FamilyField kind={kind} family={family} onChange={setFamily} />

          <div className="space-y-1.5">
            <Label htmlFor="provider-base-url">Base URL</Label>
            <Input
              id="provider-base-url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="Optional — e.g. http://localhost:11434 for Ollama"
            />
          </div>

          <ModelKeysEditor
            models={models}
            draft={modelDraft}
            onDraftChange={setModelDraft}
            onAdd={addModel}
            onRemove={removeModel}
            onKeyDown={handleModelKeyDown}
          />

          <ApiKeyField
            isEdit={isEdit}
            hasKey={provider?.has_key ?? false}
            keyAction={keyAction}
            onKeyActionChange={setKeyAction}
            apiKey={apiKey}
            onApiKeyChange={setApiKey}
          />

          {formError ? (
            <p role="alert" className="text-sm text-destructive">
              {formError}
            </p>
          ) : null}
          {mutationError ? (
            <p role="alert" className="text-sm text-destructive">
              {isEdit ? "Update" : "Create"} failed: {mutationError.message}
            </p>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={pending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              ) : null}
              {isEdit ? "Save changes" : "Add provider"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Base-model family (task 11.9). Fixed kinds show their derived family
 * read-only with the reason; mixed kinds (a vendor with both open- and
 * closed-weight models, or a generic gateway) offer a select.
 */
function FamilyField({
  kind,
  family,
  onChange,
}: {
  kind: ProviderKind;
  family: ProviderFamily;
  onChange: (family: ProviderFamily) => void;
}) {
  const mixed = isMixedKind(kind);
  const value = mixed ? family : defaultFamily(kind);
  return (
    <div className="space-y-1.5">
      <Label htmlFor="provider-family">Family</Label>
      <Select
        id="provider-family"
        value={value}
        disabled={!mixed}
        aria-describedby="provider-family-help"
        onChange={(e) => onChange(e.target.value as ProviderFamily)}
      >
        {(Object.keys(PROVIDER_FAMILY_LABELS) as ProviderFamily[]).map((f) => (
          <option key={f} value={f}>
            {PROVIDER_FAMILY_LABELS[f]}
          </option>
        ))}
      </Select>
      <p id="provider-family-help" className="text-xs text-muted-foreground">
        {mixed
          ? `${providerKindLabel(kind)} can serve open- or closed-weight models; choose the family of the models this provider exposes. Participants bound to it inherit this family.`
          : `Fixed by the kind: ${providerKindLabel(kind)} models are ${PROVIDER_FAMILY_LABELS[value].toLowerCase()}. Participants bound to this provider inherit it.`}
      </p>
    </div>
  );
}

function ModelKeysEditor({
  models,
  draft,
  onDraftChange,
  onAdd,
  onRemove,
  onKeyDown,
}: {
  models: string[];
  draft: string;
  onDraftChange: (value: string) => void;
  onAdd: () => void;
  onRemove: (value: string) => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor="provider-model-draft">Model keys</Label>
      <p className="text-xs text-muted-foreground">
        The model identifiers available from this provider (e.g.{" "}
        <code>gpt-4o</code>, <code>llama3</code>).
      </p>
      <div className="flex gap-2">
        <Input
          id="provider-model-draft"
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Add a model key and press Enter"
        />
        <Button
          type="button"
          variant="outline"
          onClick={onAdd}
          aria-label="Add model key"
        >
          <Plus className="size-4" aria-hidden />
          Add
        </Button>
      </div>
      {models.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-2" aria-label="Model keys">
          {models.map((model) => (
            <li key={model}>
              <span className="inline-flex items-center gap-1 rounded-full border bg-secondary px-2.5 py-0.5 text-xs font-medium text-secondary-foreground">
                {model}
                <button
                  type="button"
                  onClick={() => onRemove(model)}
                  aria-label={`Remove ${model}`}
                  className="rounded-full opacity-70 transition-opacity hover:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="size-3" aria-hidden />
                </button>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">No model keys yet.</p>
      )}
    </div>
  );
}

function ApiKeyField({
  isEdit,
  hasKey,
  keyAction,
  onKeyActionChange,
  apiKey,
  onApiKeyChange,
}: {
  isEdit: boolean;
  hasKey: boolean;
  keyAction: KeyAction;
  onKeyActionChange: (action: KeyAction) => void;
  apiKey: string;
  onApiKeyChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1.5 rounded-md border bg-muted/30 p-3">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor="provider-api-key">API key</Label>
        {/* Current key state (Req 8.4) — never the key value itself. */}
        <Badge
          variant={hasKey ? "secondary" : "outline"}
          aria-label={hasKey ? "API key configured" : "API key not set"}
        >
          {hasKey ? "Configured" : "Not set"}
        </Badge>
      </div>

      {isEdit ? (
        <>
          <p className="text-xs text-muted-foreground">
            The stored key is never displayed. Leave blank to keep it, enter a
            new value to replace it, or clear it to remove it.
          </p>
          <div className="flex flex-wrap gap-2 pt-1">
            <KeyActionToggle
              label="Keep existing"
              active={keyAction === "keep"}
              onClick={() => onKeyActionChange("keep")}
            />
            <KeyActionToggle
              label="Replace"
              active={keyAction === "set"}
              onClick={() => onKeyActionChange("set")}
            />
            <KeyActionToggle
              label="Clear stored key"
              active={keyAction === "clear"}
              onClick={() => onKeyActionChange("clear")}
              destructive
              disabled={!hasKey}
            />
          </div>
          {keyAction === "set" ? (
            <Input
              id="provider-api-key"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => onApiKeyChange(e.target.value)}
              placeholder="Enter new API key"
              className="mt-2"
            />
          ) : null}
          {keyAction === "clear" ? (
            <p role="status" className="pt-1 text-xs text-destructive">
              The stored key will be removed on save.
            </p>
          ) : null}
        </>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            Optional for local backends (Ollama / vLLM). Stored encrypted.
          </p>
          <Input
            id="provider-api-key"
            type="password"
            autoComplete="off"
            value={apiKey}
            onChange={(e) => onApiKeyChange(e.target.value)}
            placeholder="Enter API key"
          />
        </>
      )}
    </div>
  );
}

function KeyActionToggle({
  label,
  active,
  onClick,
  destructive,
  disabled,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  destructive?: boolean;
  disabled?: boolean;
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant={active ? (destructive ? "destructive" : "default") : "outline"}
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
    >
      {label}
    </Button>
  );
}
