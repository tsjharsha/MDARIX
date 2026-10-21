import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Markdown, parseMarkdown, safeHref } from "./markdown";

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

  it("follows the page's h1 with h2 sections, never jumping to h3 (WEB-18)", () => {
    const doc = (...lines: string[]) => lines.join("\n\n");
    const html = renderToStaticMarkup(
      <Markdown source={doc("# Terms of service", "## 1. The Service", "Text.", "### 1.1 Accounts", "## 2. Fees")} />,
    );
    expect(html).not.toContain("<h1");
    expect(html).not.toContain("Terms of service");
    expect(html).toContain("<h2>1. The Service</h2>");
    expect(html).toContain("<h3>1.1 Accounts</h3>");
    expect(html).toContain("<h2>2. Fees</h2>");
    // A document without its own title line starts one level under the page's h1, as before.
    expect(renderToStaticMarkup(<Markdown source={doc("## Contact", "Write to us.")} />)).toContain("<h3>Contact</h3>");
    expect(renderToStaticMarkup(<Markdown source={doc("# Notice", "Intro.")} />)).not.toContain("Notice");
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
