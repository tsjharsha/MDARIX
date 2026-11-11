import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import {
  OtherReportCard,
  OtherReportPage,
  pickableFor,
  submittedBody,
  submittedProblem,
  type AttachedDetail,
  type SubmittedForm,
} from "./sections/OtherCountries";
import { MarketTree } from "./sections/TreeAnswer";
import { signItems } from "./sections/TreeSign";
import { allMarkets, isOtherKey, marketIn, type AssessmentDetail, type OtherCountryItem } from "./marketAssessment";
import { byCountry, otherCountryOptions } from "./authorityReports";
import { otherLineText } from "./reportability";

// B9b step 7 (screens): a country outside the five markets on the Decision trees page, the Other Regulatory Report's
// own page, the Reports list's country filter and the watch's own line for a country.

function workspace(permissions: string[]): WorkspaceApi {
  return {
    session: { allowed_menu: ["home"], business_permissions: permissions, display_name: "Rita Regulatory" },
    open: vi.fn(),
    notify: vi.fn(),
    work: { products: [], requestOpenInvestigation: vi.fn(), setInvestigationId: vi.fn() },
  } as unknown as WorkspaceApi;
}
const render = (node: ReactNode, permissions: string[] = ["regulatory.review"]) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={workspace(permissions)}>{node}</WorkspaceContext.Provider>);

const GENERIC = "Generic starter questions, not this country's law: confirm with your consultant.";
const australia = (overrides: Partial<OtherCountryItem> = {}): OtherCountryItem => ({
  market: "OTHER",
  key: "OTHER-AU",
  country: "AU",
  country_name: "Australia",
  label: "Australia (other country)",
  generic_note: GENERIC,
  floor: { code: "OTHER-floor-1", title: "Other countries: generic starter questions" },
  question_set: {
    market: "OTHER" as never,
    market_label: "Other country",
    version: "OTHER-starter-1",
    title: "Other country: generic starter questions",
    note: null,
    starter_mark: "Starter",
    questions: [
      {
        id: "OT1",
        text: "Did a death occur?",
        definition: "Death",
        clause: "IMDRF/GHTF common criteria",
        basis: [],
        serious: true,
        note: null,
        starter: true,
      },
    ],
  },
  suggestions: {},
  record_notes: {},
  current: null,
  draft: null,
  evaluation: null,
  history: [],
  clock: null,
  report: null,
  ...overrides,
});
const detail = (other: OtherCountryItem[], on = true): AssessmentDetail =>
  ({
    complaint: {
      id: "c1",
      business_id: "CMP000042",
      complaint_identifier: "SAMPLE-RV-06",
      product_name: "OrbitCare 300",
      version: null,
      country: "Australia",
      description: "The alarm did not sound.",
      severity: "Critical",
      aware_date: "2026-10-07",
    },
    on_watch: true,
    enabled_markets: ["US"],
    preselected: null,
    markets: [],
    scale: { version: "scale-starter-1", starter_mark: "", protected_note: "", levels: [], terms: [] },
    severity: null,
    severity_level: null,
    starter_mark: "Starter",
    practice_label: null,
    training_required: true,
    legacy_decision: null,
    other_countries: other,
    other_countries_on: on,
  }) as AssessmentDetail;

