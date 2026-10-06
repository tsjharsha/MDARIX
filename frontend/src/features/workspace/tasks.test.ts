import { describe, expect, it } from "vitest";
import {
  availableTaskActions,
  dueState,
  dueText,
  hasRoleQueues,
  initialMyWorkTab,
  myWorkTabs,
  pageText,
  priorityLabel,
  priorityRank,
  priorityTone,
  reasonProblem,
  tabCount,
  taskActionBody,
  taskAssignee,
  taskCase,
  taskDestination,
  taskEventActor,
  taskEventText,
  taskListPath,
  taskPath,
  taskRequest,
  taskSignal,
  taskSourceText,
  taskTypeLabel,
  taskViewForTab,
} from "./tasks";

const UUID = "0b6f8f9e-1111-4222-8333-444455556666";
const PRODUCT = "9d1c2b3a-1111-4222-8333-444455556666";

describe("My Work tabs", () => {
  it("opens the requested tab, a former tab's replacement, or Assigned to me", () => {
    expect(initialMyWorkTab("Overdue")).toBe("Overdue");
    expect(initialMyWorkTab("Evidence requests")).toBe("Evidence requests");
    expect(initialMyWorkTab("Needs an owner")).toBe("Role queues");
    expect(initialMyWorkTab("Something else")).toBe("Assigned to me");
    expect(initialMyWorkTab(undefined)).toBe("Assigned to me");
  });

  it("maps each task tab to its server view, and only task tabs", () => {
    expect(taskViewForTab("Assigned to me")).toBe("assigned");
    expect(taskViewForTab("Role queues")).toBe("queue");
    expect(taskViewForTab("Returned to me")).toBe("returned");
    expect(taskViewForTab("Due soon")).toBe("due_soon");
    expect(taskViewForTab("My AI conversations")).toBeNull();
  });

  it("shows Role queues only to someone who works a queue (or was sent there)", () => {
    expect(myWorkTabs(null)).not.toContain("Role queues");
    expect(myWorkTabs({ queues: [] })).not.toContain("Role queues");
    const summary = { queues: [{ role: "INVESTIGATOR", task_type: "INVESTIGATION", count: 2 }] };
    expect(hasRoleQueues(summary)).toBe(true);
    expect(myWorkTabs(summary)).toEqual([
      "Assigned to me",
      "Role queues",
      "Waiting",
      "Returned to me",
      "Due soon",
      "Overdue",
      "Completed",
      "Evidence requests",
      "My AI conversations",
    ]);
    expect(myWorkTabs(null, "Role queues")).toContain("Role queues");
    expect(hasRoleQueues({ counts: { queue: 1 } })).toBe(true);
  });

  it("counts tabs from the summary, never for Completed or the other tabs", () => {
    const summary = { counts: { assigned: 3, queue: 0, overdue: 1 } };
    expect(tabCount("Assigned to me", summary)).toBe(3);
    expect(tabCount("Role queues", summary)).toBe(0);
    expect(tabCount("Overdue", summary)).toBe(1);
    expect(tabCount("Due soon", summary)).toBeNull();
    expect(tabCount("Completed", summary)).toBeNull();
    expect(tabCount("Evidence requests", summary)).toBeNull();
    expect(tabCount("Assigned to me", null)).toBeNull();
  });
});

