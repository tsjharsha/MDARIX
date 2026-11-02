import { DeadlineChip } from "../../../app/chips";
import { useEffect, useState } from "react";
import { MessageSquareReply, Paperclip } from "lucide-react";
import { ApiError, requestJson } from "../../../app/apiClient";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import {
  Drawer,
  SearchBox,
  Table,
  Tabs,
  errorText,
  formatDate,
  idColumn,
  listOf,
  send,
  useResource,
  type Column,
  type Resource,
} from "../../customer-admin/shared";
import { displayId, safeText } from "../../../app/displayId";
import { useServerSort } from "../../../app/tableSort";
import { WORKFLOW_ROLE_CODES, roleLabel } from "../../../app/roles";
import { conversationSummary } from "../../ask/structuredModel";
import { sectionAllowed, useCan, useFeatureSet, useWorkspace } from "../workspaceContext";
import { MY_WORK_APPROVALS_TAB } from "../../../app/featureSet";
import type { QueueRow } from "../humanDecision";
import { ApprovalsPanel } from "./DecisionApprovals";
import {
  REASON_MAX,
  TASK_ACTIONS,
  availableTaskActions,
  dueState,
  dueText,
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
  taskCompletedElsewhere,
  taskDestination,
  taskEventActor,
  taskEventText,
  TASK_SORTS,
  taskListPath,
  taskPath,
  taskSourceText,
  taskTypeLabel,
  taskViewForTab,
  type MyWorkTab,
  type Task,
  type TaskActionKey,
  type TaskDetail,
  type TaskList,
  type TaskSummary,
  type TaskView,
} from "../tasks";
import { StatusBadge } from "./common";
import { parseRequestTab } from "../evidenceWorkflow";
import { EvidenceRequestsPanel } from "./EvidenceRequests";
import { RemindersPanel } from "./Reminders";
import { useAiReady } from "../useAiStatus";

const PAGE_SIZE = 50;

const LIST_TITLES: Record<TaskView, string> = {
  assigned: "Tasks assigned to you",
  queue: "Tasks waiting in your role queues",
  waiting: "Tasks you are waiting on",
  returned: "Tasks returned to you",
  due_soon: "Tasks due soon",
  overdue: "Overdue tasks",
  completed: "Tasks you completed",
  created: "Tasks you created",
};

const LIST_EMPTY: Record<TaskView, { title: string; detail: string }> = {
  assigned: { title: "Nothing is assigned to you", detail: "Tasks routed to you appear here." },
  queue: {
    title: "Your role queues are empty",
    detail: "Work waiting for anyone in your roles (cases without an owner, reviews) appears here.",
  },
  waiting: { title: "Nothing to wait for", detail: "Tasks you handed to others and are waiting on appear here." },
  returned: { title: "Nothing was returned to you", detail: "Tasks sent back to you for more work appear here." },
  due_soon: { title: "Nothing is due soon", detail: "Tasks due within the next two days appear here." },
  overdue: { title: "Nothing is overdue", detail: "Tasks past their due date appear here." },
  completed: { title: "No completed tasks yet", detail: "Tasks you complete are listed here." },
  created: { title: "No tasks created", detail: "Tasks you created appear here." },
};

type MyWorkView = MyWorkTab | typeof MY_WORK_APPROVALS_TAB;

