import { useState, type ReactNode } from "react";
import { ArrowLeft, CalendarPlus, Repeat, ShieldOff, Sparkles, Trash2 } from "lucide-react";
import { Panel, ToneBadge } from "../console/charts";
import { Drawer, errorText, formatDate, listOf, send, useResource } from "../../customer-admin/shared";
import { formatDateTime } from "../../../app/dates";
import {
  EXTENSION_DAYS_MAX,
  SAMPLE_LABELS,
  STATE_LABELS,
  TRIAL_ORGS_PATH,
  convertiblePlans,
  extensionError,
  extensionSentence,
  nameMatches,
  reasonError,
  stateTone,
  type ActionState,
  type TrialDetail,
} from "./model";

type Action = "extend" | "end" | "convert" | "delete_data";
type AuditItem = {
  id: string;
  action: string;
  actor_ref: string | null;
  created_at: string;
  details: Record<string, unknown>;
};
type PlanOption = { id: string; code: string; name: string; status?: string | null };

const ACTIONS: { key: Action; label: string; icon: ReactNode; danger?: boolean }[] = [
  { key: "extend", label: "Extend", icon: <CalendarPlus size={16} /> },
  { key: "end", label: "End early", icon: <ShieldOff size={16} /> },
  { key: "convert", label: "Convert to pilot or paid", icon: <Repeat size={16} /> },
  { key: "delete_data", label: "Delete data now", icon: <Trash2 size={16} />, danger: true },
];

/** One trial: header with its next step, summary cards, the actions the server allows now, and its history. */
export function TrialDetailPage({
  tenantId,
  onBack,
  onOpenWorkspace,
  onOpenCustomers,
  onChanged,
  onMessage,
}: {
  tenantId: string;
  onBack: () => void;
  onOpenWorkspace?: (tenantId: string) => void;
  onOpenCustomers?: () => void;
  onChanged?: () => void;
  onMessage: (text: string, tone?: "good" | "critical") => void;
}) {
  const detail = useResource<TrialDetail>(`${TRIAL_ORGS_PATH}/${tenantId}`);
  const history = useResource<{ items: AuditItem[] }>(`/api/v1/platform-admin/tenants/${tenantId}/audit`);
  const [drawer, setDrawer] = useState<Action | null>(null);
  const done = (text: string) => {
    setDrawer(null);
    detail.reload();
    history.reload();
    onChanged?.();
    onMessage(text);
  };
  return (
    <div className="cc-page">
      <button type="button" className="ac-link" onClick={onBack}>
        <ArrowLeft size={14} aria-hidden="true" /> Back to trials
      </button>
      <TrialDetailView
        detail={detail.data}
        history={history.data?.items ?? []}
        onAction={setDrawer}
        onOpenWorkspace={onOpenWorkspace}
        onOpenCustomers={onOpenCustomers}
        source={detail}
      />
      {drawer && detail.data && (
        <ActionDrawer action={drawer} trial={detail.data} onClose={() => setDrawer(null)} onDone={done} />
      )}
    </div>
  );
}

