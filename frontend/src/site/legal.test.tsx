import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AccessibilityPage, LegalDocumentView, SecurityPage, legalDocumentState } from "./legal";

describe("a legal page whose text cannot be loaded (CMP-21)", () => {
  it("is an error, not 'pending approval', unless the server says the text is not provided", () => {
    expect(legalDocumentState(null, null)).toEqual({ status: "ERROR" });
    expect(legalDocumentState({ ok: false }, null)).toEqual({ status: "ERROR" });
    expect(legalDocumentState({ ok: true }, null)).toEqual({ status: "ERROR" });
    expect(legalDocumentState({ ok: true }, { markdown: "x" })).toEqual({ status: "ERROR" });
    expect(legalDocumentState({ ok: true }, { available: false, markdown: null })).toEqual({ status: "PENDING" });
    expect(legalDocumentState({ ok: true }, { available: true, markdown: "# Terms" })).toEqual({
      status: "READY",
      markdown: "# Terms",
    });
  });

  it("offers a retry and the address to ask for the text, and never says the text is unapproved", () => {
    const html = renderToStaticMarkup(
      <LegalDocumentView path="/privacy" state={{ status: "ERROR" }} contact={null} onRetry={() => undefined} />,
    );
    expect(html).toContain("could not be loaded");
    expect(html).toContain("Try again");
    expect(html).toContain('href="mailto:privacy@mdarix.in"');
    expect(html).toContain('role="alert"');
    expect(html).not.toContain("pending approval");
  });

  it("keeps the pending summary for a document the server has not been given", () => {
    const html = renderToStaticMarkup(
      <LegalDocumentView path="/terms" state={{ status: "PENDING" }} contact={null} onRetry={() => undefined} />,
    );
    expect(html).toContain("pending approval");
  });
});

describe("accessibility statement (CMP-16)", () => {
  it("says what was done, the known gaps and how to report a problem, without claiming conformance", () => {
    const html = renderToStaticMarkup(<AccessibilityPage />);
    for (const heading of ["Accessibility statement", "What we have done", "Known gaps", "Tell us about a problem"])
      expect(html).toContain(heading);
    expect(html).toContain("do not claim that it conforms");
    expect(html).toContain("mailto:support@mdarix.in");
    expect(html).toContain("Last updated: 20 October 2026");
    // The header menus' keyboard order was fixed in 0.10.38 (WEB-10): no longer a known gap.
    expect(html).not.toContain("the Tab key moves to the next menu instead of into the open menu");
    expect(html).toContain("Tab moves from a menu&#x27;s button into its links");
    expect(html).not.toMatch(/fully conform|is compliant|WCAG[^.]*certified/i);
  });
});

describe("security page (CMP-10)", () => {
  it("says which files are scanned for malware and that imports are not stored", () => {
    const html = renderToStaticMarkup(<SecurityPage />);
    expect(html).not.toContain("Every uploaded file is scanned");
    expect(html).toContain("Every file MDARIX stores, such as evidence attachments, is scanned for malware");
    expect(html).toContain("Imported CSV and Excel files are read as data only and are not stored");
  });
});

describe("the legal and trust pages' look (0.11.08)", () => {
  it("open with the dark page band of the other site pages, the page's only H1 inside it", () => {
    const view = (path: "/privacy" | "/terms" | "/trial-agreement") =>
      renderToStaticMarkup(
        <LegalDocumentView path={path} state={{ status: "LOADING" }} contact={null} onRetry={() => undefined} />,
      );
    const pages: [string, string][] = [
      [view("/privacy"), "Privacy policy"],
      [view("/terms"), "Terms of service"],
      [view("/trial-agreement"), "Free trial agreement"],
      [renderToStaticMarkup(<SecurityPage />), "Security at MDARIX"],
      [renderToStaticMarkup(<AccessibilityPage />), "Accessibility statement"],
    ];
    for (const [html, title] of pages) {
      const hero = html.match(/^<section class="ms-page-hero ms-dark">([\s\S]*?)<\/section>/);
      expect(hero, title).not.toBeNull();
      expect(hero![1], title).toMatch(new RegExp(`<h1 id="[a-z-]+-title">${title}</h1>`));
      expect(hero![1], title).toMatch(/<p>.{30,}<\/p>/);
      expect(html.match(/<h1[\s>]/g), title).toHaveLength(1);
    }
  });
});
