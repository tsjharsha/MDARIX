import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { addressFor } from "./workspaceAddress";
import {
  REPORTS,
  REPORT_VIEWS,
  REPORT_VIEW_NAMES,
  deadlineDue,
  reportPlace,
  reportsInView,
  type ReportDetail,
  type ReportListItem,
  type StageStep,
} from "./authorityReports";
import { ReportsSection, meterText, reportNext, NEVER_SUBMITS } from "./sections/ReportsTab";
import { DecisionTreesSection, chosenComplaint, nextAfter, treePlace, type Trees } from "./sections/DecisionTrees";
import { ComplaintPage } from "./sections/ComplaintPage";
import { eventPath, type EventView } from "./oversight";
import { PRACTICE_APPROVAL } from "./sections/PracticeApproval";

// 0.10.75, Release C part C3: the Decision trees and Reports tabs (the approved design's viewTrees, viewReports and
// viewReport), and a complaint's page opening its decision path and its report.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));

const api = (shownTab = "", permissions = ["regulatory.review", "regulatory.approve", "data.export"]) =>
  ({
    session: { user_id: "u1", allowed_menu: ["home"], business_permissions: permissions },
    work: { products: [], investigations: [] },
    open: vi.fn(),
    notify: vi.fn(),
    reportTab: vi.fn(),
    shownTab,
    navigation: "new",
    isTrial: true,
    persona: "regulatory",
    personaLabel: "Regulatory Leader",
  }) as unknown as WorkspaceApi;

const render = (node: ReactNode, value: WorkspaceApi = api()) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

/** The approved design's RSTAGES. */
const RSTAGES = [
  "Created from the decision tree",
  "Mandatory fields complete",
  "Sent for approval",
  "Approved · PDF ready",
  "Submitted by you",
  "Acknowledged",
];
const CODES = ["CREATED", "COMPLETE", "APPROVAL", "APPROVED", "SUBMITTED", "ACKNOWLEDGED"] as const;

function stages(at: number): StageStep[] {
  return CODES.map((code, index) => ({
    code,
    label: RSTAGES[index],
    state: index < at ? "DONE" : index === at ? "CURRENT" : "LATER",
  }));
}

const field = (id: string, number: string, label: string, status: string, value: string | null = null) => ({
  id,
  number,
  label,
  value,
  status,
  status_label: status === "MUST_HAVE" ? "Missing: must have before submission" : "From record",
  source: value ? { type: "Complaint", ref: "SAMPLE-RV-11", label: "The complaint record", id: "c-rv11" } : null,
  personal: null,
  missing_class: "MUST_HAVE",
  editable: true,
  note: null,
  by: null,
  at: null,
});

