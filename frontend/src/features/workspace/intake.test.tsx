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
  deadlineText,
  hoursText,
  linkBody,
  signProblem,
  startingZone,
  unanswered,
  zonedInput,
  type Deadline,
  type Duplicate,
  type Guide,
} from "./intake";
import { timeLeft } from "../../app/dates";

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

  it("enters a call's time on the wall clock of the time zone chosen for it (J28)", () => {
    // 15:00 UTC is 09:00 in Chicago in November and 20:30 in India; the server converts the wall time in the zone.
    const moment = new Date("2026-11-03T15:00:00Z");
    expect(zonedInput(moment, "America/Chicago")).toBe("2026-11-03T09:00");
    expect(zonedInput(moment, "Asia/Kolkata")).toBe("2026-11-03T20:30");
    const guide = {
      zones: ["UTC", "America/Chicago", "Asia/Kolkata"],
      zone_aliases: { "Asia/Calcutta": "Asia/Kolkata" },
    };
    expect(startingZone(guide, "Asia/Calcutta")).toBe("Asia/Kolkata");
    expect(startingZone(guide, "Mars/Olympus")).toBe("UTC");
  });

  it("writes the clocks in plain words", () => {
    expect(hoursText({ hours_left: 4.2 })).toBe("4 h left");
    expect(hoursText({ hours_left: -6 })).toBe("6 h overdue");
    expect(hoursText({ hours_left: -72 })).toBe("3 days overdue");
    // A legal deadline with its time zone, and the app's one time-left text (J40), overdue from the server's state.
    const now = new Date("2026-11-01T12:00:00Z");
    const india: Deadline = {
      market: "IN",
      label: "India (CDSCO)",
      role: "OWN",
      role_label: "The event's market",
      own: true,
      not_reportable: false,
      tier: "FLAGGED",
      tier_label: "Flagged",
      days: 15,
      day_basis: "CALENDAR",
      basis: "15 days (India MDR 2017 Rule 26)",
      due_date: "2026-11-07",
      due_at: "2026-11-07T18:29:59+00:00",
      due_zone: "Asia/Kolkata",
      due_label: "Sat 7 Nov 2026, 23:59 IST",
      days_left: 6,
      state: "RUNNING",
    };
    expect(timeLeft(india, now)).toBe("6 days left");
    expect(deadlineText(india)).toMatch(/^Sat 7 Nov 2026, 23:59 IST \(/);
    expect(deadlineText({ ...india, not_reportable: true })).toBe("Concluded not reportable");
    expect(timeLeft({ ...india, state: "OVERDUE" }, now)).toBe("Overdue");
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
    expect(render(<Triage onOpenTab={vi.fn()} />)).toContain("The triage list");
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
