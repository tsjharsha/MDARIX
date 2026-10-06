// Pure rules for the task inbox (My Work) and the dashboard's "My work": which tabs exist, where a task opens, how
// its due date and assignment read, and what each action sends. The server owns every task and decides every action;
// these only shape what the person sees.
import { titleCase, type Tone } from "../admin/console/dashboardModel";
import { roleLabel } from "../../app/roles";
import { safeText } from "../../app/displayId";
import type { WorkspaceSection } from "./workspaceContext";
import { signalsTab } from "./signals";

export type TaskView = "assigned" | "queue" | "waiting" | "returned" | "due_soon" | "overdue" | "completed" | "created";
export type TaskPriority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type TaskActions = {
  can_accept?: boolean;
  can_decline?: boolean;
  can_claim?: boolean;
  can_release?: boolean;
  can_reassign?: boolean;
  can_complete?: boolean;
};

export type Task = {
  id: string;
  business_id?: string | null;
  task_type: string;
  task_type_label?: string | null;
  title?: string | null;
  status?: string | null;
  priority?: TaskPriority | string | null;
  due_at?: string | null;
  is_return?: boolean | null;
  overdue?: boolean | null;
  source?: { type?: string | null; id?: string | null; business_id?: string | null; label?: string | null } | null;
  investigation?: { id: string; business_id?: string | null; product_id?: string | null } | null;
  assigned_role?: string | null;
  assigned_role_label?: string | null;
  assigned_user?: { id: string; name?: string | null } | null;
  created_at?: string | null;
  updated_at?: string | null;
  accepted_at?: string | null;
  completed_at?: string | null;
  completion_outcome?: string | null;
  actions?: TaskActions | null;
};

export type TaskEvent = {
  event_type: string;
  actor_name?: string | null;
  actor_role?: string | null;
  from_status?: string | null;
  to_status?: string | null;
  reason?: string | null;
  created_at?: string | null;
};

export type TaskDetail = Task & { events?: TaskEvent[] };
export type TaskList = { view: TaskView; items: Task[]; total: number; page: number; page_size: number };
export type TaskCounts = Partial<
  Record<"assigned" | "queue" | "waiting" | "returned" | "due_soon" | "overdue", number>
>;
export type TaskSummary = {
  counts?: TaskCounts;
  roles?: Array<{ code: string; label?: string | null }>;
  queues?: Array<{
    role: string;
    role_label?: string | null;
    task_type: string;
    task_type_label?: string | null;
    count: number;
  }>;
};

/** The task lists of My Work, in the order of its tabs, with the server view each one reads. */
export const TASK_TABS = [
  { view: "assigned", tab: "Assigned to me" },
  { view: "queue", tab: "Role queues" },
  { view: "waiting", tab: "Waiting" },
  { view: "returned", tab: "Returned to me" },
  { view: "due_soon", tab: "Due soon" },
  { view: "overdue", tab: "Overdue" },
  { view: "completed", tab: "Completed" },
] as const;

export type TaskTab = (typeof TASK_TABS)[number]["tab"];
/** My Work's tabs that are not task lists; they keep working as before. */
export const OTHER_MY_WORK_TABS = ["Evidence requests", "My AI conversations"] as const;
export type MyWorkTab = TaskTab | (typeof OTHER_MY_WORK_TABS)[number];

const ALL_TABS: readonly string[] = [...TASK_TABS.map((item) => item.tab), ...OTHER_MY_WORK_TABS];
// Former tab names still open the list that replaced them (links, bookmarks, the dashboard).
const LEGACY_TABS: Record<string, MyWorkTab> = { "Needs an owner": "Role queues" };

/** The tab My Work opens on for a requested tab name; "Assigned to me" when the name is unknown. */
export function initialMyWorkTab(tab?: string | null): MyWorkTab {
  if (tab && ALL_TABS.includes(tab)) return tab as MyWorkTab;
  return (tab && LEGACY_TABS[tab]) || "Assigned to me";
}

/** The server view a task tab reads, or null for a tab that is not a task list. */
export function taskViewForTab(tab: string): TaskView | null {
  return TASK_TABS.find((item) => item.tab === tab)?.view ?? null;
}

/** Whether the person works any role queue: the summary lists a queue, or counts tasks waiting in one. */
export function hasRoleQueues(summary: TaskSummary | null | undefined): boolean {
  return (summary?.queues?.length ?? 0) > 0 || (summary?.counts?.queue ?? 0) > 0;
}

/** My Work's tabs: Role queues only for someone who works a queue (or who was sent to it), then the other tabs. */
export function myWorkTabs(summary: TaskSummary | null | undefined, active?: string): MyWorkTab[] {
  return [
    ...TASK_TABS.filter((item) => item.view !== "queue" || hasRoleQueues(summary) || active === item.tab).map(
      (item) => item.tab,
    ),
    ...OTHER_MY_WORK_TABS,
  ];
}