/** The US MDR of SAMPLE-RV-11 as the server answers it, trimmed to what the page reads. */
function report(stage: number, patch: Partial<ReportDetail> = {}): ReportDetail {
  const missing = stage === 0 ? 2 : 0;
  return {
    id: "r1",
    kind: "INITIAL",
    complaint: {
      id: "c-rv11",
      ref: "SAMPLE-RV-11",
      complaint_identifier: "SAMPLE-RV-11",
      product_name: "PulseWatch 410",
      version: "Rev A",
      country: "US",
      description: "SpO2 read 4 to 6 points high",
      aware_date: "2026-11-01",
      sample: true,
    },
    market: "US",
    market_label: "United States (FDA)",
    form: {
      code: "FDA_3500A",
      title: "Form FDA 3500A worksheet (eMDR)",
      version: "Form FDA 3500A (09/2025)",
      authority: "FDA",
      source_document: "Form FDA 3500A (09/2025)",
      clauses: [],
    },
    routes: [{ code: "EMDR", label: "eMDR", note: "", acknowledgement_expected: true, evidence: [] }],
    state: (["DRAFT", "DRAFT", "DRAFT", "APPROVED", "SUBMITTED_PENDING", "ACCEPTED"] as const)[stage],
    state_label: "Draft",
    next_step: "",
    steps: [],
    stage: CODES[stage],
    stage_label: RSTAGES[stage],
    stages: stages(stage),
    mandatory: { total: 24, filled: 24 - missing, missing: missing ? ["D2A", "H6_CONCLUSIONS"] : [] },
    approved_snapshot:
      stage >= 3
        ? ({
            id: "s1",
            version: 1,
            state: "APPROVED",
            approved_by: "Rahul Colleague",
            preparers: ["Asha Quality"],
          } as ReportDetail["approved_snapshot"])
        : null,
    preparers: ["Asha Quality"],
    cancelled_reason: null,
    deadline: {
      due_on: "2026-12-01",
      provisional: false,
      days_left: 28,
      overdue: false,
      due_at: "2026-12-01T18:29:59Z",
      due_label: "Tue 1 Dec 2026, 23:59 IST",
    },
    assessment: {
      conclusion: "REPORTABLE",
      report_type_label: "30-day malfunction report",
      signed_by: "Asha Quality",
      signed_at: "2026-11-03T08:00:00Z",
      version: 1,
    },
    case: null,
    sections: [
      {
        code: "D",
        title: "D. Suspect medical device",
        note: null,
        fields: [
          field("D1", "D1", "Brand name", "FROM_RECORD", "PulseWatch 410"),
          field("D2A", "D2a", "Procode", missing ? "MUST_HAVE" : "ENTERED", missing ? null : "DQA"),
        ],
      },
    ],
    counts: {},
    status_labels: {},
    editable: stage <= 2,
    snapshots: [],
    pending_snapshot:
      stage === 2
        ? ({
            id: "s1",
            version: 1,
            state: "PENDING",
            requested_by: "Asha Quality",
            content_fingerprint: "f".repeat(64),
          } as ReportDetail["pending_snapshot"])
        : null,
    cannot_approve: ["Asha Quality"],
    approval:
      stage <= 2 ? { may_approve: true, same_person: true, approvers: [], message: "Practice", role: "LEADER" } : null,
    submissions: [],
    request: null,
    parent_id: null,
    responses: [],
    note: null,
    follow_up_due_on: null,
    starter_mark: "Starter text, for your consultant to confirm.",
    practice_label: "Practice record",
    never_submits: "",
    sample: false,
    ...patch,
  } as ReportDetail;
}

const listItem = (id: string, views: string[], extra: Partial<ReportListItem> = {}): ReportListItem =>
  ({
    id,
    kind: "INITIAL",
    complaint_id: `c-${id}`,
    complaint_ref: `SAMPLE-${id}`,
    complaint_identifier: `SAMPLE-${id}`,
    description: "",
    market: "US",
    market_label: "United States (FDA)",
    form_title: "Form FDA 3500A worksheet (eMDR)",
    form_version: "Form FDA 3500A (09/2025)",
    state: "DRAFT",
    state_label: "Draft",
    next_step: "",
    due_on: "2026-12-01",
    provisional: false,
    days_left: 28,
    overdue: false,
    due_at: "2026-12-01T18:29:59Z",
    assessment: null,
    can_start: false,
    sample: false,
    stage: "CREATED",
    stage_label: "Created from the decision tree",
    mandatory: { total: 24, filled: 18 },
    views,
    ...extra,
  }) as ReportListItem;

