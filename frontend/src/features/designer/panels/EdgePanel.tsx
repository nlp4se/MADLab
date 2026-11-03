import { Input } from "@/components/ui/input";
import { useDesignerStore } from "../designerStore";
import { Field, FieldGroup } from "./fields";

/**
 * Edge inspector (Req 6.4): set a selected edge's name, colour, and direction.
 * All edits flow through the store so the canvas projection (arrowheads /
 * stroke colour) and the persisted artifact stay in sync.
 */
export function EdgePanel({ edgeId }: { edgeId: string }) {
  const artifact = useDesignerStore((s) => s.artifact);
  const updateEdge = useDesignerStore((s) => s.updateEdge);

  const edge = artifact?.interaction.topology.edges.find(
    (e) => `${e.source}->${e.target}` === edgeId,
  );

  if (!edge) {
    return (
      <p className="p-4 text-sm text-muted-foreground">
        The selected edge no longer exists.
      </p>
    );
  }

  return (
    <FieldGroup
      title="Edge"
      description={`${edge.source} → ${edge.target}`}
      tone="structured"
    >
      <Field
        label="Name"
        description="An optional label shown on the edge."
        htmlFor="edge-label"
      >
        <Input
          id="edge-label"
          value={edge.label ?? ""}
          onChange={(e) => updateEdge(edgeId, { label: e.target.value || null })}
        />
      </Field>

      <Field label="Colour" description="Edge stroke colour." htmlFor="edge-color">
        <div className="flex items-center gap-2">
          <input
            id="edge-color"
            type="color"
            className="h-9 w-12 cursor-pointer rounded border border-input bg-background"
            value={edge.color ?? "#0d9488"}
            onChange={(e) => updateEdge(edgeId, { color: e.target.value })}
            aria-label="Edge colour"
          />
          <Input
            value={edge.color ?? ""}
            placeholder="#0d9488"
            onChange={(e) =>
              updateEdge(edgeId, { color: e.target.value || null })
            }
            aria-label="Edge colour hex"
          />
        </div>
      </Field>

      <Field
        label="Direction"
        description="Directed edges render an arrowhead; undirected ones do not."
      >
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="size-4 rounded border-input"
            checked={edge.directed !== false}
            onChange={(e) => updateEdge(edgeId, { directed: e.target.checked })}
          />
          Directed
        </label>
      </Field>
    </FieldGroup>
  );
}
