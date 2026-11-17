// RCA tools screens and rules: the overview (every line names its record), the fishbone grid, the 5 Whys, the Pareto,
// the cause at signing and the switches.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { CaseIntelligencePanel } from "./sections/CaseIntelligence";
import {
  CauseFields,
  ConfirmedCausePareto,
  FishboneView,
  FiveWhysView,
  OverviewView,
} from "./sections/caseIntelligence/RootCause";
import {
  causeBody,
  causeProblem,
  overviewLines,
  paretoRows,
  quickAddProblem,
  rcaPath,
  whysBody,
  whysProblem,
  type Fishbone,
} from "./rca";
import { decisionDraftBody, decisionFormProblems, emptyDecisionForm } from "./humanDecision";
import { intelligencePath } from "./intelligence";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));

const api = (permissions: string[], rca = { methods: true, intelligence: true }) =>
  ({
    session: { allowed_menu: ["home"], business_permissions: permissions, rca },
    work: {},
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
  }) as unknown as WorkspaceApi;

const render = (value: WorkspaceApi, node: React.ReactNode) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

const cause = (id: string, extra: Record<string, unknown> = {}) => ({
  id,
  business_id: `HYP-${id}`,
  statement: `Possible cause ${id}`,
  ruled_out: false,
  evidence_for: 1,
  evidence_against: 0,
  human_status: "PROPOSED",
  human_status_label: "Proposed",
  ...extra,
});

const FISHBONE: Fishbone = {
  categories: [
    { code: "PEOPLE", label: "People", causes: [] },
    {
      code: "MATERIAL",
      label: "Material",
      causes: [
        cause("1", {
          failure_mode: {
            id: "fm",
            identifier: "FM-07",
            name: "Sensor reads high",
            risks: [{ id: "r", identifier: "RSK-01" }],
          },
          confirmed_in: { id: "d", decision_identifier: "INV-1-D1", signed_by_name: "Asha Rao" },
        }),
      ],
    },
    {
      code: "ENVIRONMENT",
      label: "Environment",
      causes: [cause("2", { ruled_out: true, ruled_out_reason: "EV-002 shows the settings were default" })],
    },
  ],
  uncategorised: [cause("3", { fmea_prompt: "Not in your FMEA: consider a risk-file update" })],
  failure_modes: [{ id: "fm", identifier: "FM-07", name: "Sensor reads high" }],
  actions: { can_add: true },
};

