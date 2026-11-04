import { useEffect, useRef, useState } from "react";
import { Gavel, Scale } from "lucide-react";

import { Textarea } from "@/components/ui/textarea";
import {
  makeSchemaStrict,
  schemaStrictness,
  type SchemaStrictness,
} from "@/lib/outputSchema";
import { useTaxonomy } from "@/taxonomy/TaxonomyContext";
import type { AgreementArtifact } from "../artifact";
import { useDesignerStore } from "../designerStore";
import {
  RESOLUTION_KEYS,
  agreementNotices,
  firstCompatibleResolution,
  judgeNodes,
  resolutionCompat,
  type Authority,
  type Resolution,
} from "../interactionScope";
import {
  Disclosure,
  Field,
  FieldGroup,
  Notice,
  TaxonomySelect,
  findError,
} from "./fields";

/**
 * Agreement-dimension panel (Req 3.*, 7.4). Configures the `(authority,
 * resolution)` pair, resolution parameters (required for weighted_vote /
 * scoring, Req 3.4), and an optional structured output schema (Req 3.5).
 *
 * `resolution_params` and `output_schema` are free-form JSON edited as text;
 * invalid JSON surfaces a client-side error (Req 7.3) and is not committed to
 * the artifact until it parses.
 *
 * Scope (task 11.7): authority first, then the resolution filtered by the
 * engine-derived compatibility matrix (`resolutionCompat`); switching
 * authority keeps the resolution valid (and says so when it changes). Inline
 * notices cover a missing judge (with "Add judge"), judges that do not decide
 * under collective authority, and hand-set End connectors.
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

/** Warning text for an output schema that is not strict (task 11.13). */
function strictnessMessage({ missingRequired, allowsExtra }: SchemaStrictness): string {
  const gaps = [
    missingRequired ? "has no required list" : null,
    allowsExtra ? "allows extra properties" : null,
  ].filter(Boolean);
  return (
    `This output schema ${gaps.join(" and ")}, so providers cannot enforce it ` +
    "strictly and the judge may omit the decision field or add others. Replies " +
    "without the schema's fields end undecided. Make strict requires every " +
    "property and sets additionalProperties to false."
  );
}

