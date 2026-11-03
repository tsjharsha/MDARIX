import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HomePage, SITE_LOOP } from "./pages";
import { DEMO_REQUESTS_OFFERED } from "./offer";
import { capabilityStatus, lifecycleStages } from "./content";
import { trialIncludes } from "./legacyContent";
import { LOOP_ORDER } from "../features/workspace/qualityLoop";
import { EXAMPLE_NUMBERS } from "./visuals";
import { InvestigationAnimation } from "./motion";
import { SCENES } from "./scenes";

describe("website home", () => {
  it("draws the quality loop in story order with illustrative values", () => {
    expect(SITE_LOOP.map((station) => station.key)).toEqual(LOOP_ORDER.map((step) => step.code));
    expect(SITE_LOOP.filter((station) => station.done)).toHaveLength(3);
  });

  it("says the loop is synthetic and leads to the free trial", () => {
    const html = renderToStaticMarkup(<HomePage />);
    expect(html).toContain("Illustrative · synthetic data");
    expect(html).toContain("3 of 11 inspection checks clear");
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
    expect(html).toContain("Up to 50 people and 5,000 uploaded rows");
    expect(html).not.toContain("AI answers show their evidence");
  });

  it("keeps one worked example and moves the roadmap and the regulations to their own pages", () => {
    const html = renderToStaticMarkup(<HomePage />);
    expect(html).toContain("Why did pressure-alarm complaints rise after OrbitCare 300 Rev B?");
    expect(html).toContain("Your QMS keeps the complaint record.");
    // One line, linked to the Regulations page, instead of the standards section.
    expect(html).toMatch(
      /href="\/trust\/regulations"[^>]*>Covers reporting for the US, EU\/NI, GB and India \(MvPI worksheet\)/,
    );
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

describe("the worked example", () => {
  it("says in the hero what MDARIX is for", () => {
    const html = renderToStaticMarkup(<HomePage />);
    // Problem first (0.10.45): seeing the risk in the data, and trying it on your own data without a demo call.
    expect(html).toContain("<h1>See the risk in your post-market data, not just collect it.</h1>");
    expect(html).toContain("Try it on your own data today, no demo call needed.");
    expect(html.indexOf("no demo call needed")).toBeLessThan(html.indexOf('href="/signup"'));
    expect(html).toContain("Post-market surveillance and complaint handling for medical devices");
    expect(html).toContain(
      "Complaints, reporting clocks, trend signals, investigations and CAPA in one traceable place",
    );
  });

  it("tells one story whose numbers add up", () => {
    const { weekly, releaseWeek, lots, withoutLot } = EXAMPLE_NUMBERS;
    const sum = (values: readonly number[]) => values.reduce((total, value) => total + value, 0);
    const before = sum(weekly.slice(0, releaseWeek));
    const after = sum(weekly.slice(releaseWeek));
    const byLot = sum(lots.map((lot) => lot.count));
    // 42 complaints: 6 before Rev B and 36 after over 13 weeks each (2 and 12 a month), 40 with a lot and 2 without.
    expect([before, after, before + after]).toEqual([6, 36, 42]);
    expect(byLot + withoutLot).toBe(42);
    expect(sum(lots.filter((lot) => lot.sensor).map((lot) => lot.count))).toBe(30);
    const html = renderToStaticMarkup(<HomePage />);
    expect(html).toContain("hold 30 of the 42 complaints");
    expect(html).toContain("from about 2 to 12 a month");
    expect(html).toContain("2 of the 42 complaints name no lot.");
    expect(renderToStaticMarkup(<InvestigationAnimation />)).toContain("2 complaints without lot reference");
    // The Platform scenes tell the same case: one case ID and the same monthly rates.
    const scenes = Object.values(SCENES)
      .map((Scene) => renderToStaticMarkup(<Scene label="Scene" />))
      .join("");
    expect(scenes).toContain("INV-031");
    expect(scenes.match(/INV-\d+/g)?.every((id) => id === "INV-031")).toBe(true);
    expect(scenes).toContain("Complaints rose from 2 to 12 a month");
  });
});
