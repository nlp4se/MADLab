import type { HTMLAttributes } from "react";
import ReactMarkdown, { type Components, type Options } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn, SCROLL_PRE } from "@/lib/utils";

/**
 * Markdown rendering for model-generated text (task 11.16, Req 11.2, 12.2,
 * 13.3): agent messages, text fields of structured decisions, and
 * design-assistant replies. User-typed text is never passed through here.
 *
 * Safe by default:
 *  - raw HTML in the source is not parsed into elements (react-markdown shows
 *    it as literal text; there is no rehype-raw);
 *  - link URLs must be absolute http(s)/mailto, anything else (javascript:,
 *    data:, relative paths) drops the link and keeps its text;
 *  - links open in a new tab with rel="noopener noreferrer";
 *  - images are not loaded (model output shouldn't fetch remote resources);
 *    their alt text is shown instead.
 *
 * Styled with explicit Tailwind mappings (no typography plugin): compact
 * spacing, headings scaled for message bubbles, code blocks and tables scroll
 * inside their card, and the root keeps 11.15's wrapping (`min-w-0`, break
 * unbroken tokens anywhere) so nothing escapes the content column.
 */

/** Wrapping for rendered Markdown (the block-level counterpart of WRAP_TEXT). */
export const MARKDOWN_WRAP = "min-w-0 break-words [overflow-wrap:anywhere]";

const SAFE_PROTOCOLS = new Set(["http", "https", "mailto"]);

/** Keep only absolute http(s)/mailto URLs; anything else is dropped. */
export function safeUrl(url: string): string | null {
  const value = url.trim();
  const match = /^([a-z][a-z0-9+.-]*):/i.exec(value);
  if (!match || !SAFE_PROTOCOLS.has(match[1].toLowerCase())) return null;
  return value;
}

/** Minimal mdast shape, enough for the soft-break transform below. */
interface MdNode {
  type: string;
  value?: string;
  children?: MdNode[];
}

const NEWLINE = /\r\n|\r|\n/;

/**
 * Show single newlines as line breaks (as the plain-text view did), the way
 * chat UIs treat model replies: split text nodes on newlines into `break`
 * nodes. Code (inline and fenced) is a different node type and is untouched.
 */
function remarkSoftBreaks() {
  return (tree: MdNode) => {
    splitSoftBreaks(tree);
  };
}

function splitSoftBreaks(node: MdNode): void {
  if (!node.children) return;
  const out: MdNode[] = [];
  for (const child of node.children) {
    if (child.type === "text" && child.value && NEWLINE.test(child.value)) {
      child.value.split(NEWLINE).forEach((part, i) => {
        if (i > 0) out.push({ type: "break" });
        if (part) out.push({ type: "text", value: part });
      });
    } else {
      splitSoftBreaks(child);
      out.push(child);
    }
  }
  node.children = out;
}

const REMARK_PLUGINS: Options["remarkPlugins"] = [remarkGfm, remarkSoftBreaks];

const BLOCK_GAP = "my-1.5 first:mt-0 last:mb-0";
const HEADING = "mb-1 mt-3 font-semibold first:mt-0 last:mb-0";

