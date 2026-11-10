// 0.10.91, the owner's four design decisions (5 Nov 2026): Log a call and Raise a trend are filled primary buttons;
// the complaint list's big count; the rail's alerts as a dot with no count, named "New items"; the keyboard walk kept.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { NavRail, PhoneBar, railAlerts, trialTabs, visibleTabs, PERSONA_TABS } from "./HybridShell";
import { ListGlance } from "./sections/ComplaintList";
import { TrendHeroes } from "./sections/TrendCheck";
import type { TrendBoard, TrendItem } from "./signalAi";
import { SAMPLE_SOURCE } from "./complaintList";
import complaintViews from "./sections/ComplaintViews.tsx?raw";
import trendCheck from "./sections/TrendCheck.tsx?raw";
import journey from "../../../e2e/support/journey.ts?raw";

const ALL = Object.values(PERSONA_TABS).map((tab) => tab.section);

describe("1. Log a call and Raise a trend are the pages' filled primary buttons", () => {
  it("fills Log a call on Complaints", () => {
    expect(complaintViews).toMatch(
      /className="ac-primary"[\s\S]{0,200}<PhoneCall size=\{15\} aria-hidden="true" \/> Log a case/,
    );
  });

  it("fills Raise a trend on the trend's hero, and keeps it secondary in the table of every group", () => {
    const rising = {
      key: "g1",
      name: "OrbitCare 300 Infusion Pump (Sample) Rev B",
      result: "SIGNIFICANT",
      recent: 9,
      recent_days: 30,
      expected: 1,
      ratio: 9.3,
      history: 6,
      history_days: 180,
      baseline: "PREVIOUS_VERSION",
      basis: "UNITS",
      p_value: 0.0001,
      lots: [],
      open_signals: [],
      product: {
        id: "p1",
        business_id: null,
        identifier: "SAMPLE-ORBIT-300",
        name: "OrbitCare 300 Infusion Pump (Sample)",
      },
      product_version: { id: "v1", business_id: null, version_identifier: "Rev B" },
    } as unknown as TrendItem;
    const board = {
      items: [rising],
      recent_days: 30,
      history_days: 180,
      min_complaints: 3,
      summary: {},
    } as unknown as TrendBoard;
    const action = vi.fn(() => null);
    renderToStaticMarkup(<TrendHeroes board={board} action={action} source={SAMPLE_SOURCE} />);
    expect(action).toHaveBeenCalledWith(rising, true);
    expect(trendCheck).toContain('className={lead ? "ac-primary" : "ac-secondary"}');
    expect(trendCheck).toContain("render: (row: TrendItem) => action(row),");
  });
});

describe("2. the complaint list's big count", () => {
  it("leads the list at a glance with its count, beside the bar", () => {
    const rows = [{ work: { due: [] } }, { work: { due: [] } }, { work: null }];
    const glance = renderToStaticMarkup(<ListGlance rows={rows} />);
    expect(glance).toContain('<p class="hx-glance-big"><b class="uw-num">3</b><small>complaints</small></p>');
    expect(renderToStaticMarkup(<ListGlance rows={rows.slice(0, 1)} />)).toContain("<small>complaint</small>");
  });
});

describe("3. the rail's alerts: a dot, never a count", () => {
  const tabs = visibleTabs(trialTabs(["home", "complaints", "trees", "trends", "records"], true), ALL);

  it("marks Complaints while a complaint is overdue and Trends while a product rises", () => {
    expect([...railAlerts(3, 1)]).toEqual(["complaints", "trends"]);
    expect([...railAlerts(0, 0)]).toEqual([]);
    expect([...railAlerts(null, undefined)]).toEqual([]);
  });

  it("shows a dot named 'New items' beside the destination, and no number", () => {
    const rail = renderToStaticMarkup(
      <NavRail tabs={tabs} current="home" open={vi.fn()} progress={10} alerts={railAlerts(27, 1)} />,
    );
    const complaints = rail.slice(
      rail.indexOf('title="Complaints"'),
      rail.indexOf("</button>", rail.indexOf('title="Complaints"')),
    );
    expect(complaints).toContain('<i class="uw-tab-dot" aria-hidden="true" title="New items"></i>');
    expect(complaints).toContain('<span class="sr-only"> · New items</span>');
    expect(complaints).not.toMatch(/>\s*27\s*</);
    expect(rail.match(/uw-tab-dot/g)).toHaveLength(2);
    expect(renderToStaticMarkup(<NavRail tabs={tabs} current="home" open={vi.fn()} />)).not.toContain("uw-tab-dot");
  });

  it("puts the dot on More when the destination is behind it on a phone", () => {
    const bar = renderToStaticMarkup(
      <PhoneBar tabs={tabs} current="home" open={vi.fn()} alerts={new Set(["records"])} />,
    );
    const more = bar.slice(bar.indexOf('aria-expanded="false"'));
    expect(more).toContain("New items");
  });
});

describe("4. the keyboard walk kept", () => {
  it("tells the end of a page from focus lost in the middle of it", () => {
    expect(journey).toContain(
      "if (focus.id !== first) problems.push(`focus fell to the page after ${leftAt} Tab presses`);",
    );
  });
});

// Read as a file: the test run does not load stylesheets.
const fs = await import(/* @vite-ignore */ ["node", "fs"].join(":"));

describe("the report's Next step with 0.10.89's eMDR file, in the hero design", () => {
  const css: string = fs.readFileSync(new URL("./heroPages.css", import.meta.url), "utf8").replace(/\r\n/g, "\n");

  it("is the design's next card, with what the eMDR XML needs as a callout and its held-back button still legible", () => {
    expect(css).toMatch(
      /\.uw-hybrid \.ac-main \.uw-rail-next \{[^}]*background: linear-gradient\(160deg, var\(--ms-mint\)/,
    );
    expect(css).toMatch(
      /\.uw-rail-next #rp-emdr-needs \{[^}]*border-left: 3px solid var\(--ms-warn-mark\);[^}]*background: var\(--ms-warn-bg\);/,
    );
    expect(css).toMatch(/\.uw-rail-next > \.ac-secondary:disabled \{[^}]*color: var\(--ms-ink-2\);\s*opacity: 1;/);
    // Tokens only, so the dark theme carries it.
    const start = css.indexOf("/* The report's Next step");
    expect(start).toBeGreaterThan(0);
    expect(css.slice(start, start + 1600)).not.toMatch(/#[0-9a-f]{3,8}\b/i);
  });
});
