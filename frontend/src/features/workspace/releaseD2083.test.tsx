import reportsTab from "./sections/ReportsTab.tsx?raw";
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { addressFor } from "./workspaceAddress";
import { treePlace, type Trees } from "./decisionTrees";
import { DecisionTreesSection } from "./sections/DecisionTrees";
import { firstComplaint, groupClause } from "./sections/TreeAnswer";
import { conclusionOf, signItems } from "./sections/TreeSign";
import { guideChanges } from "./sections/TreeEdit";
import { thingsToGive } from "./sections/ReportBody";
import { ReportsSection } from "./sections/ReportsTab";
import type { ReportDetail, WorksheetField } from "./authorityReports";
import { GUIDES, questionMark, type GuideVersion } from "./decisionGuides";
import { STARTER_LABEL, isStarterVersion } from "../shared/standards";
import {
  foldedRuns,
  groupQuestions,
  questionState,
  runLabel,
  signChecklist,
  treeAnswers,
  treeFormOf,
  whyChips,
  shownOutcome,
  type TreeForm,
} from "./treeAnswer";
import type { AssessmentDetail, MarketItem, Question } from "./marketAssessment";

// 0.10.83, round D2 "Decide and report": the Decision trees tab is the questionnaire (D2.1-D2.3).

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && (resources.data[path] ?? resources.data[path.split("?")[0]])) ?? null,
    reload: () => undefined,
  }),
}));

const api = (permissions = ["regulatory.review", "regulatory.approve"], persona = "regulatory", shownTab = "") =>
  ({
    session: { user_id: "u1", display_name: "Asha Menon", allowed_menu: ["home"], business_permissions: permissions },
    work: { products: [], investigations: [] },
    open: vi.fn(),
    notify: vi.fn(),
    reportTab: vi.fn(),
    shownTab,
    navigation: "new",
    isTrial: true,
    persona,
  }) as unknown as WorkspaceApi;

const render = (node: ReactNode, value: WorkspaceApi = api()) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

const INJURY = "Serious injury (21 CFR 803.3(w)) is an injury or illness that is life-threatening …";
const q = (id: string, text: string, clause: string, definition = "The regulation's definition."): Question => ({
  id,
  text,
  clause,
  definition,
  basis: [],
  serious: false,
  note: null,
  starter: true,
});
const US_QUESTIONS: Question[] = [
  q("US1", "Did a death occur?", "21 CFR 803.50(a)(1)"),
  q("US2A", "Serious injury, part (a): is the injury or illness life-threatening?", "21 CFR 803.3(w)(1)", INJURY),
  q("US2B", "Serious injury, part (b): does it result in permanent impairment?", "21 CFR 803.3(w)(2)", INJURY),
  q("US2C", "Serious injury, part (c): does it need intervention?", "21 CFR 803.3(w)(3)", INJURY),
  q("US3", "Did the device cause or contribute to the death or serious injury?", "21 CFR 803.3(c)"),
  q("US4", "Did the device malfunction?", "21 CFR 803.3(k)"),
  q("US5", "Would the malfunction be likely to cause harm if it recurred?", "21 CFR 803.50(a)(2)"),
  q("US6", "Is remedial action needed?", "21 CFR 803.53"),
];
const FACTS = {
  US1: { answer: "NO" as const, source: "From the complaint record: no death was reported", evidence: "Patient" },
  US4: { answer: "YES" as const, source: "From the complaint record: a malfunction was reported", evidence: "M" },
};
const NOTE = "The record says no serious injury was reported · severity “No harm”.";

function usItem(over: Partial<MarketItem> = {}): MarketItem {
  return {
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
      starter_mark: "",
      questions: US_QUESTIONS,
    },
    suggestions: FACTS,
    record_notes: { US2A: NOTE, US2B: NOTE, US2C: NOTE },
    threshold: { level: "SERIOUS", label: "US serious injury" },
    current: null,
    draft: null,
    evaluation: null,
    disagreement: null,
    history: [],
    clock: null,
    training: [],
    trained_colleagues: [],
    ...over,
  };
}

