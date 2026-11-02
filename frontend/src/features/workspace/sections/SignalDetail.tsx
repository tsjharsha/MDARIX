import { useState, type ReactNode } from "react";
import { AlertTriangle, ArrowLeft, FileSearch } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import {
  Drawer,
  SearchBox,
  Table,
  errorText,
  formatDate,
  listOf,
  send,
  useResource,
} from "../../customer-admin/shared";
import { displayId, safeText } from "../../../app/displayId";
import { formatDay } from "../../../app/dates";
import { sectionAllowed, useCan, useWorkspace } from "../workspaceContext";
import { localDay } from "../workspaceModel";
import { priorityTone, taskEventActor, taskEventText } from "../tasks";
import {
  DISPOSITIONS,
  DISPOSITION_HELP,
  DISPOSITION_LABEL,
  DISPOSITION_REASON_MAX,
  EMPTY_DISPOSITION,
  PRIORITY_REASON_MAX,
  QUESTION_MAX,
  SIGNAL_PRIORITIES,
  addComplaintsProblem,
  addedHowLabel,
  ageText,
  defaultInvestigationQuestion,
  dispositionBody,
  dispositionProblem,
  harmFlags,
  investigationBody,
  investigationProblem,
  isSignalId,
  isSignalRef,
  mergeProblem,
  priorityBody,
  priorityNeedsReason,
  priorityProblem,
  priorityText,
  relatedItem,
  ruleParametersText,
  signalListPath,
  signalOriginLabel,
  signalPath,
  signalPriorityLabel,
  signalDueState,
  signalDueText,
  signalPriority,
  signalProductText,
  signalStatusLabel,
  signalStatusTone,
  versionSplit,
  type DispositionForm,
  type InvestigationForm,
  type SignalComplaint,
  type SignalDetail,
  type SignalList,
  type SignalRef,
  type SignalSummary,
} from "../signals";
import { StatusBadge, countOf, formatCount } from "./common";
import { SignalInsightPanel } from "./SignalInsight";
import { oneClickQuestion, openCasePath } from "../signalAi";

/** The status of a signal, as a badge with its label (never colour alone). */
export function SignalStatusBadge({ signal }: { signal: Pick<SignalSummary, "status" | "status_label"> }) {
  if (!signal.status) return <span className="ac-muted">—</span>;
  return (
    <ToneBadge tone={signalStatusTone(signal.status)} label={signalStatusLabel(signal.status, signal.status_label)} />
  );
}

/** The priority as it stands, with the suggestion below when a person has not confirmed it or chose another. */
export function SignalPriorityCell({ signal }: { signal: SignalSummary }) {
  const priority = signalPriority(signal);
  if (!priority.current) return <span className="ac-muted">Not set</span>;
  return (
    <span className="ca-person">
      <ToneBadge tone={priorityTone(priority.current)} label={signalPriorityLabel(priority.current)} />
      {!priority.isConfirmed && <small>Suggested · not confirmed</small>}
      {priority.changed && <small>Suggested {signalPriorityLabel(priority.suggested)}</small>}
    </span>
  );
}

/** The triage due date, flagged when it is overdue or due within two days. */
export function SignalDue({ signal }: { signal: SignalSummary }) {
  const state = signalDueState(signal);
  const text = signalDueText(signal, formatDate);
  if (state === "overdue") return <span className="uw-flag-critical">{text}</span>;
  if (state === "due_soon") return <span className="uw-flag-warning">{text}</span>;
  return <>{text}</>;
}

type ActionMode = "priority" | "disposition" | "merge" | "complaints" | "investigation";
type CreatedCase = { id: string; business_id?: string | null };

/**
 * One signal: what it is and where it came from, its complaints and how they split across versions, related records,
 * its lineage and history, and the triage actions the server allows the person right now (its `actions` flags).
 * `reference` is the signal's business ID (SIG000023, from a link or a task) or its id.
 */
export function SignalDetailView({
  reference,
  onBack,
  onOpenSignal,
}: {
  reference: string;
  onBack: () => void;
  onOpenSignal: (reference: string) => void;
}) {
  const direct = isSignalId(reference);
  // A business ID is found through the list's search; an id is read directly.
  const lookup = useResource<SignalList>(direct ? null : signalListPath({ status: "ALL", q: reference }, 1, 20));
  const match = direct
    ? null
    : ((listOf(lookup.data?.items) as SignalSummary[]).find((row) => isSignalRef(row, reference)) ?? null);
  const id = direct ? reference : (match?.id ?? null);
  const detail = useResource<SignalDetail>(id ? signalPath(id) : null);
  const back = (
    <button type="button" className="ac-secondary" onClick={onBack}>
      <ArrowLeft size={16} aria-hidden="true" /> Back to the inbox
    </button>
  );
  if (!direct && lookup.state !== "ready")
    return (
      <Panel eyebrow="Signal" title={reference} source={lookup} action={back}>
        {null}
      </Panel>
    );
  if (!id)
    return (
      <Panel eyebrow="Signal" title={reference} action={back}>
        <Empty
          title={`${reference} was not found`}
          detail="It is not a trend of your organization, or your role cannot open it."
        />
      </Panel>
    );
  return (
    <Panel
      eyebrow="Signal"
      title={detail.data ? signalHeading(detail.data) : (safeText(match?.business_id) ?? "Signal")}
      source={detail}
      action={back}
    >
      {detail.data && <SignalBody signal={detail.data} reload={detail.reload} onOpenSignal={onOpenSignal} />}
    </Panel>
  );
}

