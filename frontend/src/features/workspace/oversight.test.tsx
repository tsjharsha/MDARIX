import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import {
  ALERTS,
  NO_FILTERS,
  absenceProblem,
  eventPath,
  eventTab,
  exportPath,
  filterQuery,
  groupAlerts,
  hoursText,
  openItemsText,
  oversightPath,
  parseReadinessTab,
  readyProblem,
  type Alert,
  type AlertList,
  type EventView,
  type Oversight,
} from "./oversight";

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

const { RemindersPanel, AlertsBell } = await import("./sections/Reminders");
const { OversightView, EventDrawer } = await import("./sections/Oversight");

function workspace(permissions: string[]): WorkspaceApi {
  return {
    session: { user_id: "me", allowed_menu: ["home", "products"], business_permissions: permissions },
    open: vi.fn(),
    notify: vi.fn(),
    work: { products: [] },
  } as unknown as WorkspaceApi;
}

const render = (node: ReactNode, permissions: string[] = ["quality.review", "data.export"]) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={workspace(permissions)}>{node}</WorkspaceContext.Provider>);

const alert = (over: Partial<Alert>): Alert => ({
  id: "a1",
  ids: ["a1"],
  tier: "REMINDER",
  tier_label: "Reminder",
  reason: "OWNER",
  reason_label: "You own it",
  category: "TRIAGE",
  category_label: "Triage and first contact",
  title: "Triage SAMPLE-CALL-03: flagged",
  ref: "SAMPLE-CALL-03",
  owner: null,
  due_at: "2026-11-02T10:00:00+00:00",
  state: "DUE_SOON",
  state_label: "Due soon",
  hours_left: 20,
  read: false,
  opens: { section: "Complaints", tab: "Triage" },
  ...over,
});

const escalation = alert({
  id: "a2",
  ids: ["a2", "a3"],
  tier: "ESCALATION",
  reason: "NO_ONE_ELSE",
  reason_label: "Nobody else can be reached: invite a colleague or name a backup",
  category: "COMMUNICATION",
  category_label: "Communications",
  title: "Reply due from Reporter of SAMPLE-RV-08",
  ref: "SAMPLE-RV-08",
  owner: "Taylor Quality",
  state: "OVERDUE",
  state_label: "Overdue",
  hours_left: -50,
});

describe("the oversight rules", () => {
  it("builds the list's query from the filters that are set", () => {
    expect(filterQuery(NO_FILTERS)).toBe("");
    expect(oversightPath({ ...NO_FILTERS, market: "US", show: "all" })).toBe("/api/v1/oversight?market=US&show=all");
    expect(exportPath({ ...NO_FILTERS, product: "OrbitCare 300" })).toBe(
      "/api/v1/oversight/export.csv?product=OrbitCare+300",
    );
    expect(eventPath("c 1")).toBe("/api/v1/oversight/events/c%201");
  });

  it("opens Readiness on the oversight view, or on one event", () => {
    expect(parseReadinessTab(undefined)).toEqual({ tab: "Inspection checks", event: null });
    expect(parseReadinessTab("Oversight")).toEqual({ tab: "Oversight", event: null });
    expect(parseReadinessTab(eventTab("abc"))).toEqual({ tab: "Oversight", event: "abc" });
  });

  it("says the time left in hours, then days", () => {
    expect(hoursText({ hours_left: 3.2 })).toBe("3 h left");
    expect(hoursText({ hours_left: -5 })).toBe("5 h overdue");
    expect(hoursText({ hours_left: -72 })).toBe("3 days overdue");
    expect(hoursText({ hours_left: 0.1 })).toBe("1 h left");
    // J40: the state says overdue, so the text never reads "1 h left" beside "Overdue".
    expect(hoursText({ hours_left: 0.4, state: "OVERDUE" })).toBe("Overdue");
  });

  it("shows escalations and overdue items one by one, and groups the ones due soon", () => {
    const groups = groupAlerts([alert({}), alert({ id: "b", ref: "CMP-2" }), escalation]);
    expect(groups.urgent.map((item) => item.ref)).toEqual(["SAMPLE-RV-08"]);
    expect(groups.soon).toHaveLength(1);
    expect(groups.soon[0].items).toHaveLength(2);
  });

  it("asks for a reason before signing an event with open items, and only the owner signs", () => {
    expect(readyProblem({ you_are_owner: false, blocked: 0, reason_min: 20 }, "")).toMatch(/Only the event owner/);
    expect(readyProblem({ you_are_owner: true, blocked: 2, reason_min: 20 }, "short")).toMatch(
      /2 items are still open/,
    );
    expect(readyProblem({ you_are_owner: true, blocked: 2, reason_min: 20 }, "x".repeat(20))).toBeNull();
    expect(readyProblem({ you_are_owner: true, blocked: 0, reason_min: 20 }, "")).toBeNull();
  });

  it("says an event's open items and its next step, never a missing one (A6)", () => {
    expect(openItemsText({ blocked: 0, next: null })).toBe("None");
    expect(openItemsText({ blocked: 2, next: "Sign the US market assessment" })).toBe(
      "2 open. Next: Sign the US market assessment",
    );
    // A finished event (SAMPLE-RV-09): its open item was signed with its reason, so there is no next step.
    expect(openItemsText({ blocked: 1, next: null })).toBe("1 open, signed with its reason");
  });

  it("checks an absence before it is sent", () => {
    const form = { starts_on: "2026-11-02", ends_on: "2026-11-04", backup_id: "" };
    expect(absenceProblem(form, "2026-11-02")).toMatch(/covers for you/);
    expect(absenceProblem({ ...form, backup_id: "p", ends_on: "2026-11-01" }, "2026-11-02")).toMatch(
      /before the first/,
    );
    expect(absenceProblem({ ...form, backup_id: "p" }, "2026-11-02")).toBeNull();
  });
});

