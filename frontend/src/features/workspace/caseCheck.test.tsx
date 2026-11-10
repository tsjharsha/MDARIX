import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { CheckBody, clockChip } from "./sections/FirstContact";
import { signProblem, type Choice, type Deadline, type Guide, type IntakeItem } from "./intake";

// 0.10.93 (B2 step 5, spec 4.4/4.5): the Case check drawer with what was said later, "Correct a fact", the provisional
// clock chip, the six classifications with their disabled reasons, "Sign and escalate" with the escalation panel
// (attach to a likely duplicate or create a new complaint), and S-2's "Waiting for internal team" and withdraw.

const render = (node: ReactNode, permissions: string[]) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider
      value={
        { session: { business_permissions: permissions }, open: vi.fn(), notify: vi.fn() } as unknown as WorkspaceApi
      }
    >
      {node}
    </WorkspaceContext.Provider>,
  );

const questions: Guide["questions"] = Array.from({ length: 9 }, (_, index) => ({
  id: `Q${index + 1}`,
  text: `Question ${index + 1}`,
  not_stated: false,
  free_text: false,
}));
const guide = {
  questions,
  answers: [
    { code: "YES", label: "Yes" },
    { code: "NO", label: "No" },
  ],
  outcomes: [],
  table: [{ row: 1, answers: "a Yes on questions 1-3, and a repair is needed", outcome: "Complaint and service" }],
} as unknown as Guide;
const answers = Object.fromEntries(questions.map((q) => [q.id, { answer: "YES" as const, note: "" }]));

const choice = (code: Choice["code"], label: string, extra: Partial<Choice> = {}): Choice => ({
  code,
  label,
  suggested: false,
  escalates: false,
  disabled_reason: null,
  ...extra,
});
const CHOICES: Choice[] = [
  choice("COMPLAINT", "Complaint", { escalates: true }),
  choice("BOTH", "Complaint and service", { escalates: true, suggested: true }),
  choice("SERVICE_ONLY", "Service only", {
    disabled_reason: '"Service only" is offered only when the answers give it',
  }),
  choice("INQUIRY", "Inquiry", { disabled_reason: '"Inquiry" is offered only when the answers give it' }),
  choice("PENDING", "Pending"),
  choice("NOT_A_COMPLAINT", "Not a complaint (no deficiency confirmed)", {
    disabled_reason: '"Not a complaint" is offered only when the answers give "confirm no deficiency"',
  }),
];
const CLOCK = {
  market: "US",
  days: 30,
  due_label: "Wed 9 Dec 2026, 23:59 EST",
  state: "RUNNING",
  basis: "21 CFR 803.50",
} as Deadline;

const item = (extra: Partial<IntakeItem> = {}): IntakeItem =>
  ({
    id: "e1",
    reference: "CASE-2026-000123",
    kind: "CONTACT",
    kind_label: "Call",
    reporter_words: "The pump stopped during an infusion",
    times: {},
    awareness: {
      at: "2026-11-09T09:00:00Z",
      source: "RECEIVED",
      source_label: "received",
      unresolved: false,
      label: null,
    },
    flags: [],
    flagged: false,
    sample: false,
    version: 2,
    row_version: 3,
    answers,
    suggestion: "BOTH",
    suggestion_label: "Complaint and service",
    outcome_row: 1,
    draft: true,
    signed: null,
    tasks: [],
    qms_task: null,
    status: "OPEN",
    status_label: "To check",
    addenda: [
      {
        id: "a1",
        kind: "STATEMENT",
        said_by_role: "TECHNICIAN",
        said_at: "2026-11-09T11:00:00Z",
        text: "Occlusion alarm log shows two stops",
        masked: false,
        added_by: "Priya",
        added_at: "2026-11-09T11:05:00Z",
      },
    ],
    choices: CHOICES,
    clock: CLOCK,
    likely_complaints: [{ id: "c1", ref: "SAMPLE-RV-11", reasons: ["same product", "same lot", "same country"] }],
    ...extra,
  }) as IntakeItem;

const ALL = ["case.log", "case.classify", "quality.review"];