const draft = (answers: Record<string, string>, extra: Record<string, unknown> = {}) =>
  ({
    id: "d1",
    market: "US",
    version: 1,
    question_set: "US-starter-1",
    question_set_current: true,
    answers: Object.fromEntries(
      Object.entries(answers).map(([key, answer]) => [
        key,
        { answer, rationale: key in FACTS ? FACTS[key as "US1"].source : "Read the nurse's report", evidence: [] },
      ]),
    ),
    harm_level: "NEGLIGIBLE",
    harm_code: null,
    harm_level_reason: null,
    scale_version: "scale-starter-1",
    scale_disagreement_reason: null,
    suggested_conclusion: "REPORTABLE",
    conclusion: null,
    override_reason: null,
    report_type: "US_30_DAY",
    report_type_label: "30-calendar-day report (21 CFR 803.50)",
    window_name: null,
    due_on: "2026-12-01",
    filing_reference: null,
    filed_on: null,
    signed_record_id: null,
    content_fingerprint: null,
    signed_by: null,
    signed_at: null,
    superseded: false,
    sample: false,
    created_by: "Asha Menon",
    saved_at: "2026-11-03T10:00:00+00:00",
    ...extra,
  }) as MarketItem["draft"];

const detailOf = (item: MarketItem): AssessmentDetail =>
  ({
    complaint: {
      id: "c-rv11",
      business_id: "CMP000044",
      complaint_identifier: "SAMPLE-RV-11",
      product_name: "PulseWatch 410",
      version: "Rev A",
      country: "US",
      description: "SpO2 read 4 to 6 points high on two patients. No harm was reported.",
      severity: "No harm",
      aware_date: "2026-11-01",
      needs: [],
    },
    on_watch: true,
    enabled_markets: ["US", "IN"],
    preselected: "US",
    markets: [item],
    scale: { version: "scale-starter-1", starter_mark: "", protected_note: "", levels: [], terms: [] },
    severity: "No harm",
    severity_level: "NEGLIGIBLE",
    severity_source: "The triage record",
    starter_mark: "",
    practice_label: null,
    training_required: true,
    legacy_decision: null,
  }) as AssessmentDetail;

const TREES: Trees = {
  markets: [
    {
      market: "US",
      label: "United States (FDA)",
      title: "US medical device reporting (21 CFR Part 803)",
      version: 2,
      status: "APPROVED",
      status_label: "Approved",
      version_label: "Your version 2 · approved 28 Oct 2026",
      enabled: true,
      tests: { passed: 12, total: 12, current: true },
      questions: [],
      form: { title: "Form FDA 3500A worksheet (eMDR)", starter: false },
    },
    {
      market: "IN",
      label: "India (CDSCO)",
      title: "India adverse event reporting",
      version: 1,
      status: "STARTER",
      status_label: "Starter",
      version_label: "MDARIX starter · version 1",
      enabled: true,
      tests: { passed: 8, total: 8, current: true },
      questions: [],
      form: { title: "MvPI Medical Device Adverse Event Reporting Form worksheet", starter: false },
      foreign: "CDSCO's MvPI guidance: check it for events outside India.",
    },
  ],
  complaints: [
    { id: "c-rv09", ref: "SAMPLE-RV-09", description: "Alarm too quiet", markets: ["US"], signed: ["US"] },
    { id: "c-rv11", ref: "SAMPLE-RV-11", description: "SpO2 read high", markets: [], signed: [] },
  ],
  complaint: null,
  paths: {},
  never_decides: "",
  starter_mark: "",
};

function show(item: MarketItem, value: WorkspaceApi = api()) {
  resources.data = {
    "/api/v1/decision-trees": TREES,
    "/api/v1/complaints/c-rv11/market-assessments": detailOf(item),
  };
  return render(<DecisionTreesSection />, value);
}

const ANSWERED = { US1: "NO", US2A: "NO", US2B: "NO", US2C: "NO", US4: "YES", US5: "YES", US6: "NO" };