const list: AlertList = {
  items: [escalation, alert({})],
  unread: 2,
  escalations: 1,
  absences: [
    {
      id: "ab1",
      user_id: "author",
      user_name: "MDARIX sample author",
      backup_id: "me",
      backup_name: "Taylor Quality",
      starts_on: "2026-10-30",
      ends_on: "2026-11-06",
      note: "Sample: at a supplier audit (fictional).",
      sample: true,
    },
  ],
  people: [{ id: "p2", name: "Priya Backup" }],
  never: "An alert tells people in MDARIX; it never closes or changes the item. MDARIX sends no e-mail about it.",
};

describe("the reminders in My Work and the bell", () => {
  it("lists the escalation, groups the triage items and shows whom you cover for", () => {
    resources.data[ALERTS] = list;
    const html = render(<RemindersPanel />);
    expect(html).toContain("2 reminders for you, 2 unread");
    expect(html).toContain("Escalated to you");
    expect(html).toContain("Nobody else can be reached");
    expect(html).toContain("1 due soon");
    expect(html).toContain("You cover for <strong>MDARIX sample author</strong>");
    expect(html).toContain("I will be away");
    expect(html).toContain("Mark all read");
  });

  it("counts the unread alerts on the bell", () => {
    resources.data[ALERTS] = list;
    const html = render(<AlertsBell onOpen={() => undefined} />);
    expect(html).toContain("2 unread reminders, 1 escalated to you");
    expect(html).toContain("uw-rm-count tone-critical");
  });
});

const oversight: Oversight = {
  as_of: "2026-11-01T10:00:00+00:00",
  items: [
    {
      key: "task:1",
      category: "COMMUNICATION",
      category_label: "Communications",
      title: "Reply due from Reporter of SAMPLE-RV-08",
      ref: "SAMPLE-RV-08",
      complaint_id: "c8",
      market: "US",
      product: "PulseWatch 410",
      owner: "Taylor Quality",
      queue: null,
      away: null,
      due_at: "2026-10-29T23:59:59+00:00",
      state: "OVERDUE",
      state_label: "Overdue",
      hours_left: -58,
      escalated_to: ["Taylor Quality"],
      alerts: true,
      opens: { section: "Complaints", tab: "Communications?complaint=c8" },
    },
  ],
  total: 23,
  counts: {},
  overdue: 2,
  due_soon: 10,
  filters: { products: ["PulseWatch 410"], markets: ["US"], categories: [{ code: "TRIAGE", label: "Triage" }] },
  events: [
    {
      complaint_id: "c8",
      ref: "SAMPLE-RV-08",
      product: "PulseWatch 410",
      market: "US",
      owner_id: "me",
      owner_name: "Taylor Quality",
      stage: "Market assessment",
      blocked: 3,
      next: "Sign the United States (FDA) market assessment",
      state: "NOT_READY",
      state_label: "Not ready to close",
      sample: true,
    },
  ],
  event_counts: { NOT_READY: 1, READY_TO_SIGN: 1, NOT_FILED: 0, FILED: 0, CLOSED_BEFORE_READY: 3, CLOSED: 0 },
  away: list.absences,
  settings: {
    time_zone: "UTC",
    work_days: [0, 1, 2, 3, 4],
    holidays: [],
    reminder_hours: 24,
    escalation_role: "LEADER",
    escalation_role_label: "Leader (Quality Manager)",
    updated_at: null,
  },
  staffing: "Only one person can receive alerts: invite a colleague, so an overdue item reaches someone else.",
  never: "An alert tells people in MDARIX; it never closes or changes the item. MDARIX sends no e-mail about it.",
};