/** The page for one answer of the detail route (rendered on its own in tests). */
export function TrialDetailView({
  detail,
  history,
  onAction,
  onOpenWorkspace,
  onOpenCustomers,
  source,
}: {
  detail: TrialDetail | null;
  history: AuditItem[];
  onAction: (action: Action) => void;
  onOpenWorkspace?: (tenantId: string) => void;
  onOpenCustomers?: () => void;
  source?: { state: "loading" | "ready" | "error" | "forbidden"; error?: string; reload?: () => void };
}) {
  if (!detail)
    return (
      <Panel title="Trial" source={source}>
        {null}
      </Panel>
    );
  const { dates, people, sample, activity } = detail;
  return (
    <>
      <header className="to-hero">
        <div>
          <p className="ac-eyebrow">
            {detail.tenant_business_id ?? "Trial"} · {detail.plan ?? "Converted"}
            {sample.sample_only ? " · Sample only" : ""}
          </p>
          <h2>{detail.name}</h2>
          <p className="to-next">{detail.next_step}</p>
        </div>
        <div className="to-hero-side">
          <ToneBadge tone={stateTone(detail.state)} label={STATE_LABELS[detail.state] ?? detail.state} />
          {detail.state !== "CONVERTED" && detail.state !== "DATA_DELETED" && (
            <strong className="to-days">
              {detail.state === "ACTIVE" || detail.state === "ENDING_SOON" ? `${dates.days_left} days left` : "Ended"}
            </strong>
          )}
        </div>
      </header>

      <div className="to-actions" role="group" aria-label="Trial actions">
        {ACTIONS.map((action) => {
          const state: ActionState | undefined = detail.actions[action.key];
          return (
            <span key={action.key} className="to-action">
              <button
                type="button"
                className={action.danger ? "ac-secondary cc-danger-link" : "ac-secondary"}
                disabled={!state?.allowed}
                onClick={() => onAction(action.key)}
              >
                {action.icon} {action.label}
              </button>
              {!state?.allowed && state?.reason && <small>{state.reason}</small>}
            </span>
          );
        })}
        {detail.state === "CONVERTED" && onOpenCustomers && (
          <button type="button" className="ac-link" onClick={onOpenCustomers}>
            Open in Customers
          </button>
        )}
        {detail.state !== "CONVERTED" && detail.state !== "DATA_DELETED" && onOpenWorkspace && (
          <button type="button" className="ac-link" onClick={() => onOpenWorkspace(detail.tenant_id)}>
            Open support workspace
          </button>
        )}
      </div>

      <div className="to-cards">
        <section className="to-card" aria-label="Dates">
          <h3>Dates</h3>
          <dl>
            <dt>Started</dt>
            <dd>{formatDate(dates.starts_at)}</dd>
            {dates.original_ends_at && (
              <>
                <dt>Original end</dt>
                <dd>{formatDate(dates.original_ends_at)}</dd>
              </>
            )}
            <dt>Ends</dt>
            <dd>{dates.ends_words ?? formatDate(dates.ends_at)}</dd>
            {dates.extension_max !== undefined && (
              <>
                <dt>Extension</dt>
                <dd>
                  {dates.extension_used} of {dates.extension_max} days used · {dates.extension_left} left
                </dd>
              </>
            )}
            {dates.deletion && (
              <>
                <dt>Data deleted on</dt>
                <dd>
                  {dates.deletion.earliest_deletion
                    ? `${formatDate(dates.deletion.earliest_deletion)} at the earliest`
                    : (dates.deletion.hold_reason ?? "No date")}
                </dd>
              </>
            )}
          </dl>
        </section>
        <section className="to-card" aria-label="People">
          <h3>People</h3>
          <dl>
            <dt>Owner</dt>
            <dd>{people.owner ? `${people.owner.name ?? people.owner.email} (${people.owner.email})` : "—"}</dd>
            <dt>Users</dt>
            <dd>{people.used}</dd>
          </dl>
          <ul className="to-people">
            {people.people.map((person) => (
              <li key={person.id}>
                {person.name ?? person.email} <small>{person.status === "INVITED" ? "Invited" : "Active"}</small>
              </li>
            ))}
          </ul>
        </section>
        <section className="to-card" aria-label="Sample data">
          <h3>Sample data</h3>
          <p>
            {sample.sample_only ? "Sample only · " : ""}
            {SAMPLE_LABELS[sample.status]}
            {sample.at ? ` (${formatDate(sample.at)})` : ""}
          </p>
          <dl>
            {Object.entries(sample.sample_counts ?? {}).map(([kind, count]) => (
              <span key={kind} className="to-count">
                <dt>{kind}</dt>
                <dd>{count}</dd>
              </span>
            ))}
            <dt>Own rows imported</dt>
            <dd>{sample.uploaded_rows}</dd>
          </dl>
        </section>
        <section className="to-card" aria-label="Activity">
          <h3>Activity</h3>
          <dl>
            <dt>Chapters acted in</dt>
            <dd>
              {activity.story.acted_count} of {activity.story.total}
            </dd>
            <dt>Last activity</dt>
            <dd>{activity.story.last_activity ? formatDateTime(activity.story.last_activity) : "None yet"}</dd>
            <dt>Demo request</dt>
            <dd>{activity.demo_request ? formatDate(activity.demo_request.created_at) : "None"}</dd>
            <dt>Feedback</dt>
            <dd>{activity.feedback ? "Given" : "None yet"}</dd>
          </dl>
        </section>
      </div>

      <p className="to-ai" role="note">
        <Sparkles size={14} aria-hidden="true" /> {detail.ai.line}
      </p>

      <Panel eyebrow="History" title="What happened in this trial">
        {history.length ? (
          <ol className="to-history">
            {history.map((event) => (
              <li key={event.id}>
                <strong>{eventLabel(event.action)}</strong>
                <small>{formatDateTime(event.created_at)}</small>
              </li>
            ))}
          </ol>
        ) : (
          <p className="ac-muted">No recorded events yet.</p>
        )}
      </Panel>
    </>
  );
}

