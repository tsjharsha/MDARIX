import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { questionNumber } from "../../app/labels";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { MarketPanel, SignedVersion, TrainingPanel, WHY_ASSESSED, otherMarketLine } from "./sections/MarketAssessment";
import {
  EMPTY_SIGN,
  draftBody,
  formOf,
  lowered,
  marketChip,
  signProblem,
  type AssessmentDetail,
  type MarketItem,
  type Question,
  type Scale,
  type Version,
} from "./marketAssessment";

function workspace(permissions: string[]): WorkspaceApi {
  return {
    session: { allowed_menu: ["home"], business_permissions: permissions },
    open: vi.fn(),
    notify: vi.fn(),
    work: { products: [], requestOpenInvestigation: vi.fn(), setInvestigationId: vi.fn() },
  } as unknown as WorkspaceApi;
}
const render = (node: ReactNode, permissions: string[] = ["regulatory.review"]) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={workspace(permissions)}>{node}</WorkspaceContext.Provider>);

const STARTER = "Starter, for your consultant to confirm.";
const question = (id: string, text: string, clause: string, extra: Partial<Question> = {}): Question => ({
  id,
  text,
  definition: `Definition of ${id}`,
  clause,
  basis: ["CFR803_3"],
  serious: false,
  note: null,
  starter: true,
  ...extra,
});
const QUESTIONS = [
  question("US1", "Did a death occur?", "21 CFR 803.50(a)(1)", { serious: true }),
  question(
    "US5",
    "Would the malfunction be likely to cause or contribute to a death or serious injury if it were to recur?",
    "21 CFR 803.50(a)(2)",
    {
      note: "Recurrence is presumed: answer what would follow if it recurred, not whether it will recur. A No needs its reason.",
    },
  ),
];
const SCALE: Scale = {
  version: "scale-starter-1",
  starter_mark: STARTER,
  protected_note:
    "Death, life-threatening harm and permanent impairment sit at or above every market's threshold and cannot be lowered.",
  levels: [
    { code: "MINOR", label: "Minor", terms: [{ code: "MINOR_INJURY", label: "Minor injury" }], thresholds: [] },
    { code: "SERIOUS", label: "Serious", terms: [], thresholds: [{ market: "US", label: "US serious injury" }] },
    {
      code: "CRITICAL",
      label: "Critical",
      terms: [{ code: "LIFE_THREATENING", label: "Life-threatening illness or injury" }],
      thresholds: [],
    },
  ],
  terms: [
    { code: "MINOR_INJURY", label: "Minor injury", level: "MINOR", protected: false },
    { code: "LIFE_THREATENING", label: "Life-threatening illness or injury", level: "CRITICAL", protected: true },
  ],
};
const version = (overrides: Partial<Version> = {}): Version => ({
  id: "v1",
  market: "US",
  version: 1,
  question_set: "US-starter-1",
  question_set_current: true,
  answers: { US1: { answer: "NO", rationale: "No death reported by the nurse.", evidence: [] } },
  harm_level: "CRITICAL",
  harm_code: null,
  harm_level_reason: null,
  scale_version: "scale-starter-1",
  scale_disagreement_reason: null,
  suggested_conclusion: "PENDING_INFORMATION",
  conclusion: null,
  override_reason: null,
  report_type: null,
  report_type_label: null,
  window_name: "FDA MDR",
  due_on: "2026-11-20",
  filing_reference: null,
  filed_on: null,
  signed_record_id: null,
  content_fingerprint: null,
  signed_by: null,
  signed_at: null,
  superseded: false,
  sample: false,
  created_by: "Priya Sharma",
  saved_at: "2026-10-31T10:00:00+00:00",
  ...overrides,
});
const item = (overrides: Partial<MarketItem> = {}): MarketItem => ({
  market: "US",
  label: "United States (FDA)",
  enabled: true,
  preselected: true,
  required: true,
  question_set: {
    market: "US",
    market_label: "United States (FDA)",
    version: "US-starter-1",
    title: "US medical device reporting (21 CFR Part 803)",
    note: null,
    starter_mark: STARTER,
    questions: QUESTIONS,
  },
  threshold: { level: "SERIOUS", label: "US serious injury" },
  current: null,
  draft: version(),
  evaluation: {
    suggested: "PENDING_INFORMATION",
    report_type: null,
    notes: ["An Unknown answer could make the event reportable."],
  },
  disagreement: null,
  history: [],
  clock: {
    window: "FDA MDR (30 calendar days)",
    due_date: "2026-11-20",
    days_left: 20,
    state: "RUNNING",
    source: "WINDOW",
  },
  training: [
    {
      code: "QUESTION_SET_US",
      title: "US medical device reporting: starter questions",
      version: "US-starter-1",
      statement:
        "I have read the questions of US medical device reporting (21 CFR Part 803), MDARIX starter, version 1",
      state: "MISSING",
      held_version: null,
      trained_at: null,
      method: null,
    },
  ],
  trained_colleagues: ["Rahul"],
  ...overrides,
});
const detail = (market: MarketItem): AssessmentDetail => ({
  complaint: {
    id: "c1",
    business_id: "CMP000042",
    complaint_identifier: "SAMPLE-RV-06",
    product_name: "OrbitCare 300",
    version: "Rev B",
    country: "US",
    description: "The pressure alarm did not sound during an occlusion.",
    severity: "Critical",
    aware_date: "2026-10-07",
  },
  on_watch: true,
  enabled_markets: ["US", "EU_NI"],
  preselected: "US",
  markets: [market],
  scale: SCALE,
  severity: "Critical",
  severity_level: "CRITICAL",
  starter_mark: STARTER,
  practice_label:
    "Practice record: made in a free trial with sample or de-identified data. Not your regulatory record.",
  training_required: true,
  legacy_decision: null,
});