/* `node` (the hast element) is dropped so it never reaches the DOM. */
const COMPONENTS: Components = {
  p: ({ node: _node, className, ...props }) => (
    <p className={cn(BLOCK_GAP, className)} {...props} />
  ),
  h1: ({ node: _node, className, ...props }) => (
    <h1 className={cn(HEADING, "text-base", className)} {...props} />
  ),
  h2: ({ node: _node, className, ...props }) => (
    <h2 className={cn(HEADING, "text-[0.95rem]", className)} {...props} />
  ),
  h3: ({ node: _node, className, ...props }) => (
    <h3 className={cn(HEADING, "text-sm", className)} {...props} />
  ),
  h4: ({ node: _node, className, ...props }) => (
    <h4 className={cn(HEADING, "text-sm", className)} {...props} />
  ),
  h5: ({ node: _node, className, ...props }) => (
    <h5 className={cn(HEADING, "text-sm font-medium", className)} {...props} />
  ),
  h6: ({ node: _node, className, ...props }) => (
    <h6
      className={cn(HEADING, "text-sm font-medium text-muted-foreground", className)}
      {...props}
    />
  ),
  strong: ({ node: _node, className, ...props }) => (
    <strong className={cn("font-semibold", className)} {...props} />
  ),
  em: ({ node: _node, className, ...props }) => (
    <em className={cn("italic", className)} {...props} />
  ),
  del: ({ node: _node, className, ...props }) => (
    <del className={cn("line-through", className)} {...props} />
  ),
  ul: ({ node: _node, className, ...props }) => (
    <ul
      className={cn(
        BLOCK_GAP,
        "list-disc space-y-0.5 pl-5",
        // GFM task lists carry their own checkbox.
        className?.includes("contains-task-list") && "list-none pl-1",
        className,
      )}
      {...props}
    />
  ),
  ol: ({ node: _node, className, ...props }) => (
    <ol className={cn(BLOCK_GAP, "list-decimal space-y-0.5 pl-5", className)} {...props} />
  ),
  li: ({ node: _node, className, ...props }) => (
    <li className={cn("min-w-0 [&>ol]:my-0.5 [&>ul]:my-0.5", className)} {...props} />
  ),
  blockquote: ({ node: _node, className, ...props }) => (
    <blockquote
      className={cn(
        BLOCK_GAP,
        "border-l-2 border-muted-foreground/30 pl-3 text-muted-foreground",
        className,
      )}
      {...props}
    />
  ),
  hr: ({ node: _node, className, ...props }) => (
    <hr className={cn("my-3 border-border", className)} {...props} />
  ),
  a: ({ node: _node, href, className, children, ...props }) =>
    href ? (
      <a
        {...props}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className={cn(
          "font-medium text-primary underline underline-offset-2 hover:opacity-80",
          className,
        )}
      >
        {children}
      </a>
    ) : (
      // Unsafe or unsupported URL: keep the text, drop the link.
      <span>{children}</span>
    ),
  img: ({ alt }) => (alt ? <span className="italic">{alt}</span> : null),
  // Inline code; inside a <pre> the block styles below take over.
  code: ({ node: _node, className, ...props }) => (
    <code
      className={cn("rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]", className)}
      {...props}
    />
  ),
  // Fenced code keeps its formatting and scrolls inside the card. The parent's
  // `overflow-wrap:anywhere` is reset so long lines scroll instead of wrapping.
  pre: ({ node: _node, className, ...props }) => (
    <pre
      className={cn(
        BLOCK_GAP,
        "rounded-md bg-muted/60 p-2 font-mono text-xs leading-relaxed",
        "break-normal [&>code]:bg-transparent [&>code]:p-0 [&>code]:[font-size:inherit]",
        SCROLL_PRE,
        className,
      )}
      {...props}
    />
  ),
  // GFM tables scroll horizontally in their own wrapper; cells wrap at spaces.
  table: ({ node: _node, className, ...props }) => (
    <div className={cn(BLOCK_GAP, SCROLL_PRE)} data-markdown-table="">
      <table
        className={cn("w-full border-collapse break-normal text-xs", className)}
        {...props}
      />
    </div>
  ),
  th: ({ node: _node, className, ...props }) => (
    <th
      className={cn("border bg-muted/40 px-2 py-1 text-left font-semibold", className)}
      {...props}
    />
  ),
  td: ({ node: _node, className, ...props }) => (
    <td className={cn("border px-2 py-1 align-top", className)} {...props} />
  ),
};

export interface MarkdownProps extends Omit<HTMLAttributes<HTMLDivElement>, "children"> {
  /** The Markdown source (model-generated text). */
  children: string;
}

/** Render model-generated Markdown safely, styled to match the app. */
export function Markdown({ children, className, ...rest }: MarkdownProps) {
  return (
    <div className={cn(MARKDOWN_WRAP, className)} {...rest}>
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        components={COMPONENTS}
        urlTransform={safeUrl}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