/** The count shown on a tab, from GET /api/v1/tasks/summary; null when there is none to show. */
export function tabCount(tab: string, summary: TaskSummary | null | undefined): number | null {
  const view = taskViewForTab(tab);
  if (!view || view === "completed" || view === "created") return null;
  const value = summary?.counts?.[view];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** The signal a task is about (its source), by business ID (SIG000023) or else its id; null for any other source. */
export function taskSignal(task: Partial<Pick<Task, "source">>): string | null {
  const source = task.source;
  if (!source) return null;
  const type = String(source.type ?? "")
    .trim()
    .toUpperCase();
  const business = safeText(source.business_id);
  // A triage task that came from a complaint (or anything else) opens the inbox, not a signal it does not name.
  if (type !== "SIGNAL" && !(business && /^SIG\d/i.test(business))) return null;
  return business ?? (source.id ? String(source.id).trim() || null : null);
}

/** Where "Open" takes a task: the section (and tab) where its work is done; a signal triage task opens its signal. */
export function taskDestination(task: Pick<Task, "task_type" | "investigation"> & Partial<Pick<Task, "source">>): {
  section: WorkspaceSection;
  tab?: string;
} {
  switch (String(task.task_type ?? "").toUpperCase()) {
    case "SIGNAL_TRIAGE": {
      const signal = taskSignal(task);
      return signal ? { section: "Signals", tab: signalsTab({ signal }) } : { section: "Signals" };
    }
    case "DECISION_APPROVAL":
      return { section: "Decisions", tab: "Decision center" };
    case "RISK_REVIEW":
      return { section: "Intelligence", tab: "Risk & traceability" };
    case "REGULATORY_REVIEW":
      return { section: "Intelligence", tab: "Regulatory copilot" };
    case "INVESTIGATION":
    case "FOLLOW_UP":
    case "EVIDENCE_REQUEST":
    case "EVIDENCE_REVIEW":
    case "IMPACT_ASSESSMENT":
    case "QUALITY_REVIEW":
      return { section: "Investigations", tab: "Workspace" };
    default:
      return task.investigation ? { section: "Investigations", tab: "Workspace" } : { section: "My Work" };
  }
}

/** The product and investigation a task's work belongs to, for the context bar; null for a task without a case. */
export function taskCase(
  task: Pick<Task, "investigation">,
): { investigationId: string; productId: string | null } | null {
  // The investigation's UUID is the technical key the context uses; it is never shown.
  const id = task.investigation?.id ? String(task.investigation.id).trim() : "";
  if (!id) return null;
  return {
    investigationId: id,
    productId: task.investigation?.product_id ? String(task.investigation.product_id) : null,
  };
}

const CLOSED_TASK = ["COMPLETED", "CANCELLED", "CLOSED", "DONE"];
export const DUE_SOON_HOURS = 48;

export type DueState = "overdue" | "due_soon" | "due" | "none" | "done";

/** How a task's due date stands: overdue (as the server says, or past due), due within two days, later, or none. */
export function dueState(
  task: Pick<Task, "due_at" | "overdue" | "status" | "completed_at">,
  now = new Date(),
): DueState {
  if (task.completed_at || CLOSED_TASK.includes(String(task.status ?? "").toUpperCase())) return "done";
  if (task.overdue === true) return "overdue";
  if (!task.due_at) return "none";
  const due = new Date(task.due_at).getTime();
  if (Number.isNaN(due)) return "none";
  if (due < now.getTime()) return "overdue";
  return due - now.getTime() <= DUE_SOON_HOURS * 3_600_000 ? "due_soon" : "due";
}

/** "3 Oct 2026, 14:00 · overdue" for the Due column; "No due date" when there is none. */
export function dueText(
  task: Pick<Task, "due_at" | "overdue" | "status" | "completed_at">,
  format: (value: unknown) => string,
  now = new Date(),
): string {
  const state = dueState(task, now);
  if (!task.due_at) return state === "overdue" ? "Overdue" : "No due date";
  const when = format(task.due_at);
  if (state === "overdue") return `${when} · overdue`;
  if (state === "due_soon") return `${when} · due soon`;
  return when;
}

const PRIORITY_RANK: Record<string, number> = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };
const PRIORITY_TONE: Record<string, Tone> = {
  CRITICAL: "critical",
  HIGH: "serious",
  MEDIUM: "warning",
  LOW: "neutral",
};

/** A priority's rank for sorting (Critical first when sorted descending); 0 when unknown. */
export const priorityRank = (priority: unknown) => PRIORITY_RANK[String(priority ?? "").toUpperCase()] ?? 0;
export const priorityTone = (priority: unknown): Tone =>
  PRIORITY_TONE[String(priority ?? "").toUpperCase()] ?? "neutral";
export const priorityLabel = (priority: unknown) => (priority ? titleCase(String(priority)) : "—");

/** The task's type as people read it ("Evidence review"), never the raw code. */
export const taskTypeLabel = (task: Pick<Task, "task_type" | "task_type_label">) =>
  safeText(task.task_type_label) ?? (task.task_type ? titleCase(String(task.task_type)) : "Task");