export function MyWorkSection({ tab }: { tab?: string }) {
  const { work, open, notify, isTrial } = useWorkspace();
  const aiOff = useAiReady() === false || !!isTrial;
  // Under the MVP feature set the Decisions section is parked: the decisions awaiting a signature are listed here, for
  // people who may sign, and each opens on its case's Decision step (app/featureSet.ts).
  const canSign = useCan("decision.sign");
  const approvals = useFeatureSet() === "mvp" && canSign;
  const [active, setActive] = useState<MyWorkView>(() =>
    approvals && (tab ?? "").split("?")[0] === MY_WORK_APPROVALS_TAB ? MY_WORK_APPROVALS_TAB : initialMyWorkTab(tab),
  );
  // A task or link may name an evidence request to open ("Evidence requests?request=…", see taskDestination).
  const [request] = useState(() => {
    const target = parseRequestTab(tab);
    return target.tab === "Evidence requests" ? target.request : null;
  });
  const summary = useResource<TaskSummary>("/api/v1/tasks/summary");
  const taskTabs = myWorkTabs(summary.data, active, aiOff);
  const tabs: MyWorkView[] = approvals ? [taskTabs[0], MY_WORK_APPROVALS_TAB, ...taskTabs.slice(1)] : taskTabs;
  const counts = Object.fromEntries(tabs.map((item) => [item, tabCount(item, summary.data)]));
  const view = taskViewForTab(active);
  const openApproval = (row: QueueRow) => {
    if (!row.investigationId) return;
    if (row.productId) work.setInvestigationId(row.investigationId, row.productId);
    else if (work.investigations.some((item) => String(item.id) === row.investigationId))
      work.setInvestigationId(row.investigationId);
    else {
      notify(`Choose ${row.caseId} in the context bar above, then open its Decision step.`, "critical");
      return;
    }
    open("Investigations", "Decision");
  };
  return (
    <>
      <RemindersPanel />
      <Tabs tabs={tabs} active={active} onChange={setActive} label="My work sections" counts={counts}>
        {view && <TaskInbox key={view} view={view} summary={summary} />}
        {active === MY_WORK_APPROVALS_TAB && <ApprovalsPanel onOpen={openApproval} />}
        {active === "Evidence requests" && (
          <>
            <EvidenceRequestsPanel investigationId={null} initialRequest={request} />
            <EvidenceRequests />
          </>
        )}
        {active === "My AI conversations" && <Conversations />}
      </Tabs>
    </>
  );
}

/**
 * Open a task where its work is done: its case (and that case's product) becomes the working context, then the
 * section for its kind of work opens. Null for a task whose section the person's menu does not hold.
 */
export function useOpenTask(): (task: Task) => (() => void) | null {
  const { session, work, open } = useWorkspace();
  return (task) => {
    const target = taskDestination(task);
    if (!sectionAllowed(target.section, session?.allowed_menu, session?.business_permissions)) return null;
    return () => {
      const kase = taskCase(task);
      if (kase) work.setInvestigationId(kase.investigationId, kase.productId);
      open(target.section, target.tab);
    };
  };
}

/** Accept or claim at once; the other actions first ask for a reason (or a new holder) in the task drawer. */
function useTaskAction(onDone: () => void) {
  const { notify } = useWorkspace();
  const openTask = useOpenTask();
  const [busy, setBusy] = useState("");
  const run = async (task: Task, key: TaskActionKey, body?: unknown) => {
    const label = TASK_ACTIONS.find((action) => action.key === key)?.label ?? "Update";
    setBusy(`${task.id}:${key}`);
    try {
      await send(taskPath(task.id, key), "POST", body);
      notify(`${safeText(task.business_id) ?? "Task"}: ${label.toLowerCase()} recorded.`);
      onDone();
      return true;
    } catch (reason) {
      // An impact assessment is completed on the assessment itself (conclusion and rationale): open it there.
      const go = reason instanceof ApiError && taskCompletedElsewhere(reason.code) ? openTask(task) : null;
      if (go) {
        go();
        notify(
          `${safeText(task.business_id) ?? "This task"} is completed by recording the impact assessment opened here.`,
        );
        return false;
      }
      notify(errorText(reason, `The task could not be updated (${label.toLowerCase()}).`), "critical");
      return false;
    } finally {
      setBusy("");
    }
  };
  return { run, busy };
}

type DrawerState = { task: Task; mode: "details" | TaskActionKey };