describe("where a task opens", () => {
  const investigation = { id: UUID, business_id: "INV000147", product_id: PRODUCT };

  it("opens each kind of work in its section", () => {
    const at = (task_type: string) => taskDestination({ task_type, investigation });
    for (const type of ["INVESTIGATION", "FOLLOW_UP", "EVIDENCE_REQUEST", "EVIDENCE_REVIEW", "IMPACT_ASSESSMENT"])
      expect(at(type)).toEqual({ section: "Investigations", tab: "Workspace" });
    expect(at("DECISION_APPROVAL")).toEqual({ section: "Decisions", tab: "Decision center" });
    expect(at("RISK_REVIEW")).toEqual({ section: "Intelligence", tab: "Risk & traceability" });
    expect(at("REGULATORY_REVIEW")).toEqual({ section: "Intelligence", tab: "Regulatory copilot" });
    expect(taskDestination({ task_type: "SIGNAL_TRIAGE", investigation: null })).toEqual({ section: "Signals" });
  });

  it("opens a signal triage task on its signal, else on the signal inbox", () => {
    const triage = (source: Parameters<typeof taskDestination>[0]["source"]) =>
      taskDestination({ task_type: "SIGNAL_TRIAGE", investigation: null, source });
    expect(triage({ type: "SIGNAL", id: UUID, business_id: "SIG000023" })).toEqual({
      section: "Signals",
      tab: "Signal inbox?signal=SIG000023",
    });
    expect(triage({ type: "signal", id: UUID, business_id: null })).toEqual({
      section: "Signals",
      tab: `Signal inbox?signal=${UUID}`,
    });
    expect(triage({ business_id: "SIG000007" })).toEqual({ section: "Signals", tab: "Signal inbox?signal=SIG000007" });
    // A triage task about a complaint names no signal: the inbox opens.
    expect(triage({ type: "COMPLAINT", id: UUID, business_id: "CMP000012" })).toEqual({ section: "Signals" });
    expect(triage(null)).toEqual({ section: "Signals" });
    expect(taskSignal({ source: { type: "SIGNAL", business_id: "SIG000023" } })).toBe("SIG000023");
    expect(taskSignal({ source: { type: "INVESTIGATION", business_id: "INV000147" } })).toBeNull();
    expect(taskSignal({})).toBeNull();
  });

  it("opens an evidence request task on that request in My Work", () => {
    const source = { type: "EvidenceRequest", id: UUID, business_id: "EVR000004" };
    for (const task_type of ["EVIDENCE_RESPONSE", "EVIDENCE_REQUEST", "EVIDENCE_REVIEW"])
      expect(taskDestination({ task_type, investigation, source })).toEqual({
        section: "My Work",
        tab: `Evidence requests?request=${UUID}`,
      });
    expect(taskRequest({ source })).toBe(UUID);
    expect(taskRequest({ source: { type: "EVIDENCE_REQUEST", business_id: "EVR000004" } })).toBe("EVR000004");
    expect(taskRequest({ source: { type: "SupplierEvidenceRequest", id: UUID } })).toBeNull();
    expect(taskRequest({ source: { type: "Investigation", id: UUID } })).toBeNull();
    expect(taskRequest({})).toBeNull();
  });

  it("keeps opening the case for evidence tasks about anything else", () => {
    const supplier = { type: "SupplierEvidenceRequest", id: UUID, business_id: "SER000002" };
    expect(taskDestination({ task_type: "EVIDENCE_REQUEST", investigation, source: supplier })).toEqual({
      section: "Investigations",
      tab: "Workspace",
    });
    expect(taskDestination({ task_type: "EVIDENCE_RESPONSE", investigation })).toEqual({
      section: "Investigations",
      tab: "Workspace",
    });
    expect(taskDestination({ task_type: "EVIDENCE_RESPONSE", investigation: null })).toEqual({
      section: "My Work",
      tab: "Evidence requests",
    });
    expect(
      taskDestination({ task_type: "INVESTIGATION", investigation, source: { type: "Investigation", id: UUID } }),
    ).toEqual({ section: "Investigations", tab: "Workspace" });
  });

  it("opens My Work on the tab a destination with a request names", () => {
    expect(initialMyWorkTab(`Evidence requests?request=${UUID}`)).toBe("Evidence requests");
    expect(initialMyWorkTab("Nothing?request=x")).toBe("Assigned to me");
  });

  it("opens an unknown kind of task on its case, else stays in My Work", () => {
    expect(taskDestination({ task_type: "SOMETHING_NEW", investigation })).toEqual({
      section: "Investigations",
      tab: "Workspace",
    });
    expect(taskDestination({ task_type: "SOMETHING_NEW", investigation: null })).toEqual({ section: "My Work" });
  });

  it("brings the task's case and its product into the context", () => {
    expect(taskCase({ investigation })).toEqual({ investigationId: UUID, productId: PRODUCT });
    expect(taskCase({ investigation: { id: UUID } })).toEqual({ investigationId: UUID, productId: null });
    expect(taskCase({ investigation: null })).toBeNull();
  });
});

describe("due dates", () => {
  const now = new Date("2026-10-06T12:00:00Z");

  it("reads overdue, due within two days, later, none and done", () => {
    expect(dueState({ due_at: "2026-10-05T12:00:00Z" }, now)).toBe("overdue");
    expect(dueState({ due_at: "2026-10-20T12:00:00Z", overdue: true }, now)).toBe("overdue");
    expect(dueState({ due_at: "2026-10-07T12:00:00Z" }, now)).toBe("due_soon");
    expect(dueState({ due_at: "2026-10-20T12:00:00Z" }, now)).toBe("due");
    expect(dueState({ due_at: null }, now)).toBe("none");
    expect(dueState({ due_at: "not a date" }, now)).toBe("none");
    expect(dueState({ due_at: "2026-10-01T12:00:00Z", status: "COMPLETED" }, now)).toBe("done");
    expect(dueState({ due_at: "2026-10-01T12:00:00Z", completed_at: "2026-10-02T12:00:00Z" }, now)).toBe("done");
  });

  it("says so next to the date", () => {
    expect(dueText({ due_at: "2026-10-05T12:00:00Z" }, String, now)).toBe("2026-10-05T12:00:00Z · overdue");
    expect(dueText({ due_at: "2026-10-07T12:00:00Z" }, String, now)).toBe("2026-10-07T12:00:00Z · due soon");
    expect(dueText({ due_at: "2026-10-20T12:00:00Z" }, String, now)).toBe("2026-10-20T12:00:00Z");
    expect(dueText({ due_at: null }, String, now)).toBe("No due date");
    expect(dueText({ due_at: null, overdue: true }, String, now)).toBe("Overdue");
  });
});