describe("D2.1-D2.3: the tree is the questionnaire", () => {
  it("groups a definition's criteria into one card with one reason", () => {
    const groups = groupQuestions(US_QUESTIONS);
    expect(groups.map((group) => group.title ?? group.key)).toEqual([
      "US1",
      "Serious injury",
      "US3",
      "US4",
      "US5",
      "US6",
    ]);
    expect(groups[1].questions.map((question) => question.id)).toEqual(["US2A", "US2B", "US2C"]);
  });

  it("opens on the first complaint with nothing signed, unless one is asked for", () => {
    expect(firstComplaint(TREES, null)).toBe("c-rv11");
    expect(firstComplaint(TREES, "c-rv09")).toBe("c-rv09");
    expect(addressFor(treePlace(null, "c-rv11"))).toBe("/app/decision-trees?complaint=c-rv11");
  });

  it("offers each fact from the record as one line to confirm, and never pre-fills a judgement", () => {
    const html = show(usItem());
    expect(html).toContain("Confirm No</button>");
    expect(html).toContain("From the complaint record: no death was reported");
    expect(html).toContain("Confirm Yes</button>");
    // Serious injury: a judgement, the record's words beside it, no answer chosen.
    expect(html).toContain("Serious injury");
    expect(html).toContain('<span class="dt-tag is-judge">Your judgement</span>');
    expect(html).toContain(NOTE.replace(/“|”/g, (mark) => mark));
    expect(html).not.toMatch(/class="dt-ab" aria-pressed="true"/);
    // The complaint's own words, and the outcome before any answer.
    expect(html).toContain("“SpO2 read 4 to 6 points high on two patients. No harm was reported.”");
    expect(html).toContain("Not decided yet");
  });

  it("folds the questions earlier answers make unnecessary into one grey line saying why", () => {
    const folded = { US3: "Not asked: no death and no serious injury" };
    const item = usItem({
      draft: draft(ANSWERED),
      evaluation: { suggested: "REPORTABLE", report_type: "US_30_DAY", notes: [], not_asked: folded },
      clock: {
        window: "30 days",
        due_date: "2026-12-01",
        due_label: "Tue 1 Dec 2026, 23:59 EST",
        days_left: 28,
        state: "RUNNING",
        source: "REGULATION",
      },
    });
    const html = show(item);
    expect(html).toContain("<b>Q3</b> not asked: no death and no serious injury");
    expect(html).not.toContain("Did the device cause or contribute");
    // The outcome updates live: reportable, its type and rule, the due date, and the Why chips.
    expect(html).toContain('<p class="dt-big">Reportable</p>');
    expect(html).toContain("30-calendar-day report (21 CFR 803.50)");
    expect(html).toContain("Tue 1 Dec 2026, 23:59 EST");
    expect(html).toContain('href="#q-US4">Q4 Yes</a>');
    expect(html).toContain('href="#q-US5">Q5 Yes</a>');
    // The phone's sticky outcome bar sits below Q1 and carries Sign.
    expect(html.indexOf('class="dt-mini"')).toBeGreaterThan(html.indexOf('id="q-US1"'));
    expect(html.indexOf('class="dt-mini"')).toBeLessThan(html.indexOf('id="g-US2A"'));
    expect(html).toContain("Reportable · 30 days");
  });

  it("asks a reason for each judgement and each fact changed from the record, never for a confirmed fact", () => {
    const groups = groupQuestions(US_QUESTIONS);
    const item = usItem();
    const form = { answers: { US1: "NO", US4: "NO", US2A: "NO" } as TreeForm["answers"], reasons: {} };
    const folded = {};
    expect(questionState(US_QUESTIONS[0], item, form, folded)).toMatchObject({ changed: false, needsReason: false });
    expect(questionState(US_QUESTIONS[5], item, form, folded)).toMatchObject({ changed: true, needsReason: true });
    expect(questionState(US_QUESTIONS[1], item, form, folded).needsReason).toBe(true);
    const checks = signChecklist(groups, item, form, folded);
    expect(checks.map((check) => check.text)).toEqual([
      "5 questions to answer",
      "Facts from the record confirmed",
      "A one-line reason for Q2, Q4",
    ]);
    // One reason covers the serious-injury criteria; a confirmed fact cites the record.
    const sent = treeAnswers(groups, item, { ...form, reasons: { US2A: "Nobody was harmed, per the nurse" } }, folded);
    expect(sent.US1).toMatchObject({ rationale: FACTS.US1.source, confirmed: true });
    expect(sent.US2A).toMatchObject({ rationale: "Nobody was harmed, per the nurse", confirmed: false });
    expect(sent.US4).toMatchObject({ rationale: "", confirmed: false });
  });

  it("reads a saved draft back: answers, and each group's own reason", () => {
    const groups = groupQuestions(US_QUESTIONS);
    const form = treeFormOf(usItem({ draft: draft(ANSWERED) }), groups);
    expect(form.answers.US2B).toBe("NO");
    expect(form.reasons).toEqual({
      US2A: "Read the nurse's report",
      US5: "Read the nurse's report",
      US6: "Read the nurse's report",
    });
  });

  it("names the Why chips and the folded runs by question number", () => {
    const form = { answers: { US1: "NO", US4: "YES", US5: "UNKNOWN" } as TreeForm["answers"], reasons: {} };
    expect(whyChips(US_QUESTIONS, form, {}, "REPORTABLE").map((chip) => chip.label)).toEqual(["Q4 Yes", "Q5 Unknown"]);
    expect(whyChips(US_QUESTIONS, form, {}, "PENDING_INFORMATION").map((chip) => chip.label)).toEqual(["Q5 Unknown"]);
    const runs = foldedRuns(US_QUESTIONS, { US5: "Not asked: no malfunction", US6: "Not asked: no malfunction" });
    expect(runs.map((run) => runLabel(run.ids))).toEqual(["Q5–Q6"]);
  });
});

