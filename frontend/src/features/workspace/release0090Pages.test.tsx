// 0.10.90, the owner-approved hero design on the pages: deadline rings, the list at a glance, the deadline ruler, the
// trend's lot split and each page's emblem. Presentation only: the words stay the page's own.
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ClockPill, DeadlineRuler, OwnerCell, StageCell, listGlance, ringOf, rulerDays, stageIndex } from "./heroBits";
import { lotParts } from "./sections/TrendCheck";
import { ListGlance } from "./sections/ComplaintList";
import { sectionIcon } from "./HybridShell";
import { CalendarClock, House, Settings2, Upload } from "lucide-react";

const fs = await import(/* @vite-ignore */ ["node", "fs"].join(":"));
const pagesCss: string = fs.readFileSync(new URL("./heroPages.css", import.meta.url), "utf8").replace(/\r\n/g, "\n");

const due = (hours: number, extra: object = {}) => ({
  key: "watch:us",
  category: "REPORTING",
  due_at: new Date(Date.now() + hours * 3_600_000).toISOString(),
  state: hours < 0 ? "OVERDUE" : "RUNNING",
  hours_left: hours,
  ...extra,
});

describe("a deadline's ring", () => {
  it("counts days of a 30-day window, hours in the last day, and an overdue clock as empty and critical", () => {
    expect(ringOf(due(29 * 24 + 5))).toEqual({ left: 29, total: 30, shown: "29", status: "good" });
    expect(ringOf(due(6 * 24))).toMatchObject({ left: 6, status: "warn" });
    expect(ringOf(due(22))).toEqual({ left: 22, total: 24, shown: "22h", status: "warn" });
    expect(ringOf(due(-30))).toMatchObject({ left: -2, status: "crit", shown: "!" });
  });

  it("keeps the deadline's own words beside the ring, with its state in a word, never the colour alone", () => {
    const pill = renderToStaticMarkup(<ClockPill item={due(29 * 24 + 5)} />);
    expect(pill).toContain("29 days left");
    expect(pill).toContain("On track");
    expect(pill).toMatch(/class="hx-clock hx-clock-good"[^>]*aria-hidden="true"/);
    expect(renderToStaticMarkup(<ClockPill item={due(3 * 24 + 1)} />)).toContain("Due soon");
    // Overdue says so in its own words; no second word.
    const late = renderToStaticMarkup(<ClockPill item={due(-30)} />);
    expect(late).toContain("overdue");
    expect(late).not.toContain("On track");
  });
});

describe("the list's cells", () => {
  it("places each stage on its dots, a report at the market step, and names the owner or says none", () => {
    expect(stageIndex("Triage")).toBe(0);
    expect(stageIndex("Report")).toBe(1);
    expect(stageIndex("Closed in the QMS")).toBe(5);
    expect(stageIndex("Something else")).toBe(-1);
    expect(renderToStaticMarkup(<StageCell stage="Decision" />)).toContain("<span>Decision</span>");
    expect(renderToStaticMarkup(<StageCell stage={null} />)).toBe("—");
    expect(renderToStaticMarkup(<OwnerCell name="Taylor Quality" />)).toContain(">TQ<");
    expect(renderToStaticMarkup(<OwnerCell name={null} />)).toContain("Not named");
  });

  it("counts the list at a glance: legal clocks within a week, later, none; late replies; deaths and injuries apart", () => {
    const reply = { key: "comm:1", category: "COMMUNICATIONS", due_at: "", state: "OVERDUE", hours_left: -40 };
    const rows = [
      { work: { due: [due(27 * 24), reply] } },
      { work: { due: [due(3 * 24)] }, serious_injury: true },
      { work: { due: [due(-5)] }, death: true, serious_injury: true },
      { work: { due: [] } },
      { work: null },
    ];
    expect(listGlance(rows)).toEqual({ soon: 2, later: 1, none: 2, lateReplies: 1, serious: 1, deaths: 1 });
    const glance = renderToStaticMarkup(<ListGlance rows={rows} />);
    expect(glance).toContain("Legal clock, 7 days or less");
    expect(glance).toContain("1 communication overdue");
    expect(glance).toContain("1 serious injury");
    expect(glance).toContain("1 death");
  });
});

