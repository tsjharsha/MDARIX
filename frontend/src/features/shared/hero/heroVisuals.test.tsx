// 0.10.90, the owner-approved hero design: the shared visuals. Each has an accessible name (or is marked decorative
// where its words stand beside it), and no status is shown by colour alone.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  ClockRing,
  DeviceIcon,
  Flag,
  HarmBadge,
  MonitorBand,
  ProgressArc,
  StageDots,
  StatusPill,
  clockStatus,
  deviceKind,
  flagCode,
} from "./HeroVisuals";
import { BedsideScene, InfusionPumpArt, PatientMonitorArt, SignedSeal } from "./HeroArt";

const html = renderToStaticMarkup;
const dashoffset = (markup: string) =>
  Number(/class="hx-clock-val"[^>]*stroke-dashoffset="([\d.]+)"/.exec(markup)?.[1]);
const dasharray = (markup: string) => Number(/class="hx-clock-val"[^>]*stroke-dasharray="([\d.]+)"/.exec(markup)?.[1]);

describe("ClockRing", () => {
  it("is named, coloured by its state, and fills by the share of time left", () => {
    const ring = html(
      <ClockRing left={29} total={30} label="29 days left">
        29
      </ClockRing>,
    );
    expect(ring).toContain('role="img" aria-label="29 days left"');
    expect(ring).toContain("hx-clock-good");
    expect(ring).toContain('<span class="hx-clock-c">29</span>');
    expect(dashoffset(ring) / dasharray(ring)).toBeCloseTo(1 / 30, 2);
  });

  it("is overdue at less than nothing (an empty ring), due soon within a week, on track after", () => {
    expect([clockStatus(-2), clockStatus(0), clockStatus(7), clockStatus(8)]).toEqual(["crit", "warn", "warn", "good"]);
    const over = html(<ClockRing left={-2} total={30} label="2 days overdue" />);
    expect(over).toContain("hx-clock-crit");
    expect(dashoffset(over)).toBeCloseTo(dasharray(over), 1);
    expect(html(<ClockRing left={22} total={24} status="warn" label="22 h left" />)).toContain("hx-clock-warn");
  });

  it("draws one tick per unit on the big clock, the units left lit", () => {
    const big = html(<ClockRing left={29} total={30} size={210} stroke={14} ticks label="29 days left" />);
    expect(big.match(/class="hx-tick/g)).toHaveLength(30);
    expect(big.match(/class="hx-tick is-on"/g)).toHaveLength(29);
  });

  it("is hidden from screen readers when the words stand beside it", () => {
    const ring = html(<ClockRing left={3} total={30} label="3 days left" decorative />);
    expect(ring).toContain('aria-hidden="true"');
    expect(ring).not.toContain("aria-label");
  });
});

describe("ProgressArc", () => {
  it("draws ten segments: done, the current one, and those still to do", () => {
    const arc = html(<ProgressArc done={2} size={64} />);
    expect(arc).toContain('aria-label="2 of 10 steps completed"');
    expect(arc.match(/hx-seg is-done/g)).toHaveLength(2);
    expect(arc.match(/hx-seg is-cur/g)).toHaveLength(1);
    expect(arc.match(/hx-seg is-todo/g)).toHaveLength(7);
  });

  it("ticks the middle once all ten are done; small arcs skip the tick", () => {
    expect(html(<ProgressArc done={10} size={64} />).match(/hx-seg is-done/g)).toHaveLength(11);
    expect(html(<ProgressArc done={10} size={22} />).match(/hx-seg is-done/g)).toHaveLength(10);
    expect(html(<ProgressArc done={10} size={22} tone="light" decorative />)).toContain('aria-hidden="true"');
  });
});

describe("StatusPill and HarmBadge", () => {
  it("always carry an icon and a word beside the colour", () => {
    for (const tone of ["crit", "warn", "good"] as const) {
      const pill = html(<StatusPill tone={tone}>2 days left</StatusPill>);
      expect(pill).toContain(`hx-pill-${tone}`);
      expect(pill).toMatch(/<svg[^>]*aria-hidden="true"/);
      expect(pill).toContain("<span>2 days left</span>");
    }
  });

  it("show harm in its own hue with severity bars and the word", () => {
    const serious = html(<HarmBadge harm="SERIOUS_INJURY" />);
    expect(serious).toContain("hx-pill-harm");
    expect(serious.match(/<i class="is-on"><\/i>/g)).toHaveLength(2);
    expect(serious).toContain("<span>Serious injury</span>");
    expect(html(<HarmBadge harm="DEATH" />).match(/<i class="is-on"><\/i>/g)).toHaveLength(3);
    const none = html(<HarmBadge harm="NONE" />);
    expect(none).toContain("hx-pill-good");
    expect(none).toContain("No harm reported");
    expect(html(<HarmBadge harm="NONE" label="None reported" />)).toContain("None reported");
  });
});

describe("Flag", () => {
  it("knows the sample's countries by name or code, the EU, and any other two-letter code", () => {
    expect(["US", "USA", "United States", "united states of america"].map(flagCode)).toEqual(["US", "US", "US", "US"]);
    expect(
      ["Germany", "France", "India", "Canada", "United Kingdom", "Great Britain", "Northern Ireland", "EU"].map(
        flagCode,
      ),
    ).toEqual(["DE", "FR", "IN", "CA", "GB", "GB", "GB", "EU"]);
    expect(flagCode("JP")).toBe("JP");
    expect(flagCode("Atlantis")).toBeNull();
    expect(flagCode(null)).toBeNull();
  });

  it("is named for screen readers, or decorative beside the country's name; nothing for an unknown country", () => {
    expect(html(<Flag country="US" />)).toContain('role="img" aria-label="United States"');
    expect(html(<Flag country="Germany" decorative />)).toContain('aria-hidden="true"');
    expect(html(<Flag country="JP" />)).toContain(">JP</text>");
    expect(html(<Flag country="Atlantis" />)).toBe("");
  });
});

describe("DeviceIcon", () => {
  it("draws the monitor, the pump and the respiratory controller, and a generic device for an imported product", () => {
    expect(deviceKind("PulseWatch 410 Patient Monitor (Sample)")).toBe("monitor");
    expect(deviceKind("OrbitCare 300 Infusion Pump (Sample)")).toBe("pump");
    expect(deviceKind("VentraLink 250 Respiratory Controller (Sample)")).toBe("vent");
    expect(deviceKind("OS-NEB nebulizer")).toBe("generic");
    expect(deviceKind(undefined)).toBe("generic");
    expect(html(<DeviceIcon kind="pump" />)).toContain('aria-label="Infusion pump"');
    expect(html(<DeviceIcon kind="generic" label="OS-NEB" />)).toContain('aria-label="OS-NEB"');
  });
});

describe("StageDots", () => {
  it("says the stage in words; the dots mark done and current", () => {
    const stages = ["Triage", "Report", "Investigation", "Decision", "Ready to close", "Closed in the QMS"];
    const dots = html(<StageDots stages={stages} current={1} />);
    expect(dots).toContain('aria-label="Stage 2 of 6: Report"');
    expect(dots.match(/<i class="is-on">/g)).toHaveLength(1);
    expect(dots.match(/<i class="is-cur">/g)).toHaveLength(1);
  });
});

describe("MonitorBand", () => {
  it("is a region named by its heading or its label", () => {
    expect(
      html(
        <MonitorBand labelledBy="h">
          <h1 id="h">SAMPLE-RV-11</h1>
        </MonitorBand>,
      ),
    ).toMatch(/^<section class="hx-monitor" aria-labelledby="h">/);
    expect(html(<MonitorBand label="Story complete">x</MonitorBand>)).toContain('aria-label="Story complete"');
  });
});

describe("the illustrations", () => {
  it("are each named, and two on one page never share a gradient", () => {
    const page = html(
      <>
        <BedsideScene />
        <PatientMonitorArt />
        <InfusionPumpArt />
        <SignedSeal />
      </>,
    );
    for (const name of [
      "a hospital bedside with a patient monitor, an infusion pump and a respiratory controller",
      "a patient monitor",
      "an infusion pump",
      "a signed record with its seal",
    ])
      expect(page).toContain(`role="img" aria-label="Illustration: ${name}"`);
    const ids = [...page.matchAll(/<radialGradient id="([^"]+)"/g)].map((match) => match[1]);
    expect(ids).toHaveLength(3);
    expect(new Set(ids).size).toBe(3);
  });
});
