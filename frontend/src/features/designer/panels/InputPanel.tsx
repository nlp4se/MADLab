import { useMemo, useState } from "react";
import { Braces, Eye, LogIn, Users } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useDesignerStore } from "../designerStore";
import { effectiveEntryNodeIds } from "../ioNodes";
import {
  inputTemplate,
  isInputTemplateEmpty,
  placeholderRows,
  previewInput,
  STARTER_INPUT_SPEC,
} from "../inputEditor";
import { Field, FieldGroup, Notice } from "./fields";

/**
 * Input panel (task 11.10): the instance input (`input_spec`) where it enters
 * the debate. Opened by clicking the Start node or the inspector's Input tab.
 *
 *  - Template textarea with `{{placeholder}}` tags (backend
 *    `PLACEHOLDER_PATTERN`); placeholders are auto-detected into
 *    `input_spec.placeholders`.
 *  - A run-form label per placeholder (`ad_hoc_fields`, default = the key).
 *  - A live preview resolving the template with editable sample values (not
 *    saved; a placeholder without a sample stays visible as its tag).
 *  - Who receives it (the Start connectors) and how: "Task: <resolved input>"
 *    appended to their system prompt; judges see it in their context.
 *  - An empty template is flagged: runs would carry no task.
 */
export function InputPanel() {
  const artifact = useDesignerStore((s) => s.artifact);
  const updateInputTemplate = useDesignerStore((s) => s.updateInputTemplate);
  const updateInputLabel = useDesignerStore((s) => s.updateInputLabel);
  const [samples, setSamples] = useState<Record<string, string>>({});

  const template = inputTemplate(artifact);
  const rows = useMemo(() => placeholderRows(artifact?.input_spec), [artifact?.input_spec]);

  if (!artifact) return null;

  const empty = isInputTemplateEmpty(artifact);
  const nodes = artifact.participants.nodes;
  const labelOf = (id: string) => nodes.find((n) => n.id === id)?.label ?? id;
  const entries = effectiveEntryNodeIds(artifact);
  // Judges only decide (and so read the task) under judge-based / hybrid.
  const authority = artifact.agreement?.authority ?? "collective";
  const judgesDecide = authority === "judge_based" || authority === "hybrid";
  const judges = judgesDecide
    ? nodes.filter((n) => (n.roles ?? []).includes("judge"))
    : [];

  // Only non-empty samples substitute, so unfilled tags stay visible.
  const filled = Object.fromEntries(
    Object.entries(samples).filter(([, v]) => v !== ""),
  );
  const preview = previewInput(template, filled);

  const applyStarter = () => {
    updateInputTemplate(STARTER_INPUT_SPEC.template);
    for (const f of STARTER_INPUT_SPEC.ad_hoc_fields) updateInputLabel(f.key, f.label);
  };

  return (
    <div className="space-y-5" data-testid="input-panel">
      <FieldGroup
        title="Input"
        icon={LogIn}
        description="The task every run starts from. Each run fills the placeholders (single-run form or mapped CSV columns)."
        tone="prompt"
      >
        {empty ? (
          <Notice
            testId="input-empty-warning"
            actions={[{ label: "Use {{input}}", onClick: applyStarter }]}
          >
            No input template yet. A run would give the participants no task, so
            the Run view cannot launch this configuration. Write the task below,
            using {"{{name}}"} for each value a run supplies.
          </Notice>
        ) : null}

        <Field
          label="Template"
          htmlFor="input-template"
          icon={Braces}
          description="Use {{name}} tags for the values each run supplies (letters, digits, _ . - and spaces); spaces just inside the braces are ignored."
        >
          <Textarea
            id="input-template"
            rows={4}
            value={template}
            placeholder="Classify this requirement: {{requirement}}"
            onChange={(e) => updateInputTemplate(e.target.value)}
          />
        </Field>

        {rows.length > 0 ? (
          <Field
            label="Placeholders"
            description="Detected from the template. The label names the field in the Run view; it defaults to the key."
          >
            <ul className="space-y-2" data-testid="input-placeholders">
              {rows.map((row) => (
                <li key={row.key} className="grid grid-cols-[auto_1fr] items-center gap-2">
                  <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{`{{${row.key}}}`}</code>
                  <Input
                    aria-label={`Label for ${row.key}`}
                    value={row.label}
                    placeholder={row.key}
                    onChange={(e) => updateInputLabel(row.key, e.target.value)}
                  />
                </li>
              ))}
            </ul>
          </Field>
        ) : !empty ? (
          <Notice tone="info" testId="input-static-note">
            No placeholders: every run gets exactly this text, and the Run view's
            single-input form has no fields.
          </Notice>
        ) : null}
      </FieldGroup>

      {!empty ? (
        <FieldGroup title="Preview" icon={Eye} description="Sample values are only for this preview; they are not saved.">
          {rows.map((row) => (
            <Field key={row.key} label={row.label || row.key} htmlFor={`input-sample-${row.key}`}>
              <Input
                id={`input-sample-${row.key}`}
                aria-label={`Sample value for ${row.key}`}
                value={samples[row.key] ?? ""}
                placeholder={`{{${row.key}}}`}
                onChange={(e) =>
                  setSamples((prev) => ({ ...prev, [row.key]: e.target.value }))
                }
              />
            </Field>
          ))}
          <pre
            className="whitespace-pre-wrap break-words rounded-md border bg-muted/30 p-2.5 text-xs"
            data-testid="input-preview"
          >
            {`Task: ${preview}`}
          </pre>
        </FieldGroup>
      ) : null}

      <FieldGroup title="Who receives it" icon={Users}>
        {entries.length > 0 ? (
          <p className="text-xs text-muted-foreground" data-testid="input-receivers">
            {entries.map(labelOf).join(", ")}{" "}
            {entries.length === 1 ? "receives" : "receive"} it (the Start connectors),
            as a final <span className="font-mono">Task: …</span> line in{" "}
            {entries.length === 1 ? "its" : "their"} system prompt.
          </p>
        ) : (
          <Notice testId="input-no-receivers">
            No participant is connected to Start, so nobody receives the input.
            Drag from Start to a participant to connect it.
          </Notice>
        )}
        {judges.length > 0 ? (
          <p className="text-xs text-muted-foreground" data-testid="input-judges">
            {judges.map((j) => j.label).join(", ")}{" "}
            {judges.length === 1 ? "sees" : "see"} it at the top of the judge
            context (<span className="font-mono">Task: …</span>, then the transcript).
          </p>
        ) : null}
      </FieldGroup>
    </div>
  );
}