describe("Reports: list views, six columns, cards on a phone", () => {
  it("offers the approved design's three list views, each a filter the server marks", () => {
    expect(REPORT_VIEW_NAMES).toEqual(["Open reports", "Waiting for my approval", "Submitted this month"]);
    const items = [
      listItem("RV-11", ["open"]),
      listItem("RV-06", ["open", "my-approval"]),
      listItem("RV-09", ["submitted-month"], { stage: "ACKNOWLEDGED", state: "ACCEPTED" }),
      // A market not yet concluded is not a report: never listed on the Reports tab.
      listItem("RV-08", ["open"], { id: null }),
    ];
    expect(reportsInView(items, "Open reports").map((item) => item.id)).toEqual(["RV-11", "RV-06"]);
    expect(reportsInView(items, "Waiting for my approval").map((item) => item.id)).toEqual(["RV-06"]);
    expect(reportsInView(items, "Submitted this month").map((item) => item.id)).toEqual(["RV-09"]);
    expect(Object.values(REPORT_VIEWS).map((view) => view.code)).toEqual(["open", "my-approval", "submitted-month"]);
    // A cancelled report has no deadline chip.
    expect(deadlineDue(listItem("x", []), "CANCELLED")).toBeNull();
  });

  it("lists the reports with Due, Report, Status, Mandatory fields and Market, one Open, and the forms", () => {
    resources.data[REPORTS] = {
      items: [listItem("RV-11", ["open"])],
      forms: [
        { market: "US", title: "Form FDA 3500A worksheet (eMDR)", version: "Form FDA 3500A (09/2025)" },
        { market: "IN", title: "MvPI MDAE worksheet", version: "MvPI MDAE form, Version 1.2" },
      ],
      never_submits: "",
      starter_mark: "Starter text.",
      practice_label: null,
    };
    const html = render(<ReportsSection />);
    for (const heading of ["Due", "Report", "Status", "Mandatory fields", "Market"]) expect(html).toContain(heading);
    expect(html).toContain("Open reports · 1");
    expect(html).toContain("18 of 24 mandatory");
    expect(html).toContain("Created from the decision tree");
    expect((html.match(/>Open</g) ?? []).length).toBe(1);
    expect(html).toContain("ms-cards");
    expect(html).toContain("Forms MDARIX prepares");
    expect(html).toContain("In MDARIX today");
    // The list view in the address: /app/reports?view=my-approval opens "Waiting for my approval".
    const waiting = render(<ReportsSection />, api("?view=my-approval"));
    expect(waiting).toMatch(/<option value="Waiting for my approval" selected="">/);
    expect(waiting).toContain("Nothing waits for your approval");
    expect(meterText({ total: 0, filled: 0 })).toEqual({ text: "0 of 0 mandatory", share: 0 });
  });
});