describe("D2.1-D2.3: a group names its shared clause", () => {
  it("cuts the criteria's clauses to what they share", () => {
    expect(groupClause(US_QUESTIONS.slice(1, 4))).toBe("21 CFR 803.3(w)");
    expect(groupClause(US_QUESTIONS.slice(0, 1))).toBe("21 CFR 803.50(a)(1)");
  });
});

const FOLDED = { US3: "Not asked: no death and no serious injury" };
const READY = usItem({
  draft: draft(ANSWERED),
  evaluation: { suggested: "REPORTABLE", report_type: "US_30_DAY", notes: [], not_asked: FOLDED },
  training: [
    {
      code: "QUESTION_SET_US",
      title: "US guide",
      version: "US-v2",
      statement: "I have read it",
      state: "MISSING",
      held_version: null,
      trained_at: null,
      method: null,
    },
  ],
});

describe("D2.4: signing in about four actions", () => {
  it("puts the outcome and Sign in one card, follows the outcome by default, and lists what stands before Sign", () => {
    const html = show(READY);
    const card = html.slice(html.indexOf('id="dt-outcome"'));
    expect(card).toContain('<p class="dt-big">Reportable</p>');
    expect(card).toMatch(/<input type="radio" name="choice-US" checked=""\/>Follow the outcome/);
    expect(card).toContain("Every question answered");
    expect(card).toContain("A reason for each judgement");
    expect(card).toContain('aria-label="Your password"');
    // The training confirmation is one line under the password.
    expect(card.indexOf("training record, ISO 13485 6.2")).toBeGreaterThan(card.indexOf('aria-label="Your password"'));
    expect(card).toContain("Your training confirmation");
    expect(card).toContain("Sign as Asha Menon");
    expect(card).toMatch(/<button type="submit" class="ac-primary dt-sign-btn" disabled=""/);
  });

  it("tells a screen reader which items before Sign are done and which are still to do (0.10.88, DEV-10)", () => {
    const list = show(READY).match(/<ul class="dt-check"[^>]*>(.*?)<\/ul>/)?.[1] ?? "";
    // The tick and the circle are hidden from assistive technology, so the words carry the state.
    expect(list).toMatch(/<span class="sr-only">Done: <\/span>Every question answered/);
    expect(list).toMatch(/<span class="sr-only">To do: <\/span>Your training confirmation/);
  });

  it("lets the real role sign, never the persona", () => {
    const executive = show(READY, api(["regulatory.review"], "executive"));
    expect(executive).toContain("Sign as Asha Menon");
    const reader = show(READY, api(["records.read"], "regulatory"));
    expect(reader).not.toContain("Sign as");
    expect(reader).toContain("Your role reads this tree. A Regulatory Leader or Quality Leader signs it.");
  });

  it("turns each answer into text with its reason once signed, with who signed, when and what it means", () => {
    const current = {
      ...draft(ANSWERED, {
        conclusion: "REPORTABLE",
        signed_by: "Asha Menon",
        signed_at: "2026-11-02T09:02:00Z",
      })!,
    };
    const html = show(usItem({ current, draft: null }));
    expect(html).not.toContain('class="dt-ab"');
    expect(html).toContain('<b class="dt-given">✓ No</b>');
    expect(html).toContain('<p class="dt-reason-text">Read the nurse&#x27;s report</p>');
    expect(html).toMatch(/<b>Asha Menon<\/b> · 2 Nov 2026, \d\d:\d\d · meaning: signed reportable/);
    expect(html).not.toContain("Sign as");
  });

  it("signs the outcome when followed and the other conclusion when overridden; pending only to reportable", () => {
    expect(conclusionOf("REPORTABLE", "follow")).toBe("REPORTABLE");
    expect(conclusionOf("REPORTABLE", "override")).toBe("NOT_REPORTABLE");
    expect(conclusionOf("PENDING_INFORMATION", "follow")).toBeNull();
    expect(conclusionOf("PENDING_INFORMATION", "override")).toBe("REPORTABLE");
    const groups = groupQuestions(US_QUESTIONS);
    const form = treeFormOf(READY, groups);
    const harm = { level: "NEGLIGIBLE", reason: "", disagreement: "" };
    const base = { groups, item: READY, form, folded: FOLDED, harm, trainingNeeded: true, trained: true };
    expect(signItems({ ...base, choice: "follow", overrideReason: "" }).every((entry) => entry.ok)).toBe(true);
    expect(signItems({ ...base, choice: "override", overrideReason: "no" }).map((entry) => entry.text)).toContain(
      "Your reason for overriding the outcome",
    );
  });
});