describe("a country outside the five markets on the tree screens", () => {
  it("reads as a market keyed OTHER-<code>, with no harm scale and no practice training", () => {
    const shown = allMarkets(detail([australia()]));
    expect(shown.map((item) => item.market)).toEqual(["OTHER-AU"]);
    expect(isOtherKey("OTHER-AU") && !isOtherKey("US")).toBe(true);
    expect(marketIn(detail([australia()]), "OTHER-AU")?.training).toEqual([]);
    expect(marketIn(detail([australia()]), "OTHER-JP")).toBeUndefined();
    const items = signItems({
      groups: [],
      item: shown[0],
      form: { answers: {}, reasons: {} } as never,
      folded: {},
      harm: { level: "", reason: "", disagreement: "" },
      choice: "follow",
      overrideReason: "",
      trainingNeeded: false,
      trained: false,
    });
    expect(items.map((entry) => entry.text)).not.toContain("The harm level");
  });

  it("shows the generic note on the tree, no harm level, and the report it creates", () => {
    const draft = {
      id: "v1",
      version: 1,
      answers: { OT1: { answer: "YES", rationale: "The distributor reports a death.", evidence: [] } },
      saved_at: "2026-11-10T10:00:00+00:00",
    } as never;
    const data = detail([australia({ draft, evaluation: { suggested: "REPORTABLE", report_type: null, notes: [] } })]);
    const html = render(
      <MarketTree detail={data} item={allMarkets(data)[0]} tree={null} trees={[]} path={null} onSigned={vi.fn()} />,
    );
    expect(html).toContain(`Australia (other country): ${GENERIC.replace("'", "&#x27;")}`);
    expect(html).not.toContain("Harm level");
    expect(html).not.toContain("worked complaints pass");
    expect(html).toContain("The report for Australia");
    expect(html).toContain("Created when you sign reportable");
  });

  it("keeps a country readable, never signable, while the switch is off", () => {
    const data = detail([australia({ evaluation: { suggested: "REPORTABLE", report_type: null, notes: [] } })], false);
    const html = render(
      <MarketTree detail={data} item={allMarkets(data)[0]} tree={null} trees={[]} path={null} onSigned={vi.fn()} />,
    );
    expect(html).not.toContain("Sign as");
    expect(html).toContain("Your role reads this tree");
  });

  it("opens the country's report from a signed reportable conclusion", () => {
    const html = render(
      <OtherReportCard
        country={australia({ report: { id: "r1", state_label: "To be submitted" } })}
        outcome="REPORTABLE"
        signed
      />,
    );
    expect(html).toContain("Open the report (to be submitted)");
    expect(render(<OtherReportCard country={australia()} outcome="NOT_REPORTABLE" signed />)).toContain(
      "No report for Australia.",
    );
  });

  it("offers in the picker only the countries not yet assessed on the complaint", () => {
    const all = [
      { code: "AU", name: "Australia" },
      { code: "JP", name: "Japan" },
    ];
    expect(pickableFor(all, detail([australia()]))).toEqual([{ code: "JP", name: "Japan" }]);
  });
});

const report = (overrides: Partial<AttachedDetail> = {}): AttachedDetail => ({
  id: "r1",
  kind: "INITIAL",
  attached: true,
  follow_up: false,
  market: "OTHER",
  country: "AU",
  country_name: "Australia",
  market_label: "Australia (other country)",
  form_title: "Other Regulatory Report",
  banner: "Report prepared outside MDARIX; MDARIX holds the copy as attached",
  never_submits: "MDARIX never submits a report.",
  generic_note: GENERIC,
  complaint: { id: "c1", ref: "SAMPLE-RV-06" },
  state: "DRAFT",
  state_label: "To be submitted",
  note: null,
  due_on: "2026-11-20",
  provisional: false,
  days_left: 9,
  overdue: false,
  due_source: "CUSTOMER",
  due_source_label: "Due date entered by the customer",
  submissions: [],
  evidence_kinds: { SUBMITTED_CONTENT: ["CONTENT"], ACCEPTANCE: ["ACCEPTED"], REJECTION: ["REJECTED"] },
  evidence_labels: { ACCEPTANCE: "Acknowledgement", REJECTION: "Rejection" },
  route_label: "The authority's own route",
  parent: null,
  follow_ups: [],
  can: {
    submit: true,
    acknowledge: false,
    enter_report_id: false,
    set_due_date: true,
    follow_up: false,
    close: false,
  },
  ...overrides,
});