describe("rules", () => {
  it("every overview line names the record it comes from and the view that opens it", () => {
    const lines = overviewLines({
      observations: [
        {
          id: "o1",
          epistemic_type: "FACT",
          statement: "Lot 003 sensors read 5% high",
          evidence: { business_id: "EV-001", title: "Bench test" },
        },
        { id: "o2", epistemic_type: "AI_INTERPRETATION", statement: "Not shown" },
      ],
      hypotheses: [
        {
          id: "h1",
          business_id: "HYP-1",
          statement: "Supplier change",
          cause_category: "MATERIAL",
          evidence: { supporting: [{}, { retracted: true }], contradicting: [{}] },
        },
      ],
      contradictions: [{ id: "c1", evidence: { business_id: "EV-002" }, hypothesis: { business_id: "HYP-2" } }],
      unknowns: [
        { id: "u1", business_id: "UNK-1", description: "Bench test pending", status: "open" },
        { id: "u2", business_id: "UNK-2", description: "Resolved one", status: "resolved" },
      ],
      whys: [{ id: "w1", business_id: "FCH-1", nodes: [{ label: "Alarms" }, { label: "Reads high" }] }],
    });
    expect(lines.map((line) => line.tag)).toEqual([
      "Verified fact",
      "Hypothesis",
      "Contradiction",
      "Unknown",
      "5 Whys",
    ]);
    expect(lines.every((line) => line.record && line.view)).toBe(true);
    expect(lines[1].detail).toBe("Material · 1 for · 1 against");
    expect(lines[4].text).toBe("Alarms → Reads high");
  });

  it("checks a quick add and a 5 Whys before sending", () => {
    expect(quickAddProblem("short", "MATERIAL")).toMatch(/at least 10/);
    expect(quickAddProblem("The supplier change is the root cause", "MATERIAL")).toMatch(/not yet a finding/);
    expect(quickAddProblem("Sensor drift in lot 3", "")).toBe("Choose a category.");
    expect(quickAddProblem("Sensor drift in lot 3", "MATERIAL")).toBeNull();
    expect(whysProblem("Alarms", ["One"])).toMatch(/at least 2/);
    expect(whysProblem("Alarms", Array(8).fill("Because"))).toMatch(/at most 7/);
    expect(whysBody(" Alarms ", ["Reads high", " ", "Sensor drift"])).toEqual({
      problem: "Alarms",
      whys: [
        { text: "Reads high", state: "UNKNOWN" },
        { text: "Sensor drift", state: "UNKNOWN" },
      ],
    });
  });

  it("sizes the Pareto bars and marks where the cumulative share reaches 80%", () => {
    const rows = paretoRows({
      group_by: "category",
      total: 10,
      mark: 80,
      bars: [
        {
          label: "Material",
          count: 6,
          share: 60,
          cumulative_share: 60,
          confirmed: true,
          complaints: [],
          decisions: [],
        },
        { label: "People", count: 2, share: 20, cumulative_share: 80, confirmed: true, complaints: [], decisions: [] },
        {
          label: "No confirmed cause yet",
          count: 2,
          share: 20,
          cumulative_share: 100,
          confirmed: false,
          complaints: [],
          decisions: [],
        },
      ],
    });
    expect(rows.map((row) => row.width)).toEqual([100, 33, 33]);
    expect(rows.map((row) => row.reachesMark)).toEqual([false, true, false]);
  });

  it("the cause at signing: nothing pre-ticked, required on an accepted conclusion, sent only when chosen", () => {
    const form = emptyDecisionForm();
    expect(form.rootCauseHypotheses).toEqual([]);
    const accepting = { ...form, outcome: "ACCEPT_CONCLUSION" };
    expect(causeProblem(accepting, "ACCEPT_CONCLUSION", true)).toMatch(/choose the cause category/);
    expect(causeProblem(accepting, "ACCEPT_CONCLUSION", false)).toBeNull();
    expect(causeProblem({ ...accepting, rootCauseCategory: "NOT_DETERMINED" }, "ACCEPT_CONCLUSION", true)).toMatch(
      /at least 10/,
    );
    expect(
      decisionFormProblems(accepting, { acknowledgementRequired: false, supersedes: false, causes: true }).join(" "),
    ).toMatch(/cause category/);
    expect(causeBody(form)).toEqual({});
    const ticked = { ...form, rootCauseCategory: "MATERIAL", rootCauseHypotheses: ["h1"] };
    expect(causeBody(ticked)).toEqual({ root_cause_category: "MATERIAL", root_cause_hypothesis_ids: ["h1"] });
    expect(decisionDraftBody(ticked, { briefVersionId: "b", briefContentHash: "x" })).toMatchObject({
      root_cause_category: "MATERIAL",
      root_cause_hypothesis_ids: ["h1"],
    });
    expect(decisionDraftBody(form, { briefVersionId: "b", briefContentHash: "x" })).not.toHaveProperty(
      "root_cause_category",
    );
  });
});