describe("the deadline ruler", () => {
  it("spans ten days, three before today, and places now inside its fourth day", () => {
    const ruler = rulerDays(new Date("2026-11-04T20:00:00Z"), "America/New_York");
    expect(ruler.labels).toEqual([
      "Sun 1",
      "Mon 2",
      "Tue 3",
      "Wed 4",
      "Thu 5",
      "Fri 6",
      "Sat 7",
      "Sun 8",
      "Mon 9",
      "Tue 10",
    ]);
    expect(ruler.now).toBeGreaterThan(0.3);
    expect(ruler.now).toBeLessThan(0.4);
  });

  afterEach(() => vi.useRealTimers());

  it("groups the deadlines per day and state, says them in words, and marks the overdue stretch", () => {
    // A fixed clock: the three deadlines 50-52 hours ahead fall on one day whatever the time of day the test runs.
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-17T00:00:00Z"));
    const html = renderToStaticMarkup(<DeadlineRuler items={[due(-30), due(50), due(51), due(52)]} />);
    expect(html).toMatch(/role="img" aria-label="Deadlines on a timeline: 1 overdue since [A-Z][a-z]{2} \d+, 3 due /);
    expect(html.match(/class="hx-ruler-mk is-/g)).toHaveLength(2);
    expect(html).toContain("hx-ruler-od");
    expect(html).toContain("<em>Now</em>");
    expect(renderToStaticMarkup(<DeadlineRuler items={[]} />)).toBe("");
  });
});

describe("the trend's observed bar, split by lot", () => {
  it("splits only when the lots' counts add up to the observed count", () => {
    const row = {
      recent: 9,
      lots: ["SAMPLE-ORBIT-300-LOT-003", "SAMPLE-ORBIT-300-LOT-004", "SAMPLE-ORBIT-300-LOT-005"],
      lot_counts: { "SAMPLE-ORBIT-300-LOT-003": 3, "SAMPLE-ORBIT-300-LOT-004": 4, "SAMPLE-ORBIT-300-LOT-005": 2 },
    };
    expect(lotParts(row).map((part) => [part.short, part.n])).toEqual([
      ["003", 3],
      ["004", 4],
      ["005", 2],
    ]);
    expect(lotParts({ ...row, recent: 10 })).toEqual([]);
    expect(lotParts({ recent: 3 })).toEqual([]);
  });
});

describe("each page's emblem and the design's screens", () => {
  it("gives every page its destination's icon", () => {
    expect(sectionIcon("Settings")).toBe(Settings2);
    expect(sectionIcon("Import your data")).toBe(Upload);
    expect(sectionIcon("Look ahead")).toBe(CalendarClock);
    expect(sectionIcon("Nowhere")).toBe(House);
  });

  it("opens Home, Getting started and the complaint page on the monitor band, and stacks them on a phone", () => {
    for (const band of [".uw-home-band", ".uw-gs-band", ".uw-cp-bandgrid"]) expect(pagesCss).toContain(band);
    const phone = pagesCss.slice(pagesCss.indexOf("@media (max-width: 640px)"));
    expect(phone).toMatch(/\.uw-cp-bandgrid \{\s*grid-template-columns: minmax\(0, 1fr\);/);
    expect(phone).toMatch(/\.uw-hybrid \.uw-os-grid \{\s*grid-template-columns: minmax\(0, 1fr\);/);
  });

  it("keeps each walkthrough step's state in its accessible name (the journeys find steps by it)", () => {
    // Generated text would join the name ("Step 2: Triage ✓ Completed"); display: none would drop "Completed".
    expect(pagesCss).not.toMatch(/\.uw-os-s::(before|after)/);
    expect(pagesCss).not.toMatch(/\.uw-os-s \{\s*display: none/);
  });
});
