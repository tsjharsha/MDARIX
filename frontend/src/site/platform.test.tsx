import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AVAILABILITY, CAPABILITY_AVAILABILITY, capabilityStatus, platformGroups } from "./content";
import { menus } from "./legacyContent";
import { PlatformGroupPage, PlatformPage, RegulationsPage } from "./pages";
import { textFloor } from "./scenes/kit";

describe("the Platform pages", () => {
  it("are four pages with plain names, one per group of the former menu, holding all 19 capabilities", () => {
    expect(platformGroups.map((group) => group.name)).toEqual(["Product 360", "Investigations", "Decisions", "Trust"]);
    expect(platformGroups.map((group) => group.title)).toEqual(menus.Platform.map((group) => group.title));
    const slugs = platformGroups.flatMap((group) => group.capabilities.map((capability) => capability.slug));
    expect(slugs).toHaveLength(19);
    expect(new Set(slugs).size).toBe(19);
    for (const name of platformGroups.map((group) => group.name)) expect(name).not.toMatch(/Intelligence/);
  });

  it("label every capability with one of the roadmap's three stages", () => {
    expect(AVAILABILITY).toEqual(capabilityStatus.map((status) => status.label));
    for (const group of platformGroups)
      for (const capability of group.capabilities) {
        expect(AVAILABILITY, capability.slug).toContain(capability.availability.status);
        expect(capability.availability.note.length, capability.slug).toBeGreaterThan(20);
      }
    expect(Object.keys(CAPABILITY_AVAILABILITY)).toHaveLength(19);
  });

  it("do not claim what the free trial does not have", () => {
    // The Product 360 screen is not in the trial, and AI works on the sample data only in the trial.
    for (const slug of [
      "product-360",
      "reality-graph",
      "challenger",
      "ai-assurance",
      "ai-provenance",
      "counterfactual",
    ])
      expect(CAPABILITY_AVAILABILITY[slug].status, slug).not.toBe("Available today");
    for (const slug of ["challenger", "ai-assurance", "ai-provenance"])
      expect(CAPABILITY_AVAILABILITY[slug].note, slug).toContain("In the trial AI works on the sample data only");
    const live = capabilityStatus[0].items.map((item) => item.title);
    expect(live).not.toContain("Product 360");
  });

  it("show each capability as a section with its availability tag", () => {
    for (const group of platformGroups) {
      const html = renderToStaticMarkup(<PlatformGroupPage path={group.path} />);
      expect(html).toContain(`Platform · ${group.name}`);
      for (const capability of group.capabilities) {
        expect(html).toContain(`id="${capability.slug}"`);
        expect(html).toContain(capability.availability.note.replace(/'/g, "&#x27;"));
      }
      for (const status of new Set(group.capabilities.map((capability) => capability.availability.status)))
        expect(html).toContain(status);
    }
    const overview = renderToStaticMarkup(<PlatformPage />);
    for (const group of platformGroups) expect(overview).toContain(`href="${group.path}"`);
  });

  it("put the regulations on their own page, without claiming compliance", () => {
    const html = renderToStaticMarkup(<RegulationsPage />);
    for (const text of ["21 CFR 803.50", "EU MDR Art. 87", "UK MDR 2002", "SOR/98-282", "ISO 13485", "ISO 14971"])
      expect(html).toContain(text);
    expect(html).toContain("does not certify compliance");
    expect(html).toContain("not yet a validated (GxP) system");
  });

  it("says only investigation decisions are signed; a reportability decision is recorded with its reason", () => {
    const html = renderToStaticMarkup(<RegulationsPage />);
    expect(html).toContain("Reportability decisions are recorded by a named person with their reason.");
    expect(html).toContain("Investigation decisions are signed electronically, with re-authentication.");
    expect(html).not.toMatch(/[Rr]eportability decisions[^.<]*signed/);
  });
});

describe("diagram text", () => {
  it("is drawn large enough to read at the size each frame gets", () => {
    // A 760 px frame on a 1,440 px screen needs no more than the scenes' 13 px base size.
    expect(textFloor(760, 475)).toBeLessThanOrEqual(13);
    // A page-hero frame (588 px wide) raises small labels so they render at 13 px.
    expect(textFloor(588, 367.5) * (588 / 640)).toBeGreaterThanOrEqual(13);
    // At the 80% page scale, never below 12 px on screen.
    expect(textFloor(760, 475, 0.8) * (760 / 640) * 0.8).toBeGreaterThanOrEqual(12);
    // The cap keeps a scene's layout; a phone-sized frame keeps the scenes' own sizes.
    expect(textFloor(500, 312.5)).toBe(16);
    expect(textFloor(340, 212.5)).toBe(13);
    expect(textFloor(0, 0)).toBe(0);
  });
});
