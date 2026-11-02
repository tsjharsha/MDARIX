import { describe, expect, it } from "vitest";
import {
  BLANK_WINDOW,
  clockText,
  marketsOf,
  timelinessOf,
  watchHeadline,
  watchPath,
  watchStateOf,
  windowForm,
  windowLength,
  windowOf,
  windowsBody,
  windowsChanged,
  windowsProblem,
  type ReportabilitySettings,
  type ReportingWindow,
  type WatchSummary,
} from "./reportability";
import {
  boardHeadline,
  boardPath,
  dueText,
  parseRecordsTab,
  planBody,
  planForm,
  planProblem,
  recordsTab,
  recurrenceText,
  signBody,
  signProblem,
  stateOf,
  type BoardSummary,
  type CapaDetail,
} from "./effectiveness";
import { taskDestination } from "./tasks";

const FDA: ReportingWindow = {
  name: "FDA MDR: death, serious injury or malfunction (30 calendar days)",
  markets: ["US", "USA"],
  triggers: ["DEATH", "SERIOUS_INJURY", "MALFUNCTION"],
  days: 30,
  day_basis: "CALENDAR",
  note: null,
  basis: ["CFR803_50", "CFR803_53"],
};

const summary = (overrides: Partial<WatchSummary> = {}): WatchSummary => ({
  configured: true,
  windows: 2,
  lookback_days: 365,
  open: 0,
  overdue: 0,
  due_soon: 0,
  running: 0,
  in_review: 0,
  follow_up: 0,
  no_window: 0,
  decided: 0,
  decided_in_window: 0,
  decided_late: 0,
  held_on_second_look: 0,
  ...overrides,
});

describe("the reportability watch", () => {
  it("asks the server for a list, by product when one is chosen", () => {
    expect(watchPath("open", "", 1)).toBe("/api/v1/complaints/reportability?show=open&page=1&page_size=25");
    expect(watchPath("overdue", "p-1", 2)).toContain("show=overdue&page=2&page_size=25&product_id=p-1");
  });

  it("reads clocks as days left or overdue", () => {
    expect(clockText({ days_left: 2 })).toBe("2 days left");
    expect(clockText({ days_left: 1 })).toBe("1 day left");
    expect(clockText({ days_left: 0 })).toBe("Due today");
    expect(clockText({ days_left: -10 })).toBe("10 days overdue");
    expect(clockText(null)).toBe("No reporting window applies");
    expect(windowLength({ days: 5, day_basis: "WORK" })).toBe("5 work days");
    expect(windowLength(FDA)).toBe("30 calendar days");
  });

  it("reads every state with a label and a tone, never colour alone", () => {
    expect(watchStateOf("OVERDUE")).toEqual({ label: "Overdue", tone: "critical" });
    expect(watchStateOf("FOLLOW_UP")).toEqual({ label: "Answers missing", tone: "warning" });
    expect(watchStateOf("DECIDED").tone).toBe("good");
    expect(watchStateOf("ODD")).toEqual({ label: "—", tone: "neutral" });
  });

  it("leads with what is overdue, and says when no windows are entered", () => {
    expect(watchHeadline(summary({ open: 4, overdue: 1 }))).toMatchObject({
      title: "1 reporting clock overdue",
      tone: "critical",
    });
    expect(watchHeadline(summary({ open: 4, due_soon: 2 })).title).toBe("2 reporting clocks due soon");
    const unset = watchHeadline(summary({ configured: false, windows: 0, open: 3 }));
    expect(unset.detail).toContain("without due dates until your reporting windows are entered");
    expect(watchHeadline(summary()).tone).toBe("good");
  });

  it("says whether a decision came inside the window", () => {
    const base = {
      decision: "REPORTED" as const,
      rationale: "r",
      report_reference: "x",
      reported_on: "2026-10-01",
      window: "FDA",
      due_on: "2026-10-05",
      decided_by: "Rita",
      decided_at: null,
    };
    expect(timelinessOf({ ...base, on_time: true })).toEqual({ label: "Inside the window", tone: "good" });
    expect(timelinessOf({ ...base, on_time: false })?.tone).toBe("critical");
    expect(timelinessOf({ ...base, on_time: null })).toBeNull();
    expect(timelinessOf(null)).toBeNull();
  });
});

