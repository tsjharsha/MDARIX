// UX3: the investigation cockpit (W1b's six questions became its six steps; the advanced tools named folds). W1c: the Investigation
// Brief as one page, every part present or "Not recorded", never guessed.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ADVANCED_VIEWS, CaseSections } from "./sections/CaseSections";
import { InvestigationBriefPage } from "./sections/InvestigationBriefPage";
import { CASE_SECTIONS, STEP_PLACE, cockpitStep } from "./caseWorkflow";
import { VERSION_NOT_KNOWN, briefPage } from "./investigationBrief";
import type { DecisionSummary } from "./decisionSummary";
import type { LotImpactView } from "./lotImpact";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));
// The panels are stand-ins: what is under test is their order and what is folded.
const { part } = vi.hoisted(() => ({ part: (name: string) => () => <div data-part={name} /> }));
vi.mock("./sections/CaseHeader", () => ({ CaseHeader: () => <header />, ownerText: () => "" }));
vi.mock("./sections/CaseScope", () => ({ CaseScopePanel: part("scope") }));
vi.mock("./sections/CaseEvidence", () => ({ CaseEvidencePanel: part("evidence-table") }));
vi.mock("./sections/caseIntelligence/RootCause", () => ({
  OverviewView: part("glance"),
  FishboneView: part("fishbone"),
  FiveWhysView: part("five-whys"),
}));
vi.mock("./sections/caseIntelligence/FailureChain", () => ({ FailureChainView: part("failure-chain") }));
vi.mock("./sections/caseIntelligence/Observations", () => ({ ObservationsView: part("observations") }));
vi.mock("./sections/caseIntelligence/Challenge", () => ({ ChallengeView: part("challenge") }));
vi.mock("./sections/caseIntelligence/History", () => ({ HistoryView: part("judgements") }));
vi.mock("./sections/VersionCompare", () => ({ VersionCompareCard: part("version-compare") }));
vi.mock("./sections/caseIntelligence/Hypotheses", () => ({ HypothesesView: part("hypotheses") }));
vi.mock("./sections/caseIntelligence/Unknowns", () => ({ UnknownsView: part("unknowns") }));
vi.mock("./sections/caseIntelligence/Contradictions", () => ({ ContradictionsView: part("contradictions") }));
vi.mock("../investigator/InvestigationWorkspacePanel", () => ({ InvestigationWorkspacePanel: part("workspace") }));
vi.mock("../ask/AskMdarixPage", () => ({ AskMdarixPage: part("ask") }));
vi.mock("./sections/CaseReviews", () => ({ CaseReviewsPanel: part("reviews") }));
vi.mock("./sections/CaseDecisionBrief", () => ({ CaseDecisionBriefPanel: part("brief") }));
vi.mock("./sections/CaseDecision", () => ({ CaseDecisionPanel: part("decision") }));
vi.mock("./sections/DecisionSummary", () => ({ DecisionSummaryView: part("summary") }));
vi.mock("./sections/DidItWork", () => ({ DidItWorkView: part("did-it-work") }));
vi.mock("./sections/CaseAudit", () => ({ CaseTimeline: part("timeline"), CaseIntegrity: part("integrity") }));

const api = (rca = true) =>
  ({
    session: { allowed_menu: ["home"], business_permissions: [], rca: { intelligence: rca, methods: rca } },
    work: { investigationId: "i1", investigations: [{ id: "i1" }], products: [] },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: false,
  }) as unknown as WorkspaceApi;
const render = (tab: string, rca = true) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider value={api(rca)}>
      <CaseSections tab={tab} onChanged={() => undefined} />
    </WorkspaceContext.Provider>,
  );
const order = (html: string, marks: string[]) => marks.map((mark) => html.indexOf(mark));
const ascending = (values: number[]) =>
  values.every((value, index) => value >= 0 && (!index || value > values[index - 1]));

