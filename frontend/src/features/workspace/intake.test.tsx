import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { EscalateButton, Triage } from "./sections/Triage";
import { FirstContact } from "./sections/FirstContact";
import {
  answerChoices,
  blankAnswers,
  daysEarlier,
  daysText,
  hoursText,
  linkBody,
  signProblem,
  unanswered,
  type Duplicate,
  type Guide,
} from "./intake";

function workspace(permissions: string[]): WorkspaceApi {
  return {
    session: { allowed_menu: ["products", "investigations"], business_permissions: permissions },
    open: vi.fn(),
    notify: vi.fn(),
    work: { products: [], requestOpenInvestigation: vi.fn() },
  } as unknown as WorkspaceApi;
}

const render = (node: ReactNode, permissions: string[] = []) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={workspace(permissions)}>{node}</WorkspaceContext.Provider>);

const questions: Guide["questions"] = [
  ...Array.from({ length: 9 }, (_, index) => ({
    id: `Q${index + 1}`,
    text: `Question ${index + 1}`,
    not_stated: index >= 3 && index <= 5,
    free_text: false,
  })),
  { id: "Q10", text: "What is unknown?", not_stated: false, free_text: true },
];
const guide = {
  questions,
  answers: [
    { code: "YES", label: "Yes" },
    { code: "NO", label: "No" },
    { code: "UNKNOWN", label: "Unknown" },
    { code: "NOT_APPLICABLE", label: "Not applicable" },
    { code: "NOT_STATED", label: "Not stated" },
  ],
} as Guide;

describe("the first-contact helpers", () => {
  it("offers Not stated only on questions 4 to 6, and lists the unanswered questions", () => {
    expect(answerChoices(guide, questions[0]).map((item) => item.code)).not.toContain("NOT_STATED");
    expect(answerChoices(guide, questions[4]).map((item) => item.code)).toContain("NOT_STATED");
    const answers = blankAnswers(questions);
    expect(Object.keys(answers)).toHaveLength(9);
    expect(unanswered(answers, questions)).toHaveLength(9);
    answers.Q1 = { answer: "NO", note: "" };
    expect(unanswered(answers, questions)).not.toContain("Q1");
  });

  it("refuses the signature the server would refuse", () => {
    const form = { classification: "SERVICE_ONLY" as const, override: "", reason: "", password: "x" };
    expect(signProblem({ suggestion: "PENDING" }, form, [])).toMatch(/only when the answers give it/);
    expect(signProblem({ suggestion: "SERVICE_ONLY" }, form, [])).toMatch(/written reason/);
    expect(signProblem({ suggestion: "SERVICE_ONLY" }, { ...form, reason: "IFU request only" }, [])).toBeNull();
    expect(signProblem({ suggestion: "PENDING" }, { ...form, classification: "COMPLAINT" }, [])).toMatch(/override/);
    expect(signProblem({ suggestion: "COMPLAINT" }, { ...form, classification: "COMPLAINT" }, ["Q2"])).toMatch(
      /question 2/,
    );
  });

  it("writes the clocks in plain words", () => {
    expect(hoursText(4.2)).toBe("in 4 h");
    expect(hoursText(-6)).toBe("6 h overdue");
    expect(hoursText(-72)).toBe("3 days overdue");
    expect(daysText(0)).toBe("due today");
    expect(daysText(-1)).toBe("1 day overdue");
    expect(daysText(3)).toBe("due in 3 days");
    expect(daysEarlier("2026-11-19T10:00:00Z", "2026-11-11T10:00:00Z")).toBe(8);
    expect(daysEarlier(null, "2026-11-11T10:00:00Z")).toBe(0);
  });

  it("sends both sides of a duplicate warning with the decision", () => {
    const side = {
      source: "",
      product_name: null,
      words: "",
      event_at: null,
      awareness_at: "",
      awareness_source: null,
    };
    const pair: Duplicate = {
      left: { ...side, kind: "INTAKE", id: "a", ref: "CALL-1" },
      right: { ...side, kind: "COMPLAINT", id: "b", ref: "CMP-1" },
      reasons: [],
    };
    expect(linkBody(pair, "LINKED", " Same event ")).toEqual({
      left_kind: "INTAKE",
      left_id: "a",
      right_kind: "COMPLAINT",
      right_id: "b",
      decision: "LINKED",
      reason: "Same event",
    });
  });
});

describe("the triage and first-contact screens", () => {
  it("open while reading, and offer the entry points to people who may write", () => {
    expect(render(<Triage onOpenTab={vi.fn()} />)).toContain("Reading the triage list");
    const writer = render(<FirstContact />, ["signal.triage"]);
    expect(writer).toContain("Log a call");
    expect(writer).toContain("Urgent intake");
    expect(render(<FirstContact />)).not.toContain("Log a call</button>");
  });

  it("lets anyone who may write escalate a record by hand, and nobody else", () => {
    expect(render(<EscalateButton kind="COMPLAINT" id="x" />, ["signal.triage"])).toContain("Escalate to triage");
    expect(render(<EscalateButton kind="COMPLAINT" id="x" />)).toBe("");
  });
});