describe("the per-market assessment rules", () => {
  it("reads each market's state as a chip", () => {
    const base = { market: "US" as const, label: "US", preselected: true, report_type_label: null, clock: null };
    expect(marketChip({ ...base, state: "REPORTABLE", suggested: null, filed: false })).toEqual({
      label: "US: reportable · filing not recorded",
      tone: "warning",
    });
    expect(marketChip({ ...base, state: "REPORTABLE", suggested: null, filed: true }).tone).toBe("good");
    expect(marketChip({ ...base, market: "EU_NI", state: "NOT_STARTED", suggested: null, filed: false }).label).toBe(
      "EU and Northern Ireland: not assessed",
    );
  });

  it("refuses not reportable while an Unknown remains, an override without a reason, and signing untrained", () => {
    const form = {
      answers: {
        US1: { answer: "NO" as const, rationale: "No death reported by the nurse.", evidence: [] },
        US5: { answer: "UNKNOWN" as const, rationale: "Recurrence effect not judged yet.", evidence: [] },
      },
      harm: { level: "CRITICAL", term: "", reason: "" },
      disagreementReason: "",
    };
    const sign = { ...EMPTY_SIGN, password: "secret" };
    expect(
      signProblem(QUESTIONS, form, { ...sign, conclusion: "NOT_REPORTABLE" }, "PENDING_INFORMATION", null, true),
    ).toContain("Unknown is never No");
    expect(
      signProblem(QUESTIONS, form, { ...sign, conclusion: "REPORTABLE" }, "PENDING_INFORMATION", null, true),
    ).toContain("override");
    const reasoned = { ...sign, conclusion: "REPORTABLE" as const, overrideReason: "Report when unsure, QP-08" };
    expect(signProblem(QUESTIONS, form, reasoned, "PENDING_INFORMATION", null, false)).toContain("practice training");
    expect(signProblem(QUESTIONS, form, reasoned, "PENDING_INFORMATION", null, true)).toBeNull();
    const noReason = {
      ...form,
      answers: { ...form.answers, US5: { answer: "NO" as const, rationale: "", evidence: [] } },
    };
    expect(signProblem(QUESTIONS, noReason, reasoned, "NOT_REPORTABLE", null, true)).toContain("Question 5 is No");
    expect(signProblem(QUESTIONS, form, reasoned, "PENDING_INFORMATION", "Against the scale", true)).toContain(
      "written reason",
    );
  });

  it("starts from the saved draft, or the QMS severity's mapped level, and sends what the form holds", () => {
    expect(formOf(item(), "SERIOUS").harm.level).toBe("CRITICAL");
    expect(formOf(item({ draft: null }), "SERIOUS").harm.level).toBe("SERIOUS");
    const body = draftBody({ answers: {}, harm: { level: "", term: "", reason: "  a  b " }, disagreementReason: "" });
    expect(body).toEqual({
      answers: {},
      harm_level: null,
      harm_code: null,
      harm_level_reason: "a b",
      scale_disagreement_reason: "",
    });
    expect(lowered(SCALE, { level: "MINOR", term: "LIFE_THREATENING", reason: "" })).toBe(true);
    expect(lowered(SCALE, { level: "CRITICAL", term: "LIFE_THREATENING", reason: "" })).toBe(false);
  });
});