const signalHeading = (signal: SignalSummary) =>
  `${safeText(signal.business_id) ?? "Signal"}: ${safeText(signal.title) ?? "Untitled signal"}`;

function SignalBody({
  signal,
  reload,
  onOpenSignal,
}: {
  signal: SignalDetail;
  reload: () => void;
  onOpenSignal: (reference: string) => void;
}) {
  const { session, work, open, notify } = useWorkspace();
  const canCreateCase = useCan("investigation.create");
  const casesAllowed = sectionAllowed("Investigations", session?.allowed_menu, session?.business_permissions);
  const [mode, setMode] = useState<ActionMode | null>(null);
  const [starting, setStarting] = useState(false);
  const [created, setCreated] = useState<CreatedCase | null>(null);
  const [opening, setOpening] = useState(false);
  const actions = signal.actions ?? {};
  const name = safeText(signal.business_id) ?? "The trend";
  const reference = (item: SignalRef) => safeText(item.business_id) ?? String(item.id);

  const openCase = (kase: CreatedCase) => {
    work.setInvestigationId(String(kase.id), signal.product?.id ? String(signal.product.id) : null);
    open("Investigations", "Workspace");
  };

  const start = async () => {
    setStarting(true);
    try {
      await send(signalPath(signal.id, "start"), "POST");
      notify(`${name}: triage started.`);
      reload();
    } catch (reason) {
      notify(errorText(reason, "Triage could not be started."), "critical");
    } finally {
      setStarting(false);
    }
  };

  // One click from the signal to its case: the triage decision (when still due) and the case, with every complaint,
  // for the person clicking; then straight to the case page, where the AI analysis starts by itself.
  const openCaseNow = async () => {
    setOpening(true);
    try {
      const result = await send<{ investigation: CreatedCase; triaged?: boolean }>(
        openCasePath(String(signal.id)),
        "POST",
        {
          investigation_question: oneClickQuestion(defaultInvestigationQuestion(signal), signal),
        },
      );
      const kase = result?.investigation;
      notify(
        `${safeText(kase?.business_id) ?? "The case"} was opened for ${name}${result?.triaged ? " and the signal triaged as needing an investigation" : ""}.`,
      );
      if (kase?.id && casesAllowed) openCase(kase);
      else {
        if (kase) setCreated(kase);
        reload();
      }
    } catch (reason) {
      notify(errorText(reason, "The investigation could not be opened."), "critical");
    } finally {
      setOpening(false);
    }
  };

  const done = (message: string) => {
    setMode(null);
    notify(message);
    reload();
  };

  const complaints = listOf(signal.complaints) as SignalComplaint[];
  const split = versionSplit(signal.version_split);
  const events = listOf(signal.events);
  const rule = signal.rule;
  const ruleText = rule
    ? [
        safeText(rule.code),
        rule.version ? `version ${rule.version}` : null,
        ruleParametersText(rule.parameters) || null,
      ]
        .filter(Boolean)
        .join(" · ")
    : safeText(signal.rule_code);
  const anyAction =
    actions.can_start ||
    actions.can_set_priority ||
    actions.can_disposition ||
    actions.can_merge ||
    actions.can_add_complaints ||
    ((actions.can_create_investigation || actions.can_open_case) && canCreateCase);

  return (
    <div className="uw-signal">
      {created && (
        <div className="ac-message tone-good" role="status">
          {safeText(created.business_id) ?? "The investigation"} was opened for {name}.
          {casesAllowed && created.id && (
            <button type="button" className="ac-primary" onClick={() => openCase(created)}>
              <FileSearch size={16} aria-hidden="true" /> Open the case
            </button>
          )}
        </div>
      )}

      <dl className="ca-facts">
        <Fact label="Status">
          <SignalStatusBadge signal={signal} />
        </Fact>
        <Fact label="Priority">
          <SignalPriorityCell signal={signal} />
        </Fact>
        <Fact label="How priority was set">{priorityText(signal)}</Fact>
        <Fact label="Origin">
          <span className="ca-person">
            <span>{signalOriginLabel(signal.origin, signal.origin_label)}</span>
            {ruleText && <small>{ruleText}</small>}
          </span>
        </Fact>
        <Fact label="Product / version">{signalProductText(signal)}</Fact>
        <Fact label="Problem code">
          {signal.problem_key === "UNSPECIFIED" ? "Not specified" : (safeText(signal.problem_key) ?? "—")}
        </Fact>
        <Fact label="Owner">{safeText(signal.owner?.name) ?? "Unassigned"}</Fact>
        <Fact label="Due">
          <SignalDue signal={signal} />
        </Fact>
        <Fact label="Age">{ageText(signal.age_days)}</Fact>
        <Fact label="Complaints">
          {formatCount(signal.complaint_count ?? complaints.length)}
          {(signal.recent_complaints_7d ?? 0) > 0
            ? ` · ${formatCount(signal.recent_complaints_7d ?? 0)} in last 7 days`
            : ""}
        </Fact>
        <Fact label="Complaint dates">
          {signal.first_event_at || signal.last_event_at
            ? `${formatDay(signal.first_event_at)} – ${formatDay(signal.last_event_at)}`
            : "—"}
        </Fact>
        <Fact label="Highest severity">
          <span className="ca-person">
            <StatusBadge value={signal.highest_severity} />
            {signal.serious_harm && <small className="uw-flag-critical">Serious harm reported</small>}
          </span>
        </Fact>
      </dl>

      {safeText(signal.description) && <p className="uw-signal-text">{signal.description}</p>}
      <SignalInsightPanel signalId={String(signal.id)} />
      {safeText(signal.priority_reason) && (
        <p className="ac-muted">
          <strong>Why this priority:</strong> {signal.priority_reason}
        </p>
      )}
      {signal.disposition && (
        <section className="ca-drawer-section" aria-label="Disposition">
          <h3>Disposition</h3>
          {safeText(signal.disposition.reason) && <p>{signal.disposition.reason}</p>}
          <p className="ac-muted">
            {safeText(signal.disposition.by_name) ?? "Recorded"}
            {signal.disposition.at ? ` · ${formatDate(signal.disposition.at)}` : ""}
          </p>
          {signal.disposition.monitor_review_date && (
            <p>
              Review again on {formatDay(signal.disposition.monitor_review_date)}
              {safeText(signal.disposition.monitor_trigger) ? ` · reopen if ${signal.disposition.monitor_trigger}` : ""}
            </p>
          )}
        </section>
      )}

      <section className="ca-drawer-section" aria-label="Triage actions">
        <h3>Triage</h3>
        <div className="ca-action-row">
          {actions.can_open_case && canCreateCase && (
            <button type="button" className="ac-primary" disabled={opening} onClick={() => void openCaseNow()}>
              <FileSearch size={16} aria-hidden="true" />{" "}
              {opening ? "Opening the investigation…" : "Open an investigation"}
            </button>
          )}
          {actions.can_start && (
            <button type="button" className="ac-primary" disabled={starting} onClick={() => void start()}>
              {starting ? "Starting…" : "Start triage"}
            </button>
          )}
          {actions.can_set_priority && (
            <button type="button" className="ac-secondary" onClick={() => setMode("priority")}>
              Set priority
            </button>
          )}
          {actions.can_disposition && (
            <button type="button" className="ac-secondary" onClick={() => setMode("disposition")}>
              Record disposition
            </button>
          )}
          {actions.can_merge && (
            <button type="button" className="ac-secondary" onClick={() => setMode("merge")}>
              Merge signals
            </button>
          )}
          {actions.can_add_complaints && (
            <button type="button" className="ac-secondary" onClick={() => setMode("complaints")}>
              Add complaints
            </button>
          )}
          {actions.can_create_investigation && canCreateCase && (
            <button type="button" className="ac-secondary" onClick={() => setMode("investigation")}>
              {actions.can_open_case ? "Open an investigation with options…" : "Create investigation"}
            </button>
          )}
          {!anyAction && <p className="ac-muted">Nothing for you to do on this trend right now.</p>}
        </div>
      </section>

      {(signal.canonical || listOf(signal.merged_from).length > 0 || listOf(signal.investigations).length > 0) && (
        <section className="ca-drawer-section" aria-label="Lineage and investigations">
          <h3>Lineage and investigations</h3>
          {signal.canonical && (
            <p>
              Duplicate of{" "}
              <button type="button" className="ac-link" onClick={() => onOpenSignal(reference(signal.canonical!))}>
                {reference(signal.canonical)}
              </button>
              , which carries the work on this problem.
            </p>
          )}
          {listOf(signal.merged_from).length > 0 && (
            <p>
              Merged into this signal:{" "}
              {(listOf(signal.merged_from) as Array<SignalRef & { status?: string | null }>).map((item, index) => (
                <span key={item.id}>
                  {index > 0 && ", "}
                  <button type="button" className="ac-link" onClick={() => onOpenSignal(reference(item))}>
                    {reference(item)}
                  </button>
                </span>
              ))}
            </p>
          )}
          {listOf(signal.investigations).length > 0 && (
            <ul className="uw-list" aria-label="Investigations opened for this trend">
              {(listOf(signal.investigations) as Array<SignalRef & { status?: string | null }>).map((kase) => (
                <li key={kase.id}>
                  <span>
                    <strong>{safeText(kase.business_id) ?? "Investigation"}</strong>
                  </span>
                  <StatusBadge value={kase.status} />
                  {casesAllowed && (
                    <button type="button" className="ac-link" onClick={() => openCase(kase)}>
                      Open the case
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section className="ca-drawer-section" aria-label="Complaints in this trend">
        <h3>Complaints · {complaints.length}</h3>
        <Table
          caption="Complaints in this trend"
          rows={complaints}
          rowKey={(row) => String(row.id)}
          empty={{ title: "No complaints", detail: "Complaints grouped into this trend appear here." }}
          columns={[
            {
              key: "business_id",
              label: "Complaint ID",
              fields: ["business_id"],
              sortValue: (row) => displayId(row, "complaint_identifier"),
              render: (row) => displayId(row, "complaint_identifier"),
            },
            {
              key: "complaint_identifier",
              label: "Source ID",
              render: (row) => safeText(row.complaint_identifier) ?? "—",
            },
            {
              key: "description",
              label: "Description",
              render: (row) => safeText(row.description) ?? <span className="ac-muted">—</span>,
            },
            {
              key: "event_timestamp",
              label: "Event date",
              render: (row) => formatDay(row.event_timestamp),
            },
            {
              key: "severity",
              label: "Severity",
              fields: ["severity", "death", "serious_injury", "malfunction"],
              render: (row) => (
                <span className="ca-person">
                  <StatusBadge value={row.severity} />
                  {harmFlags(row).length > 0 && (
                    <small className={row.death || row.serious_injury ? "uw-flag-critical" : undefined}>
                      {harmFlags(row).join(" · ")}
                    </small>
                  )}
                </span>
              ),
            },
            {
              key: "version",
              label: "Version",
              fields: ["product_version"],
              sortValue: (row) => safeText(row.product_version?.version_identifier),
              render: (row) => safeText(row.product_version?.version_identifier) ?? "—",
            },
            { key: "country", label: "Country", render: (row) => safeText(row.country) ?? "—" },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> },
            { key: "added_how", label: "Added", render: (row) => addedHowLabel(row.added_how) },
          ]}
        />
      </section>

      <div className="ac-grid two">
        <section className="ca-drawer-section" aria-label="Complaints by version">
          <h3>Its complaints by product version</h3>
          {split.length ? (
            <ul className="ac-barlist uw-split">
              {split.map((item) => (
                <li key={item.key} title={`${item.label}: ${countOf(item.count, "complaint")}, ${item.percent}%`}>
                  <span className="ac-barlist-label">{item.label}</span>
                  <span className="ac-barlist-track" aria-hidden="true">
                    <span
                      className="ac-barlist-fill fill-series"
                      style={{ width: `${item.count ? Math.max(2, item.percent) : 0}%` }}
                    />
                  </span>
                  <strong className="ac-barlist-value">
                    {formatCount(item.count)} · {item.percent}%
                  </strong>
                </li>
              ))}
            </ul>
          ) : (
            <p className="ac-muted">No version recorded on these complaints.</p>
          )}
        </section>
        <section className="ca-drawer-section" aria-label="Related records">
          <h3>Related records</h3>
          <RelatedList title="Changes" rows={listOf(signal.related?.changes)} empty="No related changes." />
          <RelatedList title="Open CAPAs" rows={listOf(signal.related?.open_capas)} empty="No open CAPAs." />
          <RelatedList
            title="Open investigations"
            rows={listOf(signal.related?.open_investigations)}
            empty="No open investigations for this product."
          />
        </section>
      </div>

      <section className="ca-drawer-section" aria-label="History">
        <h3>History</h3>
        {events.length ? (
          <ol className="ca-timeline uw-task-history">
            {events.map((event, index) => (
              <li key={`${event.created_at ?? ""}:${index}`}>
                <strong>{taskEventText({ ...event, event_type: String(event.event_type ?? "") })}</strong>
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

      {mode === "priority" && (
        <PriorityDrawer
          signal={signal}
          onClose={() => setMode(null)}
          onDone={() => done(`${name}: priority recorded.`)}
        />
      )}
      {mode === "disposition" && (
        <DispositionDrawer
          signal={signal}
          onClose={() => setMode(null)}
          onDone={(label) => done(`${name}: disposition recorded (${label}).`)}
        />
      )}
      {mode === "merge" && (
        <MergeDrawer signal={signal} onClose={() => setMode(null)} onDone={() => done(`Trends merged into ${name}.`)} />
      )}
      {mode === "complaints" && (
        <AddComplaintsDrawer
          signal={signal}
          onClose={() => setMode(null)}
          onDone={(count) => done(`${count} ${count === 1 ? "complaint" : "complaints"} added to ${name}.`)}
        />
      )}
      {mode === "investigation" && (
        <InvestigationDrawer
          signal={signal}
          onClose={() => setMode(null)}
          onDone={(kase) => {
            setCreated(kase);
            done(`${safeText(kase.business_id) ?? "The investigation"} was opened for ${name}.`);
          }}
        />
      )}
    </div>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function RelatedList({ title, rows, empty }: { title: string; rows: any[]; empty: string }) {
  return (
    <div className="uw-related">
      <h3>{title}</h3>
      {rows.length ? (
        <ul className="uw-list">
          {rows.map((row, index) => {
            const item = relatedItem(row);
            return (
              <li key={`${item.id}:${index}`}>
                <span>
                  <strong>{item.id}</strong>
                  {item.text && <small>{item.text}</small>}
                </span>
                {item.status && <StatusBadge value={item.status} />}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="ac-muted">{empty}</p>
      )}
    </div>
  );
}

/** Send one triage action and keep its failure in the form (the server's message), not in a passing toast. */
function useSubmit() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Resolves to { data } once the server accepted the action, null when it refused it (the message is kept).
  const run = async <T,>(path: string, body: unknown, fallback: string): Promise<{ data: T } | null> => {
    setBusy(true);
    setError("");
    try {
      return { data: await send<T>(path, "POST", body) };
    } catch (reason) {
      setError(errorText(reason, fallback));
      setBusy(false);
      return null;
    }
  };
  return { busy, error, run };
}

function FormError({ error }: { error: string }) {
  if (!error) return null;
  return (
    <p className="ca-inline-error" role="alert">
      <AlertTriangle size={15} aria-hidden="true" /> {error}
    </p>
  );
}

function FormButtons({
  busy,
  disabled,
  label,
  onClose,
}: {
  busy: boolean;
  disabled: boolean;
  label: string;
  onClose: () => void;
}) {
  return (
    <>
      <p className="ac-muted">Recorded in the trend's history and the audit trail.</p>
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        <button type="submit" className="ac-primary" disabled={busy || disabled}>
          {busy ? "Saving…" : label}
        </button>
      </div>
    </>
  );
}

const title = (signal: SignalSummary, what: string) => `${what} · ${safeText(signal.business_id) ?? "signal"}`;

function PriorityDrawer({
  signal,
  onClose,
  onDone,
}: {
  signal: SignalDetail;
  onClose: () => void;
  onDone: () => void;
}) {
  const suggested = signal.suggested_priority ? String(signal.suggested_priority).toUpperCase() : null;
  const [priority, setPriority] = useState(
    String(signal.confirmed_priority ?? signal.suggested_priority ?? signal.priority ?? "").toUpperCase(),
  );
  const [reason, setReason] = useState("");
  const submit = useSubmit();
  const problem = priorityProblem({ priority, reason, suggested });
  const needsReason = priorityNeedsReason(suggested, priority);
  return (
    <Drawer title={title(signal, "Set priority")} onClose={onClose}>
      <form
        className="ca-form"
        onSubmit={async (event) => {
          event.preventDefault();
          if (problem) return;
          const result = await submit.run(
            signalPath(signal.id, "priority"),
            priorityBody({ priority, reason }),
            "The priority was not recorded.",
          );
          if (result !== null) onDone();
        }}
      >
        <p className="ac-muted">
          {suggested ? `MDARIX suggested ${signalPriorityLabel(suggested)}.` : "No priority was suggested."} Confirm it,
          or choose another and say why.
        </p>
        <div className="ca-chips" role="radiogroup" aria-label="Priority">
          {[...SIGNAL_PRIORITIES].reverse().map((option) => (
            <button
              type="button"
              role="radio"
              key={option}
              aria-checked={priority === option}
              className={priority === option ? "selected" : ""}
              onClick={() => setPriority(option)}
            >
              {signalPriorityLabel(option)}
              {option === suggested ? " (suggested)" : ""}
            </button>
          ))}
        </div>
        <label className="ca-field">
          {needsReason ? "Why a different priority?" : "Note (optional)"}
          <textarea
            required={needsReason}
            rows={3}
            maxLength={PRIORITY_REASON_MAX}
            value={reason}
            placeholder={needsReason ? "At least 10 characters" : "At least 10 characters, if you add one"}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        {problem && (reason.trim() || needsReason) && <p className="uw-hint">{problem}</p>}
        <FormError error={submit.error} />
        <FormButtons busy={submit.busy} disabled={!!problem} label="Record priority" onClose={onClose} />
      </form>
    </Drawer>
  );
}

/** Other open signals of the same product (for duplicate, merge and "also covers"). */
function useSiblingSignals(signal: SignalSummary) {
  const productId = signal.product?.id ? String(signal.product.id) : "";
  const list = useResource<SignalList>(
    productId ? signalListPath({ status: "OPEN", productId, sort: "priority" }, 1, 100) : null,
  );
  const rows = (listOf(list.data?.items) as SignalSummary[]).filter((row) => String(row.id) !== String(signal.id));
  return { list, rows, productId };
}

const signalOption = (row: SignalSummary) =>
  `${safeText(row.business_id) ?? "Signal"} · ${safeText(row.title) ?? "Untitled"} · ${signalStatusLabel(row.status, row.status_label)}`;

function DispositionDrawer({
  signal,
  onClose,
  onDone,
}: {
  signal: SignalDetail;
  onClose: () => void;
  onDone: (label: string) => void;
}) {
  const [form, setForm] = useState<DispositionForm>({ ...EMPTY_DISPOSITION });
  const submit = useSubmit();
  const siblings = useSiblingSignals(signal);
  const today = localDay();
  const tomorrow = localDay(new Date(Date.now() + 86_400_000));
  const problem = dispositionProblem(form, today);
  return (
    <Drawer title={title(signal, "Record disposition")} onClose={onClose}>
      <form
        className="ca-form"
        onSubmit={async (event) => {
          event.preventDefault();
          if (problem || !form.disposition) return;
          const result = await submit.run(
            signalPath(signal.id, "disposition"),
            dispositionBody(form),
            "The disposition was not recorded.",
          );
          if (result !== null) onDone(DISPOSITION_LABEL[form.disposition]);
        }}
      >
        <div className="ca-chips" role="radiogroup" aria-label="Disposition">
          {DISPOSITIONS.map((option) => (
            <button
              type="button"
              role="radio"
              key={option}
              aria-checked={form.disposition === option}
              className={form.disposition === option ? "selected" : ""}
              onClick={() => setForm({ ...form, disposition: option })}
            >
              {DISPOSITION_LABEL[option]}
            </button>
          ))}
        </div>
        {form.disposition && <p className="ac-muted">{DISPOSITION_HELP[form.disposition]}</p>}
        {form.disposition === "MONITOR" && (
          <div className="ca-form-grid">
            <label className="ca-field">
              Review again on
              <input
                type="date"
                required
                min={tomorrow}
                value={form.monitorReviewDate}
                onChange={(event) => setForm({ ...form, monitorReviewDate: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Reopen it if (optional)
              <input
                maxLength={500}
                value={form.monitorTrigger}
                placeholder="e.g. 2 more complaints within 30 days"
                onChange={(event) => setForm({ ...form, monitorTrigger: event.target.value })}
              />
            </label>
          </div>
        )}
        {form.disposition === "DUPLICATE" && (
          <label className="ca-field">
            Duplicate of
            <select
              required
              value={form.canonicalSignalId}
              onChange={(event) => setForm({ ...form, canonicalSignalId: event.target.value })}
            >
              <option value="">
                {siblings.list.state === "loading" ? "Loading…" : "Choose the trend that covers this problem"}
              </option>
              {siblings.rows.map((row) => (
                <option key={row.id} value={row.id}>
                  {signalOption(row)}
                </option>
              ))}
            </select>
            {siblings.list.state === "ready" && !siblings.rows.length && (
              <small className="ac-muted">No other open trend of this product.</small>
            )}
          </label>
        )}
        {form.disposition && (
          <label className="ca-field">
            Reason
            <textarea
              required
              rows={4}
              maxLength={DISPOSITION_REASON_MAX}
              value={form.reason}
              placeholder="At least 10 characters"
              onChange={(event) => setForm({ ...form, reason: event.target.value })}
            />
          </label>
        )}
        {problem && form.disposition && form.reason.trim() && <p className="uw-hint">{problem}</p>}
        <FormError error={submit.error} />
        <FormButtons busy={submit.busy} disabled={!!problem} label="Record disposition" onClose={onClose} />
      </form>
    </Drawer>
  );
}

function SignalChecklist({
  rows,
  chosen,
  onToggle,
  label,
}: {
  rows: SignalSummary[];
  chosen: string[];
  onToggle: (id: string) => void;
  label: string;
}) {
  return (
    <ul className="uw-pick-list" aria-label={label}>
      {rows.map((row) => (
        <li key={row.id}>
          <label className="ca-check">
            <input
              type="checkbox"
              checked={chosen.includes(String(row.id))}
              onChange={() => onToggle(String(row.id))}
            />
            <span className="ca-person">
              <strong>{safeText(row.business_id) ?? "Signal"}</strong>
              <small>
                {safeText(row.title) ?? "Untitled"} · {countOf(Number(row.complaint_count ?? 0), "complaint")} ·{" "}
                {signalStatusLabel(row.status, row.status_label)}
              </small>
            </span>
          </label>
        </li>
      ))}
    </ul>
  );
}

const toggled = (list: string[], id: string) =>
  list.includes(id) ? list.filter((item) => item !== id) : [...list, id];

function MergeDrawer({ signal, onClose, onDone }: { signal: SignalDetail; onClose: () => void; onDone: () => void }) {
  const [sources, setSources] = useState<string[]>([]);
  const [reason, setReason] = useState("");
  const submit = useSubmit();
  const siblings = useSiblingSignals(signal);
  const problem = mergeProblem(sources, reason);
  return (
    <Drawer title={title(signal, "Merge trends")} onClose={onClose}>
      <form
        className="ca-form"
        onSubmit={async (event) => {
          event.preventDefault();
          if (problem) return;
          const result = await submit.run(
            signalPath(signal.id, "merge"),
            { source_signal_ids: sources, reason: reason.trim() },
            "The trends were not merged.",
          );
          if (result !== null) onDone();
        }}
      >
        <p className="ac-muted">
          The chosen signals and their complaints are merged into {safeText(signal.business_id) ?? "this trend"}. They
          keep their records and point here.
        </p>
        {siblings.list.state === "loading" && !siblings.list.data ? (
          <p className="ac-muted">Loading trends…</p>
        ) : siblings.rows.length ? (
          <SignalChecklist
            rows={siblings.rows}
            chosen={sources}
            onToggle={(id) => setSources((current) => toggled(current, id))}
            label="Trends to merge"
          />
        ) : (
          <p className="ac-muted">No other open trend of this product.</p>
        )}
        <label className="ca-field">
          Reason
          <textarea
            required
            rows={3}
            maxLength={DISPOSITION_REASON_MAX}
            value={reason}
            placeholder="At least 10 characters"
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        {problem && reason.trim() && <p className="uw-hint">{problem}</p>}
        <FormError error={submit.error} />
        <FormButtons busy={submit.busy} disabled={!!problem} label="Merge into this trend" onClose={onClose} />
      </form>
    </Drawer>
  );
}

function AddComplaintsDrawer({
  signal,
  onClose,
  onDone,
}: {
  signal: SignalDetail;
  onClose: () => void;
  onDone: (count: number) => void;
}) {
  const productId = signal.product?.id ? String(signal.product.id) : "";
  const [chosen, setChosen] = useState<string[]>([]);
  const [reason, setReason] = useState("");
  const [search, setSearch] = useState("");
  const submit = useSubmit();
  const complaints = useResource<any>(
    productId ? `/api/v1/complaints?${new URLSearchParams({ product_id: productId, page_size: "200" })}` : null,
  );
  const already = new Set((listOf(signal.complaints) as SignalComplaint[]).map((row) => String(row.id)));
  const options = (listOf(complaints.data?.items) as any[]).filter(
    (row) =>
      !already.has(String(row.id)) &&
      (!search.trim() ||
        `${row.business_id ?? ""} ${row.complaint_identifier ?? ""} ${row.description ?? ""}`
          .toLowerCase()
          .includes(search.trim().toLowerCase())),
  );
  const problem = addComplaintsProblem(chosen, reason);
  return (
    <Drawer title={title(signal, "Add complaints")} onClose={onClose}>
      <form
        className="ca-form"
        onSubmit={async (event) => {
          event.preventDefault();
          if (problem) return;
          const result = await submit.run(
            signalPath(signal.id, "complaints"),
            { complaint_ids: chosen, reason: reason.trim() },
            "The complaints were not added.",
          );
          if (result !== null) onDone(chosen.length);
        }}
      >
        <p className="ac-muted">Complaints of {signalProductText(signal)} that this signal does not cover yet.</p>
        <SearchBox value={search} onChange={setSearch} label="Search complaints" />
        {complaints.state === "loading" && !complaints.data ? (
          <p className="ac-muted">Loading complaints…</p>
        ) : complaints.state !== "ready" ? (
          <p className="ca-inline-error">{complaints.error ?? "Complaints could not be loaded."}</p>
        ) : options.length ? (
          <ul className="uw-pick-list" aria-label="Complaints to add">
            {options.map((row) => (
              <li key={row.id}>
                <label className="ca-check">
                  <input
                    type="checkbox"
                    checked={chosen.includes(String(row.id))}
                    onChange={() => setChosen((current) => toggled(current, String(row.id)))}
                  />
                  <span className="ca-person">
                    <strong>
                      {displayId(row, "complaint_identifier")}
                      {row.version ? ` · version ${row.version}` : ""}
                    </strong>
                    <small>{safeText(row.description) ?? "No description"}</small>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        ) : (
          <p className="ac-muted">No other complaints of this product.</p>
        )}
        <label className="ca-field">
          Reason
          <textarea
            required
            rows={3}
            maxLength={DISPOSITION_REASON_MAX}
            value={reason}
            placeholder="At least 10 characters"
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        {problem && reason.trim() && <p className="uw-hint">{problem}</p>}
        <FormError error={submit.error} />
        <FormButtons
          busy={submit.busy}
          disabled={!!problem}
          label={
            chosen.length
              ? `Add ${chosen.length} ${chosen.length === 1 ? "complaint" : "complaints"}`
              : "Add complaints"
          }
          onClose={onClose}
        />
      </form>
    </Drawer>
  );
}

type Assignee = { id: string; business_id?: string | null; display_name?: string | null };

function InvestigationDrawer({
  signal,
  onClose,
  onDone,
}: {
  signal: SignalDetail;
  onClose: () => void;
  onDone: (kase: CreatedCase) => void;
}) {
  const complaints = listOf(signal.complaints) as SignalComplaint[];
  const [form, setForm] = useState<InvestigationForm>(() => ({
    question: defaultInvestigationQuestion(signal),
    complaintIds: complaints.map((row) => String(row.id)),
    assigneeUserId: "",
    alsoSignalIds: [],
    identifier: "",
  }));
  const [assignTo, setAssignTo] = useState<"queue" | "person">("queue");
  const submit = useSubmit();
  const siblings = useSiblingSignals(signal);
  const people = useResource<Assignee[]>(assignTo === "person" ? "/api/v1/investigation-assignees" : null);
  const missingPerson = assignTo === "person" && !form.assigneeUserId;
  const problem = investigationProblem(form) ?? (missingPerson ? "Choose the person to assign it to." : null);
  return (
    <Drawer title={title(signal, "Create investigation")} onClose={onClose}>
      <form
        className="ca-form"
        onSubmit={async (event) => {
          event.preventDefault();
          if (problem) return;
          const result = await submit.run<{ investigation?: CreatedCase | null }>(
            signalPath(signal.id, "create-investigation"),
            investigationBody({ ...form, assigneeUserId: assignTo === "person" ? form.assigneeUserId : "" }),
            "The investigation was not created.",
          );
          if (result !== null) onDone(result.data?.investigation ?? { id: "", business_id: null });
        }}
      >
        <label className="ca-field">
          Investigation question
          <textarea
            required
            rows={3}
            maxLength={QUESTION_MAX}
            value={form.question}
            onChange={(event) => setForm({ ...form, question: event.target.value })}
          />
        </label>
        <fieldset className="ca-fieldset uw-pick-fieldset">
          <legend>
            Complaints for the case · {form.complaintIds.length} of {complaints.length}
          </legend>
          <ul className="uw-pick-list" aria-label="Complaints for the investigation">
            {complaints.map((row) => (
              <li key={row.id}>
                <label className="ca-check">
                  <input
                    type="checkbox"
                    checked={form.complaintIds.includes(String(row.id))}
                    onChange={() => setForm({ ...form, complaintIds: toggled(form.complaintIds, String(row.id)) })}
                  />
                  <span className="ca-person">
                    <strong>{displayId(row, "complaint_identifier")}</strong>
                    <small>
                      {safeText(row.description) ?? "No description"}
                      {harmFlags(row).length ? ` · ${harmFlags(row).join(", ")}` : ""}
                    </small>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
        <div className="ca-chips" role="radiogroup" aria-label="Who works the investigation">
          {(["queue", "person"] as const).map((option) => (
            <button
              type="button"
              role="radio"
              key={option}
              aria-checked={assignTo === option}
              className={assignTo === option ? "selected" : ""}
              onClick={() => setAssignTo(option)}
            >
              {option === "queue" ? "Leave in the investigators' queue" : "Assign to a person"}
            </button>
          ))}
        </div>
        {assignTo === "person" && (
          <label className="ca-field">
            Investigator
            <select
              required
              value={form.assigneeUserId}
              onChange={(event) => setForm({ ...form, assigneeUserId: event.target.value })}
            >
              <option value="">{people.state === "loading" ? "Loading…" : "Choose a person"}</option>
              {(listOf(people.data) as Assignee[]).map((person) => (
                <option key={person.id} value={person.id}>
                  {safeText(person.display_name) ?? "Person"}
                  {safeText(person.business_id) ? ` (${person.business_id})` : ""}
                </option>
              ))}
            </select>
          </label>
        )}
        {siblings.rows.length > 0 && (
          <fieldset className="ca-fieldset uw-pick-fieldset">
            <legend>Also covers these trends of the same product (optional)</legend>
            <SignalChecklist
              rows={siblings.rows}
              chosen={form.alsoSignalIds}
              onToggle={(id) => setForm({ ...form, alsoSignalIds: toggled(form.alsoSignalIds, id) })}
              label="Other trends for the investigation"
            />
          </fieldset>
        )}
        <label className="ca-field">
          Your reference for the case (optional)
          <input
            maxLength={64}
            value={form.identifier}
            placeholder="The investigation number in your quality system, if it has one"
            onChange={(event) => setForm({ ...form, identifier: event.target.value })}
          />
        </label>
        {problem && form.question.trim() && <p className="uw-hint">{problem}</p>}
        <FormError error={submit.error} />
        <FormButtons busy={submit.busy} disabled={!!problem} label="Create investigation" onClose={onClose} />
      </form>
    </Drawer>
  );
}