describe("a report's page: the record page's shape, the status path and the rail", () => {
  it("shows the six stages as the path, the meter, and Send for approval blocked with its reason", () => {
    resources.data[`${REPORTS}/r1`] = report(0);
    const html = render(<ReportsSection />, api("?report=r1"));
    expect(html).toContain("Reports</button>");
    expect(html).toContain("Authority report · United States (FDA)");
    expect(html).toContain(
      "Created when the United States (FDA) conclusion was signed reportable: 30-day malfunction report.",
    );
    for (const label of RSTAGES) expect(html).toContain(label);
    expect(html).toContain("22 of 24 mandatory fields");
    expect(html).toContain("Show only missing");
    expect(html).toContain("Fill the 2 missing mandatory fields");
    expect(html).toMatch(/<button type="button" class="ac-secondary" disabled="" aria-describedby="rp-why-send">/);
    expect(html).toContain('id="rp-why-send">2 mandatory fields missing');
    expect(html).not.toContain("Generate the PDF");
    // Each field says where its value comes from.
    expect(html).toContain("From the complaint record");
    // MDARIX never submits: said once, where it matters.
    expect(html.split(NEVER_SUBMITS.replace(/'/g, "&#x27;")).length - 1).toBe(1);
  });

  it("opens Send for approval once every mandatory field is filled", () => {
    resources.data[`${REPORTS}/r1`] = report(1);
    const html = render(<ReportsSection />, api("?report=r1"));
    expect(reportNext(report(1)).title).toBe("Ready for approval");
    expect(html).toMatch(/<button type="button" class="ac-primary"><svg[^>]*>.*?<\/svg> Send for approval<\/button>/);
    expect(html).not.toContain("rp-why-send");
  });

  it("keeps the practice label at the approve button when the preparer approves alone in a trial", () => {
    resources.data[`${REPORTS}/r1`] = report(2);
    const html = render(<ReportsSection />, api("?report=r1"));
    expect(html).toContain("Approve the snapshot");
    expect(html).toContain(PRACTICE_APPROVAL);
    expect(html).not.toContain("Generate the PDF");
    // A colleague approves: named in Who signs, never the preparer; no practice label.
    resources.data[`${REPORTS}/r1`] = report(2, {
      approval: {
        may_approve: false,
        same_person: false,
        approvers: ["Rahul Colleague"],
        message: "A colleague approves this: Rahul Colleague.",
      },
    });
    const colleague = render(<ReportsSection />, api("?report=r1"));
    expect(colleague).toContain("May approve: Rahul Colleague");
    expect(colleague).toContain("Prepared: Asha Quality");
    expect(colleague).not.toContain(PRACTICE_APPROVAL);
  });

  it("generates the PDF only after approval", () => {
    for (const at of [0, 1, 2, 4, 5]) {
      resources.data[`${REPORTS}/r1`] = report(at);
      expect(render(<ReportsSection />, api("?report=r1")), `stage ${at}`).not.toContain("Generate the PDF");
    }
    resources.data[`${REPORTS}/r1`] = report(3);
    const html = render(<ReportsSection />, api("?report=r1"));
    expect(html).toContain("Generate the PDF");
    expect(html).toContain("Approved: Rahul Colleague");
    expect(html).toContain("Record the submission");
    // Without the export right, a colleague generates it.
    expect(render(<ReportsSection />, api("?report=r1", ["regulatory.review"]))).not.toContain("Generate the PDF");
  });

  it("says why a cancelled report is off the path", () => {
    resources.data[`${REPORTS}/r1`] = report(0, {
      state: "CANCELLED",
      state_label: "Cancelled: not reportable",
      stage: null,
      cancelled_reason: "The United States (FDA) conclusion signed on 2026-11-03 (version 2) says not reportable.",
    });
    const html = render(<ReportsSection />, api("?report=r1"));
    expect(html).toContain(
      "Cancelled: The United States (FDA) conclusion signed on 2026-11-03 (version 2) says not reportable.",
    );
    expect(html).not.toContain('aria-label="Stage"');
    expect(html).not.toContain("Send for approval");
  });

  it("has its own address, and a reader without the regulatory rights reads it only", () => {
    expect(addressFor(reportPlace("r1"))).toBe("/app/reports?report=r1");
    resources.data[`${REPORTS}/r1`] = report(1);
    const viewer = render(<ReportsSection />, api("?report=r1", []));
    expect(viewer).not.toContain("Send for approval</button>");
    expect(viewer).toContain("You can read this report");
  });
});

const trees: Trees = {
  markets: [
    {
      market: "US",
      label: "United States (FDA)",
      title: "US medical device reporting (21 CFR Part 803)",
      version: 2,
      status: "APPROVED",
      status_label: "Approved",
      version_label: "Your version 2 · approved 2026-10-28",
      enabled: true,
      tests: { passed: 12, total: 12, current: true },
      questions: [
        { id: "US1", text: "Did a death occur?", clause: "21 CFR 803.50(a)(1)", extra: false },
        { id: "US4", text: "Did the device malfunction?", clause: "21 CFR 803.3(k)", extra: false },
      ],
    },
    {
      market: "IN",
      label: "India (CDSCO)",
      title: "India MDR 2017",
      version: 1,
      status: "STARTER",
      status_label: "Starter",
      version_label: "MDARIX starter · version 1, for your consultant to confirm",
      enabled: true,
      tests: { passed: 8, total: 8, current: true },
      questions: [{ id: "IN1", text: "Is this an adverse event?", clause: "MDR 2017 Rule 26", extra: false }],
    },
  ],
  complaints: [
    { id: "c-rv09", ref: "SAMPLE-RV-09", description: "Alarm too quiet", markets: ["US"], signed: ["US"] },
    { id: "c-rv10", ref: "SAMPLE-RV-10", description: "Probe overheated", markets: ["IN"], signed: ["IN"] },
  ],
  complaint: { id: "c-rv09", ref: "SAMPLE-RV-09", description: "Alarm too quiet" },
  paths: {
    US: {
      market: "US",
      label: "United States (FDA)",
      nodes: [
        {
          id: "US1",
          text: "Did a death occur?",
          clause: "21 CFR 803.50(a)(1)",
          extra: false,
          answer: "NO",
          answer_label: "No",
        },
        {
          id: "US4",
          text: "Did the device malfunction?",
          clause: "21 CFR 803.3(k)",
          extra: false,
          answer: "YES",
          answer_label: "Yes",
        },
      ],
      outcome: {
        code: "REPORTABLE",
        label: "Reportable",
        signed: true,
        report_type_label: "30-day report",
        due_on: "2026-12-01",
        signed_by: "MDARIX sample author",
        signed_at: "2026-10-01T00:00:00Z",
        version: 1,
      },
      report: { id: "r9", state: "ACCEPTED" },
      has_form: true,
    },
  },
  never_decides: "Each tree points to a conclusion; a person confirms or overrides it and signs.",
  starter_mark: "",
};

describe("Decision trees: one tree per market, and the path a complaint took", () => {
  it("shows the market's tree: version, status, test result, question, answer, clause and outcome", () => {
    resources.data["/api/v1/decision-trees"] = trees;
    const html = render(<DecisionTreesSection />);
    expect(html).toContain("US MDR</button>");
    expect(html).toContain("India</button>");
    expect(html).toContain("Your version 2 · approved 2026-10-28");
    expect(html).toContain("Approved");
    expect(html).toContain("12 of 12 worked complaints pass");
    expect(html).toContain("<b>Did the device malfunction?</b><small>21 CFR 803.3(k)</small>");
    expect(html).toContain('<span class="uw-pill is-on">Yes</span>');
    expect(html).toContain('<li class="uw-tout is-reportable"><b>Reportable</b>');
    expect(html).toContain("Open the report");
    expect(html).toMatch(/<option value="c-rv09" selected="">SAMPLE-RV-09<\/option>/);
  });

  it("chooses the complaint asked for when it was walked through that market, else the first", () => {
    expect(chosenComplaint(trees, "US", "c-rv09")).toBe("c-rv09");
    expect(chosenComplaint(trees, "US", "c-rv10")).toBe("c-rv09");
    expect(chosenComplaint(trees, "IN", null)).toBe("c-rv10");
    expect(chosenComplaint(trees, "GB", null)).toBeNull();
    expect(nextAfter(null).title).toBe("No complaint walked through it yet");
    const unsigned = { ...trees.paths.US, outcome: { ...trees.paths.US.outcome, signed: false } };
    expect(nextAfter(unsigned).title).toBe("Points to: reportable");
    expect(nextAfter({ ...trees.paths.US, has_form: false }).detail).toContain("signed conclusion");
    expect(
      nextAfter({
        ...trees.paths.US,
        outcome: { ...trees.paths.US.outcome, code: "NOT_REPORTABLE", label: "Not reportable" },
      }).title,
    ).toBe("No report");
  });

  it("opens from a complaint's page: its decision path per market, and its report", () => {
    expect(addressFor(treePlace("US", "c-rv11"))).toBe("/app/decision-trees?market=US&complaint=c-rv11");
    resources.data[eventPath("SAMPLE-RV-11")] = rv11();
    const details = render(<ComplaintPage tab="Summary?ref=SAMPLE-RV-11" />);
    expect(details).toContain("<dt>Decision path</dt>");
    expect(details).toMatch(/<button type="button" class="ac-link">United States<\/button>/);
    const related = render(<ComplaintPage tab="Related?ref=SAMPLE-RV-11" />);
    expect(related).toContain("Open the report");
  });
});

/** SAMPLE-RV-11's page, trimmed to what the page reads (as releaseC2074.test.tsx), with its US report started. */
function rv11(): EventView {
  return {
    event: {
      complaint_id: "c-rv11",
      ref: "SAMPLE-RV-11",
      business_id: "CMP000038",
      product: "PulseWatch 410",
      version: "Rev A",
      lot: "LOT-002",
      market: "US",
      awareness_at: "2026-11-01T20:07:11Z",
      status_in_qms: "Open",
      owner_id: "u1",
      owner_name: "Asha Quality",
      owner_named: true,
      sample: true,
      description: "Biomedical engineering checked a monitor against a reference oximeter.",
      problem_code: null,
      harm: null,
    },
    summary: { nearest_deadline: null, open_requests: 0, next_action: null },
    stages: [{ code: "MARKETS", label: "Market assessment", state: "CURRENT" }],
    checklist: [],
    blocked: 0,
    state: "NOT_READY",
    state_label: "Not ready to close",
    changed_since_signed: false,
    ready: null,
    decision_record: { entries: [], sha256: "", version: 0, filed: null },
    you_are_owner: true,
    people: [{ id: "u1", name: "Asha Quality" }],
    reason_min: 20,
    never_closes: "MDARIX never closes the complaint.",
    practice_label: null,
    work: { owner_name: "Asha Quality", stage: "Market assessment", next: null, due: [], markets: ["US"] },
    signers: {},
    service: null,
    related: [
      { key: "assessments", label: "Market assessments", count: 1, lines: ["United States (FDA): reportable"] },
      {
        key: "reports",
        label: "Authority reports",
        count: 1,
        lines: ["United States (FDA) · Form FDA 3500A worksheet (eMDR) · draft"],
        items: [{ id: "r1", ref: "US" }],
      },
    ],
  } as unknown as EventView;
}