describe("D2.5: the form for the incident's country", () => {
  it("names the form a reportable outcome creates, and flags where another market may also apply, as advice", () => {
    const html = show(READY);
    expect(html).toContain("The form for this incident&#x27;s country");
    expect(html).toContain("<b>Form FDA 3500A (eMDR)</b>");
    expect(html).toContain("Created when you sign reportable");
    expect(html).toContain(
      "<b>May also apply</b><span>CDSCO&#x27;s MvPI guidance: check it for events outside India.</span>",
    );
    expect(html).toContain("Starter, for your consultant to confirm · no second report is created");
  });

  it("opens the report once signed, and says no report when not reportable", () => {
    const current = draft(ANSWERED, {
      conclusion: "REPORTABLE",
      signed_by: "Asha Menon",
      signed_at: "2026-11-02T09:02:00Z",
    });
    resources.data = {
      "/api/v1/decision-trees": TREES,
      "/api/v1/decision-trees?complaint_id=c-rv11": {
        ...TREES,
        paths: {
          US: { market: "US", label: "", nodes: [], outcome: {}, report: { id: "r1", state: "DRAFT" }, has_form: true },
        },
      },
      "/api/v1/complaints/c-rv11/market-assessments": detailOf(usItem({ current, draft: null })),
    };
    expect(render(<DecisionTreesSection />)).toContain("Open the report");
    const not = usItem({
      draft: draft(ANSWERED),
      evaluation: { suggested: "NOT_REPORTABLE", report_type: null, notes: [], not_asked: FOLDED },
    });
    const html = show(not);
    expect(html).toContain("No report for United States (FDA).");
    expect(html).not.toContain("May also apply");
  });
});

const guideVersion = (over: Partial<GuideVersion>): GuideVersion =>
  ({
    version: 2,
    code: "US-v2",
    state: "PUBLISHED",
    state_label: "In use",
    starter: false,
    approved_by: "Rahul Iyer",
    published_at: "2026-10-30T10:00:00Z",
    sample: false,
    market: "US",
    market_label: "United States (FDA)",
    title: "US medical device reporting (21 CFR Part 803)",
    based_on: null,
    question_set: { ...usItem().question_set, questions: US_QUESTIONS.slice(0, 2) },
    test_cases: [],
    test_results: { results: [], passed: 6, failed: 0, current: true, run_at: null, run_by: "" },
    problems: [],
    change_reason: null,
    editors: [],
    requested_by: null,
    requested_at: null,
    approved_at: null,
    signature: null,
    editable: false,
    catalog: [],
    answer_labels: {},
    expected_labels: {} as GuideVersion["expected_labels"],
    report_types: [],
    core_rule: "",
    never_decides: "",
    scale_note: "",
    starter_mark: "",
    practice_label: null,
    ...over,
  }) as GuideVersion;

const IN_USE = guideVersion({});
const PREPARED = guideVersion({
  version: 3,
  code: "US-v3",
  state: "AWAITING_APPROVAL",
  requested_by: "Asha Menon",
  change_reason: "Explain question 1 for our pumps",
  approval: { may_approve: true, same_person: false, approvers: ["Rahul Iyer"], message: null },
  question_set: {
    ...IN_USE.question_set,
    questions: [
      { ...US_QUESTIONS[0], explanation: "A death of anyone the device touched." },
      US_QUESTIONS[1],
      { ...q("X1", "Is the device part of VMSR?", ""), extra: true },
    ],
  },
});

function showEdit(open: GuideVersion | null, permissions?: string[]) {
  resources.data = {
    "/api/v1/decision-trees": TREES,
    [GUIDES]: {
      markets: [
        {
          market: "US",
          label: "United States (FDA)",
          enabled: true,
          current: { ...IN_USE, title: IN_USE.title, questions: 2, extra_questions: 0, tests: 6 },
          open: open ? { ...open, problems: [], editors: ["Asha Menon"] } : null,
          history: [],
        },
      ],
    },
    [`${GUIDES}/US/versions/2`]: IN_USE,
    [`${GUIDES}/US/versions/3`]: open,
  };
  return render(<DecisionTreesSection />, api(permissions, "regulatory", "?mode=edit&market=US"));
}

