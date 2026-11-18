import { describe, expect, it } from "vitest";
import { alsoIndia } from "./sections/MarketAssessment";

// Quality plan stage 8 (8.7): every step ends with the next step as its main button.

const sources = import.meta.glob(["./sections/*.tsx"], { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;
const source = (name: string) => sources[`./sections/${name}.tsx`] ?? "";

describe("the next step, always", () => {
  it("ends each step done on another screen with the complaint's next action", () => {
    for (const screen of ["MarketAssessment", "Reports", "Dispositions", "CaseSections"])
      expect(source(screen), screen).toContain("<ComplaintNextStep");
    // A triaged complaint opens its page, whose main button is its next action.
    expect(source("Triage")).toContain('open("Complaint", `Summary?ref=${encodeURIComponent(item.ref)}`)');
    // The investigation cockpit's strip names its next step (UX3).
    expect(source("Cockpit")).toContain("Next: {next.label}");
  });

  it("asks for India next in the flagship story once the US is signed", () => {
    const us = { market: "US" as const, current: { version: 1 } as never };
    const india = { market: "IN" as const, current: null };
    expect(alsoIndia("reportable", [us, india], us)).toBe(true);
    expect(alsoIndia("reportable", [us, { ...india, current: { version: 1 } as never }], us)).toBe(false);
    expect(alsoIndia(null, [us, india], us)).toBe(false);
    expect(alsoIndia("reportable", [{ ...us, current: null }, india], { ...us, current: null })).toBe(false);
  });
});
