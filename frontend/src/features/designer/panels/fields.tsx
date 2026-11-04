import { type ComponentType, type ReactNode } from "react";
import { AlertTriangle, ChevronDown, Info, Wrench } from "lucide-react";

import type { FieldError, SubDimensionDTO, ValueDTO } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";

/**
 * Shared, taxonomy-driven form primitives for the designer dimension panels
 * (task 8.4). They render selects / checkboxes directly from catalog values so
 * labels, descriptions/tooltips (Req 7.4), defaults (Req 7.1), and "under
 * development" badges (Req 7.5) come from a single data source and never drift.
 */

/** Minimal icon prop: any lucide-style component taking a className. */
export type FieldIcon = ComponentType<{ className?: string }>;

/**
 * An info marker with a hover/focus tooltip. Used to flag properties whose
 * effective value is shaped by other decisions (topology, roles, prompts) or is
 * descriptive rather than directly driving execution, so the user understands
 * the field is not a simple independent switch.
 */
export function InfoHint({ text, className }: { text: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex cursor-help text-muted-foreground hover:text-foreground",
        className,
      )}
      title={text}
      tabIndex={0}
      role="img"
      aria-label={text}
    >
      <Info className="size-3.5" aria-hidden />
    </span>
  );
}

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
 * (everything else) per the design's distinction. `icon` gives the group a
 * recognizable glyph; `hint` adds an info tooltip next to the title.
 */
export function FieldGroup({
  title,
  description,
  tone,
  icon: Icon,
  hint,
  children,
}: {
  title: string;
  description?: string;
  tone?: "prompt" | "structured";
  icon?: FieldIcon;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3" data-tone={tone}>
      <div className="space-y-0.5">
        <div className="flex items-center gap-2">
          {Icon ? <Icon className="size-4 text-muted-foreground" /> : null}
          <h4 className="text-sm font-semibold">{title}</h4>
          {hint ? <InfoHint text={hint} /> : null}
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
  icon: Icon,
  hint,
  children,
}: {
  label: string;
  description?: string;
  htmlFor?: string;
  underDev?: boolean;
  error?: string;
  icon?: FieldIcon;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5">
        {Icon ? <Icon className="size-3.5 text-muted-foreground" /> : null}
        <Label htmlFor={htmlFor} title={description}>
          {label}
        </Label>
        {hint ? <InfoHint text={hint} /> : null}
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
 * non-executable, and an inline warning explains the gating. `icon` and `hint`
 * decorate the field label (points 7 and 8 of the designer UX pass).
 */
export function TaxonomySelect({
  sub,
  value,
  onChange,
  isUnderDevelopment,
  id,
  error,
  icon,
  hint,
  disabled,
  note,
  disabledOptions,
}: {
  sub: SubDimensionDTO;
  value: string | undefined;
  onChange: (value: string) => void;
  isUnderDevelopment: (key: string) => boolean;
  id?: string;
  error?: string;
  icon?: FieldIcon;
  hint?: string;
  /** Render the select read-only (e.g. governed elsewhere / not applicable). */
  disabled?: boolean;
  /** An inline note under the select (e.g. why it is disabled). */
  note?: ReactNode;
  /**
   * Options that would fail / have no effect in the current context, keyed by
   * value with a short reason appended to the option label (task 11.7). They
   * stay visible but cannot be picked.
   */
  disabledOptions?: Record<string, string>;
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
      icon={icon}
      hint={hint}
    >
      <Select
        id={id}
        value={selectedKey ?? ""}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      >
        {sub.values.map((v) => {
          const unavailable = disabledOptions?.[v.key];
          return (
            <option key={v.key} value={v.key} disabled={unavailable !== undefined}>
              {v.label}
              {isUnderDevelopment(v.key) ? " — under development" : ""}
              {unavailable !== undefined ? ` (${unavailable})` : ""}
            </option>
          );
        })}
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
      {note ? <div className="text-xs text-muted-foreground">{note}</div> : null}
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
  icon,
  hint,
}: {
  sub: SubDimensionDTO;
  selected: string[];
  onToggle: (key: string, next: boolean) => void;
  isUnderDevelopment: (key: string) => boolean;
  /** Extra rows rendered below the catalog values (e.g. custom roles). */
  extra?: ReactNode;
  icon?: FieldIcon;
  hint?: string;
}) {
  return (
    <Field label={sub.label} description={sub.description} icon={icon} hint={hint}>
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

/**
 * An inline notice (task 11.7): `warning` = amber (a setting that does not do
 * what it says, with fixes), `error` = the run would fail, `info` = neutral
 * behaviour note. Optional action buttons render below the message.
 */
export function Notice({
  tone = "warning",
  testId,
  actions,
  children,
}: {
  tone?: "warning" | "error" | "info";
  testId?: string;
  actions?: Array<{ label: string; onClick: () => void }>;
  children: ReactNode;
}) {
  const classes =
    tone === "error"
      ? "border-destructive/50 bg-destructive/5 text-destructive"
      : tone === "warning"
        ? "border-amber-500/50 bg-amber-500/10 text-amber-800 dark:text-amber-300"
        : "border-dashed bg-muted/40 text-muted-foreground";
  const Icon = tone === "info" ? Info : AlertTriangle;
  return (
    <div
      role={tone === "info" ? "note" : "alert"}
      data-testid={testId}
      className={cn("space-y-2 rounded-md border p-2.5 text-xs", classes)}
    >
      <p className="flex items-start gap-1.5">
        <Icon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        <span>{children}</span>
      </p>
      {actions && actions.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {actions.map((a) => (
            <Button key={a.label} type="button" size="sm" variant="outline" onClick={a.onClick}>
              {a.label}
            </Button>
          ))}
        </div>
      ) : null}
    </div>
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