function TaskInbox({ view, summary }: { view: TaskView; summary: Resource<TaskSummary> }) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const { sort, onSort } = useServerSort(() => setPage(1));
  const [drawer, setDrawer] = useState<DrawerState | null>(null);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(query.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [query]);
  const list = useResource<TaskList>(taskListPath(view, page, PAGE_SIZE, search, sort));
  const reload = () => {
    list.reload();
    summary.reload();
  };
  const action = useTaskAction(reload);
  const openTask = useOpenTask();
  const rows = listOf(list.data?.items) as Task[];
  const total = list.data?.total ?? rows.length;
  const pages = Math.max(1, Math.ceil(total / (list.data?.page_size || PAGE_SIZE)));
  const choose = (task: Task, key: TaskActionKey) => {
    if (TASK_ACTIONS.find((item) => item.key === key)?.needsInput) setDrawer({ task, mode: key });
    else void action.run(task, key);
  };
  return (
    <>
      <Panel eyebrow="My work" title={LIST_TITLES[view]} source={list}>
        {view === "queue" && <QueueSummary summary={summary.data} />}
        <div className="ca-toolbar">
          <SearchBox value={query} onChange={setQuery} label="Search task ID, title or source" />
        </div>
        <Table
          caption={LIST_TITLES[view]}
          rows={rows}
          rowKey={(row) => String(row.id)}
          empty={search ? { title: "No matching tasks", detail: "Change the search to see more." } : LIST_EMPTY[view]}
          serverSort={{ sort, onSort, keys: TASK_SORTS }}
          columns={taskColumns(view, {
            busy: action.busy,
            openTask,
            onAction: choose,
            onDetails: (task) => setDrawer({ task, mode: "details" }),
          })}
        />
        {pages > 1 && (
          <div className="ca-action-row uw-pager">
            <span className="ac-muted">{pageText(list.data, rows.length)}</span>
            <button
              type="button"
              className="ac-secondary"
              disabled={page <= 1 || list.state === "loading"}
              onClick={() => setPage((value) => Math.max(1, value - 1))}
            >
              Previous
            </button>
            <button
              type="button"
              className="ac-secondary"
              disabled={page >= pages || list.state === "loading"}
              onClick={() => setPage((value) => value + 1)}
            >
              Next
            </button>
          </div>
        )}
      </Panel>
      {drawer && (
        <TaskDrawer
          task={drawer.task}
          mode={drawer.mode}
          onMode={(mode) => setDrawer({ ...drawer, mode })}
          onClose={() => setDrawer(null)}
          onDone={() => {
            setDrawer(null);
            reload();
          }}
        />
      )}
    </>
  );
}

/** The queues the person works, with how many tasks wait in each. */
function QueueSummary({ summary }: { summary: TaskSummary | null }) {
  const queues = (summary?.queues ?? []).filter((queue) => queue.count > 0);
  if (!queues.length) return null;
  return (
    <ul className="ca-pill-list uw-queue-list" aria-label="Your role queues">
      {queues.map((queue) => (
        <li key={`${queue.role}:${queue.task_type}`}>
          {roleLabel(queue.role, queue.role_label)} · {safeText(queue.task_type_label) ?? titleCase(queue.task_type)}:{" "}
          <strong>{queue.count}</strong>
        </li>
      ))}
    </ul>
  );
}

function DueCell({ task }: { task: Task }) {
  const state = dueState(task);
  // An open task with a due time shows the one time-left chip (app/chips.tsx), its date beside it.
  if (task.due_at && (state === "overdue" || state === "due_soon" || state === "due"))
    return (
      <span className="uw-due-cell">
        <DeadlineChip item={{ due_at: task.due_at, state: state === "overdue" ? "OVERDUE" : "RUNNING" }} />
        <span className="ac-muted">{formatDate(task.due_at)}</span>
      </span>
    );
  return <>{dueText(task, formatDate)}</>;
}