describe("the reporting windows", () => {
  const settings = (windows: ReportingWindow[] = [FDA]): ReportabilitySettings => ({
    windows,
    lookback_days: 365,
    configured: windows.length > 0,
    templates: [FDA],
    version: 1,
    updated_by_name: null,
    updated_at: null,
  });

  it("reads markets typed with commas or lines, without repeats in any case or dots", () => {
    expect(marketsOf("US, usa\nU.S.A.; United States, ,us")).toEqual(["US", "usa", "United States"]);
  });

  it("round-trips a window through its form", () => {
    expect(windowOf(windowForm(FDA))).toEqual(FDA);
    expect(windowForm(FDA).key).not.toBe(windowForm(FDA).key);
  });

  it("keeps a template's basis through the form, in the order the server returns a window", () => {
    expect(Object.keys(windowOf(windowForm(FDA)))).toEqual(Object.keys(FDA));
    expect(windowOf(windowForm(FDA)).basis).toEqual(["CFR803_50", "CFR803_53"]);
    expect(windowOf(windowForm(BLANK_WINDOW)).basis).toEqual([]);
    const { basis: _dropped, ...older } = FDA;
    expect(windowForm(older as ReportingWindow).basis).toEqual([]);
  });

  it("sees changes in the windows and the look-back only", () => {
    const forms = [windowForm(FDA)];
    expect(windowsChanged(settings(), forms, "365")).toBe(false);
    expect(windowsChanged(settings(), forms, "180")).toBe(true);
    expect(windowsChanged(settings(), [{ ...forms[0], days: "15" }], "365")).toBe(true);
    expect(windowsChanged(settings(), [], "365")).toBe(true);
  });

  it("checks each window, the look-back and the reason", () => {
    const form = windowForm(FDA);
    const reason = "Procedure QP-08 revision 4";
    expect(windowsProblem([form], "365", reason)).toBeNull();
    expect(windowsProblem([{ ...form, name: "ab" }], "365", reason)).toContain("Window 1: give it a name");
    expect(windowsProblem([form, { ...form, key: 99, name: form.name.toUpperCase() }], "365", reason)).toContain(
      "already called",
    );
    expect(windowsProblem([{ ...form, triggers: [] }], "365", reason)).toBe("Window 1: choose what starts its clock");
    expect(windowsProblem([{ ...form, days: "0" }], "365", reason)).toContain("whole number of days from 1 to 365");
    expect(windowsProblem([{ ...form, days: "2.5" }], "365", reason)).toContain("whole number of days");
    expect(windowsProblem([form], "10", reason)).toBe("Look back a whole number of days from 30 to 3650");
    expect(windowsProblem([form], "365", "short")).toContain("at least 10 characters");
    expect(windowsProblem([windowForm(BLANK_WINDOW)], "365", reason)).toContain("give it a name");
  });

  it("sends the windows tidied", () => {
    const form = { ...windowForm(FDA), name: "  FDA  30 ", note: "  " };
    expect(windowsBody([form], "180", " QP-08 rev 4  ")).toEqual({
      windows: [{ ...FDA, name: "FDA 30" }],
      lookback_days: 180,
      reason: "QP-08 rev 4",
    });
  });
});