describe("UX3: the investigation cockpit, one 6-step rail (W1b's six questions folded into it)", () => {
  it("names six steps in order, and each recorded step lands on its own", () => {
    expect([...CASE_SECTIONS]).toEqual([
      "Signal",
      "Product reality",
      "Evidence",
      "Possible causes",
      "Brief",
      "Decision & action",
    ]);
    expect(STEP_PLACE.hypotheses).toEqual({ section: "Possible causes", part: "causes" });
    expect(STEP_PLACE.gaps).toEqual({ section: "Evidence", part: "unknowns" });
    expect(STEP_PLACE.brief).toEqual({ section: "Brief", part: "brief" });
    expect(STEP_PLACE.human_review).toEqual({ section: "Decision & action", part: "decision" });
  });

  it("has no six-question guide and no tab list on any step", () => {
    for (const step of CASE_SECTIONS) {
      const html = render(step);
      expect(html).not.toContain("six questions");
      expect(html).not.toContain('role="tablist"');
      expect(html).toContain(`aria-label="Investigation step: ${step.replace("&", "&amp;")}"`);
    }
  });

  it("Signal answers What happened? with the complaints in scope", () => {
    const body = render("Signal").slice(render("Signal").indexOf("uw-case-body"));
    expect(body.indexOf("What happened?")).toBeLessThan(body.indexOf('data-part="scope"'));
  });

  it("Evidence: what is known and what not, the records, then the unknowns and contradictions; no causes", () => {
    const html = render("Evidence").slice(render("Evidence").indexOf("uw-case-body"));
    expect(
      ascending(
        order(html, [
          "What do we know, and what not?",
          'data-part="glance"',
          'data-part="evidence-table"',
          'data-part="unknowns"',
          'data-part="contradictions"',
        ]),
      ),
    ).toBe(true);
    expect(html).not.toContain('data-part="hypotheses"');
  });

  it("Possible causes: the hypotheses, then each cause tool as a named fold, closed and not read until opened", () => {
    const html = render("Possible causes");
    expect(ascending(order(html, ["What could have caused it?", 'data-part="hypotheses"', "Fishbone: causes"]))).toBe(
      true,
    );
    expect(ADVANCED_VIEWS).toEqual(["Fishbone", "5 Whys", "Failure chain", "Observations", "Challenge", "History"]);
    for (const label of ["5 Whys", "Failure chains: how a cause leads", "Observations", "Judgement history"])
      expect(html).toContain(label);
    expect(html).toContain("The AI analysis workspace");
    // Closed folds draw nothing (no read on the server, nothing hidden in the accessibility tree).
    expect(html).not.toContain('data-part="fishbone"');
    expect(html).not.toContain('data-part="workspace"');
  });

  it("a former link to a cause tool opens Possible causes with that tool open; a main view opens its step", () => {
    const html = render("Evidence?view=Failure chain&part=intelligence");
    expect(html).toContain('aria-label="Investigation step: Possible causes"');
    expect(html).toContain('data-part="failure-chain"');
    expect(html).not.toContain('data-part="fishbone"');
    expect(render("Evidence?view=Unknowns&part=intelligence")).toContain('aria-label="Investigation step: Evidence"');
  });

  it("opens the evidence records when the read-only overview is switched off", () => {
    expect(render("Evidence", false)).toMatch(/<details class="uw-more" id="case-part-evidence" open="">/);
    expect(render("Evidence")).toMatch(/<details class="uw-more" id="case-part-evidence">/);
  });

  it("Brief: what the decision rests on, the reviews, then the brief", () => {
    const html = render("Brief");
    expect(
      ascending(
        order(html.slice(html.indexOf("uw-case-body")), [
          "What should we decide?",
          "What the decision rests on",
          'data-part="reviews"',
          'data-part="brief"',
        ]),
      ),
    ).toBe(true);
  });

  it("Decision & action: the signed summary, the decision, did it work, then the record folded", () => {
    const html = render("Decision & action");
    expect(
      ascending(
        order(html.slice(html.indexOf("uw-case-body")), [
          "What was decided, and did it work?",
          'data-part="summary"',
          'data-part="decision"',
          'data-part="did-it-work"',
          "The record: download, history and trust details",
        ]),
      ),
    ).toBe(true);
    expect(html).not.toContain('data-part="timeline"');
  });

  it("every former section address still opens its step (e-mails, bookmarks, the link table)", () => {
    expect(render("Summary")).toContain('aria-label="Investigation step: Signal"');
    expect(render("Summary?part=lot-impact")).toContain('aria-label="Investigation step: Product reality"');
    expect(render("Decisions & actions?part=brief")).toContain('aria-label="Investigation step: Brief"');
    expect(render("Decisions & actions?part=decision")).toContain(
      'aria-label="Investigation step: Decision &amp; action"',
    );
    const history = render("History");
    expect(history).toContain('aria-label="Investigation step: Decision &amp; action"');
    expect(history).toContain('data-part="timeline"');
    expect(history).toMatch(/<details class="uw-more uw-case-part" id="case-part-trust">/);
    expect(render("History?part=trust")).toMatch(/<details class="uw-more uw-case-part" id="case-part-trust" open="">/);
  });
});