describe("D2.6: Edit this tree on the same tab", () => {
  it("shows the questions as read-only rows with a pencil, the regulation's text and clause always locked", () => {
    const html = showEdit(null);
    expect(html).toContain('aria-pressed="true">Edit this tree</button>');
    expect(html).toContain("The regulation&#x27;s text, locked · 21 CFR 803.50(a)(1)");
    expect(html).toContain('aria-label="Edit question 1&#x27;s explanation"');
    expect(html).not.toContain("<textarea");
    expect(html).toContain("Add an extra question");
    expect(html).toContain("6 of 6 worked complaints pass");
    expect(html).toContain("A reportable outcome creates the Form FDA 3500A (eMDR).");
  });

  it("tests and sends for approval with one button", () => {
    const draft3 = guideVersion({ ...PREPARED, state: "DRAFT", approval: null });
    const html = showEdit(draft3);
    expect(html).toContain("Your version 3 (draft) · version 2 in use");
    expect(html).toContain("Test against the worked complaints and send for approval</button>");
    expect(html).not.toContain(">Send for approval<");
  });

  it("shows the approver only what changed, read-only, with password and authenticator code", () => {
    const html = showEdit(PREPARED);
    expect(html).toContain("What changes in version 3");
    expect(html).toContain("Q1 · your explanation");
    expect(html).toContain("A death of anyone the device touched.");
    expect(html).toContain("Extra question · added, never changes the conclusion");
    expect(html).not.toContain('aria-label="Edit question');
    expect(html).toContain("Prepared by Asha Menon.");
    expect(html).toContain('aria-label="Authenticator code"');
    expect(html).toContain("Approve version 3</button>");
    expect(guideChanges(IN_USE, PREPARED).map((change) => change.label)).toEqual([
      "Q1 · your explanation",
      "Extra question · added, never changes the conclusion",
    ]);
  });
});

const wf = (id: string, number: string, label: string, over: Partial<WorksheetField> = {}): WorksheetField => ({
  id,
  number,
  label,
  value: null,
  status: "MUST_HAVE",
  status_label: "Missing: must have before submission",
  source: null,
  personal: null,
  missing_class: "MUST_HAVE",
  editable: true,
  note: null,
  by: null,
  at: null,
  scope: "EVENT",
  once: false,
  ...over,
});

const REPORT = {
  id: "r1",
  kind: "INITIAL",
  complaint: {
    id: "c-rv11",
    ref: "SAMPLE-RV-11",
    complaint_identifier: "SAMPLE-RV-11",
    product_name: "PulseWatch 410",
    version: "Rev A",
    country: "US",
    description: "",
    aware_date: null,
    sample: true,
  },
  market: "US",
  market_label: "United States (FDA)",
  form: {
    code: "FDA_3500A",
    title: "Form FDA 3500A worksheet (eMDR)",
    version: "09/2025",
    authority: "FDA",
    source_document: "",
    clauses: [{ id: "CFR803_50", short: "21 CFR 803.50", title: "" }],
  },
  routes: [],
  state: "DRAFT",
  state_label: "Draft",
  next_step: "",
  steps: [],
  stage: "CREATED",
  stage_label: "Created from the decision tree",
  stages: [],
  mandatory: { total: 19, filled: 15, missing: ["D2A", "G4", "D3", "B4"] },
  preparers: ["Asha Menon"],
  deadline: {},
  assessment: null,
  case: null,
  sections: [
    {
      code: "D",
      title: "D. Suspect medical device",
      note: null,
      fields: [
        wf("D1", "D1", "Brand name", { status: "FROM_RECORD", value: "PulseWatch 410", scope: "PRODUCT" }),
        wf("D2A", "D2a", "Procode", { scope: "PRODUCT", once: true, once_key: "US_REGISTRATION" }),
        wf("D3", "D3", "Manufacturer name", { scope: "ORGANIZATION", once: true, once_key: "D3" }),
      ],
    },
    {
      code: "G",
      title: "G. Manufacturer",
      note: null,
      fields: [wf("G4", "G4", "PMA/510(k) #", { scope: "PRODUCT", once: true, once_key: "US_REGISTRATION" })],
    },
    { code: "B", title: "B. Event", note: null, fields: [wf("B4", "B4", "Date of this report", { kind: "DATE" })] },
  ],
  counts: {},
  status_labels: {},
  editable: true,
  snapshots: [],
  pending_snapshot: null,
  cannot_approve: [],
  approval: { may_approve: false, same_person: false, approvers: ["Rahul Iyer"], message: null },
  submissions: [],
  request: null,
  parent_id: null,
  responses: [],
  note: null,
  follow_up_due_on: null,
  starter_mark: "",
  practice_label: null,
  never_submits: "",
  sample: true,
} as unknown as ReportDetail;

