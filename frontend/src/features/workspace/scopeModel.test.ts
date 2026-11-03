import { describe, expect, it } from "vitest";
import type { Product360 } from "../../app/types";
import {
  chooseComplaint,
  compareScopes,
  complaintChoice,
  diffLines,
  parseMarkets,
  scopeBody,
  scopeFormFrom,
  scopeOptions,
  scopePath,
  scopeProblems,
  setExclusionReason,
  visibleOptions,
  type ScopeVersion,
} from "./scopeModel";

const UUID = "0b6f8f9e-1111-4222-8333-444455556666";

const v1: ScopeVersion = {
  version: 1,
  question: "Why did occlusion alarms rise after release B?",
  product_versions: [{ id: "pv-b", business_id: "PV000002", version_identifier: "B" }],
  included_complaints: [
    { id: "c-1", business_id: "CMP000001", description: "Occlusion alarm" },
    { id: "c-2", business_id: "CMP000002", description: "Alarm at start" },
  ],
  excluded_complaints: [{ id: "c-3", business_id: "CMP000003", reason: "User error confirmed" }],
  lots: [{ id: "l-1", business_id: "LOT000001", lot_identifier: "KS-5521" }],
  markets: ["DE"],
  failure_modes: [{ id: "f-1", business_id: "FM000001", name: "Occlusion" }],
  date_from: "2026-01-01",
  date_to: "2026-06-30T00:00:00Z",
  objectives: "Find what changed in release B",
};

describe("the scope form", () => {
  it("starts from the current version (without its reason or flags)", () => {
    const form = scopeFormFrom(v1);
    expect(form).toMatchObject({
      question: v1.question,
      versionIds: ["pv-b"],
      included: ["c-1", "c-2"],
      excluded: [{ id: "c-3", reason: "User error confirmed" }],
      lotIds: ["l-1"],
      markets: ["DE"],
      failureModeIds: ["f-1"],
      dateFrom: "2026-01-01",
      dateTo: "2026-06-30",
      changeReason: "",
      reviewsMustRestart: false,
      conclusionsInvalidated: false,
    });
  });

  it("starts an empty scope with the case's question", () => {
    expect(scopeFormFrom(null, "Why do batteries drain?")).toMatchObject({
      question: "Why do batteries drain?",
      included: [],
      excluded: [],
    });
  });

  it("puts a complaint in, keeps it out (keeping its reason) or takes it off", () => {
    let form = scopeFormFrom(v1);
    expect(complaintChoice(form, "c-1")).toBe("included");
    expect(complaintChoice(form, "c-3")).toBe("excluded");
    expect(complaintChoice(form, "c-9")).toBe("none");
    form = chooseComplaint(form, "c-1", "excluded");
    expect(form.included).toEqual(["c-2"]);
    expect(form.excluded.map((row) => row.id)).toEqual(["c-3", "c-1"]);
    form = setExclusionReason(form, "c-1", "Different product line");
    form = chooseComplaint(form, "c-1", "excluded");
    expect(form.excluded.find((row) => row.id === "c-1")?.reason).toBe("Different product line");
    form = chooseComplaint(form, "c-3", "included");
    expect(form.included).toEqual(["c-2", "c-3"]);
    form = chooseComplaint(form, "c-2", "none");
    expect(complaintChoice(form, "c-2")).toBe("none");
  });

  it("reads markets as a list without repeats", () => {
    expect(parseMarkets(" DE, fr;US\nde,, ")).toEqual(["DE", "fr", "US"]);
    expect(parseMarkets("")).toEqual([]);
  });
});

describe("checking a scope before it is saved", () => {
  const valid = { ...scopeFormFrom(v1), changeReason: "Added lot KS-5522 after new complaints" };

  it("accepts a complete scope", () => {
    expect(scopeProblems(valid, true)).toEqual([]);
    expect(scopeProblems({ ...valid, changeReason: "" }, false)).toEqual([]);
  });

  it("needs a question, reasons for exclusions, a valid period and, after version 1, a change reason", () => {
    expect(scopeProblems({ ...valid, question: "Why?" }, true).join(" ")).toMatch(/question in at least 10/);
    expect(scopeProblems({ ...valid, excluded: [{ id: "c-3", reason: "no" }] }, true).join(" ")).toMatch(
      /reason of at least 5 characters \(1 missing\)/,
    );
    expect(scopeProblems({ ...valid, dateFrom: "2026-07-01", dateTo: "2026-01-01" }, true).join(" ")).toMatch(
      /start before it ends/,
    );
    expect(scopeProblems({ ...valid, changeReason: "short" }, true).join(" ")).toMatch(/Say why the scope changes/);
    expect(
      scopeProblems({ ...valid, included: ["c-3"], excluded: [{ id: "c-3", reason: "Duplicate" }] }, true),
    ).toContain("A complaint cannot be both in the scope and kept out of it.");
  });

  it("sends the scope with the change reason once a version exists", () => {
    const body = scopeBody(valid, true);
    expect(body).toEqual({
      question: v1.question,
      product_version_ids: ["pv-b"],
      included_complaint_ids: ["c-1", "c-2"],
      excluded_complaints: [{ complaint_id: "c-3", reason: "User error confirmed" }],
      lot_ids: ["l-1"],
      markets: ["DE"],
      failure_mode_ids: ["f-1"],
      date_from: "2026-01-01",
      date_to: "2026-06-30",
      objectives: "Find what changed in release B",
      change_reason: "Added lot KS-5522 after new complaints",
      reviews_must_restart: false,
      conclusions_invalidated: false,
    });
    const first = scopeBody({ ...scopeFormFrom(null, "Why do batteries drain overnight?") }, false);
    expect(first).not.toHaveProperty("change_reason");
    expect(first).not.toHaveProperty("date_from");
    expect(first).not.toHaveProperty("objectives");
    expect(scopePath(UUID)).toBe(`/api/v1/investigations/${UUID}/scope`);
    expect(scopePath(UUID, 2)).toBe(`/api/v1/investigations/${UUID}/scope/versions/2`);
  });
});