/** The record a task came from, by its business ID (or its label), never a UUID. */
export const taskSourceText = (task: Pick<Task, "source">) =>
  safeText(task.source?.business_id) ?? safeText(task.source?.label) ?? "—";

/** Who holds a task: the person (with their role queue below), else the role queue, else "Unassigned". */
export function taskAssignee(task: Pick<Task, "assigned_user" | "assigned_role" | "assigned_role_label">): {
  primary: string;
  secondary: string | null;
} {
  const role =
    task.assigned_role || task.assigned_role_label ? roleLabel(task.assigned_role, task.assigned_role_label) : "";
  const person = safeText(task.assigned_user?.name);
  if (person) return { primary: person, secondary: role || null };
  if (role) return { primary: role, secondary: "Role queue" };
  return { primary: "Unassigned", secondary: null };
}

export type TaskActionKey = "accept" | "claim" | "complete" | "decline" | "release" | "reassign";

/** The actions a task offers, in the order they are shown, each named as the server endpoint it calls. */
export const TASK_ACTIONS: ReadonlyArray<{
  key: TaskActionKey;
  flag: keyof TaskActions;
  label: string;
  /** Opens a drawer to give a reason (or choose a new holder) before it is sent. */
  needsInput: boolean;
}> = [
  { key: "accept", flag: "can_accept", label: "Accept", needsInput: false },
  { key: "claim", flag: "can_claim", label: "Claim", needsInput: false },
  { key: "complete", flag: "can_complete", label: "Complete", needsInput: true },
  { key: "decline", flag: "can_decline", label: "Decline", needsInput: true },
  { key: "release", flag: "can_release", label: "Release", needsInput: true },
  { key: "reassign", flag: "can_reassign", label: "Reassign", needsInput: true },
];

/** The actions the server allows on this task right now (its `actions` flags). */
export function availableTaskActions(task: Pick<Task, "actions">): TaskActionKey[] {
  return TASK_ACTIONS.filter((action) => task.actions?.[action.flag] === true).map((action) => action.key);
}

export const REASON_MIN = 10;
export const REASON_MAX = 1000;

/** Why a written reason cannot be sent yet, or null when it can (the server checks the same limits). */
export function reasonProblem(reason: string, required = true): string | null {
  const text = reason.trim();
  if (!text && !required) return null;
  if (text.length < REASON_MIN) return `Give a reason of at least ${REASON_MIN} characters.`;
  if (text.length > REASON_MAX) return `Keep the reason to ${REASON_MAX} characters.`;
  return null;
}

/** The body an action sends (none for accept and claim); empty optional fields are left out. */
export function taskActionBody(
  key: TaskActionKey,
  input: { reason?: string; assigneeUserId?: string; assignedRole?: string; outcome?: string } = {},
): Record<string, string> | undefined {
  const reason = (input.reason ?? "").trim();
  switch (key) {
    case "accept":
    case "claim":
      return undefined;
    case "decline":
    case "release":
      return { reason };
    case "reassign":
      return {
        ...(input.assigneeUserId ? { assignee_user_id: input.assigneeUserId } : {}),
        ...(!input.assigneeUserId && input.assignedRole ? { assigned_role: input.assignedRole } : {}),
        reason,
      };
    case "complete": {
      const outcome = (input.outcome ?? "").trim();
      return { ...(outcome ? { outcome } : {}), ...(reason ? { reason } : {}) };
    }
  }
}

/** The task's own address, or one of its actions (POST /api/v1/tasks/{id}/accept …). */
export const taskPath = (id: string, action?: TaskActionKey) =>
  `/api/v1/tasks/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;

/** One page of a task list (GET /api/v1/tasks), optionally searched. */
export function taskListPath(view: TaskView, page = 1, pageSize = 50, query = ""): string {
  const params = new URLSearchParams({ view, page: String(Math.max(1, page)), page_size: String(pageSize) });
  if (query.trim()) params.set("q", query.trim());
  return `/api/v1/tasks?${params}`;
}

/** "Showing 51–100 of 130" under a list that has more than one page; "" when everything is on one page. */
export function pageText(list: Pick<TaskList, "total" | "page" | "page_size"> | null | undefined, shown: number) {
  if (!list || !list.total || list.total <= shown) return "";
  const first = (list.page - 1) * list.page_size + 1;
  return `Showing ${first}–${first + shown - 1} of ${list.total}`;
}

/** One line of a task's history: what happened and, when its status moved, from what to what. */
export function taskEventText(event: TaskEvent): string {
  const what = event.event_type ? titleCase(String(event.event_type)) : "Updated";
  const from = event.from_status ? titleCase(String(event.from_status)) : "";
  const to = event.to_status ? titleCase(String(event.to_status)) : "";
  if (from && to && from !== to) return `${what}: ${from} → ${to}`;
  return to && to !== what ? `${what}: ${to}` : what;
}

/** Who did it, as "Name (Role label)"; "MDARIX" for an event without a person. */
export function taskEventActor(event: TaskEvent): string {
  const name = safeText(event.actor_name) ?? "MDARIX";
  return event.actor_role ? `${name} (${roleLabel(event.actor_role)})` : name;
}