describe("the assessment screen", () => {
  it("shows every question with its clause and the starter mark, the scale with its threshold, and the training", () => {
    const html = render(<MarketPanel detail={detail(item())} item={item()} onSaved={vi.fn()} />);
    expect(html).toContain("1.</strong> Did a death occur?");
    expect(html).not.toContain("US1.");
    expect(html).toContain("21 CFR 803.50(a)(2)");
    expect(html.split("Starter, for your consultant to confirm</span>").length - 1).toBe(QUESTIONS.length + 1);
    expect(html).toContain("Recurrence is presumed");
    expect(html).toContain("US serious injury threshold");
    expect(html).toContain("<strong>critical</strong>, at or above the US serious injury threshold");
    expect(html).toContain("Before you sign: practice training on MDARIX starter, version 1");
    expect(html).toContain("Trained colleagues who can sign instead: Rahul.");
    expect(html).toContain("Suggested: Pending information");
    expect(html).toContain("Save and sign");
    expect(html).toContain("Authenticator code");
  });

  it("keeps each definition behind an accessible Show definition toggle, collapsed at first", () => {
    const html = render(<MarketPanel detail={detail(item())} item={item()} onSaved={vi.fn()} />);
    const toggles = html.match(/<button type="button" class="ac-link uw-ma-definition-toggle"[^>]*>/g) ?? [];
    expect(toggles).toHaveLength(QUESTIONS.length);
    expect(toggles[0]).toContain('aria-expanded="false"');
    const controls = /aria-controls="([^"]+)"/.exec(toggles[0] ?? "")?.[1];
    expect(html).toContain(`<div id="${controls}" hidden=""><p class="ac-muted">Definition of US1</p>`);
    expect(html.split("Show definition").length - 1).toBe(QUESTIONS.length);
    // Read-only: the answers are disabled, the toggle is not.
    const readOnly = render(<MarketPanel detail={detail(item())} item={item()} onSaved={vi.fn()} />, []);
    expect(readOnly).toMatch(/<input type="radio" disabled=""/);
    expect(readOnly).not.toMatch(/uw-ma-definition-toggle"[^>]*disabled/);
  });

  it("shows only the judgement questions to answer; the record's facts wait for Confirm (0.10.72, B1)", () => {
    const facts = item({
      draft: version({ answers: {} }),
      evaluation: { suggested: "REPORTABLE", report_type: "US_30_DAY", notes: [] },
      suggestions: {
        US1: {
          answer: "NO",
          source: "From the complaint record: no death was reported",
          evidence: "Patient outcome fields",
        },
      },
      training: [{ ...item().training[0], state: "CURRENT", held_version: "US-starter-1" }],
    });
    const html = render(<MarketPanel detail={detail(facts)} item={facts} onSaved={vi.fn()} />);
    // The fact: suggested with its source and a Confirm, no radios for it; the judgement question: radios.
    expect(html).toContain("<strong>Suggested: No</strong> · From the complaint record: no death was reported");
    expect(html).toContain(">Confirm</button>");
    expect(html).not.toContain('name="answer-US1"');
    expect(html).toContain('name="answer-US5"');
    // Revealed on request: the full scale, the evidence ticks, the definitions.
    expect(html).toMatch(/<ol id="[^"]+" class="uw-ma-levels" hidden="">/);
    expect(html).toMatch(/class="uw-ma-evidence" aria-label="Evidence relied on" hidden=""/);
    expect(html).toContain("Show scale");
    // Training read: one line.
    expect(html).toContain("You have read: US guide v1 · ");
    expect(questionNumber("X1")).toBe("Extra 1");
    expect(questionNumber("US2A")).toBe("2a");
    expect(html).not.toContain("Before you sign");
    // The conclusion is never pre-selected, even with a suggestion.
    expect(html).not.toMatch(/name="conclusion-US" checked=""/);
    expect(html).toContain("Reportable (the suggestion)");
  });

  it("records a confirmed answer as confirmed, and shows how the signed answers came", () => {
    const body = draftBody({
      answers: { US1: { answer: "NO", rationale: "From the complaint record", evidence: [], origin: "CONFIRMED" } },
      harm: { level: "", term: "", reason: "" },
      disagreementReason: "",
    });
    expect(body.answers.US1.confirmed).toBe(true);
    const signed = version({
      conclusion: "REPORTABLE",
      signed_by: "Asha",
      signed_at: "2026-11-02T10:00:00+00:00",
      answers: {
        US1: { answer: "NO", rationale: "From the complaint record", evidence: [], origin: "CONFIRMED" },
        US4: { answer: "NO", rationale: "Checked: in specification.", evidence: [], origin: "CORRECTED" },
        US5: { answer: "YES", rationale: "Wrong reading.", evidence: [], origin: "ENTERED" },
      },
    });
    expect(render(<SignedVersion version={signed} complaintId="c1" onSaved={vi.fn()} />)).toContain(
      "Answers: 1 confirmed from the complaint record, 1 corrected from the record&#x27;s suggestion, 1 entered.",
    );
  });

  it("lets a non-trial organization sign without the practice training, and still record it", () => {
    const pilot = { ...detail(item()), training_required: false, practice_label: null };
    const html = render(<MarketPanel detail={pilot} item={item()} onSaved={vi.fn()} />);
    expect(html).not.toContain("Before you sign");
    expect(html).toContain("Training record on MDARIX starter, version 1");
    expect(html).toContain("signing here does not wait for this one");
  });

  it("is read-only without regulatory review or approval", () => {
    const html = render(<MarketPanel detail={detail(item())} item={item()} onSaved={vi.fn()} />, []);
    expect(html).not.toContain("Save and sign");
    expect(html).not.toContain("Before you sign");
  });

  it("shows a signed conclusion with its override, its scale reason and the filing to record", () => {
    const signed = version({
      conclusion: "REPORTABLE",
      suggested_conclusion: "PENDING_INFORMATION",
      override_reason: "Report when unsure, QP-08",
      report_type_label: "30-calendar-day report (21 CFR 803.50)",
      signed_by: "Priya Sharma",
      signed_at: "2026-10-31T10:05:00+00:00",
    });
    const html = render(<SignedVersion version={signed} complaintId="c1" onSaved={vi.fn()} />);
    expect(html).toContain("Reportable · version 1");
    expect(html).toContain("30-calendar-day report (21 CFR 803.50)");
    expect(html).toContain("Overrides the suggestion (pending information): Report when unsure, QP-08");
    // A US conclusion opens its report worksheet (0.10.58); EU/NI and GB keep the filing reference and date.
    expect(html).toContain("Open the report worksheet");
    expect(html).not.toContain("Record the filing");
    expect(html).toContain("MDARIX submits nothing");
    const eu = render(<SignedVersion version={{ ...signed, market: "EU_NI" }} complaintId="c1" onSaved={vi.fn()} />);
    expect(eu).toContain("Record the filing");
    const filed = render(
      <SignedVersion
        version={{ ...signed, market: "EU_NI", filed_on: "2026-10-31", filing_reference: "MDR-1" }}
        complaintId="c1"
        onSaved={vi.fn()}
      />,
    );
    expect(filed).toContain("MDR-1");
    expect(filed).not.toContain("Record the filing");
    // 0.10.70: classic keeps the worksheet as the main button; on the new navigation the drawer's one main button is
    // the complaint's next step, so the worksheet is secondary.
    expect(html).toMatch(/class="ac-primary"[^>]*>.*Open the report worksheet/);
    const fresh = renderToStaticMarkup(
      <WorkspaceContext.Provider value={{ ...workspace(["regulatory.review"]), navigation: "new" }}>
        <SignedVersion version={signed} complaintId="c1" onSaved={vi.fn()} />
      </WorkspaceContext.Provider>,
    );
    expect(fresh).toMatch(/class="ac-secondary"[^>]*>.*Open the report worksheet/);
    expect(fresh).not.toMatch(/class="ac-primary"/);
  });

  it("says why a market other than the event's own is assessed, as starter wording (0.10.70)", () => {
    expect(otherMarketLine("Market conclusion, India (CDSCO)", "US")).toBe(true);
    expect(otherMarketLine("Market conclusion, United States (FDA)", "US")).toBe(false);
    expect(otherMarketLine("Disposition", "US")).toBe(false);
    const india = render(
      <MarketPanel
        item={item({ market: "IN", label: "India (CDSCO)", preselected: false })}
        detail={{
          ...detail(item()),
          markets: [item({ preselected: true }), item({ market: "IN", preselected: false })],
        }}
        onSaved={vi.fn()}
      />,
    );
    expect(india).toContain(WHY_ASSESSED);
    expect(india).toContain("Starter, for your consultant to confirm.");
    const own = render(
      <MarketPanel item={item({ preselected: true })} detail={detail(item({ preselected: true }))} onSaved={vi.fn()} />,
    );
    expect(own).not.toContain(WHY_ASSESSED);
  });

  it("names the document and version to acknowledge", () => {
    const html = render(<TrainingPanel documents={item().training} colleagues={[]} required onDone={vi.fn()} />);
    expect(html).toContain(
      "I have read the questions of US medical device reporting (21 CFR Part 803), MDARIX starter, version 1",
    );
    expect(html).toContain("No colleague holds a current acknowledgement yet.");
    expect(html).toContain("ISO 13485 clause 6.2");
  });
});
