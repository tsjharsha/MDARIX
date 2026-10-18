import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HomePage, SITE_LOOP } from "./pages";
import { DEMO_REQUESTS_OFFERED } from "./offer";
import { capabilityStatus, lifecycleStages } from "./content";
import { trialIncludes } from "./legacyContent";
import { LOOP_ORDER } from "../features/workspace/qualityLoop";

describe("website home", () => {
  it("draws the quality loop in story order with illustrative values", () => {
    expect(SITE_LOOP.map((station) => station.key)).toEqual(LOOP_ORDER.map((step) => step.code));
    expect(SITE_LOOP.filter((station) => station.done)).toHaveLength(2);
  });

  it("says the loop is synthetic and leads to the free trial", () => {
    const html = renderToStaticMarkup(<HomePage />);
    expect(html).toContain("Illustrative · synthetic data");
    expect(html).toContain("2 of 8 inspection checks clear");
    expect(html).toContain('href="/signup"');
    expect(html).toContain("Start free trial");
  });

  it("offers no demo while only the free trial is offered", () => {
    expect(DEMO_REQUESTS_OFFERED).toBe(false);
    const html = renderToStaticMarkup(<HomePage />);
    expect(html).not.toContain('href="/request-demo"');
    expect(html).not.toContain("Request a demo");
    expect(html).not.toContain("one-to-one demo");
  });

  it("keeps AI out of what is available today and says the free trial runs without it", () => {
    const today = capabilityStatus.find((status) => status.label === "Available today")!;
    expect(today.items.map((item) => `${item.title} ${item.detail}`).join(" ")).not.toMatch(/\bAI\b/);
    expect(today.text).toContain("free trial");
    expect(trialIncludes).toContain("AI is off during the trial: every step works by hand");
    const html = renderToStaticMarkup(<HomePage />);
    expect(html).toContain("In your free trial");
    expect(html).toContain("Up to 3 users and 5,000 uploaded rows");
    expect(html).not.toContain("AI answers show their evidence");
  });

  it("keeps one worked example and moves the roadmap and the regulations to their own pages", () => {
    const html = renderToStaticMarkup(<HomePage />);
    expect(html).toContain("Why did pressure-alarm complaints rise after OrbitCare 300 Rev B?");
    expect(html).toContain("Your systems stay the record.");
    // One line, linked to the Regulations page, instead of the standards section.
    expect(html).toMatch(/href="\/trust\/regulations"[^>]*>Covers FDA, EU MDR, UK and Canada reporting/);
    expect(html).not.toContain("Built around the evidence regulators ask for.");
    expect(html).not.toContain("Know what is available today, and what comes next.");
    // The three overlapping story sections are one.
    expect(html).not.toContain("From field signal to a decision you can defend.");
    expect(html).not.toContain("From a rising signal to the lot, the component and the supplier.");
    expect(html).not.toContain("Bring quality, regulatory, product, supplier, and manufacturing context");
  });

  it("shows signals and CAPA as current lifecycle capability", () => {
    const items = lifecycleStages.flatMap((stage) => stage.items);
    for (const slug of ["signal", "capa"]) {
      expect(items.find((item) => item.slug === slug)).toMatchObject({
        future: false,
        href: `/product-lifecycle#${slug}`,
      });
    }
    expect(items.find((item) => item.slug === "recall")?.future).toBe(true);
  });
});