function taskColumns(
  view: TaskView,
  handlers: {
    busy: string;
    openTask: (task: Task) => (() => void) | null;
    onAction: (task: Task, key: TaskActionKey) => void;
    onDetails: (task: Task) => void;
  },
): Column<Task>[] {
  return [
    idColumn<Task>("Task ID"),
    {
      key: "title",
      label: "Task",
      fields: ["title", "task_type", "task_type_label"],
      sortValue: (row) => row.title ?? taskTypeLabel(row),
      render: (row) => (
        <span className="ca-person">
          <strong>{safeText(row.title) ?? taskTypeLabel(row)}</strong>
          <small>{taskTypeLabel(row)}</small>
        </span>
      ),
    },
    {
      key: "source",
      label: "Source",
      fields: ["source"],
      sortValue: (row) => taskSourceText(row),
      render: (row) => {
        const source = taskSourceText(row);
        const kase = safeText(row.investigation?.business_id);
        return (
          <span className="ca-person">
            <span>{source}</span>
            {kase && kase !== source && <small>Case {kase}</small>}
          </span>
        );
      },
    },
    {
      key: "priority",
      label: "Priority",
      sortValue: (row) => priorityRank(row.priority),
      render: (row) =>
        row.priority ? <ToneBadge tone={priorityTone(row.priority)} label={priorityLabel(row.priority)} /> : "—",
    },
    {
      key: "status",
      label: "Status",
      fields: ["status", "is_return"],
      render: (row) => (
        <span className="ca-person">
          <StatusBadge value={row.status} />
          {row.is_return && <small>Returned</small>}
        </span>
      ),
    },
    {
      key: "due_at",
      label: "Due",
      fields: ["due_at", "overdue"],
      sortValue: (row) => row.due_at ?? "",
      render: (row) => <DueCell task={row} />,
    },
    {
      key: "assigned",
      label: "Assigned",
      fields: ["assigned_role", "assigned_role_label", "assigned_user"],
      sortValue: (row) => taskAssignee(row).primary,
      render: (row) => {
        const who = taskAssignee(row);
        return (
          <span className="ca-person">
            <span>{who.primary}</span>
            {who.secondary && <small>{who.secondary}</small>}
          </span>
        );
      },
    },
    ...(view === "completed"
      ? [
          {
            key: "completed_at",
            label: "Completed",
            fields: ["completed_at", "completion_outcome"],
            render: (row: Task) => (
              <span className="ca-person">
                <span>{formatDate(row.completed_at)}</span>
                {row.completion_outcome && <small>{titleCase(String(row.completion_outcome))}</small>}
              </span>
            ),
          },
        ]
      : []),
    {
      key: "actions",
      label: "",
      render: (row) => {
        const open = handlers.openTask(row);
        return (
          <span className="uw-task-actions">
            {open && (
              <button type="button" className="ac-link" onClick={open}>
                Open
              </button>
            )}
            {availableTaskActions(row).map((key) => (
              <button
                type="button"
                key={key}
                className="ac-link"
                disabled={handlers.busy === `${row.id}:${key}`}
                onClick={() => handlers.onAction(row, key)}
              >
                {TASK_ACTIONS.find((item) => item.key === key)?.label}
              </button>
            ))}
            <button type="button" className="ac-link" onClick={() => handlers.onDetails(row)}>
              Details
            </button>
          </span>
        );
      },
    },
  ];
}

/** One task: its facts and history, and the form for an action that needs a reason or a new holder. */
function TaskDrawer({
  task,
  mode,
  onMode,
  onClose,
  onDone,
}: {
  task: Task;
  mode: DrawerState["mode"];
  onMode: (mode: DrawerState["mode"]) => void;
  onClose: () => void;
  onDone: () => void;
}) {
  const detail = useResource<TaskDetail>(taskPath(task.id));
  const current: TaskDetail = { ...task, ...(detail.data ?? {}) };
  const action = useTaskAction(onDone);
  const openTask = useOpenTask();
  const open = openTask(current);
  const events = listOf(detail.data?.events);
  const who = taskAssignee(current);
  const name = safeText(current.business_id) ?? "Task";
  return (
    <Drawer title={`${name}: ${safeText(current.title) ?? taskTypeLabel(current)}`} onClose={onClose}>
      <dl className="ca-facts">
        <div>
          <dt>Task ID</dt>
          <dd>{name}</dd>
        </div>
        <div>
          <dt>Type</dt>
          <dd>{taskTypeLabel(current)}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>
            <StatusBadge value={current.status} />
          </dd>
        </div>
        <div>
          <dt>Priority</dt>
          <dd>{priorityLabel(current.priority)}</dd>
        </div>
        <div>
          <dt>Due</dt>
          <dd>
            <DueCell task={current} />
          </dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>{taskSourceText(current)}</dd>
        </div>
        {safeText(current.investigation?.business_id) && (
          <div>
            <dt>Case</dt>
            <dd>{current.investigation?.business_id}</dd>
          </div>
        )}
        <div>
          <dt>Assigned</dt>
          <dd>
            {who.primary}
            {who.secondary ? ` · ${who.secondary}` : ""}
          </dd>
        </div>
      </dl>

      {mode === "details" ? (
        <section className="ca-drawer-section">
          <h3>Actions</h3>
          <div className="ca-action-row">
            {open && (
              <button type="button" className="ac-primary" onClick={open}>
                Open
              </button>
            )}
            {availableTaskActions(current).map((key) => {
              const item = TASK_ACTIONS.find((entry) => entry.key === key);
              return (
                <button
                  type="button"
                  key={key}
                  className="ac-secondary"
                  disabled={!!action.busy}
                  onClick={() => (item?.needsInput ? onMode(key) : void action.run(current, key))}
                >
                  {item?.label}
                </button>
              );
            })}
            {!open && !availableTaskActions(current).length && (
              <p className="ac-muted">Nothing for you to do on this task right now.</p>
            )}
          </div>
        </section>
      ) : (
        <TaskActionForm
          task={current}
          action={mode}
          onCancel={() => onMode("details")}
          onSubmit={(body) => action.run(current, mode, body)}
        />
      )}

      <section className="ca-drawer-section">
        <h3>History</h3>
        {detail.state === "loading" && !detail.data ? (
          <p className="ac-muted">Loading…</p>
        ) : detail.state !== "ready" ? (
          <p className="ac-muted">{detail.error ?? "The task's history is unavailable."}</p>
        ) : events.length ? (
          <ol className="ca-timeline uw-task-history">
            {events.map((event, index) => (
              <li key={`${event.created_at ?? ""}:${index}`}>
                <strong>{taskEventText(event)}</strong>
                <small className="ac-muted">
                  {taskEventActor(event)} · {formatDate(event.created_at)}
                </small>
                {safeText(event.reason) && <p>{event.reason}</p>}
              </li>
            ))}
          </ol>
        ) : (
          <p className="ac-muted">No history recorded yet.</p>
        )}
      </section>
    </Drawer>
  );
}