describe("screens", () => {
  it("the fishbone shows each column, ruled-out causes with their reason, the FMEA link and the signed cause", () => {
    resources.data[rcaPath("inv-1", "fishbone")] = FISHBONE;
    const html = render(api(["investigation.work"]), <FishboneView investigationId="inv-1" caseLabel="INV-1" />);
    expect(html).toContain("People");
    expect(html).toContain("is-ruled-out");
    expect(html).toContain("Reason: EV-002 shows the settings were default");
    expect(html).toContain("FM-07");
    expect(html).toContain("can lead to RSK-01");
    expect(html).toContain("Named as root cause in decision INV-1-D1");
    expect(html).toContain("Not in your FMEA");
    expect(html).toContain("Add a possible cause");
    const viewer = render(api(["records.read"]), <FishboneView investigationId="inv-1" caseLabel="INV-1" />);
    expect(viewer).not.toContain("Add a possible cause");
  });

  it("the 5 Whys reads top down with unknown whys prompting a question", () => {
    resources.data[rcaPath("inv-1", "five-whys")] = {
      items: [
        {
          id: "w1",
          business_id: "FCH-9",
          name: "5 Whys: alarms",
          nodes: [
            { id: "n1", kind: "PROBLEM", label: "Pressure alarms" },
            { id: "n2", kind: "WHY", label: "Pump reads high" },
            { id: "n3", kind: "WHY", label: "Inspection cut", is_last: true, hypothesis: { business_id: "HYP-4" } },
          ],
          links: [
            { id: "l1", state: "SUPPORTED", state_label: "Supported", evidence: { business_id: "EV-001" } },
            {
              id: "l2",
              state: "UNKNOWN",
              state_label: "Unknown",
              evidence: null,
              unknown_prompt: "Unknown: what would show it?",
            },
          ],
        },
      ],
      actions: { can_add: true },
    };
    const html = render(
      api(["investigation.work"]),
      <FiveWhysView investigationId="inv-1" caseLabel="INV-1" onView={() => undefined} />,
    );
    expect(html).toContain("Problem");
    expect(html).toContain("Why 2");
    expect(html).toContain("Unknown: what would show it?");
    expect(html).toContain("This why is hypothesis HYP-4");
    expect(html).toContain("Open a question");
    expect(html).toContain("The last why is not a root cause");
  });

  it("the overview lists lines that each open their record, and the version at the event date", () => {
    resources.data[intelligencePath("inv-1", "hypotheses")] = {
      items: [{ id: "h1", business_id: "HYP-1", statement: "Supplier change", evidence: {} }],
    };
    resources.data[rcaPath("inv-1", "event-versions")] = {
      items: [
        {
          complaint: { id: "c1", business_id: "CMP-1" },
          anchor_label: "Event date",
          anchor_date: "2026-10-01T00:00:00Z",
          version: null,
          version_label: "Version unknown",
          candidate_versions: [{ version_identifier: "Rev A" }],
          components: [],
          flags: [],
        },
        {
          complaint: { id: "c2", business_id: "CMP-2" },
          anchor_label: "Event date",
          version: { version_identifier: "Rev C" },
          version_label: "Named on the complaint",
          candidate_versions: [],
          components: [],
          flags: [{ code: "RELEASED_AFTER_EVENT", label: "Version released after the event: check" }],
        },
      ],
    };
    const html = render(
      api(["records.read"]),
      <OverviewView investigationId="inv-1" caseLabel="INV-1" onView={() => undefined} methods />,
    );
    expect(html).toContain("HYP-1");
    // G-12: the right plural, and no zero counts.
    expect(html).toContain("<strong>1</strong> hypothesis</li>");
    expect(html).not.toContain("hypothesiss");
    expect(html).not.toContain("verified facts");
    // W1: never filled in; the candidates are listed.
    expect(html).toContain("Version not known (unverified)");
    expect(html).toContain("Candidates released by then: Rev A");
    expect(html).toContain("Version released after the event: check");
  });

  it("the Pareto shows counts, never a rate", () => {
    resources.data["/api/v1/rca/pareto"] = {
      group_by: "category",
      total: 3,
      mark: 80,
      note: "Counts of complaints, each once under its current confirmed cause. Not a rate.",
      bars: [
        {
          label: "Material",
          count: 2,
          share: 66.7,
          cumulative_share: 66.7,
          confirmed: true,
          complaints: [],
          decisions: [],
        },
        {
          label: "No confirmed cause yet",
          count: 1,
          share: 33.3,
          cumulative_share: 100,
          confirmed: false,
          complaints: [],
          decisions: [],
        },
      ],
    };
    const html = render(api(["records.read"]), <ConfirmedCausePareto />);
    expect(html).toContain("Pareto of confirmed causes");
    expect(html).toContain("No confirmed cause yet");
    expect(html).toContain("Not a rate");
  });

  it("signing offers the case's hypotheses unticked", () => {
    resources.data[intelligencePath("inv-1", "hypotheses")] = {
      items: [
        { id: "h1", business_id: "HYP-1", statement: "Supplier change", human_status_label: "Strongly supported" },
      ],
    };
    const html = render(
      api(["decision.sign"]),
      <CauseFields
        investigationId="inv-1"
        form={emptyDecisionForm()}
        outcome="ACCEPT_CONCLUSION"
        set={() => undefined}
      />,
    );
    expect(html).toContain("HYP-1");
    expect(html).not.toContain("checked");
    expect(html).toContain("Not determined");
  });

  it("the switches hide the RCA views", () => {
    const panel = (rca: { methods: boolean; intelligence: boolean }) =>
      render(
        api(["records.read"], rca),
        <CaseIntelligencePanel investigationId="inv-1" caseLabel="INV-1" view="Hypotheses" onView={() => undefined} />,
      );
    const on = panel({ methods: true, intelligence: true });
    expect(on).toContain("Fishbone");
    expect(on).toContain("5 Whys");
    expect(on).toContain("Overview");
    const off = panel({ methods: false, intelligence: false });
    expect(off).not.toContain("Fishbone");
    expect(off).not.toContain("5 Whys");
    expect(off).not.toContain(">Overview<");
  });
});
