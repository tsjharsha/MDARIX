import { formatDay } from "../../app/dates";
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import {
  askNote,
  deadlineText,
  fieldTone,
  owesWorksheet,
  parseReportsTab,
  reportsTab,
  stepIndex,
  submissionProblem,
  summaryLine,
  type ReportDetail,
  type ReportList,
  type SubmissionForm,
} from "./authorityReports";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));

vi.mock("../customer-admin/shared", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../customer-admin/shared")>();
  return {
    ...actual,
    useResource: (path: string | null) => ({
      data: path ? (resources.data[path] ?? null) : null,
      error: null,
      state: "ready",
      loading: false,
      reload: vi.fn(),
    }),
  };
});

const { Reports, ReportDrawer } = await import("./sections/Reports");

function workspace(permissions: string[], extra: Record<string, unknown> = {}): WorkspaceApi {
  return {
    session: { allowed_menu: ["products", "investigations"], business_permissions: permissions, ...extra },
    open: vi.fn(),
    notify: vi.fn(),
    work: { products: [], requestOpenInvestigation: vi.fn() },
  } as unknown as WorkspaceApi;
}

const render = (node: ReactNode, permissions: string[] = ["regulatory.review", "data.export"]) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={workspace(permissions)}>{node}</WorkspaceContext.Provider>);

const field = (id: string, status: string, value: string | null, extra = {}) => ({
  id,
  number: id,
  label: `Field ${id}`,
  value,
  status,
  status_label: status,
  source: value ? { type: "Complaint", ref: "CMP-1", label: "The complaint's description", id: "c" } : null,
  personal: null,
  missing_class: "MUST_HAVE",
  editable: true,
  note: null,
  by: null,
  at: null,
  ...extra,
});

const detail = (state: ReportDetail["state"], extra: Partial<ReportDetail> = {}): ReportDetail =>
  ({
    id: "r1",
    kind: "INITIAL",
    complaint: {
      id: "c1",
      ref: "CMP-1",
      complaint_identifier: "SAMPLE-RV-06",
      product_name: "Pump",
      version: "Rev B",
      country: "US",
      description: "Alarm",
      aware_date: "2026-10-08",
      sample: true,
    },
    market: "US",
    market_label: "United States (FDA)",
    form: {
      code: "FDA_3500A",
      title: "Form FDA 3500A worksheet (eMDR)",
      version: "Form FDA 3500A (09/2025)",
      authority: "FDA",
      source_document: "Form FDA 3500A",
      clauses: [],
    },
    routes: [
      {
        code: "EMDR",
        label: "FDA eMDR",
        note: "",
        acknowledgement_expected: true,
        evidence: [{ kind: "ACK3", label: "Ack3", outcomes: ["ACCEPTED", "REJECTED"] }],
      },
    ],
    state,
    state_label: state,
    next_step: "Next",
    steps: [
      { state: "DRAFT", label: "Draft" },
      { state: "APPROVED", label: "Approved snapshot" },
      { state: "SUBMITTED_PENDING", label: "Submitted, acceptance pending" },
      { state: "ACCEPTED", label: "Accepted" },
      { state: "COMPLETE", label: "Complete" },
    ],
    deadline: { due_on: "2026-11-07", provisional: false, days_left: 6, overdue: false },
    assessment: {
      conclusion: "REPORTABLE",
      report_type_label: "30-calendar-day report",
      signed_by: "Priya",
      signed_at: "2026-11-01T10:00:00Z",
      version: 1,
    },
    case: null,
    sections: [
      {
        code: "A",
        title: "A. Patient information",
        note: null,
        fields: [field("A1", "OUTSIDE", null, { personal: "PATIENT", editable: false })],
      },
      {
        code: "B",
        title: "B. Adverse event or product problem",
        note: null,
        fields: [field("B5", "FROM_RECORD", "Alarm"), field("B4", "MUST_HAVE", null)],
      },
    ],
    counts: { FROM_RECORD: 1, MUST_HAVE: 1, OUTSIDE: 1 },
    status_labels: {},
    editable: state === "DRAFT" || state === "CORRECTION_REQUIRED",
    snapshots: [],
    pending_snapshot: null,
    cannot_approve: ["Priya"],
    submissions: [],
    request: null,
    parent_id: null,
    responses: [],
    note: null,
    follow_up_due_on: null,
    starter_mark: "Starter text",
    practice_label: "Practice record",
    never_submits: "Prepared by MDARIX, submitted by you: MDARIX never submits a report.",
    sample: true,
    ...extra,
  }) as ReportDetail;