export function AgreementPanel() {
  const { getSubDimension, getValue, isUnderDevelopment } = useTaxonomy();
  const artifact = useDesignerStore((s) => s.artifact);
  const updateAgreement = useDesignerStore((s) => s.updateAgreement);
  const setAuthority = useDesignerStore((s) => s.setAuthority);
  const addJudge = useDesignerStore((s) => s.addJudge);
  const resetExitNodes = useDesignerStore((s) => s.resetExitNodes);
  const errors = useDesignerStore((s) => s.validationErrors);
  // Says so when switching authority also switched the resolution.
  const [switchNote, setSwitchNote] = useState<string | null>(null);

  if (!artifact) return null;

  const agreement = artifact.agreement ?? {};
  const authority: Authority = agreement.authority ?? "collective";
  const resolution: Resolution = agreement.resolution ?? "majority_vote";
  const authoritySub = getSubDimension("agreement", "authority");
  const resolutionSub = getSubDimension("agreement", "resolution");
  const resLabel = (key: string) => getValue("agreement", "resolution", key)?.label ?? key;
  const authLabel = (key: string) => getValue("agreement", "authority", key)?.label ?? key;

  // Authority 'other' has no executable semantics in the engine (UnderDevelopment).
  const authorityUnderDev = (key: string) => key === "other" || isUnderDevelopment(key);

  // Resolutions that would fail / not apply under the current authority.
  const disabledResolutions: Record<string, string> = {};
  for (const key of RESOLUTION_KEYS) {
    const c = resolutionCompat(authority, key);
    if (!c.allowed && c.short) disabledResolutions[key] = c.short;
  }
  const current = resolutionCompat(authority, resolution);
  const fallback = firstCompatibleResolution(authority);

  const needsParams =
    current.allowed && (resolution === "weighted_vote" || resolution === "scoring");

  const onAuthority = (value: Authority) => {
    const switched = setAuthority(value);
    setSwitchNote(
      switched
        ? `Resolution switched from ${resLabel(switched.from)} to ${resLabel(switched.to)}: ${
            resolutionCompat(value, switched.from).reason ?? "not compatible with this authority."
          }`
        : null,
    );
  };

  const notices = agreementNotices(artifact);
  const judges = judgeNodes(artifact.participants.nodes);
  const strictness = schemaStrictness(agreement.output_schema);

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
            onChange={(v) => onAuthority(v as Authority)}
            isUnderDevelopment={authorityUnderDev}
            id="agr-authority"
            error={findError(errors, "agreement.authority")}
            icon={Gavel}
            hint={EMERGENT_HINT}
          />
        ) : null}

        {notices.map((n) => {
          switch (n.kind) {
            case "no_judge":
              return (
                <Notice
                  key={n.kind}
                  testId="agr-no-judge"
                  actions={[{ label: "Add judge", onClick: () => addJudge() }]}
                >
                  {n.authority === "judge_based"
                    ? "Judge-based authority needs a participant with the Judge role; the config cannot be saved or run without one."
                    : "Hybrid authority falls back to a judge when the collective step is inconclusive, but no participant has the Judge role: such debates end undecided."}
                </Notice>
              );
            case "judges_ignored":
              return (
                <Notice key={n.kind} testId="agr-judges-ignored">
                  Judges do not decide under {authLabel("collective")} authority:{" "}
                  {judges.map((j) => j.label).join(", ")}{" "}
                  {judges.length === 1 ? "is" : "are"} left out of the decision, and a
                  judge-only participant takes no turn.
                </Notice>
              );
            case "custom_exits":
              return (
                <Notice
                  key={n.kind}
                  tone={n.missingJudge ? "warning" : "info"}
                  testId="agr-custom-exits"
                  actions={[{ label: "Reset End connectors", onClick: resetExitNodes }]}
                >
                  {n.missingJudge
                    ? "The End connectors were set by hand and none is a judge: judge-based authority needs a judge connected to End."
                    : "The End connectors were set by hand on the canvas, so they do not follow the authority. Reset them to derive them from the authority again."}
                </Notice>
              );
            default:
              return null;
          }
        })}

        {resolutionSub ? (
          <TaxonomySelect
            sub={resolutionSub}
            value={agreement.resolution}
            onChange={(v) => {
              setSwitchNote(null);
              updateAgreement({ resolution: v as AgreementArtifact["resolution"] });
            }}
            isUnderDevelopment={isUnderDevelopment}
            id="agr-resolution"
            error={findError(errors, "agreement.resolution")}
            icon={Scale}
            hint={EMERGENT_HINT}
            disabledOptions={disabledResolutions}
            note={
              current.allowed && current.reason ? (
                <span data-testid="agr-resolution-behaviour">{current.reason}</span>
              ) : authority === "other" ? (
                <span>
                  Authority {authLabel("other")} is under development: the
                  resolution is saved but not run.
                </span>
              ) : null
            }
          />
        ) : null}

        {switchNote ? (
          <Notice tone="info" testId="agr-resolution-switched">
            {switchNote}
          </Notice>
        ) : null}

        {!current.allowed ? (
          <Notice
            testId="agr-resolution-incompatible"
            actions={[
              {
                label: `Switch to ${resLabel(fallback)}`,
                onClick: () => updateAgreement({ resolution: fallback }),
              },
            ]}
          >
            {current.reason}
          </Notice>
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

      <Disclosure summary="Structured output schema" defaultOpen={strictness != null}>
        <JsonField
          label="Output schema (JSON)"
          description="A JSON schema constraining the final decision, e.g. { class: F | NF }. The OpenAI { name, schema } envelope is accepted."
          value={agreement.output_schema ?? null}
          nullable
          onCommit={(obj) => updateAgreement({ output_schema: obj })}
          error={findError(errors, "agreement.output_schema")}
        />
        {strictness && agreement.output_schema ? (
          <Notice
            testId="agr-schema-not-strict"
            actions={[
              {
                label: "Make strict",
                onClick: () =>
                  updateAgreement({
                    output_schema: makeSchemaStrict(agreement.output_schema!),
                  }),
              },
            ]}
          >
            {strictnessMessage(strictness)}
          </Notice>
        ) : null}
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
