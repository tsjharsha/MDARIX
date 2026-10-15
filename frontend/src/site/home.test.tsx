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
    expect(today.items.join(" ")).not.toMatch(/AI/);
    expect(today.text).toContain("free trial");
    expect(trialIncludes).toContain("AI is off during the trial: every step works by hand");
    const html = renderToStaticMarkup(<HomePage />);
    expect(html).toContain("In your free trial");
    expect(html).toContain("Up to 3 users and 5,000 uploaded rows");
    expect(html).not.toContain("AI answers show their evidence");
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