describe("the Case check drawer (spec 4.4)", () => {
  it("shows what was said later, the fact correction, the clock chip, the six classifications and their reasons", () => {
    const html = render(<CheckBody item={item()} guide={guide} onChanged={vi.fn()} />, ALL);
    for (const text of [
      "What was said",
      "Occlusion alarm log shows two stops",
      "A technician",
      "Add what they said later",
      "Correct a fact",
      "Provisional: US 30 days, due Wed 9 Dec 2026, 23:59 EST",
      "The ten questions",
      "Suggestion",
      "row 1: a Yes on questions 1-3, and a repair is needed",
      "Your classification",
      "Complaint and service (suggested)",
      "Inquiry",
      "Not a complaint (no deficiency confirmed)",
      "is offered only when the answers give it",
      "Fixed on the call is still a complaint when a deficiency was alleged.",
      "does not change the answers.",
      "Waiting for internal team",
      "Withdraw: entered in error",
    ])
      expect(html).toContain(text);
    // Six classifications, three disabled with their reason.
    expect(html.match(/name="classification"/g)).toHaveLength(6);
    expect(html.match(/<input type="radio" disabled="" name="classification"/g)).toHaveLength(3);
  });

  it("signs a complaint as 'Sign and escalate' with the escalation panel and the duplicate choice", () => {
    const html = render(<CheckBody item={item()} guide={guide} onChanged={vi.fn()} />, ALL);
    for (const text of [
      "This case becomes a complaint",
      "CASE-2026-000123 keeps its reference and its awareness time",
      "Carried to the complaint:",
      "Possibly the same event as SAMPLE-RV-11: same product, same lot, same country",
      "Attach this case to SAMPLE-RV-11",
      "Create a new complaint",
      "Sign and escalate",
    ])
      expect(html).toContain(text);
    // One strong match is pre-selected (spec 3.3 step 2).
    expect(html).toMatch(/name="attach" checked=""/);
  });

  it("pre-selects the only match on the case's event day among several (SAMPLE-CASE-11 and RV-11, 0.10.93)", () => {
    const likely = [
      { id: "c1", ref: "SAMPLE-RV-11", reasons: ["same product", "same lot"], same_day: true },
      { id: "c2", ref: "SAMPLE-RT-02", reasons: ["same product", "same lot"], same_day: false },
    ];
    const html = render(
      <CheckBody item={item({ likely_complaints: likely })} guide={guide} onChanged={vi.fn()} />,
      ALL,
    );
    expect(html.match(/name="attach" checked=""/g)).toHaveLength(1);
    expect(html).toMatch(/name="attach" checked=""\/>Attach this case to SAMPLE-RV-11/);
    // Two matches on other days: the signer chooses.
    const none = likely.map((candidate) => ({ ...candidate, same_day: false }));
    const open = render(<CheckBody item={item({ likely_complaints: none })} guide={guide} onChanged={vi.fn()} />, ALL);
    expect(open).not.toContain('checked=""/>Attach');
  });

  it("signs any other outcome as 'Sign the case check', without the panel", () => {
    const pending = item({ suggestion: "PENDING", suggestion_label: "Pending", likely_complaints: [] });
    const html = render(<CheckBody item={pending} guide={guide} onChanged={vi.fn()} />, ALL);
    expect(html).toContain("Sign the case check");
    expect(html).not.toContain("This case becomes a complaint");
  });

  it("after the escalation says the Case is a complaint and offers Next: Triage; a Service Desk agent cannot withdraw", () => {
    const done = item({ status: "ESCALATED", draft: false, complaint_ref: "CASE-2026-000123", clock: null });
    const html = render(<CheckBody item={done} guide={guide} onChanged={vi.fn()} />, ["case.log"]);
    expect(html).toContain("CASE-2026-000123 is now a complaint");
    expect(html).toContain("Next: Triage");
    expect(html).not.toContain("Withdraw: entered in error");
    expect(html).not.toContain("Waiting for internal team");
  });

  it("refuses a disabled classification in its own words, and names the clock chip", () => {
    const form = { classification: "INQUIRY" as const, override: "", reason: "", password: "x" };
    expect(signProblem({ suggestion: "BOTH", choices: CHOICES }, form, [])).toMatch(/only when the answers give it/);
    expect(signProblem({ suggestion: "INQUIRY" }, { ...form, override: "a long enough reason" }, [])).toMatch(
      /"Inquiry" needs a written reason/,
    );
    expect(clockChip(CLOCK)).toBe("Provisional: US 30 days, due Wed 9 Dec 2026, 23:59 EST");
  });
});
