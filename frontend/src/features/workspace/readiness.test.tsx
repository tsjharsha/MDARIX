import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import {
  basisIds,
  checkStateOf,
  checkValue,
  itemsText,
  readinessHeadline,
  summaryPdfPath,
  type Readiness,
} from "./readiness";
import { CheckRow, HomeTile } from "./sections/Readiness";
import { PARKED_SECTIONS, routeFor } from "../../app/featureSet";
import { addressFor, locationFromAddress } from "./workspaceAddress";
import { VIEW_TO_SECTION } from "./UserWorkspace";
import { WORKSPACE_SECTIONS, sectionAllowed } from "./workspaceContext";
import { viewFromPath } from "../../app/router";

const check = (overrides = {}) => ({
  code: "COMPLAINTS_TO_RECHECK",
  title: "Complaints to recheck",
  value: 3,
  state: "CRITICAL" as const,
  detail: "1 of 5 records to recheck reports a death or serious injury",
  why: "2026 FDA warning letters cite complaints cancelled or logged as inquiries.",
  basis: [
    { id: "ISO13485_8_2_2", short: "ISO 13485 8.2.2", title: "Complaint handling" },
    { id: "CFR820_35", short: "21 CFR 820.35", title: "Control of records (QMSR)" },
  ],
  opens: { section: "Complaints", tab: "Second look" },
  items: [
    { id: "a", ref: "CMP000001" },
    { id: "b", ref: "CMP000002" },
  ],
  ...overrides,
});

const data = (summary: Partial<Readiness["summary"]>): Readiness => ({
  as_of: "2026-10-13",
  home: [],
  checks: [],
  summary: { checks: 7, clear: 7, attention: 0, critical: 0, not_set: 0, ...summary },
  note: "",
});

describe("readiness rules", () => {
  it("reads states with a label and a tone", () => {
    expect(checkStateOf("CRITICAL")).toEqual({ label: "Critical", tone: "critical" });
    expect(checkStateOf("NOT_SET")).toEqual({ label: "Not set up", tone: "serious" });
    expect(checkStateOf("CLEAR").tone).toBe("good");
    expect(checkStateOf("ODD").label).toBe("—");
  });

  it("leads with how many checks are clear and the worst tone", () => {
    expect(readinessHeadline(data({}))).toMatchObject({
      title: "Ready: every inspection check is clear",
      tone: "good",
    });
    const mixed = readinessHeadline(data({ clear: 3, critical: 2, attention: 1, not_set: 1 }));
    expect(mixed.title).toBe("3 of 7 inspection checks clear");
    expect(mixed.detail).toBe("2 critical, 1 needing attention, 1 not set up. Each one opens the records behind it.");
    expect(mixed.tone).toBe("critical");
    expect(readinessHeadline(data({ clear: 6, attention: 1 })).tone).toBe("warning");
  });

  it("shows values and the records a check names", () => {
    expect(checkValue({ value: 1200 })).toBe("1,200");
    expect(checkValue({ value: null })).toBe("—");
    expect(itemsText(check())).toBe("CMP000001, CMP000002 and 1 more");
    expect(itemsText(check({ value: 2 }))).toBe("CMP000001, CMP000002");
    expect(itemsText(check({ items: [] }))).toBe("");
    expect(summaryPdfPath(90)).toBe("/api/v1/readiness/summary.pdf?period_days=90");
  });
});

describe("readiness screens", () => {
  it("a home tile shows the number, its state, the records and why it matters", () => {
    const markup = renderToStaticMarkup(<HomeTile check={check()} onOpen={vi.fn()} />);
    expect(markup).toContain("Complaints to recheck");
    expect(markup).toContain(">3<");
    expect(markup).toContain("Critical");
    expect(markup).toContain("CMP000001, CMP000002 and 1 more");
    expect(markup).toContain("2026 FDA warning letters");
    expect(markup).toContain("uw-rd-tile tone-critical");
    expect(markup).toContain("Open");
  });

  it("a further check opens its list", () => {
    const markup = renderToStaticMarkup(
      <ul>
        <CheckRow
          check={check({
            code: "HARM_CLOSED_WITHOUT_CASE",
            title: "Harm complaints closed without an investigation",
            value: 0,
            state: "CLEAR",
            items: [],
          })}
          onOpen={vi.fn()}
        />
      </ul>,
    );
    expect(markup).toContain("Harm complaints closed without an investigation");
    expect(markup).toContain("0 · Clear");
    expect(markup).toContain("Why it matters:");
  });

  it("shows each check's basis as chips under why it matters", () => {
    for (const markup of [
      renderToStaticMarkup(<HomeTile check={check()} onOpen={vi.fn()} />),
      renderToStaticMarkup(
        <ul>
          <CheckRow check={check()} onOpen={vi.fn()} />
        </ul>,
      ),
    ]) {
      expect(markup).toContain('title="Complaint handling">ISO 13485 8.2.2<');
      expect(markup).toContain(">21 CFR 820.35<");
      expect(markup.indexOf("2026 FDA warning letters")).toBeLessThan(markup.indexOf("ISO 13485 8.2.2"));
    }
    expect(basisIds(check())).toEqual(["ISO13485_8_2_2", "CFR820_35"]);
    // A check without a basis shows none.
    expect(renderToStaticMarkup(<HomeTile check={check({ basis: [] })} onOpen={vi.fn()} />)).not.toContain("uw-basis");
  });
});

describe("Readiness in the workspace", () => {
  it("is the MVP's home; the full product keeps the dashboard", () => {
    expect(routeFor("Dashboard", undefined, "mvp")).toEqual({ section: "Readiness", tab: undefined });
    expect(routeFor("Dashboard", undefined, "full")).toEqual({ section: "Dashboard", tab: undefined });
    expect(PARKED_SECTIONS).toContain("Dashboard");
    expect(PARKED_SECTIONS).not.toContain("Readiness");
  });

  it("has its own address and menu entry", () => {
    expect(viewFromPath("/app/readiness")).toBe("readiness");
    expect(VIEW_TO_SECTION.readiness).toEqual(["Readiness"]);
    expect(addressFor({ section: "Readiness" })).toBe("/app/readiness");
    expect(locationFromAddress("/app/readiness", "?tab=x", VIEW_TO_SECTION, WORKSPACE_SECTIONS)).toEqual({
      section: "Readiness",
      tab: "x",
    });
    expect(sectionAllowed("Readiness", ["home"])).toBe(true);
    expect(WORKSPACE_SECTIONS.indexOf("Readiness")).toBeLessThan(WORKSPACE_SECTIONS.indexOf("Dashboard"));
  });
});