const EVENT_LABELS: Record<string, string> = {
  TRIAL_REQUEST_APPROVED: "Trial approved",
  TRIAL_EXTENDED: "Trial extended",
  TRIAL_EXIT_RAISED_BY_MDARIX: "Ended by MDARIX",
  TRIAL_EXIT_REQUESTED: "Owner asked to end early",
  TRIAL_ENDED_EARLY: "Trial ended early",
  TRIAL_EXIT_DECLINED: "Request to end early declined",
  TRIAL_CONVERTED: "Converted",
  TRIAL_DATA_DELETED_BY_ADMIN: "Data deleted by MDARIX",
  TRIAL_ACTION_REFUSED: "Action refused",
  TRIAL_SAMPLE_REMOVED: "Sample data removed",
  TRIAL_SAMPLE_RESTARTED: "Sample data restarted",
  SUBSCRIPTION_CHANGED: "Plan changed",
  TRIAL_OWNER_PROMOTED: "Owner became Customer Administrator",
};

/** An audit action in plain words ("TRIAL_EXTENDED" -> "Trial extended"). */
export const eventLabel = (action: string) =>
  EVENT_LABELS[action] ??
  action
    .toLowerCase()
    .split("_")
    .join(" ")
    .replace(/^./, (first) => first.toUpperCase());

