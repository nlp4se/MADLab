import { useEffect, useRef, useState } from "react";
import { Pencil } from "lucide-react";

import { cn } from "@/lib/utils";
import { useDesignerStore } from "./designerStore";

/**
 * Designer header (task 11.10): the configuration name as an inline-editable
 * title plus an optional, inline-editable description.
 *
 * Click the text (or the pencil) to edit; Enter or blur commits, Escape
 * cancels. An empty name is rejected inline (the editor stays open with the
 * reason). Edits go through the store's `updateMeta`, which marks the store
 * dirty; they persist with the toolbar's Save (the backend syncs the
 * configurations row name/description from the artifact).
 */
export function DesignerHeader() {
  const name = useDesignerStore((s) => s.artifact?.name ?? "");
  const description = useDesignerStore((s) => s.artifact?.description ?? "");
  const updateMeta = useDesignerStore((s) => s.updateMeta);

  return (
    <div
      className="flex min-w-0 flex-col gap-0.5 border-b px-3 py-2"
      data-testid="designer-header"
    >
      <InlineEdit
        value={name}
        label="Configuration name"
        required
        emptyError="The name can't be empty."
        className="text-base font-semibold"
        onCommit={(next) => updateMeta({ name: next })}
      />
      <InlineEdit
        value={description}
        label="Configuration description"
        placeholder="Add a description"
        className="text-xs text-muted-foreground"
        onCommit={(next) => updateMeta({ description: next })}
      />
    </div>
  );
}

/**
 * A text shown as a button that turns into an input on click. `onCommit`
 * returns false to reject the value (the editor stays open).
 */
function InlineEdit({
  value,
  label,
  placeholder,
  required = false,
  emptyError = "This field is required.",
  className,
  onCommit,
}: {
  value: string;
  label: string;
  placeholder?: string;
  required?: boolean;
  emptyError?: string;
  className?: string;
  onCommit: (next: string) => boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  // Set while Escape closes the editor, so the trailing blur doesn't commit.
  const cancelled = useRef(false);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  const start = () => {
    cancelled.current = false;
    setDraft(value);
    setError(null);
    setEditing(true);
  };

  const commit = () => {
    if (cancelled.current) return;
    if (required && draft.trim() === "") {
      setError(emptyError);
      return;
    }
    if (!onCommit(draft)) {
      setError(emptyError);
      return;
    }
    setError(null);
    setEditing(false);
  };

  const cancel = () => {
    cancelled.current = true;
    setDraft(value);
    setError(null);
    setEditing(false);
  };

  if (editing) {
    const errorId = `${label.replace(/\s+/g, "-").toLowerCase()}-error`;
    return (
      <div className="flex min-w-0 flex-col gap-0.5">
        <input
          ref={inputRef}
          aria-label={label}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          value={draft}
          placeholder={placeholder}
          onChange={(e) => {
            setDraft(e.target.value);
            if (error && e.target.value.trim() !== "") setError(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commit();
            } else if (e.key === "Escape") {
              e.preventDefault();
              cancel();
            }
          }}
          onBlur={commit}
          className={cn(
            "w-full max-w-xl rounded border border-input bg-background px-1.5 py-0.5 outline-none focus-visible:ring-2 focus-visible:ring-ring",
            error && "border-destructive focus-visible:ring-destructive",
            className,
          )}
        />
        {error ? (
          <p id={errorId} role="alert" className="text-xs text-destructive">
            {error}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={start}
      title={`Edit ${label.toLowerCase()}`}
      className={cn(
        "group flex w-fit max-w-full items-center gap-1.5 rounded px-1.5 py-0.5 text-left hover:bg-accent/60",
        className,
      )}
    >
      <span className={cn("truncate", !value && "italic opacity-70")}>
        {value || placeholder}
      </span>
      <Pencil
        className="size-3.5 shrink-0 opacity-50 group-hover:opacity-100"
        aria-hidden
      />
      <span className="sr-only">(edit {label.toLowerCase()})</span>
    </button>
  );
}