describe("the Other Regulatory Report's page", () => {
  it("says MDARIX holds the copy, the due date's source, and asks the recorder's signature to record Submitted", () => {
    const html = render(<OtherReportPage detail={report()} onBack={vi.fn()} onChanged={vi.fn()} />);
    expect(html).toContain("Report prepared outside MDARIX; MDARIX holds the copy as attached");
    expect(html).toContain("Due date entered by the customer");
    expect(html).toContain("Record that it was submitted");
    expect(html).toContain("Not issued yet");
    expect(html).toContain("Your password");
    expect(html).toContain("Authenticator code");
    expect(html).toContain("No second person approves it");
    // A viewer reads it and changes nothing.
    const viewer = render(<OtherReportPage detail={report()} onBack={vi.fn()} onChanged={vi.fn()} />, []);
    expect(viewer).not.toContain("Record that it was submitted");
    expect(viewer).toContain("You can read this report");
  });

  it("lists a submission's Report ID and file with its SHA-256, the follow-ups, and Close", () => {
    const html = render(
      <OtherReportPage
        detail={report({
          state: "ACCEPTED",
          state_label: "Acknowledged",
          can: { ...report().can, submit: false, set_due_date: false, follow_up: true, close: true },
          submissions: [
            {
              id: "s1",
              attempt: 1,
              submitted_at: "2026-11-02T10:00:00+00:00",
              report_id: "Not issued yet",
              report_id_pending: true,
              result: "ACCEPTED",
              late: false,
              note: null,
              recorded_by: "Rita Regulatory",
              recorded_at: "2026-11-02T10:05:00+00:00",
              signature_id: "sig1",
              evidence: [
                {
                  id: "e1",
                  kind: "SUBMITTED_CONTENT",
                  kind_label: "Submitted content",
                  outcome: "CONTENT",
                  note: null,
                  file_name: "report.pdf",
                  size: 10,
                  sha256: "ab".repeat(32),
                  received_at: "2026-11-02T10:00:00+00:00",
                  recorded_by: "Rita Regulatory",
                },
              ],
            },
          ],
          follow_ups: [{ id: "f1", number: 1, state: "DRAFT", state_label: "To be submitted", due_on: null }],
        })}
        onBack={vi.fn()}
        onChanged={vi.fn()}
      />,
    );
    expect(html).toContain("Report ID: Not issued yet");
    expect(html).toContain("report.pdf");
    expect(html).toContain(`SHA-256 ${"ab".repeat(32)}`);
    expect(html).not.toContain("Save the Report ID"); // can.enter_report_id is the server's to give
    expect(html).toContain("Follow-up 1");
    expect(html).toContain("Start a follow-up report");
    expect(html).toContain("Close the report");
  });

  it("refuses Submitted without the file, the date, the Report ID (or not issued yet) or the password", () => {
    const form: SubmittedForm = {
      submittedAt: "2026-11-01T10:00",
      reportId: "TGA-1",
      notIssued: false,
      password: "pw",
      code: "",
      note: "",
    };
    const now = new Date("2026-11-11T10:00:00Z");
    expect(submittedProblem(form, false, now)).toBe("Attach the report you submitted");
    expect(submittedProblem({ ...form, submittedAt: "" }, true, now)).toBe("Give when it was submitted");
    expect(submittedProblem({ ...form, submittedAt: "2026-12-01T10:00" }, true, now)).toMatch(/future/);
    expect(submittedProblem({ ...form, reportId: " " }, true, now)).toMatch(/Report ID/);
    expect(submittedProblem({ ...form, reportId: "", notIssued: true }, true, now)).toBeNull();
    expect(submittedProblem({ ...form, password: "" }, true, now)).toBe("Enter your password to sign");
    const body = submittedBody(
      { ...form, notIssued: true },
      { name: "r.pdf", content_type: "application/pdf", data: "" },
    );
    expect(body.report_id).toBe("");
    expect(body.not_issued_yet).toBe(true);
    expect(body.mfa_code).toBeNull();
  });
});

describe("the Reports list's country filter and the watch's line", () => {
  const rows = [
    { market: "US", country: null, market_label: "United States (FDA)" },
    { market: "OTHER", country: "JP", market_label: "Japan (other country)" },
    { market: "OTHER", country: "AU", market_label: "Australia (other country)" },
  ];
  it("filters every other country, or one by name", () => {
    expect(byCountry(rows, "")).toHaveLength(3);
    expect(byCountry(rows, "OTHER").map((row) => row.country)).toEqual(["JP", "AU"]);
    expect(byCountry(rows, "AU").map((row) => row.country)).toEqual(["AU"]);
    expect(otherCountryOptions(rows)).toEqual([
      { code: "AU", label: "Australia (other country)" },
      { code: "JP", label: "Japan (other country)" },
    ]);
  });

  it("says a country's state and its due date's source on the watch", () => {
    const line = {
      country: "JP",
      label: "Japan (other country)",
      state_label: "To be submitted",
      due_on: "2026-11-20",
      due_label: "Due date entered by the customer",
      clock_state: "RUNNING" as const,
      report_id: "r1",
    };
    expect(otherLineText(line)).toMatch(/^Japan \(other country\): to be submitted · due .+ \(due date entered by/);
    expect(otherLineText({ ...line, due_on: null })).toBe("Japan (other country): to be submitted · no due date yet");
  });
});
