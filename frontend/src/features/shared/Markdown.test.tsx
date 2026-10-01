import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Markdown, parseMarkdown } from "./Markdown";

describe("parseMarkdown", () => {
  it("splits headings, paragraphs, lists and tables", () => {
    const blocks = parseMarkdown(
      [
        "## Answer",
        "Complaints rose after Rev B.",
        "",
        "- first",
        "- second",
        "",
        "1. one",
        "2. two",
        "",
        "| # | Missing | Why |",
        "|---|---|---|",
        "| 1 | Lot data | Rate <br> per lot |",
      ].join("\n"),
    );
    expect(blocks.map((block) => block.kind)).toEqual(["heading", "paragraph", "list", "list", "table"]);
    expect(blocks[4]).toEqual({
      kind: "table",
      header: ["#", "Missing", "Why"],
      rows: [["1", "Lot data", "Rate; per lot"]],
    });
  });
});

describe("Markdown", () => {
  it("renders formatting as elements and marks known citations", () => {
    const html = renderToStaticMarkup(
      <Markdown
        source="**Bold** and *soft* with `code` [SAMPLE-EV-001] [OTHER-1]"
        citations={new Set(["SAMPLE-EV-001"])}
      />,
    );
    expect(html).toContain("<strong>Bold</strong>");
    expect(html).toContain("<em>soft</em>");
    expect(html).toContain("<code>code</code>");
    expect(html).toContain('class="md-cite is-known"');
    expect(html).toContain('class="md-cite"');
  });

  it("never turns model output into live HTML or links", () => {
    const html = renderToStaticMarkup(
      <Markdown source={"<script>alert(1)</script> <img src=x onerror=alert(1)> [click](javascript:alert(1))"} />,
    );
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("<a ");
    expect(html).toContain("&lt;script&gt;");
  });
});

describe("citations", () => {
  it("accepts underscores and a bolded identifier inside the brackets", () => {
    const html = renderToStaticMarkup(
      <Markdown source="See [**R1_TENANT_1-EVIDENCE-CANARY**]." citations={new Set(["R1_TENANT_1-EVIDENCE-CANARY"])} />,
    );
    expect(html).toContain('<span class="md-cite is-known" title="Cited evidence">R1_TENANT_1-EVIDENCE-CANARY</span>');
  });
});