describe("the oversight view", () => {
  it("shows the counts, the items with owner and escalation, the events and the calendar", () => {
    resources.data["/api/v1/oversight"] = oversight;
    const html = render(<OversightView />, ["data.export"]);
    expect(html).toContain("Closed in the QMS before ready");
    expect(html).toContain("1 of 23 dated items");
    expect(html).toContain("Reply due from Reporter of SAMPLE-RV-08");
    expect(html).toMatch(/\d+ (days?|h) overdue/);
    expect(html).toContain("Not ready to close");
    expect(html).toContain("3 open. Next: Sign the United States (FDA) market assessment");
    expect(html).toContain("invite a colleague");
    expect(html).toContain("is away until");
    expect(html).toContain("CSV");
    expect(html).toContain("UTC, Mon Tue Wed Thu Fri");
    expect(html).not.toContain("This list is incomplete");
  });

  it("says plainly when a source reached its read cut (B6a run 3: never silently incomplete)", () => {
    resources.data["/api/v1/oversight"] = {
      ...oversight,
      incomplete: ["the reportability watch beyond its first 20,000 complaints"],
    };
    const html = render(<OversightView />, ["data.export"]);
    expect(html).toContain("This list is incomplete: the reportability watch beyond its first 20,000 complaints");
    resources.data["/api/v1/oversight"] = oversight;
  });

  it("shows an event's checklist, its stage and the form to sign ready to close", () => {
    const view: EventView = {
      event: {
        complaint_id: "c3",
        ref: "SAMPLE-RT-03",
        business_id: "CMP000012",
        product: "PulseWatch 410",
        market: "US",
        awareness_at: null,
        status_in_qms: "open",
        owner_id: "me",
        owner_name: "Taylor Quality",
        owner_named: true,
        sample: true,
      },
      summary: { nearest_deadline: null, open_requests: 0, next_action: null },
      stages: [
        { code: "TRIAGE", label: "Triage", state: "DONE" },
        { code: "READY", label: "Ready to close", state: "CURRENT" },
      ],
      checklist: [
        {
          code: "DECISION",
          label: "The decision is signed",
          result: "PASS",
          result_label: "Done",
          detail: "Signed",
          opens: null,
        },
      ],
      blocked: 0,
      state: "READY_TO_SIGN",
      state_label: "Checklist clear: the owner signs ready to close",
      changed_since_signed: false,
      ready: null,
      decision_record: {
        entries: [
          {
            kind: "Disposition",
            summary: "Version 1: service level",
            reason: null,
            signer: "MDARIX sample author",
            signed_at: "2026-10-12T09:00:00+00:00",
            meaning: "Signed disposition",
            record_id: "r1",
            record_ref: null,
          },
        ],
        sha256: "a".repeat(64),
        version: 0,
        filed: null,
      },
      you_are_owner: true,
      people: [{ id: "me", name: "Taylor Quality" }],
      reason_min: 20,
      never_closes: "MDARIX never closes the complaint.",
      practice_label: null,
    };
    resources.data[eventPath("c3")] = view;
    const html = render(<EventDrawer complaintId="c3" onClose={() => undefined} onChanged={() => undefined} />);
    expect(html).toContain("Event SAMPLE-RT-03");
    expect(html).toContain("stage-current");
    expect(html).toContain("Every MDARIX decision on this event is signed");
    expect(html).toContain("Sign ready to close");
    expect(html).toContain("Version 1: service level");
    expect(html).toContain("Decision record (PDF)");
  });
});

describe("Try the daily list beside the deadline downloads (B6a, owner 11 Nov)", () => {
  it("is offered in a free trial while the list is off, and gone once it is on", async () => {
    const { TryDailyList } = await import("./sections/Account");
    const path = "/api/v1/me/email-preferences";
    resources.data[path] = { daily_deadlines_eligible: true, daily_deadlines_trial: true, daily_deadlines: false };
    expect(render(<TryDailyList />)).toContain("Try the daily list");
    resources.data[path] = { daily_deadlines_eligible: true, daily_deadlines_trial: true, daily_deadlines: true };
    expect(render(<TryDailyList />)).not.toContain("Try the daily list");
    resources.data[path] = { daily_deadlines_eligible: true, daily_deadlines_trial: false, daily_deadlines: false };
    expect(render(<TryDailyList />)).not.toContain("Try the daily list");
  });
});
