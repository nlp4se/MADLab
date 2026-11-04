import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown, safeUrl } from "./Markdown";

function renderMd(source: string) {
  const { container } = render(<Markdown data-testid="md">{source}</Markdown>);
  return container.querySelector<HTMLElement>("[data-testid='md']")!;
}

describe("Markdown (task 11.16)", () => {
  it("renders bold, italics, strikethrough and inline code", () => {
    const root = renderMd("**Functional (F).** The *requirement* is ~~not~~ `fast`.");
    expect(root.querySelector("strong")).toHaveTextContent("Functional (F).");
    expect(root.querySelector("em")).toHaveTextContent("requirement");
    expect(root.querySelector("del")).toHaveTextContent("not");
    const code = root.querySelector("code")!;
    expect(code).toHaveTextContent("fast");
    expect(code.closest("pre")).toBeNull();
    expect(root.textContent).not.toContain("**");
  });

  it("renders headings, lists and blockquotes", () => {
    const root = renderMd(
      "## Verdict\n\n- one\n- two\n\n1. first\n2. second\n\n> quoted",
    );
    expect(root.querySelector("h2")).toHaveTextContent("Verdict");
    expect(root.querySelectorAll("ul > li")).toHaveLength(2);
    expect(root.querySelectorAll("ol > li")).toHaveLength(2);
    expect(root.querySelector("blockquote")).toHaveTextContent("quoted");
  });

  it("renders fenced code blocks that scroll inside their card", () => {
    const root = renderMd("```json\n{\"label\": \"NFR\"}\n```");
    const pre = root.querySelector("pre")!;
    expect(pre.querySelector("code")).toHaveTextContent('{"label": "NFR"}');
    expect(pre).toHaveClass("max-w-full", "overflow-x-auto");
  });

  it("renders GFM tables in a horizontal scroll wrapper", () => {
    const root = renderMd("| Class | Votes |\n| --- | --- |\n| F | 2 |\n| NFR | 1 |");
    const table = root.querySelector("table")!;
    expect(table.querySelectorAll("th")).toHaveLength(2);
    expect(table.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(table.parentElement).toHaveClass("max-w-full", "overflow-x-auto");
  });

  it("shows single newlines as line breaks", () => {
    const root = renderMd("line one\nline two");
    expect(root.querySelectorAll("p")).toHaveLength(1);
    expect(root.querySelector("p br")).not.toBeNull();
  });

  it("does not render raw HTML as elements", () => {
    const root = renderMd(
      'Hi <script>alert(1)</script> <img src="x" onerror="alert(2)"> <b>bold</b>',
    );
    expect(root.querySelector("script")).toBeNull();
    expect(root.querySelector("img")).toBeNull();
    expect(root.querySelector("b")).toBeNull();
    expect(root.querySelector("[onerror]")).toBeNull();
    // The source stays visible as text.
    expect(root.textContent).toContain("<script>");
  });

  it("strips unsafe link URLs and keeps the text", () => {
    const root = renderMd(
      "[click](javascript:alert(1)) [data](data:text/html,x) [rel](/admin) [vb](VBScript:x)",
    );
    expect(root.querySelector("a")).toBeNull();
    expect(root).toHaveTextContent("click data rel vb");
  });

  it("opens safe links in a new tab with noopener noreferrer", () => {
    const root = renderMd(
      "[docs](https://example.com/a) [mail](mailto:team@example.com) see http://example.org",
    );
    const links = Array.from(root.querySelectorAll("a"));
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "https://example.com/a",
      "mailto:team@example.com",
      "http://example.org",
    ]);
    for (const a of links) {
      expect(a).toHaveAttribute("target", "_blank");
      expect(a).toHaveAttribute("rel", "noopener noreferrer");
    }
  });

  it("does not load images; shows their alt text", () => {
    const root = renderMd("![a chart](https://example.com/x.png)");
    expect(root.querySelector("img")).toBeNull();
    expect(root).toHaveTextContent("a chart");
  });

  it("keeps long content wrapping inside its column (task 11.15)", () => {
    const long = `**${"x".repeat(400)}**`;
    const root = renderMd(long);
    expect(root).toHaveClass("min-w-0", "break-words", "[overflow-wrap:anywhere]");
    expect(root.querySelector("strong")).toHaveTextContent("x".repeat(400));
  });

  it("safeUrl allows only http(s) and mailto", () => {
    expect(safeUrl("https://a.b")).toBe("https://a.b");
    expect(safeUrl(" HTTP://a.b ")).toBe("HTTP://a.b");
    expect(safeUrl("mailto:x@y.z")).toBe("mailto:x@y.z");
    for (const bad of ["javascript:alert(1)", "data:x", "ftp://a", "/rel", "#top", ""]) {
      expect(safeUrl(bad)).toBeNull();
    }
  });
});
