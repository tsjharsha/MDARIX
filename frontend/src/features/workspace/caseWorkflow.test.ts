import { describe, expect, it } from "vitest";
import {
  CASE_STEPS,
  STEP_PLACE,
  caseDueState,
  caseProgress,
  casePriorityLabel,
  caseState,
  caseStateLabel,
  caseStateTone,
  caseStatusText,
  caseSteps,
  caseTransitions,
  dayFromDueAt,
  dueAtFromDay,
  myCaseTiles,
  nextCaseStep,
  planningChange,
  rankMyCases,
  readinessChecks,
  readinessHeadline,
  readinessPath,
  transitionBody,
  transitionPath,
  transitionProblem,
  type StepStatus,
} from "./caseWorkflow";

const UUID = "0b6f8f9e-1111-4222-8333-444455556666";
const now = new Date("2026-10-06T12:00:00Z");

describe("how an investigation's state reads", () => {
  it("shows the server's label, else the known label, else the plain status", () => {
    expect(caseStateLabel({ workflow_state: "ON_HOLD", workflow_state_label: "Paused by QA" })).toBe("Paused by QA");
    expect(caseStateLabel({ workflow_state: "READY_FOR_DECISION" })).toBe("Ready for decision");
    expect(caseStateLabel({ status: "open" })).toBeNull();
    expect(caseStatusText({ status: "open" })).toBe("open");
    expect(caseStatusText({ workflow_state: "IN_PROGRESS", status: "open" })).toBe("In progress");
    expect(caseStatusText({})).toBe("—");
    expect(caseStateLabel({ workflow_state_label: UUID })).toBeNull();
  });

  it("reads the state code in any case and tones it", () => {
    expect(caseState({ workflow_state: "in_progress" })).toBe("IN_PROGRESS");
    expect(caseState({ workflow_state: "SOMETHING" })).toBeNull();
    expect(caseStateTone({ workflow_state: "CANCELLED" })).toBe("neutral");
    expect(caseStateTone({ workflow_state: "ON_HOLD" })).toBe("serious");
    expect(caseStateTone({ status: "closed" })).toBe("good");
    expect(caseStateTone({ status: "open" })).toBe("warning");
  });

  it("labels priorities", () => {
    expect(casePriorityLabel("HIGH")).toBe("High");
    expect(casePriorityLabel(null)).toBe("Not set");
  });
});

describe("state changes offered on the investigation header", () => {
  const all = { work: true, assign: true };
  const labels = (state: string | null, can = all) =>
    caseTransitions({ workflow_state: state }, can).map((item) => `${item.label}>${item.to}`);

  it("starts, holds, resumes and cancels by state", () => {
    expect(labels("OPEN")).toEqual(["Start work>IN_PROGRESS", "Cancel investigation>CANCELLED"]);
    expect(labels("IN_PROGRESS")).toEqual(["Put on hold>ON_HOLD", "Cancel investigation>CANCELLED"]);
    expect(labels("ON_HOLD")).toEqual(["Resume>IN_PROGRESS", "Cancel investigation>CANCELLED"]);
    for (const state of ["BRIEF_IN_REVIEW", "READY_FOR_DECISION", "DECIDED", "CLOSED", "CANCELLED"])
      expect(labels(state)).toEqual([]);
    expect(labels(null)).toEqual([]);
  });

  it("follows the person's permissions: work for start/hold/resume, assign for cancel", () => {
    expect(labels("OPEN", { work: true, assign: false })).toEqual(["Start work>IN_PROGRESS"]);
    expect(labels("IN_PROGRESS", { work: false, assign: true })).toEqual(["Cancel investigation>CANCELLED"]);
    expect(labels("ON_HOLD", { work: false, assign: false })).toEqual([]);
  });

  it("needs a reason of 10 to 1000 characters and sends the target state", () => {
    expect(transitionProblem("short")).toMatch(/at least 10/);
    expect(transitionProblem("x".repeat(1001))).toMatch(/1000/);
    expect(transitionProblem("Waiting for the supplier's lab results")).toBeNull();
    expect(transitionBody({ to: "ON_HOLD" }, "  Waiting for lab results  ")).toEqual({
      to_state: "ON_HOLD",
      reason: "Waiting for lab results",
    });
    expect(transitionPath(UUID)).toBe(`/api/v1/investigations/${UUID}/transition`);
    expect(readinessPath(UUID)).toBe(`/api/v1/investigations/${UUID}/readiness`);
  });
});