describe("UX3: where an address opens in the cockpit", () => {
  it("reads a part first, then the step or the former section", () => {
    expect(cockpitStep("Evidence", "causes")).toEqual({ section: "Possible causes", part: "causes" });
    expect(cockpitStep("Evidence", "ai-proposals")).toEqual({ section: "Possible causes", part: "ai-proposals" });
    expect(cockpitStep("Evidence", "intelligence", "Overview")).toEqual({ section: "Evidence", part: "glance" });
    expect(cockpitStep("Evidence", "intelligence", "Contradictions")).toEqual({
      section: "Evidence",
      part: "unknowns",
    });
    expect(cockpitStep("Evidence", "intelligence", "5 Whys")).toEqual({ section: "Possible causes", part: "advanced" });
    expect(cockpitStep("Decisions & actions", "reviews")).toEqual({ section: "Brief", part: "reviews" });
    expect(cockpitStep("Decisions & actions", "did-it-work")).toEqual({
      section: "Decision & action",
      part: "did-it-work",
    });
    expect(cockpitStep("History", null)).toEqual({ section: "Decision & action", part: "history" });
    expect(cockpitStep("Brief", null)).toEqual({ section: "Brief", part: null });
    expect(cockpitStep("All investigations", null)).toBeNull();
  });
});

const TITLES = [
  "Problem statement",
  "Product and exact version",
  "Affected components, supplier and lots",
  "Evidence for",
  "Evidence against",
  "Competing hypotheses and their status",
  "Unknowns and limitations",
  "Risk implications",
  "Recommended action",
  "Decision and approval",
  "AI used, as locked at signing",
  "Effectiveness criteria for the follow-up",
];

