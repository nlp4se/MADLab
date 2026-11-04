import { useEffect, useRef, useState } from "react";
import { Gavel, Scale } from "lucide-react";

import { Textarea } from "@/components/ui/textarea";
import { useTaxonomy } from "@/taxonomy/TaxonomyContext";
import type { AgreementArtifact } from "../artifact";
import { useDesignerStore } from "../designerStore";
import { Disclosure, Field, FieldGroup, TaxonomySelect, findError } from "./fields";

/**
 * Agreement-dimension panel (Req 3.*, 7.4). Configures the `(authority,
 * resolution)` pair, resolution parameters (required for weighted_vote /
 * scoring, Req 3.4), and an optional structured output schema (Req 3.5).
 *
 * `resolution_params` and `output_schema` are free-form JSON edited as text;
 * invalid JSON surfaces a client-side error (Req 7.3) and is not committed to
 * the artifact until it parses.
 */
/**
 * Agreement authority/resolution work *together with* the topology and the
 * judge/debater roles and prompts — e.g. judge-based authority only does
 * something if a judge node exists and its prompt tells it how to decide. This
 * hint flags that these selections are not independent switches.
 */
const EMERGENT_HINT =
  "Works together with your topology and the judge/debater roles & prompts. " +
  "For example, 'judge-based' authority requires a judge node whose prompt " +
  "defines how it decides; the effective behaviour emerges from those choices.";

export function AgreementPanel() {
  const { getSubDimension, isUnderDevelopment } = useTaxonomy();
  const artifact = useDesignerStore((s) => s.artifact);
  const updateAgreement = useDesignerStore((s) => s.updateAgreement);
  const errors = useDesignerStore((s) => s.validationErrors);

  if (!artifact) return null;

  const agreement = artifact.agreement ?? {};
  const authoritySub = getSubDimension("agreement", "authority");
  const resolutionSub = getSubDimension("agreement", "resolution");

  const needsParams =
    agreement.resolution === "weighted_vote" ||
    agreement.resolution === "scoring";

  return (
    <div className="space-y-6">
      <FieldGroup
        title="Agreement"
        description="How the debate resolves to a final output."
        tone="structured"
        icon={Gavel}
        hint={EMERGENT_HINT}
      >
        {authoritySub ? (
          <TaxonomySelect
            sub={authoritySub}
            value={agreement.authority}
            onChange={(v) =>
              updateAgreement({
                authority: v as AgreementArtifact["authority"],
              })
            }
            isUnderDevelopment={isUnderDevelopment}
            id="agr-authority"
            error={findError(errors, "agreement.authority")}
            icon={Gavel}
            hint={EMERGENT_HINT}
          />
        ) : null}
        {resolutionSub ? (
          <TaxonomySelect
            sub={resolutionSub}
            value={agreement.resolution}
            onChange={(v) =>
              updateAgreement({
                resolution: v as AgreementArtifact["resolution"],
              })
            }
            isUnderDevelopment={isUnderDevelopment}
            id="agr-resolution"
            error={findError(errors, "agreement.resolution")}
            icon={Scale}
            hint={EMERGENT_HINT}
          />
        ) : null}
      </FieldGroup>

      {needsParams ? (
        <JsonField
          label="Resolution parameters"
          description="Weighting/scoring signals and aggregation logic (required for this resolution)."
          value={agreement.resolution_params ?? {}}
          onCommit={(obj) =>
            updateAgreement({ resolution_params: obj ?? {} })
          }
          error={findError(errors, "agreement.resolution_params")}
        />
      ) : null}

      <Disclosure summary="Structured output schema">
        <JsonField
          label="Output schema (JSON)"
          description="A JSON schema constraining the final decision, e.g. { class: F | NF }."
          value={agreement.output_schema ?? null}
          nullable
          onCommit={(obj) => updateAgreement({ output_schema: obj })}
          error={findError(errors, "agreement.output_schema")}
        />
      </Disclosure>
    </div>
  );
}

/**
 * A JSON object editor. Text is held locally; it commits to the store only when
 * it parses to an object, otherwise it shows a client-side parse error (Req
 * 7.3). An empty value commits `{}` (or `null` when `nullable`).
 */
function JsonField({
  label,
  description,
  value,
  onCommit,
  nullable = false,
  error,
}: {
  label: string;
  description?: string;
  value: Record<string, unknown> | null;
  onCommit: (obj: Record<string, unknown> | null) => void;
  nullable?: boolean;
  error?: string;
}) {
  const serialize = (v: Record<string, unknown> | null) =>
    v == null ? "" : JSON.stringify(v, null, 2);

  const [text, setText] = useState(() => serialize(value));
  const [parseError, setParseError] = useState<string | null>(null);
  // The value this field last committed, so an external resync (loading a
  // different config) overwrites the editor but our own commits do not clobber
  // in-progress typing.
  const lastCommitted = useRef<string>(serialize(value));

  useEffect(() => {
    const incoming = serialize(value);
    if (incoming !== lastCommitted.current) {
      setText(incoming);
      lastCommitted.current = incoming;
      setParseError(null);
    }
  }, [value]);

  const handleChange = (next: string) => {
    setText(next);
    const trimmed = next.trim();
    if (trimmed === "") {
      setParseError(null);
      const committed = nullable ? null : {};
      lastCommitted.current = serialize(committed);
      onCommit(committed);
      return;
    }
    try {
      const parsed = JSON.parse(trimmed);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        setParseError("Must be a JSON object.");
        return;
      }
      setParseError(null);
      lastCommitted.current = serialize(parsed as Record<string, unknown>);
      onCommit(parsed as Record<string, unknown>);
    } catch {
      setParseError("Invalid JSON.");
    }
  };

  return (
    <Field
      label={label}
      description={description}
      htmlFor={`json-${label}`}
      error={parseError ?? error}
    >
      <Textarea
        id={`json-${label}`}
        rows={5}
        className="font-mono text-xs"
        value={text}
        onChange={(e) => handleChange(e.target.value)}
        spellCheck={false}
      />
    </Field>
  );
}