const ACTION_COPY: Partial<Record<TaskActionKey, { title: string; reason: string; submit: string }>> = {
  decline: { title: "Decline this task", reason: "Why are you declining it?", submit: "Decline task" },
  release: { title: "Release this task", reason: "Why are you releasing it?", submit: "Release to the queue" },
  reassign: { title: "Reassign this task", reason: "Why is it being reassigned?", submit: "Reassign task" },
  complete: { title: "Complete this task", reason: "Note (optional)", submit: "Complete task" },
};

function TaskActionForm({
  task,
  action,
  onCancel,
  onSubmit,
}: {
  task: Task;
  action: TaskActionKey;
  onCancel: () => void;
  onSubmit: (body: unknown) => Promise<boolean>;
}) {
  const copy = ACTION_COPY[action] ?? { title: "Update this task", reason: "Reason", submit: "Save" };
  const [reason, setReason] = useState("");
  const [target, setTarget] = useState<"person" | "role">("person");
  const [assignee, setAssignee] = useState("");
  const [role, setRole] = useState(task.assigned_role ?? "");
  const [busy, setBusy] = useState(false);
  const people = useResource<Array<{ id: string; business_id?: string | null; display_name?: string | null }>>(
    action === "reassign" ? "/api/v1/investigation-assignees" : null,
  );
  const required = action !== "complete";
  const problem = reasonProblem(reason, required);
  const missingTarget = action === "reassign" && (target === "person" ? !assignee : !role);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem || missingTarget) return;
    setBusy(true);
    const body = taskActionBody(action, {
      reason,
      assigneeUserId: action === "reassign" && target === "person" ? assignee : undefined,
      assignedRole: action === "reassign" && target === "role" ? role : undefined,
    });
    const done = await onSubmit(body);
    if (!done) setBusy(false);
  };
  return (
    <form className="ca-form ca-drawer-section" onSubmit={submit}>
      <h3>{copy.title}</h3>
      {action === "reassign" && (
        <>
          <div className="ca-chips" role="radiogroup" aria-label="Reassign to">
            {(["person", "role"] as const).map((option) => (
              <button
                type="button"
                role="radio"
                key={option}
                aria-checked={target === option}
                className={target === option ? "selected" : ""}
                onClick={() => setTarget(option)}
              >
                {option === "person" ? "A person" : "A role queue"}
              </button>
            ))}
          </div>
          {target === "person" ? (
            <label className="ca-field">
              Person
              <select required value={assignee} onChange={(event) => setAssignee(event.target.value)}>
                <option value="">{people.state === "loading" ? "Loading…" : "Choose a person"}</option>
                {listOf(people.data).map((person) => (
                  <option key={person.id} value={person.id}>
                    {safeText(person.display_name) ?? "Person"}
                    {safeText(person.business_id) ? ` (${person.business_id})` : ""}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <label className="ca-field">
              Role queue
              <select required value={role} onChange={(event) => setRole(event.target.value)}>
                <option value="">Choose a role</option>
                {WORKFLOW_ROLE_CODES.map((code) => (
                  <option key={code} value={code}>
                    {roleLabel(code)}
                  </option>
                ))}
              </select>
            </label>
          )}
        </>
      )}
      <label className="ca-field">
        {copy.reason}
        <textarea
          required={required}
          rows={3}
          maxLength={REASON_MAX}
          value={reason}
          placeholder={required ? "At least 10 characters" : "At least 10 characters, if you add one"}
          onChange={(event) => setReason(event.target.value)}
        />
      </label>
      {reason.trim() && problem && <p className="ac-muted">{problem}</p>}
      <p className="ac-muted">Recorded in the task's history and the audit trail.</p>
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" onClick={onCancel} disabled={busy}>
          Back
        </button>
        <button type="submit" className="ac-primary" disabled={busy || !!problem || missingTarget}>
          {busy ? "Saving…" : copy.submit}
        </button>
      </div>
    </form>
  );
}

const EMPTY_REQUEST = { supplier_id: "", recipient: "", title: "", items: "" };

/** Ask one of your suppliers for evidence by email: plain text, no links; the supplier answers through MDARIX. */
function NewEvidenceRequest({ onSent }: { onSent: () => void }) {
  const { work, isTrial } = useWorkspace();
  const suppliers = useResource<any>("/api/v1/data-plane/suppliers");
  const [form, setForm] = useState({ ...EMPTY_REQUEST });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const items = form.items
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const result = await send<any>("/api/v1/stage3/supplier-evidence-requests", "POST", {
        supplier_id: form.supplier_id,
        recipient: form.recipient.trim(),
        title: form.title.trim(),
        requested_items: items,
        investigation_id: work.investigationId || undefined,
      });
      setMessage({
        tone: "ok",
        text:
          result.email_delivery === "NOT_SENT_IN_TRIAL"
            ? "Request saved, not sent: the free trial sends no email to suppliers. Send it to the supplier yourself if you need the evidence."
            : result.status === "SENT"
              ? "Request sent to the supplier."
              : "Request saved; the email will be sent when delivery is available.",
      });
      setForm({ ...EMPTY_REQUEST });
      onSent();
    } catch (reason) {
      setMessage({ tone: "error", text: errorText(reason, "The request was not sent.") });
    } finally {
      setBusy(false);
    }
  };
  const options = listOf(suppliers.data?.records);
  return (
    <Panel eyebrow="Suppliers" title="Request evidence from a supplier">
      <form className="ca-form" onSubmit={submit}>
        <div className="ca-form-grid">
          <label className="ca-field">
            Supplier
            <select
              required
              value={form.supplier_id}
              onChange={(event) => setForm({ ...form, supplier_id: event.target.value })}
            >
              <option value="">{suppliers.state === "loading" ? "Loading…" : "Choose a supplier"}</option>
              {options.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name} ({displayId(row, "supplier_identifier")})
                </option>
              ))}
            </select>
          </label>
          <label className="ca-field">
            Supplier contact email
            <input
              type="email"
              required
              value={form.recipient}
              placeholder="quality@supplier.com"
              onChange={(event) => setForm({ ...form, recipient: event.target.value })}
            />
          </label>
        </div>
        <label className="ca-field">
          What you need
          <input
            required
            minLength={3}
            maxLength={240}
            value={form.title}
            placeholder="e.g. Certificate of conformance for lot KS-5521"
            onChange={(event) => setForm({ ...form, title: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Documents or data requested (one per line)
          <textarea
            required
            rows={3}
            value={form.items}
            onChange={(event) => setForm({ ...form, items: event.target.value })}
          />
        </label>
        <p className="ac-muted">
          {work.investigationId ? "Linked to the investigation open in your workspace. " : ""}
          {supplierRequestNote(isTrial)}
        </p>
        {!options.length && suppliers.state === "ready" && (
          <p className="ac-muted">No suppliers yet: load them from your ERP or supplier system first.</p>
        )}
        {message && (
          <p className={message.tone === "ok" ? "ca-inline-ok" : "ca-inline-error"} role="status">
            {message.text}
          </p>
        )}
        <div className="ca-action-row">
          <button
            type="submit"
            className="ac-primary"
            disabled={busy || !form.supplier_id || !items.length || form.title.trim().length < 3}
          >
            {busy ? "Sending…" : "Send request"}
          </button>
        </div>
      </form>
    </Panel>
  );
}

/** Supplier attachments the server accepts (stage3_workflow_router.ALLOWED_ATTACHMENT_TYPES, MAX_ATTACHMENT_BYTES). */
export const ATTACHMENT_TYPES = ["application/pdf", "text/plain", "text/csv", "image/png", "image/jpeg"];
export const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;

/** Why a file cannot be attached to a supplier reply, or null when it can (the server checks it again). */
export function attachmentProblem(file: { type: string; size: number } | null): string | null {
  if (!file) return null;
  if (!ATTACHMENT_TYPES.includes(file.type.toLowerCase()))
    return "Attach a PDF, a text or CSV file, or a PNG or JPEG image.";
  if (file.size > MAX_ATTACHMENT_BYTES) return "The file is larger than 10 MB.";
  return null;
}

/** The body of POST /api/v1/stage3/supplier-requests/{id}/reply: the note, and the uploaded file when there is one. */
export function replyBody(note: string, attachmentId?: string | null) {
  return { note: note.trim(), ...(attachmentId ? { attachment_id: attachmentId } : {}) };
}

export type SupplierReply = {
  id: string;
  note: string;
  attachment_id?: string | null;
  recorded_by?: string;
  recorded_at?: string;
};

/** "2 replies, latest 3 Oct 2026" for the request list (or "No reply yet"). */
export function repliesSummary(replies: SupplierReply[] | undefined, format: (value: unknown) => string): string {
  const list = replies ?? [];
  if (!list.length) return "No reply yet";
  const latest = list[list.length - 1];
  return `${list.length === 1 ? "1 reply" : `${list.length} replies`}, latest ${format(latest.recorded_at)}`;
}

/** What happens to a supplier request: a free trial saves it and e-mails nobody (0.10.62, J33); a pilot e-mails it. */
export function supplierRequestNote(isTrial: boolean | undefined): string {
  return isTrial
    ? "In the free trial MDARIX saves the request here and e-mails nobody: send it to the supplier from your own mail."
    : "The email carries this text only, without links. Requests are limited per person and per day.";
}

/** The date column of supplier requests: when a trial saved it, or when a pilot sent it. */
export const supplierDateLabel = (isTrial: boolean | undefined) => (isTrial ? "Saved" : "Sent");

export const REVIEW_NOTICE =
  "Replies are recorded for review. Supplier material is never accepted as evidence automatically: review it and add it to the investigation's evidence yourself.";

function EvidenceRequests() {
  const { isTrial } = useWorkspace();
  const requests = useResource<any>("/api/v1/stage3/supplier-evidence-requests");
  const canWrite = useCan("records.write");
  const [replying, setReplying] = useState<any | null>(null);
  const rows = listOf(requests.data?.requests ?? requests.data);
  return (
    <>
      {canWrite && <NewEvidenceRequest onSent={requests.reload} />}
      <Panel eyebrow="My work" title="Supplier evidence requests" source={requests}>
        <p className="ac-note">{REVIEW_NOTICE}</p>
        <Table
          caption="Evidence requests"
          rows={rows}
          rowKey={(row, index) => String(row.id ?? index)}
          empty={{ title: "No evidence requests", detail: "Requests sent to suppliers for evidence appear here." }}
          columns={[
            idColumn("Request ID", "request_identifier"),
            {
              key: "title",
              label: "Request",
              render: (row) => <strong>{row.title ?? "Request"}</strong>,
            },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> },
            { key: "recipient", label: "To", render: (row) => row.recipient ?? "—" },
            { key: "created", label: supplierDateLabel(isTrial), render: (row) => formatDate(row.created_at) },
            { key: "replies", label: "Replies", render: (row) => repliesSummary(row.replies, formatDate) },
            {
              key: "reply",
              label: "",
              render: (row) => (
                <button type="button" className="ac-link" onClick={() => setReplying(row)}>
                  <MessageSquareReply size={14} aria-hidden="true" /> {canWrite ? "Record reply" : "View replies"}
                </button>
              ),
            },
          ]}
        />
      </Panel>
      {replying && (
        <SupplierReplies
          request={replying}
          canWrite={canWrite}
          onClose={() => setReplying(null)}
          onSaved={(updated) => {
            setReplying({ ...replying, ...updated });
            requests.reload();
          }}
        />
      )}
    </>
  );
}