describe("the report helpers", () => {
  it("carries one complaint's reports in a tab name", () => {
    expect(reportsTab()).toBe("Reports");
    expect(parseReportsTab(reportsTab("abc"))).toEqual({ isReports: true, complaintId: "abc" });
    expect(parseReportsTab("Reportability").isReports).toBe(false);
  });

  it("offers a worksheet only for a US or India market reportable or pending", () => {
    expect(owesWorksheet([{ market: "US", state: "REPORTABLE", suggested: null }])).toBe(true);
    expect(owesWorksheet([{ market: "IN", state: "DRAFT", suggested: "PENDING_INFORMATION" }])).toBe(true);
    expect(owesWorksheet([{ market: "EU_NI", state: "REPORTABLE", suggested: null }])).toBe(false);
    expect(owesWorksheet([{ market: "US", state: "NOT_REPORTABLE", suggested: null }])).toBe(false);
  });

  it("puts each state on its step, a rejected draft back on the first", () => {
    expect(stepIndex("CORRECTION_REQUIRED")).toBe(0);
    expect(stepIndex("SUBMITTED_PENDING")).toBe(2);
    expect(stepIndex("COMPLETE")).toBe(4);
    expect(fieldTone("MUST_HAVE")).toBe("critical");
    expect(fieldTone("OUTSIDE")).toBe("neutral");
  });

  it("writes the deadline and the worksheet summary plainly", () => {
    const ninth = new Date(2026, 10, 9, 10, 0);
    expect(
      deadlineText({ due_on: "2026-11-07", days_left: -2, provisional: true, overdue: true }, undefined, ninth),
    ).toBe(`Provisional deadline ${formatDay("2026-11-07")} · 2 days overdue`);
    const india = {
      due_on: "2026-11-07",
      days_left: 6,
      provisional: false,
      overdue: false,
      due_at: "2026-11-07T18:29:59+00:00",
      due_label: "Sat 7 Nov 2026, 23:59 IST",
    };
    expect(deadlineText(india, undefined, new Date("2026-11-01T12:00:00Z"))).toBe(
      "Deadline Sat 7 Nov 2026, 23:59 IST · 6 days left",
    );
    expect(deadlineText(india, "ACCEPTED")).toBe("Deadline Sat 7 Nov 2026, 23:59 IST: met by the submission");
    expect(summaryLine({ FROM_RECORD: 3, ENTERED: 1, MUST_HAVE: 2, OUTSIDE: 4 })).toBe(
      "3 from your records · 1 entered · 2 must have before submission · 4 entered in the authority's route",
    );
  });

  it("refuses a submission the server would refuse", () => {
    const form: SubmissionForm = {
      route: "EMDR",
      submittedAt: "2026-11-01T10:00",
      note: "",
      reference: "",
      matches: true,
      differences: [],
    };
    expect(submissionProblem(form, false)).toMatch(/Attach the submitted content/);
    expect(submissionProblem(form, true)).toBeNull();
    expect(
      submissionProblem(
        { ...form, matches: false, differences: [{ field: "B5", classification: "MATERIAL", reason: "x" }] },
        true,
      ),
    ).toMatch(/re-approval/);
  });
});