const VERSION = {
  id: "b1",
  business_id: "BRF-001",
  version: 2,
  status_label: "Accepted for decision",
  reviewed_by_name: "Asha Rao",
  reviewed_at: "2026-11-10T09:00:00Z",
  narrative: {
    problem_statement: "Pressure-alarm complaints rose 9.3× after OrbitCare 300 Rev B.",
    proposed_conclusion: "The NovaSense sensors are the most likely cause.",
    recommended_actions: ["Contain lots 003 and 004", "Restore 32-unit inspection"],
  },
  content: {
    investigation: { question: "Why did alarms rise after Rev B?" },
    product: { name: "OrbitCare 300", versions: [] },
    scope: {
      product_versions: [{ version_identifier: "Rev B" }],
      unknown_version_count: 1,
      lots: [
        { lot_number: "LOT-003", version_identifier: "Rev B" },
        { lot_number: "LOT-004", version_identifier: null },
      ],
    },
    leading_hypothesis: {
      business_id: "HYP-1",
      statement: "Sensor drift",
      human_status_label: "Strongly supported",
      origin: "HUMAN",
      supporting_count: 3,
      contradicting_count: 0,
    },
    alternative_hypotheses: [
      { business_id: "HYP-2", statement: "Software", origin: "AI", kind_label: "AI proposal, not reviewed" },
    ],
    supporting_evidence: [{ source: "CASE", evidence_business_id: "EV-003", title: "Trend 9.3×" }],
    contradicting_evidence: [{ source: "CASE", evidence_business_id: "EV-009", title: "Bench test passed" }],
    unknowns: {
      open: [{ business_id: "UNK-1", description: "Sensor lot of unit 7", evidence_needed: "teardown" }],
      accepted_limitations: [],
    },
    risk_review: {
      state: "COMPLETED",
      review: { business_id: "RR-1", outcome: "Risk acceptable", reviewer_name: "Ravi" },
    },
  },
};
const SIGNED = {
  investigation: { id: "i1", ref: "SAMPLE-INV-001", question: "q" },
  decision: { outcome_label: "Accept the conclusion", conclusion: "Sensors. Contain." },
  signature: { name: "Meera", role_label: "Quality head", signed_at: "2026-11-12T10:00:00Z", mfa_verified: true },
  affects: { risks: [{ ref: "SAMPLE-RSK-01", description: "Over-infusion", status: "OPEN" }] },
  capas: [
    {
      id: "c1",
      ref: "SAMPLE-CAPA-02",
      title: "t",
      status: "OPEN",
      due_at: null,
      check: {
        round: 1,
        status: "PLANNED",
        planned_on: "2027-02-10",
        signed_at: null,
        result_summary: null,
        criteria: "No alarm from new lots",
      },
    },
  ],
  worked: { state: "TOO_EARLY", text: "Too early.", on: "2027-02-10" },
} as unknown as DecisionSummary;
const LOTS = {
  saved: { factor: { kind: "COMPONENT_LOT", id: "x", lot: "NS-SL-2531" } },
  options: [
    {
      kind: "COMPONENT_LOT",
      id: "x",
      lot: "NS-SL-2531",
      kind_label: "Component lot",
      label: "NovaSense sensor NS-SL-2531",
      lots: 2,
      case_lots: 2,
    },
    { kind: "SUPPLIER", id: "s", lot: null, kind_label: "Supplier", label: "NovaSense", lots: 5, case_lots: 2 },
    { kind: "SUPPLIER", id: "o", lot: null, kind_label: "Supplier", label: "Other", lots: 5, case_lots: 0 },
    { kind: "PRODUCT_VERSION", id: "v", lot: null, kind_label: "Version", label: "Rev B", lots: 2, case_lots: 2 },
  ],
} as unknown as LotImpactView;