describe("D2.7: the report page body", () => {
  it("counts the things to give and their fields, grouped by who knows them; a registration's two fields are one", () => {
    const give = thingsToGive(REPORT);
    expect([give.things, give.fields]).toEqual([3, 4]);
    expect(give.groups.map((group) => group.title)).toEqual([
      "Your product · enter once",
      "Your organization · enter once",
      "This event",
    ]);
    expect(give.groups[0].things[0].map((item) => item.id)).toEqual(["D2A", "G4"]);
  });

  it("asks each thing once, names its form box and rule, and folds the full report while anything is missing", () => {
    resources.data = { [`/api/v1/reports/r1`]: REPORT };
    const html = render(<ReportsSection />, api(undefined, "regulatory", "?report=r1"));
    expect(html).toContain("3 things to give (4 fields)");
    // 0.10.87: the form is the page's heading; the give-head names only its rule.
    expect(html).toContain('<span class="ac-muted">21 CFR 803.50</span>');
    expect(html).toContain("D2a · G4");
    expect(html).toContain("Save for PulseWatch 410");
    expect(html).toContain("Entered once for PulseWatch 410: used on every report for that product.");
    expect(html).toContain("Save for your organization");
    expect(html).toMatch(/<details class="uw-card uw-rec-main rp-fold" aria-label="The form&#x27;s fields"><summary/);
    expect(html).toContain("The report, in the form&#x27;s order");
    // The field count is the "things to give" head; the meter chip waits until nothing is missing (0.10.87).
    expect(html.split("of 19 mandatory").length - 1).toBe(0);
  });
});

describe("D2.8: approval in plain words", () => {
  const FILLED = {
    ...REPORT,
    stage: "APPROVAL",
    mandatory: { total: 19, filled: 19, missing: [] },
    sections: [
      {
        code: "D",
        title: "D. Suspect medical device",
        note: null,
        fields: [
          wf("D1", "D1", "Brand name", {
            status: "FROM_RECORD",
            value: "PulseWatch 410",
            source: { type: "Product", ref: "PW-410", label: "The product's name", id: null },
          }),
        ],
      },
    ],
    pending_snapshot: {
      id: "s1",
      version: 1,
      state: "PENDING",
      requested_by: "Asha Menon",
      requested_at: "2026-11-02T09:00:00Z",
      content_fingerprint: "f".repeat(64),
      sections: [
        {
          code: "D",
          title: "D. Suspect medical device",
          note: null,
          fields: [
            wf("D1", "D1", "Brand name", {
              status: "FROM_RECORD",
              value: "PulseWatch 410 (as frozen)",
              source: { type: "Product", ref: "PW-410", label: "The product's name", id: null },
            }),
          ],
        },
      ],
    },
    approval: { may_approve: true, same_person: false, approvers: [], message: null },
    signatures: [
      { name: "Asha Menon", at: "2026-11-02T08:30:00Z", meaning: "signed reportable" },
      { name: "Asha Menon", at: "2026-11-02T09:00:00Z", meaning: "prepared" },
    ],
  } as unknown as ReportDetail;

  it("shows what you are approving, the real values with their sources, above the password and Approve", () => {
    resources.data = { [`/api/v1/reports/r1`]: FILLED };
    const html = render(<ReportsSection />, api(undefined, "regulatory", "?report=r1"));
    const doc = html.indexOf("What you are approving</p>");
    expect(doc).toBeGreaterThan(-1);
    expect(doc).toBeLessThan(html.indexOf("Your password"));
    expect(html.indexOf("Your password")).toBeLessThan(html.indexOf(">Approve</button>"));
    expect(html).toContain("PulseWatch 410 (as frozen)<small>The product&#x27;s name: PW-410</small>");
    expect(html).toContain(
      "<strong>Approve the United States report for SAMPLE-RV-11.</strong> Prepared by Asha Menon. You confirm with your password.",
    );
    expect(html).not.toMatch(/snapshot|fingerprint|checksum/i);
    // Every signature: full name, date and time, meaning.
    expect(html).toMatch(/<li>Asha Menon · 2 Nov 2026, \d\d:\d\d · signed reportable<\/li>/);
    expect(html).toMatch(/<li>Asha Menon · 2 Nov 2026, \d\d:\d\d · prepared<\/li>/);
  });

  it("shows a success panel with the approval's name, time and meaning", () => {
    resources.data = {
      [`/api/v1/reports/r1`]: {
        ...FILLED,
        stage: "APPROVED",
        state: "APPROVED",
        pending_snapshot: null,
        approved_snapshot: { id: "s1", version: 1, state: "APPROVED", approved_by: "Rahul Iyer", preparers: [] },
        signatures: [
          ...FILLED.signatures!,
          { name: "Rahul Iyer", at: "2026-11-02T09:32:00Z", meaning: "approved for submission" },
        ],
      },
    };
    const html = render(<ReportsSection />, api(undefined, "regulatory", "?report=r1"));
    expect(html).toMatch(/<p class="dt-success">✓ Rahul Iyer · 2 Nov 2026, \d\d:\d\d · approved for submission<\/p>/);
  });
});