describe("CAPA effectiveness", () => {
  const board = (overrides: Partial<BoardSummary> = {}): BoardSummary => ({
    capas: 5,
    not_planned: 0,
    closed_without_check: 0,
    overdue: 0,
    due_soon: 0,
    scheduled: 0,
    effective: 0,
    not_effective: 0,
    date_from_source: 0,
    ...overrides,
  });

  it("asks the server for the board", () => {
    expect(boardPath("attention", 1)).toBe("/api/v1/capas/effectiveness?show=attention&page=1&page_size=25");
  });

  it("reads each state and its due day", () => {
    expect(stateOf("NOT_PLANNED")).toEqual({ label: "No check planned", tone: "serious" });
    expect(stateOf("EFFECTIVE").tone).toBe("good");
    expect(dueText({ state: "DUE_SOON", days_left: 10 })).toBe("10 days left");
    expect(dueText({ state: "OVERDUE", days_left: -3 })).toBe("3 days overdue");
    expect(dueText({ state: "DUE_SOON", days_left: 0 })).toBe("Due today");
    expect(dueText({ state: "NOT_PLANNED", days_left: null })).toBe("No check planned");
  });

  it("counts the days to a check from today where the person is, not from the UTC date (DEV-020)", () => {
    // Planned at 01:05 on 20 October for 18 January: 90 days. The server, counting from the UTC date (still
    // 19 October in India), said 91.
    const justAfterMidnight = new Date(2026, 9, 20, 1, 5);
    const check = { state: "SCHEDULED" as const, days_left: 91, planned_on: "2027-01-18" };
    expect(dueText(check, justAfterMidnight)).toBe("90 days left");
    expect(dueText({ ...check, planned_on: "2026-10-20" }, justAfterMidnight)).toBe("Due today");
    expect(dueText({ ...check, planned_on: "2026-10-17" }, justAfterMidnight)).toBe("3 days overdue");
    expect(clockText({ days_left: 3, due_date: "2026-10-22" }, justAfterMidnight)).toBe("2 days left");
  });

  it("leads with overdue checks and CAPAs closed without one", () => {
    const urgent = boardHeadline(board({ overdue: 1, closed_without_check: 2 }));
    expect(urgent.title).toBe("1 check overdue · 2 CAPAs closed without an effectiveness check");
    expect(urgent.tone).toBe("critical");
    expect(boardHeadline(board({ due_soon: 3 })).title).toBe("3 checks due within 14 days");
    expect(boardHeadline(board({ not_planned: 2 })).title).toBe("2 CAPAs without a planned check");
    expect(boardHeadline(board({ effective: 5 })).tone).toBe("good");
    expect(boardHeadline(board({ capas: 0 })).title).toBe("No CAPAs yet");
  });

  it("describes the recurrence in plain words", () => {
    expect(
      recurrenceText({
        available: true,
        before: { complaints: 3, days: 31, per_30_days: 2.9 },
        since: { complaints: 1, days: 31, per_30_days: 1 },
      }),
    ).toBe("3 complaints in 31 days before (2.9 per 30 days); 1 in 31 days since (1 per 30 days).");
    expect(recurrenceText({ available: false, reason: "No product" })).toBe("No product");
    expect(recurrenceText(null)).toBe("Recurrence was not measured");
  });

  const detail = (check: CapaDetail["check"] = null): Pick<CapaDetail, "check" | "suggestion"> => ({
    check,
    suggestion: {
      criteria: "No new OCC complaints for 90 days",
      planned_on: "2027-01-10",
      measured_from: "2026-10-01",
    },
  });
  const planned = {
    id: "c1",
    round: 1,
    status: "PLANNED" as const,
    criteria: "At most one OCC complaint in 90 days",
    planned_on: "2026-12-31",
    measured_from: "2026-10-01",
    plan_version: 2,
    planned_by: "Ivy",
    planned_at: null,
    result_summary: null,
    evidence: {},
    signed_by: null,
    signer_role: null,
    signed_at: null,
    content_fingerprint: null,
  };

  it("starts a plan from the suggestion, or from the plan already made", () => {
    expect(planForm(detail())).toEqual({
      criteria: "No new OCC complaints for 90 days",
      plannedOn: "2027-01-10",
      measuredFrom: "2026-10-01",
      reason: "",
    });
    expect(planForm(detail(planned)).criteria).toBe(planned.criteria);
  });

  it("checks a plan, and asks a reason only to change one", () => {
    const form = planForm(detail());
    expect(planProblem(form, detail())).toBeNull();
    expect(planProblem({ ...form, criteria: "short" }, detail())).toContain("what will show the action worked");
    expect(planProblem({ ...form, measuredFrom: "2027-02-01" }, detail())).toBe(
      "The measurement starts on or before the day of the check",
    );
    const current = planForm(detail(planned));
    expect(planProblem(current, detail(planned))).toBe("This is already the plan");
    expect(planProblem({ ...current, plannedOn: "2027-01-15" }, detail(planned))).toContain("why the plan changes");
    expect(
      planBody({ ...current, plannedOn: "2027-01-15", reason: " Sensor delivery late " }, detail(planned)),
    ).toEqual({
      criteria: planned.criteria,
      planned_on: "2027-01-15",
      measured_from: "2026-10-01",
      reason: "Sensor delivery late",
    });
    expect(planBody(form, detail())).not.toHaveProperty("reason");
  });

  it("checks a signature and sends the plan version read", () => {
    const form = { result: "EFFECTIVE" as const, summary: "No OCC complaints since", password: "secret", code: "" };
    expect(signProblem({ ...form, result: "" })).toBe("Choose whether the action was effective");
    expect(signProblem({ ...form, summary: "ok" })).toContain("what you found");
    expect(signProblem({ ...form, password: "" })).toBe("Enter your password to sign");
    expect(signProblem({ ...form, code: "12ab" })).toBe("The authenticator code is 6 to 8 digits");
    expect(signProblem(form)).toBeNull();
    expect(signBody({ ...form, code: " 123456 " }, 2)).toEqual({
      result: "EFFECTIVE",
      summary: "No OCC complaints since",
      plan_version: 2,
      password: "secret",
      mfa_code: "123456",
    });
    expect(signBody(form, 1)).not.toHaveProperty("mfa_code");
  });

  it("opens a CAPA a link or a task names", () => {
    expect(parseRecordsTab(recordsTab("abc"))).toEqual({ tab: "Effectiveness checks", capa: "abc" });
    expect(parseRecordsTab(undefined)).toEqual({ tab: "Effectiveness checks", capa: null });
    expect(parseRecordsTab("Unknown")).toEqual({ tab: "Effectiveness checks", capa: null });
  });
});

describe("the reminder tasks", () => {
  it("open the reportability watch and the CAPA's check", () => {
    expect(taskDestination({ task_type: "REPORTABILITY_DECISION", investigation: null })).toEqual({
      section: "Complaints",
      tab: "Reportability",
    });
    expect(
      taskDestination({ task_type: "EFFECTIVENESS_CHECK", investigation: null, details: { capa_id: "c-9" } }),
    ).toEqual({ section: "Records", tab: "Effectiveness checks?capa=c-9" });
    expect(taskDestination({ task_type: "EFFECTIVENESS_CHECK", investigation: null })).toEqual({
      section: "Records",
      tab: "Effectiveness checks",
    });
  });
});
