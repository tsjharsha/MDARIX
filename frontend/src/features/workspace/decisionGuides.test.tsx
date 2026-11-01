import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import {
  answersText,
  editProblem,
  moveExtra,
  questionMark,
  saveBody,
  type GuideList,
  type GuideVersion,
  type QuestionForm,
} from "./decisionGuides";

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

const { DecisionGuides, GuideDrawer } = await import("./sections/DecisionGuides");

function workspace(permissions: string[]): WorkspaceApi {
  return {
    session: { allowed_menu: ["products"], business_permissions: permissions },
    open: vi.fn(),
    notify: vi.fn(),
    work: { products: [] },
  } as unknown as WorkspaceApi;
}

const render = (node: ReactNode, permissions: string[] = ["regulatory.review", "data.export"]) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={workspace(permissions)}>{node}</WorkspaceContext.Provider>);

const q = (id: string, extra = false): QuestionForm => ({
  id,
  text: `Question ${id}`,
  definition: "",
  note: "",
  clause: extra ? "" : "21 CFR 803.3",
  basis: extra ? [] : ["CFR803_3"],
  extra,
});

const summary = { approved_by: null, published_at: null, sample: true };

const version = (patch: Partial<GuideVersion> = {}): GuideVersion =>
  ({
    ...summary,
    version: 3,
    code: "US-v3",
    state: "DRAFT",
    state_label: "Draft",
    starter: false,
    market: "US",
    market_label: "United States (FDA)",
    title: "US medical device reporting",
    based_on: "US-v2",
    question_set: {
      market: "US",
      market_label: "United States (FDA)",
      version: "US-v3",
      title: "US",
      note: null,
      starter_mark: "Starter text",
      questions: [
        {
          id: "US1",
          text: "Did a death occur?",
          definition: "",
          clause: "21 CFR 803.50(a)(1)",
          basis: ["CFR803_50"],
          serious: true,
          note: null,
          starter: true,
          extra: false,
        },
        {
          id: "X1",
          text: "Do we take part in VMSR?",
          definition: "",
          clause: "",
          basis: [],
          serious: false,
          note: null,
          starter: false,
          extra: true,
        },
      ],
    },
    test_cases: [
      {
        id: "T1",
        name: "Outcome unknown",
        answers: { US2B: "UNKNOWN" },
        expected: "NOT_REPORTABLE",
        expected_report_type: null,
      },
    ],
    test_results: {
      results: [
        {
          id: "T1",
          name: "Outcome unknown",
          expected: "NOT_REPORTABLE",
          expected_report_type: null,
          actual: "PENDING_INFORMATION",
          actual_report_type: null,
          passed: false,
        },
      ],
      passed: 0,
      failed: 1,
      current: true,
      run_at: "2026-11-01T10:00:00+00:00",
      run_by: "MDARIX sample author",
    },
    problems: ["Question X1 has no regulation clause", "1 of 1 test cases fail: fix them, then run again"],
    change_reason: null,
    editors: ["MDARIX sample author"],
    requested_by: null,
    requested_at: null,
    approved_at: null,
    signature: null,
    editable: true,
    catalog: [{ id: "CFR803_19", short: "21 CFR 803.19", title: "VMSR" }],
    answer_labels: { YES: "Yes", NO: "No", UNKNOWN: "Unknown", NOT_APPLICABLE: "Not applicable" },
    expected_labels: {
      REPORTABLE: "Reportable",
      NOT_REPORTABLE: "Not reportable",
      PENDING_INFORMATION: "Pending information",
    },
    report_types: [{ code: "US_30_DAY", label: "30-calendar-day report (21 CFR 803.50)" }],
    core_rule: "The questions that drive the conclusion can be reworded, not removed.",
    never_decides: "A guide points to a conclusion; a person confirms or overrides it.",
    scale_note: "The harm-severity scale stays fixed.",
    starter_mark: "Starter text",
    practice_label: "Practice record",
    ...patch,
  }) as GuideVersion;