function ActionDrawer({
  action,
  trial,
  onClose,
  onDone,
}: {
  action: Action;
  trial: TrialDetail;
  onClose: () => void;
  onDone: (text: string) => void;
}) {
  const [days, setDays] = useState(7);
  const [reason, setReason] = useState("");
  const [typed, setTyped] = useState("");
  const [kind, setKind] = useState<"PILOT" | "PAID">("PILOT");
  const [planId, setPlanId] = useState("");
  const today = new Date().toISOString().slice(0, 10);
  const [starts, setStarts] = useState(today);
  const [ends, setEnds] = useState(new Date(Date.now() + 90 * 86_400_000).toISOString().slice(0, 10));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const plans = useResource<unknown>(action === "convert" ? "/api/v1/platform-admin/plans" : null);
  const options = convertiblePlans(listOf(plans.data) as PlanOption[]);
  const left = trial.dates.extension_left ?? EXTENSION_DAYS_MAX;
  const used = trial.dates.extension_used ?? 0;

  const problem =
    action === "extend"
      ? (extensionError(days, left) ?? reasonError(reason))
      : action === "end"
        ? reasonError(reason)
        : action === "convert"
          ? !planId
            ? "Choose a pilot or paid plan."
            : ends <= starts
              ? "The end must be after the start."
              : reasonError(reason)
          : nameMatches(typed, trial.name)
            ? null
            : "Type the organization's name exactly to confirm.";

  const submit = async () => {
    setBusy(true);
    setError("");
    const base = `${TRIAL_ORGS_PATH}/${trial.tenant_id}`;
    try {
      if (action === "extend") {
        const result = await send<{ ends_words: string }>(`${base}/extend`, "POST", { days, reason });
        onDone(`Trial extended: it now ends ${result.ends_words}.`);
      } else if (action === "end") {
        await send(`${base}/end`, "POST", { reason });
        onDone("Trial ended. Its data is kept for 30 days and the owner has been emailed.");
      } else if (action === "convert") {
        await send(`${base}/convert`, "POST", {
          kind,
          plan_id: planId,
          starts_at: `${starts}T00:00:00Z`,
          expires_at: `${ends}T23:59:59Z`,
          reason,
        });
        onDone("Converted. The organization is now listed under Customers & Tenants.");
      } else {
        await send(`${base}/delete-data`, "POST", { confirm_name: typed });
        onDone("The trial's data has been deleted and the organization archived.");
      }
    } catch (reason_) {
      setError(errorText(reason_, "The action could not be completed"));
    } finally {
      setBusy(false);
    }
  };

  const title =
    action === "extend"
      ? `Extend ${trial.name}`
      : action === "end"
        ? `End ${trial.name}'s trial now`
        : action === "convert"
          ? `Convert ${trial.name}`
          : `Delete ${trial.name}'s data`;
  const confirmLabel =
    action === "extend"
      ? "Extend trial"
      : action === "end"
        ? "End trial now"
        : action === "convert"
          ? "Convert trial"
          : "Delete data now";

  return (
    <Drawer title={title} onClose={onClose}>
      <form
        className="cc-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!problem) void submit();
        }}
      >
        {action === "extend" && (
          <>
            <label>
              Days to add (1 to {left})
              <input
                type="number"
                min={1}
                max={left}
                value={days}
                onChange={(event) => setDays(Number(event.target.value))}
              />
            </label>
            <p className="ac-muted">
              {extensionSentence(trial.dates.ends_at, used, days, (date) => formatDateTime(date.toISOString()))}
            </p>
          </>
        )}
        {action === "end" && (
          <p className="ac-muted">
            The trial ends now and sign-in to it closes. Its data is kept for 30 days, then deleted; the owner is
            emailed. This is recorded as a request to end early raised by MDARIX.
          </p>
        )}
        {action === "convert" && (
          <>
            <fieldset className="cc-fieldset">
              <legend>Convert to</legend>
              <label>
                <input type="radio" checked={kind === "PILOT"} onChange={() => setKind("PILOT")} /> Pilot
              </label>
              <label>
                <input type="radio" checked={kind === "PAID"} onChange={() => setKind("PAID")} /> Paid
              </label>
            </fieldset>
            <label>
              Plan
              <select value={planId} onChange={(event) => setPlanId(event.target.value)} aria-label="Plan">
                <option value="">Choose a plan</option>
                {options.map((plan) => (
                  <option key={plan.id} value={plan.id}>
                    {plan.name || plan.code}
                  </option>
                ))}
              </select>
            </label>
            <div className="cc-two-fields">
              <label>
                Starts
                <input type="date" value={starts} onChange={(event) => setStarts(event.target.value)} />
              </label>
              <label>
                Ends
                <input type="date" value={ends} onChange={(event) => setEnds(event.target.value)} />
              </label>
            </div>
            <p className="ac-muted">
              The organization moves to Customers &amp; Tenants. Its trial history stays, and its owner becomes its
              Customer Administrator.
            </p>
          </>
        )}
        {action === "delete_data" && (
          <>
            <p className="ac-muted">
              Every record, file and person of this trial is deleted and the organization archived. This cannot be
              undone.
            </p>
            <label>
              Type <strong>{trial.name}</strong> to confirm
              <input value={typed} onChange={(event) => setTyped(event.target.value)} aria-label="Organization name" />
            </label>
          </>
        )}
        {action !== "delete_data" && (
          <label>
            Reason (10 characters or more)
            <textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={3} />
          </label>
        )}
        {problem && <p className="cc-hint">{problem}</p>}
        {error && (
          <p className="ac-message tone-critical" role="alert">
            {error}
          </p>
        )}
        <div className="cc-actions">
          <button type="button" className="ac-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={Boolean(problem) || busy}>
            {confirmLabel}
          </button>
        </div>
      </form>
    </Drawer>
  );
}