describe("the reports screens", () => {
  it("lists each obligation with its deadline and the path to follow", () => {
    // Six days from today, so the fixture never goes stale (it read a fixed 7 Nov 2026 before).
    const dueOn = new Date(Date.now() + 6 * 86_400_000).toISOString().slice(0, 10);
    resources.data["/api/v1/reports"] = {
      items: [
        {
          id: null,
          kind: "INITIAL",
          complaint_id: "c1",
          complaint_ref: "CMP-1",
          complaint_identifier: "SAMPLE-RV-06",
          description: "Alarm",
          market: "US",
          market_label: "United States (FDA)",
          form_title: "Form FDA 3500A worksheet (eMDR)",
          form_version: "Form FDA 3500A (09/2025)",
          state: "NOT_STARTED",
          state_label: "Not started",
          next_step: "Start the worksheet",
          due_on: dueOn,
          provisional: false,
          days_left: 6,
          overdue: false,
          assessment: "Reportable",
          can_start: true,
          sample: true,
        },
      ],
      forms: [{ market: "US", title: "Form FDA 3500A worksheet (eMDR)", version: "Form FDA 3500A (09/2025)" }],
      never_submits: "MDARIX never submits a report.",
      starter_mark: "Starter text",
      practice_label: null,
    } satisfies ReportList;
    const html = render(<Reports />);
    expect(html).toContain("Second-person approval");
    expect(html).toContain("Start the worksheet");
    expect(html).toMatch(/Deadline [^<]*\d{4} · \d+ days? left/);
    expect(render(<Reports />, [])).not.toContain("Start the worksheet</button>");
  });

  it("shows every field with its status, patient fields for the authority's route, and the approval refusal rule", () => {
    resources.data["/api/v1/reports/r1"] = detail("DRAFT", {
      pending_snapshot: {
        id: "s1",
        version: 1,
        state: "PENDING",
        form_version: "x",
        content_fingerprint: "abcdef0123456789",
        requested_by: "Priya",
        requested_at: "2026-11-01T10:00:00Z",
        approved_by: null,
        approved_at: null,
        preparers: ["Priya"],
        sample: false,
      },
    });
    const html = render(<ReportDrawer id="r1" onOpen={vi.fn()} onClose={vi.fn()} />);
    expect(html).toContain("A. Patient information");
    expect(html).toContain("OUTSIDE");
    expect(html).toContain("You confirm with your password.");
    expect(html).toContain("Not allowed to approve: Priya");
    // The drawer says it once, at the submission (DecideAndSign), not as a note at its top (0.10.66, V5).
    expect(html).not.toContain("MDARIX never submits a report.");
    expect(html).toContain("PDF (draft preview, not approved)");
  });

  it("tells who approves before any password: the names in place of the form, or the trial's practice note", () => {
    const pending = {
      id: "s1",
      version: 1,
      state: "PENDING" as const,
      form_version: "x",
      content_fingerprint: "abcdef0123456789",
      requested_by: "Priya",
      requested_at: "2026-11-01T10:00:00Z",
      approved_by: null,
      approved_at: null,
      preparers: ["Priya"],
      sample: false,
    };
    const colleague = "You prepared this worksheet. A colleague with regulatory approval rights approves this: Rahul.";
    resources.data["/api/v1/reports/r1"] = detail("DRAFT", {
      pending_snapshot: pending,
      approval: { may_approve: false, same_person: false, approvers: ["Rahul"], message: colleague },
    });
    let html = render(<ReportDrawer id="r1" onOpen={vi.fn()} onClose={vi.fn()} />);
    expect(html).toContain(colleague);
    expect(html).not.toContain("Your password");
    const practice =
      "In a pilot a colleague approves this; in the trial you may approve your own practice report as Leader.";
    resources.data["/api/v1/reports/r1"] = detail("DRAFT", {
      pending_snapshot: pending,
      approval: { may_approve: true, same_person: true, approvers: [], message: practice },
    });
    html = render(<ReportDrawer id="r1" onOpen={vi.fn()} onClose={vi.fn()} />);
    // 0.10.87: the pilot half is the Approve button's practice line; the warning says only who you approve as.
    expect(html).toContain("You may approve your own practice report as Leader.");
    expect(html.split("in a pilot a colleague approves this").length - 1).toBe(1);
    expect(html).toContain("Your password");
    expect(askNote({ may_approve: false, same_person: false, approvers: ["Rahul"], message: "x" })).toBe(
      "When ready, ask for approval: Rahul gets a task in My Work.",
    );
    expect(askNote({ may_approve: true, same_person: true, approvers: [], message: "x" })).toContain(
      "working alone in the trial, you approve your own practice report",
    );
  });

  it("offers to mark an approved snapshot as submitted", () => {
    resources.data["/api/v1/reports/r1"] = detail("APPROVED");
    const html = render(<ReportDrawer id="r1" onOpen={vi.fn()} onClose={vi.fn()} />);
    expect(html).toContain("Mark as submitted");
    expect(html).toContain("Reopen the draft");
  });
});