describe("decision guide rules", () => {
  it("moves only extra questions and keeps the core order", () => {
    const list = [q("US1"), q("X1", true), q("X2", true)];
    expect(moveExtra(list, 2, -1).map((item) => item.id)).toEqual(["US1", "X2", "X1"]);
    expect(moveExtra(list, 1, -1)).toBe(list); // never above a core question
  });

  it("asks for the question text and reads an empty test as all Unknown", () => {
    expect(editProblem([{ ...q("X1", true), text: "Why" }])).toMatch("at least 5");
    expect(answersText({ answers: {} }, {})).toBe("none (all Unknown)");
    expect(questionMark({ starter: false, extra: true })).toMatch("does not change the conclusion");
    expect(saveBody([q("US1")], []).questions[0]).not.toHaveProperty("extra");
  });
});

describe("the decision guide screens", () => {
  it("lists each market with the version in use and the one being prepared", () => {
    resources.data["/api/v1/decision-guides"] = {
      markets: [
        {
          market: "US",
          label: "United States (FDA)",
          enabled: true,
          current: {
            ...summary,
            version: 2,
            code: "US-v2",
            state: "PUBLISHED",
            state_label: "Published: in use",
            starter: false,
            approved_by: "MDARIX sample approver",
            title: "US",
            questions: 9,
            extra_questions: 1,
            tests: 6,
          },
          open: {
            ...summary,
            version: 3,
            code: "US-v3",
            state: "DRAFT",
            state_label: "Draft",
            starter: false,
            problems: ["1 of 7 test cases fail"],
            editors: [],
          },
          history: [
            { ...summary, version: 3, code: "US-v3", state: "DRAFT", state_label: "Draft", starter: false },
            {
              ...summary,
              version: 2,
              code: "US-v2",
              state: "PUBLISHED",
              state_label: "Published: in use",
              starter: false,
            },
            {
              ...summary,
              version: 1,
              code: "US-starter-1",
              state: "SUPERSEDED",
              state_label: "MDARIX starter: superseded by your version",
              starter: true,
              sample: false,
            },
          ],
        },
      ],
      core_rule: "Core rule.",
      never_decides: "MDARIX never decides.",
      scale_note: "Scale fixed.",
      starter_mark: "Starter text",
      practice_label: null,
    } satisfies GuideList;
    const html = render(<DecisionGuides />);
    expect(html).toContain("US-v2 in use");
    expect(html).toContain("approved by MDARIX sample approver");
    expect(html).toContain("1 of 7 test cases fail");
    expect(html).toContain("US-starter-1");
  });

  it("edits a draft with the clause column and shows the failing test that blocks publication", () => {
    resources.data["/api/v1/decision-guides/US/versions/3"] = version();
    const html = render(<GuideDrawer market="US" version={3} onClose={vi.fn()} />);
    expect(html).toContain(">Clause<");
    expect(html).toContain("No clause yet");
    expect(html).toContain("the guide points to Pending information");
    expect(html).toContain("Question X1 has no regulation clause");
    expect(html).toContain("PDF for an audit");
  });

  it("names who may not approve, and shows a published version read-only with its approval", () => {
    resources.data["/api/v1/decision-guides/US/versions/4"] = version({
      version: 4,
      state: "AWAITING_APPROVAL",
      state_label: "Waiting for approval",
      problems: [],
      you_edited: true,
      you_asked: true,
      requested_by: "Asha",
      approval: {
        may_approve: false,
        same_person: false,
        approvers: ["Rahul"],
        message: "You edited this version. A colleague with regulatory approval rights approves this: Rahul.",
      },
    });
    // Who approves is said in place of the form, before any password (J13); its author may withdraw it.
    const waiting = render(<GuideDrawer market="US" version={4} onClose={vi.fn()} />);
    expect(waiting).toContain("A colleague with regulatory approval rights approves this: Rahul.");
    expect(waiting).not.toContain("Your password");
    expect(waiting).toContain("Withdraw it: back to draft");
    resources.data["/api/v1/decision-guides/US/versions/2"] = version({
      version: 2,
      code: "US-v2",
      state: "PUBLISHED",
      state_label: "Published: in use",
      editable: false,
      problems: [],
      signature: {
        signer_name: "MDARIX sample approver",
        signer_role: "Sample approver",
        signed_at: "2026-10-28T10:00:00+00:00",
        meaning: "I approve US-v2",
        record_business_id: "SIG-1",
        record_id: "r",
        content_fingerprint: "abcdef1234567890",
      },
    });
    const html = render(<GuideDrawer market="US" version={2} onClose={vi.fn()} />);
    expect(html).toContain("Approved by <strong>MDARIX sample approver</strong>");
    expect(html).not.toContain("Save the draft");
  });
});
