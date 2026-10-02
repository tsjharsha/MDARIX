import { describe, expect, it } from "vitest";
import {
  defaultTimeContext,
  preferredInvestigationId,
  countBy,
  investigationStatusSlices,
  isHighSeverity,
  isOpenInvestigation,
  isVerified,
  workspaceAttention,
} from "./workspaceModel";
import { sectionAllowed } from "./workspaceContext";

describe("user workspace model", () => {
  it("counts records by a field with a readable label for missing values", () => {
    expect(countBy([{ t: "LAB" }, { t: "LAB" }, { t: null }], "t").map((slice) => [slice.label, slice.count])).toEqual([
      ["Lab", 2],
      ["Not recorded", 1],
    ]);
  });

  it("treats closed-like statuses as not open", () => {
    expect(isOpenInvestigation("open")).toBe(true);
    expect(isOpenInvestigation("RESOLVED")).toBe(false);
    expect(investigationStatusSlices([{ status: "open" }, { status: "closed" }]).map((slice) => slice.tone)).toEqual([
      "good",
      "warning",
    ]);
  });

  it("recognises verified evidence and high-severity signals", () => {
    expect(isVerified("verified")).toBe(true);
    expect(isVerified("Reviewed")).toBe(true);
    expect(isVerified("UNVERIFIED")).toBe(false);
    expect(isHighSeverity("Critical")).toBe(true);
    expect(isHighSeverity(null)).toBe(false);
  });

  it("lists attention items most severe first and stays empty when nothing needs action", () => {
    const items = workspaceAttention({
      openInvestigations: 2,
      unreliableEvidence: 0,
      limitations: [{ code: "LATE", severity: "HIGH" }],
      highSeveritySignals: 1,
    });
    expect(items.map((item) => item.section)).toEqual(["Signals", "Trust & Audit", "Investigations"]);
    expect(
      workspaceAttention({ openInvestigations: 0, unreliableEvidence: 0, limitations: [], highSeveritySignals: 0 }),
    ).toEqual([]);
  });

  it("fails closed when the server gives no menu, but always allows My Account", () => {
    expect(sectionAllowed("Products", undefined)).toBe(false);
    expect(sectionAllowed("My Account", undefined)).toBe(true);
    expect(sectionAllowed("Products", ["products"])).toBe(true);
    expect(sectionAllowed("Decisions", ["products"])).toBe(false);
  });
});

describe("defaultTimeContext", () => {
  it("opens on the current state with today's date, not a fixed historical date", () => {
    expect(defaultTimeContext(new Date("2026-10-02T09:30:00Z"))).toEqual({ asOf: "2026-10-02", mode: "current" });
  });
});

describe("preferredInvestigationId", () => {
  const cases = [
    { id: "closed-1", status: "closed" },
    { id: "open-1", status: "open" },
  ];
  it("opens the first open case", () => {
    expect(preferredInvestigationId(cases, "")).toBe("open-1");
  });
  it("keeps a selection that is still listed, even a closed one", () => {
    expect(preferredInvestigationId(cases, "closed-1")).toBe("closed-1");
  });
  it("falls back to the first case, or nothing", () => {
    expect(preferredInvestigationId([{ id: "c", status: "closed" }], "gone")).toBe("c");
    expect(preferredInvestigationId([], "")).toBe("");
  });
});
