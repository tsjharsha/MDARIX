import { describe, expect, it } from "vitest";
import {
  dashboardStatus,
  defaultTimeContext,
  localDay,
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

  it("shows Import data only to roles the server lets change records", () => {
    expect(sectionAllowed("Import data", ["products"], ["records.write"])).toBe(true);
    expect(sectionAllowed("Import data", ["products"], ["ai.run"])).toBe(false);
    expect(sectionAllowed("Import data", ["products"], undefined)).toBe(false);
    expect(sectionAllowed("Share feedback", undefined)).toBe(true);
  });
});

describe("dashboard headline", () => {
  const ready = ["ready", "ready", "ready", "ready"] as const;
  const counts = { products: 2, complaints: 10, investigations: 1, evidence: 4 };
  it("says nothing needs attention only after the data was read and the organization has records", () => {
    expect(dashboardStatus({ states: [...ready], counts, attention: 0 })).toBe("clear");
    expect(dashboardStatus({ states: [...ready], counts, attention: 2 })).toBe("attention");
  });
  it("reports a failed source as an error, not as all clear", () => {
    expect(dashboardStatus({ states: ["ready", "error", "ready", "ready"], counts, attention: 0 })).toBe("error");
    expect(dashboardStatus({ states: ["loading", "error"], counts: null, attention: 0 })).toBe("loading");
  });
  it("recognises an organization with no records yet", () => {
    expect(
      dashboardStatus({
        states: [...ready],
        counts: { products: 0, complaints: 0, investigations: 0, evidence: 0 },
        attention: 0,
      }),
    ).toBe("empty");
  });
  it("does not count a source the role may not read as a failure", () => {
    expect(dashboardStatus({ states: ["ready", "forbidden", "ready", "ready"], counts, attention: 0 })).toBe("clear");
  });
});

describe("localDay", () => {
  it("uses the person's calendar day, not the UTC one", () => {
    // 23:30 local time on 4 October is 5 October in UTC for anyone west of Greenwich.
    expect(localDay(new Date(2026, 9, 4, 23, 30))).toBe("2026-10-04");
    expect(localDay(new Date(2026, 0, 1, 0, 5))).toBe("2026-01-01");
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
