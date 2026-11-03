import { type ReactNode } from "react";
import { AlertTriangle, ChevronDown, Wrench } from "lucide-react";

import type { FieldError, SubDimensionDTO, ValueDTO } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";

/**
 * Shared, taxonomy-driven form primitives for the designer dimension panels
 * (task 8.4). They render selects / checkboxes directly from catalog values so
 * labels, descriptions/tooltips (Req 7.4), defaults (Req 7.1), and "under
 * development" badges (Req 7.5) come from a single data source and never drift.
 */

/** A small "under development" badge for a non-executable taxonomy value (Req 7.5). */
export function UnderDevBadge({ className }: { className?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1 border-amber-500/60 bg-amber-500/10 text-amber-700 dark:text-amber-400",
        className,
      )}
      title="Configurable and savable, but not yet executable by the engine."
    >
      <Wrench className="size-3" aria-hidden />
      Under development
    </Badge>
  );
}

/**
 * A labelled group of fields. `tone` optionally marks the group as
 * prompt-designed (free-form persona/system-prompt text) vs. structured
 * (everything else) per the design's distinction.
 */
export function FieldGroup({
  title,
  description,
  tone,
  children,
}: {
  title: string;
  description?: string;
  tone?: "prompt" | "structured";
  children: ReactNode;
}) {
  return (
    <section className="space-y-3" data-tone={tone}>
      <div className="space-y-0.5">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-semibold">{title}</h4>
          {tone ? (
            <Badge variant="secondary" className="font-normal">
              {tone === "prompt" ? "Prompt-designed" : "Structured"}
            </Badge>
          ) : null}
        </div>
        {description ? (
          <p className="text-xs text-muted-foreground">{description}</p>
        ) : null}
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

/** A labelled field wrapper carrying a description and an optional field error. */
export function Field({
  label,
  description,
  htmlFor,
  underDev,
  error,
  children,
}: {
  label: string;
  description?: string;
  htmlFor?: string;
  underDev?: boolean;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <Label htmlFor={htmlFor} title={description}>
          {label}
        </Label>
        {underDev ? <UnderDevBadge /> : null}
      </div>
      {children}
      {description ? (
        <p className="text-xs text-muted-foreground">{description}</p>
      ) : null}
      {error ? (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/**
 * A single-choice selector rendered from a `single`-selection sub-dimension's
 * values. Each option is tooltipped with its paper-aligned description; the
 * currently-selected value shows an "under development" badge when it is
 * non-executable, and an inline warning explains the gating.
 */
export function TaxonomySelect({
  sub,
  value,
  onChange,
  isUnderDevelopment,
  id,
  error,
}: {
  sub: SubDimensionDTO;
  value: string | undefined;
  onChange: (value: string) => void;
  isUnderDevelopment: (key: string) => boolean;
  id?: string;
  error?: string;
}) {
  const selectedKey = value ?? sub.values.find((v) => v.default)?.key;
  const selected = sub.values.find((v) => v.key === selectedKey);
  const selectedUnderDev = selectedKey
    ? isUnderDevelopment(selectedKey)
    : false;

  return (
    <Field
      label={sub.label}
      description={sub.description}
      htmlFor={id}
      underDev={selectedUnderDev}
      error={error}
    >
      <Select
        id={id}
        value={selectedKey ?? ""}
        onChange={(e) => onChange(e.target.value)}
      >
        {sub.values.map((v) => (
          <option key={v.key} value={v.key}>
            {v.label}
            {isUnderDevelopment(v.key) ? " — under development" : ""}
          </option>
        ))}
      </Select>
      {selected ? (
        <p className="text-xs text-muted-foreground">{selected.description}</p>
      ) : null}
      {selectedUnderDev ? (
        <p className="flex items-center gap-1 text-xs text-amber-700 dark:text-amber-400">
          <AlertTriangle className="size-3" aria-hidden />
          This value is not yet executable — runs that depend on it are blocked.
        </p>
      ) : null}
    </Field>
  );
}

/**
 * A multi-choice selector rendered from a `multi`-selection sub-dimension's
 * values (e.g. roles, metadata signals). Values are toggled as checkboxes;
 * non-executable values carry an inline "under development" badge.
 */
export function TaxonomyMultiSelect({
  sub,
  selected,
  onToggle,
  isUnderDevelopment,
  extra,
}: {
  sub: SubDimensionDTO;
  selected: string[];
  onToggle: (key: string, next: boolean) => void;
  isUnderDevelopment: (key: string) => boolean;
  /** Extra rows rendered below the catalog values (e.g. custom roles). */
  extra?: ReactNode;
}) {
  return (
    <Field label={sub.label} description={sub.description}>
      <div className="space-y-1.5">
        {sub.values.map((v: ValueDTO) => {
          const checked = selected.includes(v.key);
          return (
            <label
              key={v.key}
              className="flex items-start gap-2 text-sm"
              title={v.description}
            >
              <input
                type="checkbox"
                className="mt-0.5 size-4 rounded border-input"
                checked={checked}
                onChange={(e) => onToggle(v.key, e.target.checked)}
                aria-label={v.label}
              />
              <span className="flex flex-wrap items-center gap-1.5">
                <span className="font-medium">{v.label}</span>
                {isUnderDevelopment(v.key) ? <UnderDevBadge /> : null}
                <span className="text-xs text-muted-foreground">
                  {v.description}
                </span>
              </span>
            </label>
          );
        })}
        {extra}
      </div>
    </Field>
  );
}

/**
 * A progressive-disclosure container (Req 7.2): advanced options collapse by
 * default behind a summary toggle so the simple defaults lead.
 */
export function Disclosure({
  summary,
  defaultOpen = false,
  children,
}: {
  summary: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  return (
    <details className="group rounded-md border bg-muted/30 p-3" open={defaultOpen}>
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-sm font-medium">
        <ChevronDown
          className="size-4 transition-transform group-open:rotate-180"
          aria-hidden
        />
        {summary}
      </summary>
      <div className="mt-3 space-y-3">{children}</div>
    </details>
  );
}

/** Look up the first field error whose path matches any of `paths`. */
export function findError(
  errors: FieldError[],
  ...paths: string[]
): string | undefined {
  for (const path of paths) {
    const hit = errors.find(
      (e) => e.field === path || e.field.startsWith(`${path}.`),
    );
    if (hit) return hit.message;
  }
  return undefined;
}