describe("B9 step 15: India's chain card and files follow the India switch", () => {
  const INDIA = { b9: { india: true } };
  const renderAs = (node: ReactNode, session: Record<string, unknown>) =>
    renderToStaticMarkup(
      <WorkspaceContext.Provider value={workspace(["regulatory.review", "data.export"], session)}>
        {node}
      </WorkspaceContext.Provider>,
    );
  const india = (state: ReportDetail["state"], chain: ReportDetail["india_chain"], extra: Partial<ReportDetail> = {}) =>
    detail(state, {
      market: "IN",
      form: { ...detail("DRAFT").form, code: "MVPI_MDAE", title: "MvPI adverse event report worksheet" },
      snapshots: [{ id: "s1", version: 1, state: "APPROVED" } as ReportDetail["snapshots"][number]],
      india_chain: chain,
      ...extra,
    });

  it("offers a follow-up or final on a submitted initial report, and the official form and ADRMS sheet", () => {
    resources.data["/api/v1/reports/r1"] = india("ACCEPTED", {
      type: "Initial",
      items: [],
      ended: false,
      can_create: true,
      note: "No legal clock: your date",
    });
    const html = renderAs(<ReportDrawer id="r1" onOpen={vi.fn()} onClose={vi.fn()} />, INDIA);
    expect(html).toContain("Create a follow-up or final report");
    expect(html).toContain("No legal clock: your date");
    expect(html).toContain("Official MvPI form v1.2 (PDF)");
    expect(html).toContain("ADRMS entry sheet (PDF)");
    // Off: today's worksheet only.
    const off = renderAs(<ReportDrawer id="r1" onOpen={vi.fn()} onClose={vi.fn()} />, { b9: { india: false } });
    expect(off).not.toContain("Create a follow-up or final report");
    expect(off).not.toContain("Official MvPI form");
    expect(off).not.toContain("ADRMS entry sheet");
  });

  it("says a Final ends the chain and shows a child's own date as the user's", () => {
    resources.data["/api/v1/reports/r1"] = india("ACCEPTED", {
      type: "Initial",
      items: [
        { id: "f1", type: "Follow up", state: "ACCEPTED" },
        { id: "f2", type: "Final", state: "ACCEPTED" },
      ],
      ended: true,
      can_create: false,
      note: "No legal clock: your date",
    });
    let html = renderAs(<ReportDrawer id="r1" onOpen={vi.fn()} onClose={vi.fn()} />, INDIA);
    expect(html).toContain("A Final report ends the chain: nothing follows it.");
    expect(html).not.toContain("Create a follow-up or final report");
    resources.data["/api/v1/reports/r1"] = india(
      "DRAFT",
      { type: "Follow up", next_report_on: "2027-01-15", note: "No legal clock: your date" },
      { kind: "RESPONSE", parent_id: "r0" },
    );
    html = renderAs(<ReportDrawer id="r1" onOpen={vi.fn()} onClose={vi.fn()} />, INDIA);
    expect(html).toContain("Follow up report");
    expect(html).toContain("No legal clock: your date");
    expect(html).toContain("Cancel this follow up report");
  });

  it("shows no chain on an India initial report that is not submitted yet", () => {
    resources.data["/api/v1/reports/r1"] = india("DRAFT", {
      type: "Initial",
      items: [],
      ended: false,
      can_create: false,
      note: "No legal clock: your date",
    });
    expect(renderAs(<ReportDrawer id="r1" onOpen={vi.fn()} onClose={vi.fn()} />, INDIA)).not.toContain("Report chain");
  });
});