describe("how a task reads", () => {
  it("ranks and labels priorities", () => {
    expect(priorityRank("CRITICAL")).toBeGreaterThan(priorityRank("HIGH"));
    expect(priorityRank("HIGH")).toBeGreaterThan(priorityRank("LOW"));
    expect(priorityRank(null)).toBe(0);
    expect(priorityTone("CRITICAL")).toBe("critical");
    expect(priorityTone("unknown")).toBe("neutral");
    expect(priorityLabel("MEDIUM")).toBe("Medium");
    expect(priorityLabel(null)).toBe("—");
  });

  it("shows the type's label and the source's business ID, never a code or a UUID", () => {
    expect(taskTypeLabel({ task_type: "EVIDENCE_REVIEW", task_type_label: "Evidence review" })).toBe("Evidence review");
    expect(taskTypeLabel({ task_type: "EVIDENCE_REVIEW" })).toBe("Evidence Review");
    expect(taskSourceText({ source: { business_id: "CMP000012", label: "Complaint" } })).toBe("CMP000012");
    expect(taskSourceText({ source: { business_id: UUID, label: "Complaint" } })).toBe("Complaint");
    expect(taskSourceText({ source: null })).toBe("—");
  });

  it("names the person holding a task, else its role queue", () => {
    expect(taskAssignee({ assigned_user: { id: UUID, name: "Ana Silva" }, assigned_role: "RISK_REVIEWER" })).toEqual({
      primary: "Ana Silva",
      secondary: "Risk Reviewer",
    });
    expect(taskAssignee({ assigned_user: null, assigned_role: "INVESTIGATOR" })).toEqual({
      primary: "Quality Investigator",
      secondary: "Role queue",
    });
    expect(taskAssignee({ assigned_role: "X", assigned_role_label: "Site lead" }).primary).toBe("Site lead");
    expect(taskAssignee({})).toEqual({ primary: "Unassigned", secondary: null });
  });

  it("describes history events with who did them", () => {
    expect(taskEventText({ event_type: "ACCEPTED", from_status: "ASSIGNED", to_status: "IN_PROGRESS" })).toBe(
      "Accepted: Assigned → In Progress",
    );
    expect(taskEventText({ event_type: "CREATED", to_status: "CREATED" })).toBe("Created");
    expect(taskEventText({ event_type: "REASSIGNED", from_status: "ASSIGNED", to_status: "ASSIGNED" })).toBe(
      "Reassigned: Assigned",
    );
    expect(taskEventActor({ event_type: "x", actor_name: "Ana Silva", actor_role: "RISK_REVIEWER" })).toBe(
      "Ana Silva (Risk Reviewer)",
    );
    expect(taskEventActor({ event_type: "x" })).toBe("MDARIX");
  });
});

describe("task actions", () => {
  it("offers only what the server allows, in a fixed order", () => {
    expect(
      availableTaskActions({ actions: { can_reassign: true, can_decline: true, can_accept: true, can_claim: false } }),
    ).toEqual(["accept", "decline", "reassign"]);
    expect(availableTaskActions({ actions: null })).toEqual([]);
  });

  it("checks reasons with the server's limits", () => {
    expect(reasonProblem("too short")).toMatch(/at least 10/);
    expect(reasonProblem("Out of office until next month")).toBeNull();
    expect(reasonProblem("x".repeat(1001))).toMatch(/1000/);
    expect(reasonProblem("", false)).toBeNull();
    expect(reasonProblem("short", false)).toMatch(/at least 10/);
  });

  it("sends the body each action expects", () => {
    expect(taskActionBody("accept")).toBeUndefined();
    expect(taskActionBody("claim")).toBeUndefined();
    expect(taskActionBody("decline", { reason: "  Not my product line  " })).toEqual({
      reason: "Not my product line",
    });
    expect(
      taskActionBody("reassign", { assigneeUserId: UUID, assignedRole: "REVIEWER", reason: "Holiday cover" }),
    ).toEqual({ assignee_user_id: UUID, reason: "Holiday cover" });
    expect(taskActionBody("reassign", { assignedRole: "REVIEWER", reason: "Needs a reviewer" })).toEqual({
      assigned_role: "REVIEWER",
      reason: "Needs a reviewer",
    });
    expect(taskActionBody("complete", {})).toEqual({});
    expect(taskActionBody("complete", { reason: "Evidence reviewed", outcome: "ACCEPTED" })).toEqual({
      outcome: "ACCEPTED",
      reason: "Evidence reviewed",
    });
  });

  it("builds the task addresses", () => {
    expect(taskPath(UUID)).toBe(`/api/v1/tasks/${UUID}`);
    expect(taskPath(UUID, "release")).toBe(`/api/v1/tasks/${UUID}/release`);
    expect(taskListPath("queue", 2, 50, "  INV000147 ")).toBe(
      "/api/v1/tasks?view=queue&page=2&page_size=50&q=INV000147",
    );
    expect(taskListPath("assigned", 0, 5)).toBe("/api/v1/tasks?view=assigned&page=1&page_size=5");
  });

  it("says which part of a long list is shown", () => {
    expect(pageText({ total: 130, page: 2, page_size: 50 }, 50)).toBe("Showing 51–100 of 130");
    expect(pageText({ total: 12, page: 1, page_size: 50 }, 12)).toBe("");
    expect(pageText(null, 0)).toBe("");
  });
});
