import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { DidItWorkView } from "./sections/DidItWork";
import {
  actionsFor,
  countsLine,
  denominatorLine,
  didItWorkPath,
  resultTone,
  type DidItWork,
  type LoopGroup,
} from "./didItWork";

// B5b step 12: Did it work? (backend/app/closed_loop/service.py). Words, never verdicts; the denominator or "units
// unknown"; version-unknown complaints apart; per-lot rows only when the server sends them (a trial, B5-D9); hidden
// while the session says closed_loop is off.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));

const api = (closedLoop = true) =>
  ({
    session: { allowed_menu: ["home"], business_permissions: ["records.read"], closed_loop: closedLoop },
    work: {},
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
  }) as unknown as WorkspaceApi;

const render = (value: WorkspaceApi, node: React.ReactNode) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

const group = (changes: Partial<LoopGroup>): LoopGroup => ({
  name: "Rev B",
  before: 12,
  after: 0,
  basis: "RELEASED",
  counts_only: false,
  result: "TOO_EARLY",
  word: "Too early",
  rate_before: 4.1,
  rate_after: 0,
  upper_bound_after: 9.2,
  before_complaints: [{ id: "c1", ref: "SAMPLE-CMP-0003" }],
  after_complaints: [],
  ...changes,
});

const LIMITS = ["Reporting lag: recent events may not be reported yet."];
const VIEW: DidItWork = {
  rule_version: 1,
  notice:
    "Counts from your records; not a verdict. Only your signed effectiveness check says whether an action worked.",
  limits: LIMITS,
  superseded: [],
  decision: { id: "d1", ref: "DEC000001", decided_at: "2026-11-01T10:00:00Z", outcome: "ACCEPT_CONCLUSION" },
  scope: { versions: [{ id: "v1", ref: "Rev B" }], new_versions: [], problems: ["PRESSURE_ALARM"], complaints: 14 },
  later: {
    count: 0,
    complaints: [],
    version_unknown: { count: 1, complaints: [{ id: "c9", ref: "LOOP-NOVERSION-1" }] },
  },
  capas: [{ id: "p1", ref: "SAMPLE-CAPA-02", title: "Restore incoming inspection", status: "open", checks: [] }],
  field_actions: [],
  actions: [
    {
      kind: "CAPA",
      on: "2026-11-01",
      ref: "SAMPLE-CAPA-02",
      measured_from: "decision",
      window: { before: ["2026-10-22", "2026-10-31"], after: ["2026-11-01", "2026-11-10"], after_days: 10, days: 10 },
      by_version: [group({})],
      lot_cohorts: group({
        name: "Lots released after the action vs before",
        basis: "UNKNOWN",
        counts_only: true,
        result: "COUNTS_ONLY",
        word: "Counts only (units unknown)",
        lot_unknown: 2,
      }),
      lots: [
        { id: "l1", ref: "LOT-003", version: "Rev B", released: "2026-06-01", cohort: "before", after: 0, units: null },
      ],
    },
  ],
};
resources.data[didItWorkPath("inv-1")] = VIEW;
resources.data[didItWorkPath("inv-none")] = { ...VIEW, decision: null };

describe("Did it work? view", () => {
  it("shows words, not verdicts, with the denominator or units unknown, and version-unknown complaints apart", () => {
    const html = render(api(), <DidItWorkView investigationId="inv-1" caseLabel="SAMPLE-INV-001" />);
    expect(html).toContain("Did it work?");
    expect(html).toContain("Too early");
    expect(html).toContain("Counts only (units unknown)");
    expect(html).toContain("Units released, with release dates");
    expect(html).toContain("Units unknown");
    expect(html).toContain("not a verdict");
    expect(html).toContain("measured from the decision");
    expect(html).toContain("1 more have no version and are counted in no version");
    expect(html).toContain("2 complaints after the action have no lot");
    expect(html).toContain("Each lot (1)");
    expect(html).toContain("Reporting lag");
    expect(html).not.toMatch(/\beffective\b(?! check)|eliminated|proven|confirmed|root cause/i);
  });

  it("has no per-lot rows when the server sends none (a paid pilot, B5-D9)", () => {
    resources.data[didItWorkPath("inv-pilot")] = {
      ...VIEW,
      actions: VIEW.actions!.map((action) => ({ ...action, lots: undefined })),
    };
    const html = render(api(), <DidItWorkView investigationId="inv-pilot" caseLabel="INV-2" />);
    expect(html).not.toContain("Each lot");
    expect(html).toContain("Rev B");
  });

  it("says nothing is signed yet before the decision", () => {
    const html = render(api(), <DidItWorkView investigationId="inv-none" caseLabel="INV-3" />);
    expect(html).toContain("Nothing signed yet");
  });

  it("is hidden while the switch is off", () => {
    expect(render(api(false), <DidItWorkView investigationId="inv-1" caseLabel="INV-1" />)).toBe("");
  });

  it("on an effectiveness check shows that CAPA only and not the later list", () => {
    const html = render(api(), <DidItWorkView investigationId="inv-1" caseLabel="INV-1" capaRef="OTHER-CAPA" />);
    expect(html).toContain("No action date yet");
    expect(html).not.toContain("later complaints with the same problem");
  });
});

describe("Did it work? rules on the screen", () => {
  it("never shows a rate from unknown units, and bounds a zero", () => {
    expect(countsLine(group({}))).toContain("could still be up to 9.2");
    const calendar = group({ counts_only: true, per_30_days_before: 1.2, per_30_days_after: 0.4, basis: "UNKNOWN" });
    expect(countsLine(calendar)).toBe("12 before · 0 after, by calendar days (1.2 vs 0.4 per 30 days)");
    expect(denominatorLine({ ...calendar, lots_with_units_unknown: 1, lots_in_group: 4 })).toBe(
      "Units unknown for 1 of 4 lots",
    );
    expect(denominatorLine(group({ basis: "SHIPPED" }))).toBe("Units shipped, with ship dates");
  });

  it("marks only More for a look; Fewer is not shown as good", () => {
    expect(resultTone("MORE")).toBe("warning");
    expect(resultTone("FEWER")).toBe("neutral");
  });

  it("filters the actions to one CAPA", () => {
    expect(actionsFor(VIEW, "SAMPLE-CAPA-02")).toHaveLength(1);
    expect(actionsFor(VIEW, "OTHER")).toHaveLength(0);
    expect(actionsFor(VIEW, null)).toHaveLength(1);
  });
});