describe("W1c: the Investigation Brief on one page", () => {
  it("has every part, in order, and each says Not recorded when nothing is recorded", () => {
    const parts = briefPage({ id: "b", version: 1 }, null, null);
    expect(parts.map((item) => item.title)).toEqual(TITLES);
    // A brief with nothing recorded: only the decision says it is not signed; every other part is empty.
    expect(parts.filter((item) => item.key !== "decision").every((item) => item.lines.length === 0)).toBe(true);
    expect(parts.find((item) => item.key === "decision")?.lines[0]).toBe("No decision signed yet");
    const html = renderToStaticMarkup(
      <WorkspaceContext.Provider value={api()}>
        <InvestigationBriefPage investigationId="i1" caseLabel="INV-1" version={{ id: "b", version: 1 }} />
      </WorkspaceContext.Provider>,
    );
    for (const title of TITLES) expect(html).toContain(`aria-label="${title}"`);
    expect(html.split(`<p class="ac-muted">Not recorded</p>`).length - 1).toBe(11);
    expect(html).toContain("Print or save as PDF");
  });

  it("never guesses a version", () => {
    const parts = briefPage({ id: "b", version: 1, content: { product: { name: "OrbitCare 300" } } }, null, null);
    expect(parts[1].lines).toEqual([`OrbitCare 300: ${VERSION_NOT_KNOWN}`]);
  });

  it("reads every part from the records: brief, decision summary and lot impact", () => {
    const parts = Object.fromEntries(briefPage(VERSION, SIGNED, LOTS).map((item) => [item.key, item.lines]));
    expect(parts.problem).toEqual(["Pressure-alarm complaints rose 9.3× after OrbitCare 300 Rev B."]);
    expect(parts.product).toEqual(["OrbitCare 300: Rev B", `1 complaint in scope: ${VERSION_NOT_KNOWN}`]);
    expect(parts.affected).toEqual([
      "Suspect component lot: NovaSense sensor NS-SL-2531 (chosen by a person)",
      "Also in the case's lots: Supplier NovaSense",
      "Lot LOT-003 (Rev B)",
      `Lot LOT-004 (${VERSION_NOT_KNOWN})`,
    ]);
    // Without a person's choice, the rule's suggestion is said to be one.
    const suggested = { ...LOTS, saved: null, suggestion: { kind: "SUPPLIER", id: "s", lot: null } } as LotImpactView;
    expect(
      briefPage(VERSION, null, suggested)
        .find((item) => item.key === "affected")
        ?.lines.slice(0, 2),
    ).toEqual([
      "Suspect supplier: NovaSense (suggested by rule, not confirmed)",
      "Also in the case's lots: Component lot NovaSense sensor NS-SL-2531",
    ]);
    expect(parts.for.join()).toContain("Trend 9.3×");
    expect(parts.against.join()).toContain("Bench test passed");
    expect(parts.hypotheses[0]).toBe("Leading: HYP-1: Sensor drift · Strongly supported · 3 for, 0 against");
    // An AI proposal keeps its review label.
    expect(parts.hypotheses[1]).toContain("AI proposal, not reviewed");
    expect(parts.unknowns).toEqual(["UNK-1: Sensor lot of unit 7 · needs teardown"]);
    expect(parts.risk).toEqual([
      "Risk review RR-1 · Risk acceptable · by Ravi",
      "Risk file SAMPLE-RSK-01: Over-infusion · OPEN",
    ]);
    expect(parts.action).toEqual([
      "Proposed conclusion: The NovaSense sensors are the most likely cause.",
      "Contain lots 003 and 004",
      "Restore 32-unit inspection",
    ]);
    expect(parts.decision[0]).toBe("Accept the conclusion: Sensors");
    expect(parts.decision[1]).toMatch(/^Signed by Meera \(Quality head\) on .* · Password and authenticator code$/);
    expect(parts.effectiveness[0]).toMatch(/^SAMPLE-CAPA-02: No alarm from new lots · check planned for /);
    expect(parts.effectiveness[1]).toBe("Too early.");
  });

  it("before signing: the brief's own status and the risk file read before the decision", () => {
    const parts = Object.fromEntries(
      briefPage(VERSION, { ...SIGNED, decision: null, affects: undefined, risks: SIGNED.affects?.risks }, null).map(
        (item) => [item.key, item.lines],
      ),
    );
    expect(parts.decision[0]).toBe("No decision signed yet");
    expect(parts.decision[1]).toMatch(/^Brief BRF-001 version 2: Accepted for decision · reviewed by Asha Rao on /);
    expect(parts.risk[1]).toBe("Risk file SAMPLE-RSK-01: Over-infusion · OPEN");
    // No lot impact read: the lots alone.
    expect(parts.affected).toEqual(["Lot LOT-003 (Rev B)", `Lot LOT-004 (${VERSION_NOT_KNOWN})`]);
  });
});