describe("priority and due date", () => {
  it("turns a chosen day into the end of that local day and back", () => {
    const iso = dueAtFromDay("2026-10-20");
    expect(iso).not.toBeNull();
    const date = new Date(iso as string);
    expect([date.getFullYear(), date.getMonth() + 1, date.getDate(), date.getHours()]).toEqual([2026, 10, 20, 23]);
    expect(dayFromDueAt(iso)).toBe("2026-10-20");
    expect(dayFromDueAt("2026-10-21")).toBe("2026-10-21");
    expect(dueAtFromDay("20/10/2026")).toBeNull();
    expect(dayFromDueAt(null)).toBe("");
    expect(dayFromDueAt("not a date")).toBe("");
  });

  it("sends only what changed, and null to clear the due date", () => {
    const row = { priority: "MEDIUM", due_at: dueAtFromDay("2026-10-20") };
    expect(planningChange(row, { priority: "MEDIUM", dueDay: "2026-10-20" })).toBeNull();
    expect(planningChange(row, { priority: "HIGH", dueDay: "2026-10-20" })).toEqual({ priority: "HIGH" });
    expect(planningChange(row, { priority: "MEDIUM", dueDay: "" })).toEqual({ due_at: null });
    expect(planningChange(row, { priority: "MEDIUM", dueDay: "2026-10-25" })).toEqual({
      due_at: dueAtFromDay("2026-10-25"),
    });
    expect(planningChange({}, { priority: "", dueDay: "" })).toBeNull();
    expect(planningChange({}, { priority: "URGENT", dueDay: "" })).toBeNull();
  });

  it("flags an investigation overdue or due soon, never once it is decided, closed or cancelled", () => {
    expect(caseDueState({ workflow_state: "IN_PROGRESS", due_at: "2026-10-05T12:00:00Z" }, now)).toBe("overdue");
    expect(caseDueState({ workflow_state: "OPEN", due_at: "2026-10-07T12:00:00Z" }, now)).toBe("due_soon");
    expect(caseDueState({ workflow_state: "OPEN", due_at: "2026-10-30T12:00:00Z", overdue: true }, now)).toBe(
      "overdue",
    );
    expect(caseDueState({ workflow_state: "DECIDED", due_at: "2026-10-01T12:00:00Z" }, now)).toBe("done");
    expect(caseDueState({ status: "closed", due_at: "2026-10-01T12:00:00Z" }, now)).toBe("done");
    expect(caseDueState({ workflow_state: "OPEN" }, now)).toBe("none");
  });
});

describe("the investigation stepper", () => {
  it("lists the nine steps in order with the server's status, and Not available for a step not reported", () => {
    const steps = caseSteps({
      steps: [
        { key: "evidence", label: "Evidence", status: "IN_PROGRESS", detail: "3 of 7 reviewed" },
        { key: "overview", status: "DONE" },
        { key: "human_review", status: "blocked" },
      ],
    });
    expect(steps.map((step) => step.key)).toEqual(CASE_STEPS.map((step) => step.key));
    expect(steps.map((step) => step.label)).toEqual([
      "Overview",
      "Scope",
      "Evidence",
      "Analysis",
      "Hypotheses",
      "Unknowns",
      "Risk & Regulatory",
      "Decision Brief",
      "Human review",
    ]);
    expect(steps[0].status).toBe("DONE");
    expect(steps[1].status).toBe("NOT_AVAILABLE");
    expect(steps[2]).toMatchObject({ status: "IN_PROGRESS", detail: "3 of 7 reviewed" });
    expect(steps[8].status).toBe("BLOCKED");
  });

  it("opens each step where its work is done", () => {
    const at = (key: string) => caseSteps(null).find((step) => step.key === key)?.destination;
    expect(at("scope")).toEqual({ section: "Investigations", tab: "Scope" });
    expect(at("evidence")).toEqual({ section: "Evidence", tab: "Case evidence" });
    expect(at("analysis")).toEqual({ section: "Investigations", tab: "Workspace", anchor: "workflow-analysis" });
    expect(at("hypotheses")).toEqual({ section: "Investigations", tab: "Intelligence", view: "Hypotheses" });
    expect(at("gaps")).toEqual({ section: "Investigations", tab: "Intelligence", view: "Unknowns" });
    expect(at("risk_regulatory")).toEqual({ section: "Investigations", tab: "Reviews" });
    expect(at("brief")).toEqual({ section: "Investigations", tab: "Decision Brief" });
    expect(at("human_review")).toEqual({ section: "Investigations", tab: "Decision" });
  });

  it("keeps a step it does not know at the end, without a destination", () => {
    const steps = caseSteps({ steps: [{ key: "capa", label: "CAPA", status: "NOT_STARTED" }] });
    expect(steps).toHaveLength(10);
    expect(steps[9]).toMatchObject({ key: "capa", label: "CAPA", status: "NOT_STARTED", destination: null });
  });
});