describe("D2.9: the starter mark only on starter content, in one wording", () => {
  it("marks MDARIX's starter version and never the organization's approved one", () => {
    expect(STARTER_LABEL).toBe("Starter, for your consultant to confirm");
    expect(isStarterVersion("US-starter-1")).toBe(true);
    expect(isStarterVersion("US-v2")).toBe(false);
    expect(questionMark({ starter: true, extra: false })).toBe(STARTER_LABEL);
    expect(show(usItem())).toContain(`<span class="dt-tag"> ${STARTER_LABEL}</span>`);
    const approved = usItem();
    approved.question_set = { ...approved.question_set, version: "US-v2" };
    expect(show(approved)).not.toContain(STARTER_LABEL);
  });
});

describe("D2.3: pending information only once everything is answered", () => {
  it("says not decided yet while questions are open, and pending once only an Unknown remains", () => {
    const groups = groupQuestions(US_QUESTIONS);
    const item = usItem();
    const some = { answers: { US1: "NO", US5: "UNKNOWN" } as TreeForm["answers"], reasons: {} };
    expect(shownOutcome("PENDING_INFORMATION", groups, item, some, {})).toBeNull();
    const all = treeFormOf(usItem({ draft: draft({ ...ANSWERED, US3: "NO", US5: "UNKNOWN" }) }), groups);
    expect(shownOutcome("PENDING_INFORMATION", groups, item, all, {})).toBe("PENDING_INFORMATION");
    expect(shownOutcome("REPORTABLE", groups, item, some, {})).toBe("REPORTABLE");
  });
});

describe("0.10.84: the tree while answering, compact enough for Sign on the first screen", () => {
  it("puts Answer · Edit on the market row, says the starter once and not the version again beside Sign", () => {
    const starter = usItem({
      question_set: { ...usItem().question_set, version: "US-starter-1" },
    });
    const trees = {
      ...TREES,
      markets: [{ ...TREES.markets[0], version_label: "MDARIX starter · version 1, for your consultant to confirm" }],
    };
    resources.data = {
      "/api/v1/decision-trees": trees,
      "/api/v1/complaints/c-rv11/market-assessments": detailOf(starter),
    };
    const html = render(<DecisionTreesSection />);
    const row = html.slice(html.indexOf('class="dt-markets"'), html.indexOf('class="dt-rec"'));
    expect(row).toContain('class="dt-modes"');
    expect(html.split("for your consultant to confirm").length - 1).toBe(1);
    const rail = html.slice(html.indexOf('class="dt-rail"'));
    expect(rail).toContain("12 of 12 worked complaints pass");
    expect(rail).not.toContain("MDARIX starter · version 1");
  });
});

describe("0.10.87, duplication review rows 28-34: one report says each thing once", () => {
  it("names the market and the due day once each, counts what is missing once, and keeps the starter to its chip", () => {
    resources.data = { [`/api/v1/reports/r1`]: { ...REPORT, starter_mark: "Starter text." } };
    const html = render(<ReportsSection />, api(undefined, "regulatory", "?report=r1"));
    expect(html).not.toContain("<dt>Market</dt>");
    expect(html).not.toContain("<dt>Due</dt>");
    // While fields are missing the "things to give" head counts them; the meter chip waits until none is.
    expect(html).not.toContain("15 of 19 mandatory fields");
    expect(html).toContain("3 things to give (4 fields)");
    if (REPORT.form.starter) expect(html).not.toContain("Starter text.");
    // "MDARIX never submits" is said once, on the rail.
    expect(html.split("never submits").length - 1).toBe(1);
  });

  it("shows the meter chip once every field is filled", () => {
    resources.data = { [`/api/v1/reports/r1`]: { ...REPORT, mandatory: { total: 19, filled: 19, missing: [] } } };
    expect(render(<ReportsSection />, api(undefined, "regulatory", "?report=r1"))).toContain(
      "19 of 19 mandatory fields",
    );
  });

  it("gives the list one eyebrow, the page's", () => {
    expect(reportsTab).not.toContain('<Panel eyebrow="Reports"');
  });
});
