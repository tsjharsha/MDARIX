import { describe, expect, it } from "vitest";
import { parseMarkdown, safeHref } from "./markdown";

describe("legal document Markdown", () => {
  it("reads headings, paragraphs and both kinds of list", () => {
    const blocks = parseMarkdown(
      "# Privacy policy\r\n\r\nWe keep\nvery little.\n\n- one\n- two\n  continued\n\n1. first\n2. second\n## Contact",
    );
    expect(blocks).toEqual([
      { kind: "heading", level: 1, text: "Privacy policy" },
      { kind: "paragraph", text: "We keep very little." },
      { kind: "list", ordered: false, items: ["one", "two continued"] },
      { kind: "list", ordered: true, items: ["first", "second"] },
      { kind: "heading", level: 2, text: "Contact" },
    ]);
  });

  it("keeps HTML as text instead of markup", () => {
    expect(parseMarkdown("<script>alert(1)</script>")).toEqual([
      { kind: "paragraph", text: "<script>alert(1)</script>" },
    ]);
  });

  it("allows only web, email and same-site links", () => {
    expect(safeHref("https://example.com/terms")).toBe("https://example.com/terms");
    expect(safeHref("mailto:privacy@example.com")).toBe("mailto:privacy@example.com");
    expect(safeHref("/privacy")).toBe("/privacy");
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref("data:text/html,hi")).toBeNull();
    expect(safeHref("//evil.example")).toBeNull();
  });
});
