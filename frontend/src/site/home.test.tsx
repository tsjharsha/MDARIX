import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HomePage, PlatformPage } from "./pages";
import { DEMO_REQUESTS_OFFERED } from "./offer";
import { AVAILABILITY, WORK_AREAS, trialIncludes } from "./content";
import { EXAMPLE_NUMBERS } from "./visuals";

const text = (html: string) =>
  html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/\s+/g, " ");

describe("website home", () => {
  it("says in one hero line what MDARIX is for, with one primary and one secondary action", () => {
    const html = renderToStaticMarkup(<HomePage />);
    // The approved positioning (11 Nov 2026): a defensible decision and the right report, on time, in every market.
    expect(html).toContain(
      "Get every complaint to a defensible decision, and the right report on time in every market.",
    );
    expect(html.match(/<h1[ >]/g)).toHaveLength(1);
    const hero = html.slice(0, html.indexOf("</section>"));
    expect(hero.match(/class="ms-btn ms-btn-primary"/g)).toHaveLength(1);
    expect(hero).toMatch(/class="ms-btn ms-btn-primary" href="\/signup">Start free trial/);
    expect(hero).toContain('href="/platform">See how it works');
    expect(hero).toContain("Works beside your QMS or complaint software");
  });

  it("tells the product story in five steps, each leading to the place in MDARIX that does it", () => {
    const html = renderToStaticMarkup(<HomePage />);
    const steps = [...html.matchAll(/<li id="([a-z]+)" class="ms-story-step"/g)].map((match) => match[1]);
    expect(steps).toEqual(["signal", "product", "investigation", "decision", "effectiveness"]);
    expect(html).toContain("Why did pressure-alarm complaints rise after OrbitCare 300 Rev B?");
    for (const area of ["Cases", "Products", "Investigations", "Decisions &amp; Reports"])
      expect(html).toContain(`In MDARIX: ${area}`);
    // Every picture says it is illustrative.
    expect(html.match(/Illustrative · synthetic sample data/g)?.length).toBe(6);
  });

  it("names the five markets and says people submit every report", () => {
    const words = text(renderToStaticMarkup(<HomePage />));
    for (const market of ["United States", "EU and Northern Ireland", "Great Britain", "Canada", "India"])
      expect(words).toContain(market);
    expect(words).toContain("People submit every report; MDARIX never does.");
  });

  it("offers no demo while only the free trial is offered", () => {
    expect(DEMO_REQUESTS_OFFERED).toBe(false);
    const html = renderToStaticMarkup(<HomePage />);
    expect(html).not.toContain('href="/request-demo"');
    expect(html).not.toMatch(/request a demo|book a demo/i);
  });

  it("shows no photos and no screenshots, only drawn illustrations", () => {
    for (const page of [<HomePage key="home" />, <PlatformPage key="platform" />]) {
      const html = renderToStaticMarkup(page);
      expect(html).not.toContain("<img");
      expect(html).not.toContain(".webp");
    }
  });

  it("tells one story whose numbers add up", () => {
    const { weekly, releaseWeek } = EXAMPLE_NUMBERS;
    const sum = (values: readonly number[]) => values.reduce((total, value) => total + value, 0);
    // The trial sample's 19 OrbitCare pressure-alarm complaints: 4 before Rev B (released in week 16), 15 after.
    expect([sum(weekly.slice(0, releaseWeek - 1)), sum(weekly.slice(releaseWeek - 1))]).toEqual([4, 15]);
    expect(weekly).toHaveLength(26);
  });

  it("shows the trial sample's own records, not invented ones", () => {
    const words = text(renderToStaticMarkup(<HomePage />));
    // backend/app/trial: sample_data.py, sample_decision.py, sample_reports.py, sample_assessments.py, flagship.py.
    for (const fact of [
      "Changed in SAMPLE-CHG-014",
      "Precision Sensors Ltd",
      "NovaSense Components (SAMPLE-CHG-014)",
      "32 units",
      "13 units",
      "003–008",
      "9.3×",
      "Partially supported",
      "Weakly supported",
      "SAMPLE-RV-09",
      "SAMPLE-RV-10",
      "SAMPLE-CAPA-02: incoming inspection of NovaSense pressure sensors restored to 32 units per lot",
      "Inconclusive",
    ])
      expect(words).toContain(fact);
    expect(words).not.toMatch(/a month (before|after)|drifts at low pressure|firmware/);
  });
});

describe("how it works", () => {
  it("walks the five work areas of the product in order, each with its own section", () => {
    const html = renderToStaticMarkup(<PlatformPage />);
    expect(WORK_AREAS.map((area) => area.name)).toEqual([
      "Today",
      "Cases",
      "Investigations",
      "Products",
      "Decisions & Reports",
    ]);
    for (const area of WORK_AREAS) {
      expect(html).toContain(`href="#${area.id}"`);
      expect(html).toContain(`id="${area.id}"`);
    }
  });

  it("keeps AI out of what the trial offers today, and says what comes in a pilot and what is planned", () => {
    const [today, pilot, planned] = AVAILABILITY;
    expect(today.items.join(" ")).not.toMatch(/\bAI\b/);
    expect(pilot.items.join(" ")).toContain("Live connections");
    expect(planned.items.join(" ")).toContain("Single sign-on");
    expect(trialIncludes).toContain(
      "AI on the trial's sample data only, with outputs labelled as AI proposals that a person reviews",
    );
    const html = renderToStaticMarkup(<PlatformPage />);
    expect(html).toContain('id="availability"');
    expect(html).toContain("Up to 50 people and 5,000 uploaded rows");
  });
});