describe("the readiness checklist", () => {
  const checks = readinessChecks({
    checks: [
      { key: "scope", label: "Scope recorded", result: "PASS", rationale: "Version 2" },
      { key: "evidence", label: "Evidence reviewed", result: "BLOCKED", rationale: "4 unreviewed" },
      { key: "risk", label: "Risk review", result: "NOT_REQUIRED", rationale: null },
      { key: "brief", label: "Brief", result: "PENDING" },
      { key: "odd", result: "SOMETHING" },
    ],
  });

  it("puts blocked first, then pending, pass and not required", () => {
    expect(checks.map((check) => `${check.key}:${check.result}`)).toEqual([
      "evidence:BLOCKED",
      "brief:PENDING",
      "odd:PENDING",
      "scope:PASS",
      "risk:NOT_REQUIRED",
    ]);
    expect(checks[0].rationale).toBe("4 unreviewed");
    expect(checks[2].label).toBe("Odd");
  });

  it("summarizes with counts, never a percentage", () => {
    const headline = readinessHeadline(checks);
    expect(headline).toBe("1 blocked · 2 pending · 1 pass · 1 not required");
    expect(headline).not.toMatch(/%/);
    expect(readinessHeadline([])).toBe("No readiness checks reported yet.");
  });

  it("shows a check the organization cannot record yet as not available, last, not as pending work", () => {
    const listed = readinessChecks({
      checks: [
        { key: "regulatory", label: "Regulatory review", result: "NOT_AVAILABLE", rationale: "Not recorded yet" },
        { key: "brief", label: "Brief", result: "PENDING" },
      ],
    });
    expect(listed.map((check) => `${check.key}:${check.result}`)).toEqual([
      "brief:PENDING",
      "regulatory:NOT_AVAILABLE",
    ]);
    expect(readinessHeadline(listed)).toBe("1 pending · 1 not available yet");
  });
});

describe("my investigations", () => {
  it("builds the count tiles with where each opens", () => {
    const tiles = myCaseTiles({ counts: { in_progress: 3, overdue: 1, requests_to_review: 2 } });
    expect(tiles.map((tile) => tile.label)).toEqual([
      "In progress",
      "On hold",
      "Due soon",
      "Overdue",
      "Evidence to review",
      "Requests waiting",
      "Requests to review",
    ]);
    expect(tiles.find((tile) => tile.key === "in_progress")?.value).toBe(3);
    expect(tiles.find((tile) => tile.key === "on_hold")?.value).toBeNull();
    expect(tiles.find((tile) => tile.key === "unreviewed_evidence")?.target).toEqual({
      section: "Evidence",
      tab: "Case evidence",
    });
    expect(tiles.find((tile) => tile.key === "requests_waiting")?.target).toEqual({
      section: "My Work",
      tab: "Evidence requests",
    });
    expect(myCaseTiles(null).every((tile) => tile.value === null)).toBe(true);
  });

  it("ranks overdue investigations first, then by priority, then by the nearest due date", () => {
    const cases = [
      { id: "a", priority: "LOW", due_at: "2026-10-20T12:00:00Z", workflow_state: "OPEN" },
      { id: "b", priority: "CRITICAL", due_at: "2026-10-30T12:00:00Z", workflow_state: "IN_PROGRESS" },
      { id: "c", priority: "LOW", due_at: "2026-10-01T12:00:00Z", workflow_state: "IN_PROGRESS" },
      { id: "d", priority: "CRITICAL", due_at: "2026-10-10T12:00:00Z", workflow_state: "IN_PROGRESS" },
      { id: "e", priority: null, due_at: null, workflow_state: "OPEN" },
    ];
    expect(rankMyCases(cases, now).map((row) => row.id)).toEqual(["c", "d", "b", "a", "e"]);
    expect(rankMyCases(null, now)).toEqual([]);
  });
});

describe("the investigation's one progress line (stage 8)", () => {
  const step = (key: string, status: StepStatus) => ({ key, label: key, status, detail: null, destination: null });
  it("counts each section's steps and names the first unfinished step as the next one", () => {
    const steps = [
      step("overview", "DONE"),
      step("scope", "DONE"),
      step("evidence", "DONE"),
      step("analysis", "NOT_AVAILABLE"),
      step("hypotheses", "DONE"),
      step("gaps", "IN_PROGRESS"),
      step("risk_regulatory", "NOT_STARTED"),
      step("brief", "NOT_STARTED"),
      step("human_review", "NOT_STARTED"),
    ];
    expect(caseProgress(steps)).toEqual([
      { section: "Summary", state: "DONE", done: 2, total: 2 },
      { section: "Evidence", state: "CURRENT", done: 3, total: 4 },
      { section: "Decisions & actions", state: "OPEN", done: 0, total: 3 },
      { section: "History", state: "OPEN", done: 0, total: 1 },
    ]);
    expect(nextCaseStep(steps)).toEqual({ key: "gaps", label: "gaps", section: "Evidence", part: "intelligence" });
  });
  it("is done, with no next step, once the decision is signed", () => {
    const steps = Object.keys(STEP_PLACE).map((key) => step(key, "DONE"));
    expect(caseProgress(steps).every((item) => item.state === "DONE")).toBe(true);
    expect(nextCaseStep(steps)).toBeNull();
  });
});