/** The exchange with the supplier on one request, and the form to record what they answered. */
function SupplierReplies({
  request,
  canWrite,
  onClose,
  onSaved,
}: {
  request: any;
  canWrite: boolean;
  onClose: () => void;
  onSaved: (updated: { status: string; replies: SupplierReply[] }) => void;
}) {
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const base = `/api/v1/stage3/supplier-evidence-requests/${encodeURIComponent(String(request.id))}`;
  const replies: SupplierReply[] = listOf(request.replies);
  const fileProblem = attachmentProblem(file);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (fileProblem) return;
    setBusy(true);
    setMessage(null);
    try {
      let attachmentId: string | null = null;
      if (file) {
        // The file is stored (and scanned) first; the reply then names it.
        const form = new FormData();
        form.append("file", file);
        const stored = await requestJson<{ id: string }>(`${base}/attachments`, {
          method: "POST",
          body: form,
          timeoutMs: 120_000,
        });
        attachmentId = stored.id;
      }
      const result = await send<{ status: string; replies: SupplierReply[] }>(
        `/api/v1/stage3/supplier-requests/${encodeURIComponent(String(request.id))}/reply`,
        "POST",
        replyBody(note, attachmentId),
      );
      setNote("");
      setFile(null);
      setMessage({ tone: "ok", text: "Reply recorded for review." });
      onSaved({ status: result.status, replies: result.replies });
    } catch (reason) {
      setMessage({ tone: "error", text: errorText(reason, "The reply was not recorded.") });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Drawer title={`Replies: ${request.title ?? "Evidence request"}`} onClose={onClose}>
      <p className="ac-note">{REVIEW_NOTICE}</p>
      <section className="ca-drawer-section">
        <h3>Recorded replies</h3>
        {replies.length ? (
          <ul>
            {replies.map((reply) => (
              <li key={reply.id}>
                <p>{reply.note}</p>
                <small className="ac-muted">
                  Recorded {formatDate(reply.recorded_at)}
                  {reply.attachment_id && (
                    <>
                      {" · "}
                      <a
                        className="ac-link"
                        href={`${base}/attachments/${encodeURIComponent(reply.attachment_id)}`}
                        download
                      >
                        <Paperclip size={12} aria-hidden="true" /> Attached file
                      </a>
                    </>
                  )}
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <p className="ac-muted">No reply recorded yet.</p>
        )}
      </section>
      {canWrite && (
        <form className="ca-form ca-drawer-section" onSubmit={submit}>
          <h3>Record a reply</h3>
          <label className="ca-field">
            What the supplier answered
            <textarea
              required
              rows={4}
              maxLength={4000}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="e.g. Certificate of conformance for lot KS-5521 received by email on 3 Oct"
            />
          </label>
          <label className="ca-field">
            File they sent (optional: PDF, text, CSV, PNG or JPEG, up to 10 MB)
            <input
              type="file"
              accept={ATTACHMENT_TYPES.join(",")}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          {fileProblem && (
            <p className="ca-inline-error" role="alert">
              {fileProblem}
            </p>
          )}
          {message && (
            <p className={message.tone === "ok" ? "ca-inline-ok" : "ca-inline-error"} role="status">
              {message.text}
            </p>
          )}
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy || !note.trim() || !!fileProblem}>
              {busy ? "Recording…" : "Record reply"}
            </button>
          </div>
        </form>
      )}
    </Drawer>
  );
}

function Conversations() {
  const interactions = useResource<any>("/api/v1/stage3/interactions");
  const rows = listOf(interactions.data?.interactions ?? interactions.data);
  return (
    <Panel eyebrow="My work" title="Your Ask MDARIX conversations" source={interactions}>
      {rows.length ? (
        <Table
          caption="AI conversations"
          rows={rows}
          pageSize={50}
          pageNoun="conversation"
          rowKey={(row, index) => String(row.interaction_id ?? row.id ?? index)}
          empty={{ title: "", detail: "" }}
          columns={[
            {
              key: "prompt",
              label: "Question",
              render: (row) => <span className="uw-clamp">{row.prompt ?? row.question ?? "—"}</span>,
            },
            {
              key: "summary",
              label: "Answer summary",
              fields: ["structured"],
              sortValue: (row) => conversationSummary(row) ?? "",
              render: (row) =>
                conversationSummary(row) ? (
                  <span className="uw-clamp">{conversationSummary(row)}</span>
                ) : (
                  <span className="ac-muted">—</span>
                ),
            },
            { key: "page", label: "Asked from", render: (row) => titleCase(String(row.page_context ?? "—")) },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> },
            {
              key: "when",
              label: "When",
              fields: ["created_at"],
              sortValue: (row) => row.created_at ?? "",
              render: (row) => formatDate(row.created_at),
            },
          ]}
        />
      ) : (
        <Empty title="No conversations yet" detail="Questions you ask Ask MDARIX are listed here, only for you." />
      )}
    </Panel>
  );
}
