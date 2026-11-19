import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HomePage, PlatformPage } from "./pages";
import { DEMO_REQUESTS_OFFERED } from "./offer";
import { AVAILABILITY, WORK_AREAS, trialIncludes } from "./content";
import { EXAMPLE_NUMBERS } from "./visuals";

// The screens shipped with the website (public/site/app).
const SHIPPED = Object.keys(import.meta.glob("/public/site/app/*.webp"));

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
    const steps = [...html.matchAll(/<li id="([a-z]+)" class="ms-story-step[^"]*"/g)].map((match) => match[1]);
    expect(steps).toEqual(["signal", "product", "investigation", "decision", "effectiveness"]);
    expect(html).toContain("Why did pressure-alarm complaints rise after OrbitCare 300 Rev B?");
    for (const area of ["Cases", "Products", "Investigations", "Decisions &amp; Reports"])
      expect(html).toContain(`In MDARIX: ${area}`);
    // Every picture says it is illustrative: the hero's screen and story graphic, five screens and the drawn trend.
    expect(html.match(/Illustrative · synthetic sample data/g)?.length).toBe(8);
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

  it("shows the app's own screens from the sample data: described, sized, and only the hero's loaded first", () => {
    for (const page of [<HomePage key="home" />, <PlatformPage key="platform" />]) {
      const images = [...renderToStaticMarkup(page).matchAll(/<img [^>]*>/g)].map((match) => match[0]);
      expect(images.length).toBeGreaterThanOrEqual(5);
      for (const image of images) {
        const src = image.match(/src="([^"]+)"/)?.[1] ?? "";
        expect(src).toMatch(/^\/site\/app\/[a-z]+\.webp$/);
        expect(SHIPPED, src).toContain(`/public${src}`);
        expect(image).toMatch(/alt="MDARIX [^"]+"/);
        expect(image).toContain('width="1600"');
        expect(image).toContain('height="1000"');
      }
      // No photos: every image is a screen of MDARIX.
      expect(images.every((image) => image.includes("/site/app/"))).toBe(true);
    }
    const home = [...renderToStaticMarkup(<HomePage />).matchAll(/<img [^>]*>/g)].map((match) => match[0]);
    expect(home[0]).toContain('fetchPriority="high"');
    expect(home[0]).toContain('loading="eager"');
    for (const image of home.slice(1)) expect(image).toContain('loading="lazy"');
  });

  it("states what is true at a glance, naming the standards as context and not as badges", () => {
    const html = renderToStaticMarkup(<HomePage />);
    const facts = text(
      html.slice(html.indexOf('class="ms-facts"'), html.indexOf("</section>", html.indexOf("ms-facts"))),
    );
    for (const fact of ["5 markets", "6-step investigation", "A person signs", "Sample data in minutes"])
      expect(facts).toContain(fact);
    for (const standard of ["21 CFR 803", "EU MDR Art. 87", "UK MDR 2002", "SOR/98-282", "India MDR 2017"])
      expect(facts).toContain(standard);
    expect(facts).not.toMatch(/certified|compliant|approved by/i);
  });

  it("tells the hero's story graphic in words: signal, version, evidence, a person's signature", () => {
    const words = text(renderToStaticMarkup(<HomePage />));
    for (const step of [
      "Signal 15 pressure-alarm complaints after Rev B, 4 before",
      "Product version Rev B: new sensor supplier, SAMPLE-CHG-014",
      "Evidence For and against, side by side",
      "Decision Signed by a person, never by AI",
    ])
      expect(words).toContain(step);
  });

  it("tells one story whose numbers add up", () => {
    const { weekly, releaseWeek } = EXAMPLE_NUMBERS;
    const sum = (values: readonly number[]) => values.reduce((total, value) => total + value, 0);
    // The trial sample's 19 OrbitCare pressure-alarm complaints: 4 before Rev B (released in week 16), 15 after.
    expect([sum(weekly.slice(0, releaseWeek - 1)), sum(weekly.slice(releaseWeek - 1))]).toEqual([4, 15]);
    expect(weekly).toHaveLength(26);
  });

  it("shows the trial sample's own records, not invented ones", () => {
    // The screens' descriptions and the drawn trend: backend/app/trial (sample_data.py, flagship.py).
    const html = renderToStaticMarkup(<HomePage />).replace(/&#x27;/g, "'");
    for (const fact of [
      "Precision Sensors Ltd",
      "NovaSense Components in SAMPLE-CHG-014",
      "SAMPLE-INV-001",
      "SAMPLE-CAPA-02",
      "signed inconclusive",
      "9.3×",
    ])
      expect(html).toContain(fact);
    expect(html).not.toMatch(/a month (before|after)|drifts at low pressure|firmware/);
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