describe("picker options", () => {
  const view = {
    versions: [
      { id: "pv-a", business_id: "PV000001", version_identifier: "A" },
      { id: "pv-b", business_id: "PV000002", version_identifier: "B" },
    ],
    complaints: [
      { id: "c-2", business_id: "CMP000002", description: "Alarm at start", country: "FR" },
      { id: "c-4", business_id: null, complaint_identifier: "ACD-4", description: "Leak", country: "DE" },
    ],
    manufacturing: { lots: [{ id: "l-2", business_id: "LOT000002", lot_identifier: "KS-5522", site_name: "Plant 1" }] },
    failure_modes: [{ id: "f-2", business_id: "FM000002", failure_mode_identifier: "FM-2", name: "Leak" }],
  } as unknown as Product360;

  it("offers the product's records and keeps what the scope already holds, by business ID", () => {
    const options = scopeOptions(view, v1);
    expect(options.versions.map((option) => option.label)).toEqual(["A", "B"]);
    expect(options.complaints.map((option) => option.label)).toEqual(["CMP000001", "CMP000002", "CMP000003", "ACD-4"]);
    // The customer's own lot and complaint references lead (0.10.72): the MDARIX IDs only where none is held.
    expect(options.lots.map((option) => `${option.label}|${option.detail}`)).toEqual([
      "KS-5521|null",
      "KS-5522|Plant 1",
    ]);
    expect(options.failureModes.map((option) => option.label)).toEqual(["FM000001", "FM000002"]);
    expect(options.markets).toEqual(["DE", "FR"]);
    expect(JSON.stringify(options)).not.toContain(UUID);
  });

  it("works without a product context or a scope", () => {
    expect(scopeOptions(null, null)).toEqual({ versions: [], complaints: [], lots: [], failureModes: [], markets: [] });
  });

  it("shows matching options, at most a page, with the chosen ones kept", () => {
    const options = Array.from({ length: 80 }, (_, index) => ({
      id: `c-${index}`,
      label: `CMP${String(index).padStart(6, "0")}`,
      detail: index === 70 ? "Occlusion alarm" : "Battery",
    }));
    expect(visibleOptions(options, "", []).shown).toHaveLength(50);
    expect(visibleOptions(options, "occlusion", ["c-3"]).shown.map((option) => option.id)).toEqual(["c-3", "c-70"]);
    expect(visibleOptions(options, "occlusion", []).total).toBe(1);
  });
});

describe("what changed", () => {
  it("lists a save's diff by business ID", () => {
    expect(
      diffLines({
        question_changed: true,
        added_complaints: ["CMP000004", { id: UUID, business_id: "CMP000005" }],
        removed_complaints: [],
        newly_excluded: [{ id: UUID, complaint_identifier: "ACD-9" }],
        versions_added: [{ id: UUID, version_identifier: "C" }],
        versions_removed: null,
      }),
    ).toEqual([
      "The question changed.",
      "Complaints added: CMP000004, CMP000005",
      "Complaints newly kept out: ACD-9",
      "Versions added: C",
    ]);
    expect(diffLines(null)).toEqual([]);
    expect(diffLines({ added_complaints: [UUID] })).toEqual(["Complaints added: —"]);
  });

  it("compares two versions side by side", () => {
    const v2: ScopeVersion = {
      ...v1,
      version: 2,
      included_complaints: [
        { id: "c-1", business_id: "CMP000001" },
        { id: "c-4", business_id: "CMP000004" },
      ],
      lots: [],
      excluded_lots: [{ id: "l-1", business_id: "LOT000001", reason: "On quality hold in our warehouse" }],
      markets: ["DE", "FR"],
      date_to: null,
    };
    // Lots left out show only where a version has one (the lot impact list, a free trial).
    expect(compareScopes(v1, v1).map((item) => item.key)).not.toContain("lots_left_out");
    const rows = compareScopes(v1, v2);
    const row = (key: string) => rows.find((item) => item.key === key);
    expect(row("question")?.same).toBe(true);
    expect(row("included")).toMatchObject({ added: ["CMP000004"], removed: ["CMP000002"], same: false });
    expect(row("excluded")?.left).toEqual(["CMP000003 (User error confirmed)"]);
    expect(row("lots")).toMatchObject({ left: ["KS-5521"], right: [], removed: ["KS-5521"] });
    expect(row("lots_left_out")?.added).toEqual(["LOT000001 (On quality hold in our warehouse)"]);
    expect(row("markets")?.added).toEqual(["FR"]);
    expect(row("failure_modes")?.left).toEqual(["FM000001 Occlusion"]);
    expect(row("period")).toMatchObject({ left: ["2026-01-01 to 2026-06-30"], right: ["2026-01-01 to open"] });
    expect(rows.map((item) => item.label)).toEqual([
      "Question",
      "Product versions",
      "Complaints in scope",
      "Complaints kept out",
      "Lots",
      "Lots left out",
      "Markets",
      "Failure modes",
      "Period",
      "Objectives",
    ]);
  });
});
