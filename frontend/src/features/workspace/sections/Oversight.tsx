import { PracticeApproval } from "./PracticeApproval";
import { useState } from "react";
import { DeadlineChip, SampleDates } from "../../../app/chips";
import { DecideAndSign, shortPrint } from "./common";
import { marketLabel } from "../../../app/labels";
import { WhyAssessed, otherMarketLine } from "./MarketAssessment";
import { AlertTriangle, CalendarClock, ChevronRight, Download, FileCheck2, Users } from "lucide-react";
import { Panel, ToneBadge } from "../../admin/console/charts";
import { Drawer, Table, errorText, formatDate, send, useResource, type Column } from "../../customer-admin/shared";
import { downloadFile } from "../../reports/download";
import { useCan, useDeadlineList, useOpenTarget, useTabParam, useWorkspace } from "../workspaceContext";
import {
  CHECK_TONES,
  EVENT_TONES,
  NO_FILTERS,
  OVERSIGHT,
  WEEKDAY_SHORT,
  eventPath,
  exportPath,
  openItemsText,
  oversightPath,
  readyProblem,
  stateTone,
  type EventRow,
  type EventView,
  type Filters,
  type Opens,
  type Oversight,
  type OversightItem,
  type OversightSettings,
} from "../oversight";
import { InlineError, Why } from "./boardParts";
import { TryDailyList } from "./Account";
import { AuditTrailReview } from "../../customer-admin/sections/Reviews";
import { ValueCentre } from "./ValueCentre";

const useOpen = useOpenTarget;

/**
 * The Quality and Regulatory Oversight view (T-G9), in Readiness: everything overdue or due soon across triage,
 * reporting deadlines, report obligations, replies due, guide approvals, tasks and CAPAs, with its owner and who it
 * escalated to; the events and whether each is ready to close (T-G28); who is away; the working calendar. Filters by
 * product, market and category; the list downloads as CSV for the monthly product review.
 */
export function OversightView({
  initialEvent = null,
  part = "all",
}: {
  initialEvent?: string | null;
  /** The new navigation (0.10.68): My work › Team overview shows the dated items alone; the events are Records ›
   * Decision records, the calendar is in Settings and each event is the complaint's own page. */
  part?: "all" | "items" | "events";
}) {
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const data = useResource<Oversight>(oversightPath(filters));
  // The event whose checklist is open is part of the address (Oversight?event=<complaint id>).
  const [event, setEvent] = useTabParam("event", "push", initialEvent);
  const view = data.data;
  // B6a G1: the audit trail review is signed by a Leader or Quality Reviewer (the server decides; this only shows it).
  const reviews = useCan("quality.review");
  // B6a P2: the Value Centre, for Leaders, quality reviewers and approvers (the server decides).
  const approves = useCan("regulatory.approve");
  const outcomes = reviews || approves;
  const go = useOpen();
  const { open } = useWorkspace();
  if (part === "events")
    return view ? (
      <EventsPanel
        events={view.events}
        onOpen={(id) => open("Complaint", `Summary?${new URLSearchParams({ ref: id })}`)}
      />
    ) : (
      <Panel eyebrow="Decision records" title="Every complaint MDARIX has worked on" source={data}>
        {null}
      </Panel>
    );
  return (
    <div className="uw-ov">
      <div className="uw-rd-home uw-ov-tiles" aria-label="At a glance" hidden={part !== "all"}>
        <Tile label="Overdue" value={view?.overdue} tone={view?.overdue ? "critical" : "good"} />
        <Tile label="Due soon" value={view?.due_soon} tone={view?.due_soon ? "warning" : "good"} />
        <Tile
          label="Events not ready to close"
          value={view?.event_counts.NOT_READY}
          tone={view?.event_counts.NOT_READY ? "warning" : "good"}
        />
        <Tile
          label="Decision records not filed"
          value={view?.event_counts.NOT_FILED}
          tone={view?.event_counts.NOT_FILED ? "warning" : "good"}
        />
        <Tile
          label="Closed in the QMS before ready"
          value={view?.event_counts.CLOSED_BEFORE_READY}
          tone={view?.event_counts.CLOSED_BEFORE_READY ? "critical" : "good"}
        />
      </div>
      {view?.incomplete?.length ? (
        <p className="uw-ov-warning tone-critical" role="alert">
          <AlertTriangle size={15} aria-hidden="true" /> This list is incomplete: {view.incomplete.join(", ")} could not
          be read. Some deadlines may be missing from this list.
        </p>
      ) : null}
      {part === "all" && view?.staffing && (
        <p className="uw-ov-warning tone-warning" role="status">
          <Users size={15} aria-hidden="true" /> {view.staffing}
        </p>
      )}
      {part === "all" &&
        view?.away.map((item) => (
          <p key={item.id} className="uw-rm-cover">
            <CalendarClock size={15} aria-hidden="true" /> <strong>{item.user_name}</strong> is away until{" "}
            {formatDate(item.ends_on)}; {item.backup_name} receives their reminders and escalations.
          </p>
        ))}
      <Panel
        eyebrow="Due and overdue"
        title={view ? `${view.items.length} of ${view.total} dated items` : "Dated items"}
        source={data}
        action={<ExportButton filters={filters} />}
      >
        {view && <FilterBar filters={filters} options={view.filters} onChange={setFilters} />}
        {view && (
          <Table
            rows={view.items}
            columns={itemColumns(go)}
            rowKey={(row) => row.key}
            caption="Dated items by due time"
            pageSize={25}
            pageNoun="items"
            empty={{
              title: "Nothing overdue or due soon",
              detail:
                filters.show === "all"
                  ? "No dated item matches these filters."
                  : "Choose Show: Every dated item to see later ones.",
            }}
          />
        )}
      </Panel>
      {part === "all" && view && <EventsPanel events={view.events} onOpen={setEvent} />}
      {part === "all" && view && <CalendarPanel settings={view.settings} onSaved={data.reload} />}
      {part === "all" && reviews && <AuditTrailReview />}
      {/* The new navigation's Team overview (part "items") is where a manager looks: the numbers show there too. */}
      {outcomes && <ValueCentre />}
      {event && <EventDrawer complaintId={event} onClose={() => setEvent(null)} onChanged={data.reload} />}
    </div>
  );
}

function Tile({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | undefined;
  tone: "good" | "warning" | "critical";
}) {
  return (
    <div className={`uw-rd-tile tone-${tone}`}>
      <span className="uw-rd-tile-head">{label}</span>
      <strong className="uw-rd-value">{value ?? "…"}</strong>
    </div>
  );
}

function itemColumns(go: (opens: Opens) => void): Column<OversightItem>[] {
  return [
    {
      key: "state",
      label: "State",
      render: (row) => <ToneBadge tone={stateTone(row.state)} label={row.state_label} />,
      sortValue: (row) => row.hours_left,
    },
    { key: "category", label: "Kind", render: (row) => row.category_label },
    {
      key: "title",
      label: "Item",
      render: (row) => (
        <span>
          <strong>{row.ref}</strong> {row.title}
        </span>
      ),
    },
    { key: "product", label: "Product", render: (row) => row.product ?? "—" },
    { key: "market", label: "Market", render: (row) => marketLabel(row.market) },
    {
      key: "owner",
      label: "Owner",
      render: (row) => (
        <span>
          {row.owner ?? (row.queue ? `${row.queue} (no one yet)` : "—")}
          {row.away && <small className="ac-muted"> away; {row.away.backup} covers</small>}
        </span>
      ),
    },
    {
      key: "due_at",
      label: "Due",
      render: (row) => (
        // The time left is the key fact, so it leads as the deadline chip; the end follows (V4).
        <span className="uw-due-cell">
          <DeadlineChip item={row} />
          <span className="ac-muted">{row.due_label ?? formatDate(row.due_at)}</span>
        </span>
      ),
    },
    {
      key: "escalated_to",
      label: "Escalated to",
      render: (row) => (row.escalated_to.length ? row.escalated_to.join(", ") : row.alerts ? "—" : "Your QMS"),
    },
    {
      key: "open",
      label: "",
      render: (row) =>
        row.opens && (
          <button type="button" className="ac-secondary" onClick={() => go(row.opens)} aria-label={`Open ${row.ref}`}>
            Open <ChevronRight size={14} aria-hidden="true" />
          </button>
        ),
    },
  ];
}

function FilterBar({
  filters,
  options,
  onChange,
}: {
  filters: Filters;
  options: Oversight["filters"];
  onChange: (filters: Filters) => void;
}) {
  return (
    <div className="ca-form-grid uw-ov-filters" role="group" aria-label="Filters">
      <label className="ca-field">
        Product
        <select value={filters.product} onChange={(e) => onChange({ ...filters, product: e.target.value })}>
          <option value="">Every product</option>
          {options.products.map((name) => (
            <option key={name}>{name}</option>
          ))}
        </select>
      </label>
      <label className="ca-field">
        Market
        <select value={filters.market} onChange={(e) => onChange({ ...filters, market: e.target.value })}>
          <option value="">Every market</option>
          {options.markets.map((code) => (
            <option key={code} value={code}>
              {marketLabel(code)}
            </option>
          ))}
        </select>
      </label>
      <label className="ca-field">
        Kind
        <select value={filters.category} onChange={(e) => onChange({ ...filters, category: e.target.value })}>
          <option value="">Every kind</option>
          {options.categories.map((item) => (
            <option key={item.code} value={item.code}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <label className="ca-field">
        Show
        <select
          value={filters.show}
          onChange={(e) => onChange({ ...filters, show: e.target.value === "all" ? "all" : "attention" })}
        >
          <option value="attention">Overdue and due soon</option>
          <option value="all">Every dated item</option>
        </select>
      </label>
    </div>
  );
}

export function ExportButton({ filters }: { filters: Filters }) {
  const canExport = useCan("data.export");
  const deadlines = useDeadlineList();
  const [error, setError] = useState("");
  if (!canExport) return null;
  const get = (path: string, name: string) =>
    void downloadFile(path, { fallbackName: name }).catch((reason) =>
      setError(errorText(reason, "The list could not be downloaded.")),
    );
  return (
    <>
      <button type="button" className="ac-secondary" onClick={() => get(exportPath(filters), "mdarix-oversight.csv")}>
        <Download size={15} aria-hidden="true" /> CSV
      </button>
      {deadlines && (
        <>
          {/* B6a G18a: the open reporting deadlines, an offline copy to keep for an outage. */}
          <button
            type="button"
            className="ac-secondary"
            title="Open reporting deadlines: your copy if MDARIX is unavailable"
            onClick={() => get(`${OVERSIGHT}/deadlines.pdf`, "mdarix-deadlines.pdf")}
          >
            <Download size={15} aria-hidden="true" /> Deadlines PDF
          </button>
          <button
            type="button"
            className="ac-secondary"
            onClick={() => get(`${OVERSIGHT}/deadlines.csv`, "mdarix-deadlines.csv")}
          >
            <Download size={15} aria-hidden="true" /> Deadlines CSV
          </button>
          <TryDailyList />
        </>
      )}
      <InlineError text={error} />
    </>
  );
}

function EventsPanel({ events, onOpen }: { events: EventRow[]; onOpen: (id: string) => void }) {
  const columns: Column<EventRow>[] = [
    {
      key: "state",
      label: "Closure",
      render: (row) => <ToneBadge tone={EVENT_TONES[row.state]} label={row.state_label} />,
    },
    { key: "ref", label: "Event", render: (row) => <strong>{row.ref}</strong> },
    { key: "product", label: "Product", render: (row) => row.product ?? "—" },
    { key: "stage", label: "Stage", render: (row) => row.stage },
    { key: "owner_name", label: "Event owner", render: (row) => row.owner_name ?? "Not named" },
    {
      key: "next",
      label: "Open items",
      render: (row) => openItemsText(row),
      sortValue: (row) => row.blocked,
    },
    {
      key: "open",
      label: "",
      render: (row) => (
        <button
          type="button"
          className="ac-secondary"
          onClick={() => onOpen(row.complaint_id)}
          aria-label={`Open ${row.ref}`}
        >
          Checklist <ChevronRight size={14} aria-hidden="true" />
        </button>
      ),
    },
  ];
  return (
    <Panel eyebrow="Events" title="Ready to close in the QMS?">
      <p className="ac-muted">
        Every complaint MDARIX has worked on, with its owner, its stage and what still blocks its closure. Your QMS
        closes the complaint; MDARIX shows when every decision on it is signed.
      </p>
      <Table
        rows={events}
        columns={columns}
        rowKey={(row) => row.complaint_id}
        caption="Events and their closure readiness"
        pageSize={15}
        pageNoun="events"
        empty={{ title: "No events yet", detail: "Events appear once a complaint is triaged, assessed or disposed." }}
      />
    </Panel>
  );
}

/** One event (T-G28): its summary, stage line, checklist, the signed "ready to close", and its decision record. */
export function EventDrawer({
  complaintId,
  onClose,
  onChanged,
}: {
  complaintId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const resource = useResource<EventView>(eventPath(complaintId));
  const [shown, setShown] = useState<EventView | null>(null);
  const view = shown && shown.event.complaint_id === complaintId ? shown : resource.data;
  const go = useOpen();
  if (!view)
    return (
      <Drawer title="Event" onClose={onClose}>
        <p className="ac-muted">
          {resource.error ? errorText(resource.error, "The event could not be read.") : "Reading…"}
        </p>
      </Drawer>
    );
  const changed = (next: EventView) => {
    setShown(next);
    onChanged();
  };
  const { event, summary } = view;
  return (
    <Drawer title={`Event ${event.ref}`} onClose={onClose}>
      <section className="ca-drawer-section" aria-label="Event summary">
        <div className="uw-cr-head">
          <ToneBadge tone={EVENT_TONES[view.state]} label={view.state_label} />
        </div>
        <dl className="uw-ov-summary">
          <dt>Product</dt>
          <dd>{event.product ?? "—"}</dd>
          <dt>Market</dt>
          <dd>{marketLabel(event.market)}</dd>
          <dt>Awareness</dt>
          <dd>{formatDate(event.awareness_at)}</dd>
          <dt>Nearest deadline</dt>
          <dd>
            {summary.nearest_deadline
              ? `${summary.nearest_deadline.title}, ${formatDate(summary.nearest_deadline.due_at)}`
              : "None"}
          </dd>
          <dt>Unresolved questions</dt>
          <dd>{summary.open_requests ? `${summary.open_requests} open` : "None"}</dd>
          <dt>Next action</dt>
          <dd>
            {summary.next_action ? (
              <button type="button" className="ac-link" onClick={() => go(summary.next_action!.opens)}>
                {summary.next_action.label}
              </button>
            ) : (
              "None: the checklist is clear"
            )}
          </dd>
        </dl>
        <OwnerPicker view={view} onChanged={changed} />
      </section>
      <section className="ca-drawer-section" aria-label="Stage">
        <h3>Stage</h3>
        <ol className="uw-ov-stages">
          {view.stages.map((stage) => (
            <li key={stage.code} className={`stage-${stage.state.toLowerCase()}`}>
              {stage.label}
              {stage.state === "NOT_NEEDED" && <span className="ac-muted">: not needed</span>}
            </li>
          ))}
        </ol>
        <p className="ac-muted">A summary, not a gate: reporting, investigation and containment can run at once.</p>
      </section>
      <section className="ca-drawer-section" aria-label="Closure checklist">
        <h3>Closure checklist</h3>
        <ul className="uw-ov-checks">
          {view.checklist.map((item) => (
            <li key={item.code}>
              <ToneBadge tone={CHECK_TONES[item.result]} label={item.result_label} />
              <span>
                <strong>{item.label}.</strong> {item.detail}
              </span>
              {item.opens && item.result !== "PASS" && (
                <button type="button" className="ac-link" onClick={() => go(item.opens)}>
                  {item.action ?? "Open"} <ChevronRight size={13} aria-hidden="true" />
                </button>
              )}
            </li>
          ))}
        </ul>
        {view.changed_since_signed && (
          <p className="tone-warning">
            Something changed since "ready to close" was signed: read the checklist and sign again.
          </p>
        )}
      </section>
      <ReadyForm view={view} onChanged={changed} />
      <DecisionRecord view={view} onChanged={changed} />
      <p className="ac-note">{view.never_closes}</p>
    </Drawer>
  );
}

function useRun(onChanged: (view: EventView) => void, failure: string) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (path: string, method: "POST" | "PUT", body?: unknown) => {
    setBusy(true);
    setError("");
    try {
      onChanged(await send<EventView>(path, method, body));
      return true;
    } catch (reason) {
      setError(errorText(reason, failure));
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}

export function OwnerPicker({ view, onChanged }: { view: EventView; onChanged: (view: EventView) => void }) {
  const triage = useCan("signal.triage");
  const work = useCan("investigation.work");
  const quality = useCan("quality.review");
  const canWrite = triage || work || quality;
  const [owner, setOwner] = useState(view.event.owner_id ?? "");
  const action = useRun(onChanged, "The event owner was not changed.");
  return (
    <div className="uw-ov-owner">
      <p>
        Event owner: <strong>{view.event.owner_name ?? "not named yet"}</strong>
        {view.you_are_owner ? " (you)" : ""}
        {!view.event.owner_named && view.event.owner_name ? " (from the triage record)" : ""}
      </p>
      {canWrite && (
        <div className="ca-action-row">
          <label className="ca-field">
            Name the event owner
            <select value={owner} onChange={(e) => setOwner(e.target.value)}>
              <option value="">Choose a person</option>
              {view.people.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="ac-secondary"
            disabled={action.busy || !owner || owner === view.event.owner_id}
            aria-describedby="owner-why"
            onClick={() => void action.run(`${eventPath(view.event.complaint_id)}/owner`, "PUT", { owner_id: owner })}
          >
            Save owner
          </button>
          <Why
            id="owner-why"
            text={
              !owner ? "Choose a person first." : owner === view.event.owner_id ? "They are the owner already." : null
            }
          />
        </div>
      )}
      <InlineError text={action.error} />
    </div>
  );
}

export function ReadyForm({ view, onChanged }: { view: EventView; onChanged: (view: EventView) => void }) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [reason, setReason] = useState("");
  const action = useRun(onChanged, "Ready to close was not signed.");
  const closed = view.state === "CLOSED" || view.state === "CLOSED_BEFORE_READY";
  if (closed && !view.ready) return null;
  const problem = readyProblem(view, reason);
  const signedNow = view.ready && !view.changed_since_signed;
  return (
    <section className="ca-drawer-section" aria-label="Ready to close">
      <h3>Ready to close in the QMS</h3>
      {view.ready && (
        <p className={view.ready.state === "READY" ? "tone-good" : "tone-warning"}>
          Signed by {view.ready.signed_by} {formatDate(view.ready.signed_at)} (version {view.ready.version})
          {view.ready.state === "READY" ? ": checklist clear." : `, with items open: ${view.ready.reason}`}
          <SampleDates sample={view.event.sample} />
        </p>
      )}
      {!signedNow && (
        <form
          className="uw-rp-approval"
          aria-label="Sign ready to close"
          onSubmit={(e) => {
            e.preventDefault();
            if (!problem)
              void action.run(`${eventPath(view.event.complaint_id)}/ready`, "POST", {
                password,
                mfa_code: code || null,
                reason,
              });
          }}
        >
          <p>
            {view.blocked
              ? `${view.blocked} ${view.blocked === 1 ? "item is" : "items are"} still open. Resolve them first, or sign with the reason the event can close anyway.`
              : "Every MDARIX decision on this event is signed. As its owner, sign that it is ready to close in your QMS."}
          </p>
          {view.blocked > 0 && (
            <label className="ca-field">
              Why it can close with these items open
              <textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
          )}
          <div className="ca-form-grid">
            <DecideAndSign
              signs={`${view.event.ref} is ready to close in your QMS${view.blocked ? `, with ${view.blocked} ${view.blocked === 1 ? "item" : "items"} open` : ""}.`}
              restsOn={[
                `The checklist as it stands: ${view.checklist.filter((item) => item.result === "PASS").length} done, ${view.blocked} open.`,
                (view.work?.markets ?? []).length ? `Markets: ${(view.work?.markets ?? []).join(", ")}.` : null,
                `Decision record version ${view.decision_record.version}, fingerprint ${shortPrint(view.decision_record.sha256)}.`,
              ]}
            />
            <label className="ca-field">
              Your password
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <label className="ca-field">
              Authenticator code
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
            </label>
          </div>
          <div className="ca-action-row">
            <button
              type="submit"
              className="ac-primary"
              disabled={action.busy || !password || !!problem}
              aria-describedby="ready-why"
            >
              {action.busy ? "Signing…" : "Sign ready to close"}
            </button>
            <Why id="ready-why" text={problem || (!password && "Enter your password to sign.")} />
          </div>
        </form>
      )}
      <InlineError text={action.error} />
    </section>
  );
}

export function DecisionRecord({ view, onChanged }: { view: EventView; onChanged: (view: EventView) => void }) {
  const canExport = useCan("data.export");
  const [reference, setReference] = useState("");
  const [error, setError] = useState("");
  const action = useRun(onChanged, "The QMS reference was not recorded.");
  const record = view.decision_record;
  return (
    <section className="ca-drawer-section uw-receipt" aria-label="Event decision record">
      {/* Wow screen 6: the decision record reads as a receipt: who signed what, when, and its fingerprint. */}
      <header className="uw-receipt-head">
        <h3>Decision record</h3>
        <span>
          {view.event.ref} · version {record.version}
        </span>
      </header>
      {view.record_people && (
        // Separation of duties, shown honestly (0.10.71, A6).
        <dl className="uw-receipt-people">
          <div>
            <dt>Prepared by</dt>
            <dd>{view.record_people.prepared_by.join(", ") || "Nobody yet"}</dd>
          </div>
          <div>
            <dt>May approve</dt>
            <dd>{view.record_people.may_approve.join(", ") || "Nobody holds the role yet"}</dd>
          </div>
          <div>
            <dt>Approved by</dt>
            <dd>
              {view.record_people.approved_by.join(", ") || "Nobody yet"}
              <PracticeApproval shown={!!view.record_people.practice_note} />
            </dd>
          </div>
        </dl>
      )}
      {record.entries.length ? (
        <ol className="uw-ov-record uw-receipt-lines">
          {record.entries.map((entry, index) => (
            <li key={`${entry.kind}-${index}`}>
              <span className="uw-receipt-line">
                <strong>{entry.kind}</strong>
                <span>{entry.summary}</span>
              </span>
              {entry.reason && <span className="ac-muted">Reason: {entry.reason}</span>}
              {otherMarketLine(entry.kind, view.event.market) && <WhyAssessed />}
              <small>
                Signed by {entry.signer}, {formatDate(entry.signed_at)}. {entry.meaning}
                <SampleDates sample={view.event.sample} />
              </small>
            </li>
          ))}
        </ol>
      ) : (
        <p className="ac-muted">No decision on this event is signed yet.</p>
      )}
      <p className="uw-receipt-total">
        <span>
          {record.entries.length} signed {record.entries.length === 1 ? "decision" : "decisions"}
        </span>
        <span>
          Fingerprint (SHA-256) <code>{record.sha256.slice(0, 16)}…</code>
        </span>
      </p>
      <div className="ca-action-row">
        {canExport && (
          <button
            type="button"
            className="ac-secondary"
            onClick={() =>
              void downloadFile(`${eventPath(view.event.complaint_id)}/decision-record.pdf`, {
                fallbackName: `mdarix-event-record-${view.event.ref}.pdf`,
              }).catch((reason) => setError(errorText(reason, "The record could not be downloaded.")))
            }
          >
            <FileCheck2 size={15} aria-hidden="true" /> Decision record (PDF)
          </button>
        )}
      </div>
      {record.filed ? (
        <p className="tone-good">
          Filed in your QMS as <strong>{record.filed.reference}</strong> by {record.filed.by}{" "}
          {formatDate(record.filed.at)}.
        </p>
      ) : (
        view.ready && (
          <div className="ca-action-row">
            <label className="ca-field">
              QMS reference where you filed it
              <input value={reference} maxLength={120} onChange={(e) => setReference(e.target.value)} />
            </label>
            <button
              type="button"
              className="ac-secondary"
              disabled={action.busy || reference.trim().length < 3}
              aria-describedby="filing-why"
              onClick={() => void action.run(`${eventPath(view.event.complaint_id)}/filing`, "PUT", { reference })}
            >
              Record the filing
            </button>
            <Why
              id="filing-why"
              text={reference.trim().length < 3 && "Enter the QMS reference (3 characters or more) first."}
            />
          </div>
        )
      )}
      <InlineError text={error || action.error} />
    </section>
  );
}

/** The working calendar and the simple escalation rule; quality review or regulatory approval changes them. */
export function CalendarPanel({ settings, onSaved }: { settings: OversightSettings; onSaved: () => void }) {
  const quality = useCan("quality.review");
  const approve = useCan("regulatory.approve");
  const canSet = quality || approve;
  const full = useResource<OversightSettings>(canSet ? `${OVERSIGHT}/settings` : null);
  const [draft, setDraft] = useState<OversightSettings | null>(null);
  const [holiday, setHoliday] = useState({ date: "", name: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [why, setWhy] = useState("");
  const shown = draft ?? full.data ?? settings;
  const edit = (next: Partial<OversightSettings>) => setDraft({ ...shown, ...next });
  const save = async () => {
    setBusy(true);
    setError("");
    setSaved("");
    try {
      const body = await send<OversightSettings>(`${OVERSIGHT}/settings`, "PUT", {
        time_zone: shown.time_zone,
        work_days: shown.work_days,
        holidays: shown.holidays,
        reminder_hours: shown.reminder_hours,
        escalation_role: shown.escalation_role,
        reason: why.trim(),
      });
      setDraft(body);
      setWhy("");
      setSaved("Saved. Due times from now on count on this calendar.");
      onSaved();
    } catch (reason) {
      setError(errorText(reason, "The calendar was not saved."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel
      eyebrow="Working calendar and escalation"
      title={`${shown.time_zone}, ${shown.work_days.map((d) => WEEKDAY_SHORT[d]).join(" ")}`}
    >
      <p className="ac-muted">
        Your own due times (a follow-up at the end of the next working day, the one-working-hour rule of the
        communications log) count on this calendar. An authority's legal deadline keeps its own counting rule.
      </p>
      {!canSet ? (
        <p>
          Reminders go {shown.reminder_hours} hours before an item is due; an overdue item escalates to its backup and
          to the {shown.escalation_role_label}. {shown.holidays.length} holidays are set.
        </p>
      ) : (
        <div className="uw-ov-calendar">
          <div className="ca-form-grid">
            <label className="ca-field">
              Time zone
              <select value={shown.time_zone} onChange={(e) => edit({ time_zone: e.target.value })}>
                {(shown.zones ?? [shown.time_zone]).map((zone) => (
                  <option key={zone}>{zone}</option>
                ))}
              </select>
            </label>
            <label className="ca-field">
              Remind this many hours before
              <input
                type="number"
                min={1}
                max={168}
                value={shown.reminder_hours}
                onChange={(e) => edit({ reminder_hours: Number(e.target.value) })}
              />
            </label>
            <label className="ca-field">
              Overdue items escalate to
              <select value={shown.escalation_role} onChange={(e) => edit({ escalation_role: e.target.value })}>
                {(shown.roles ?? []).map((role) => (
                  <option key={role.code} value={role.code}>
                    {role.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <fieldset className="uw-ov-days">
            <legend>Working days</legend>
            {WEEKDAY_SHORT.map((name, day) => (
              <label key={name} className="ca-check">
                <input
                  type="checkbox"
                  checked={shown.work_days.includes(day)}
                  onChange={(e) =>
                    edit({
                      work_days: e.target.checked
                        ? [...shown.work_days, day].sort()
                        : shown.work_days.filter((value) => value !== day),
                    })
                  }
                />{" "}
                {name}
              </label>
            ))}
          </fieldset>
          <fieldset className="uw-ov-holidays">
            <legend>Holidays</legend>
            {shown.holidays.length ? (
              <ul>
                {shown.holidays.map((item) => (
                  <li key={item.date}>
                    {formatDate(item.date)} {item.name}{" "}
                    <button
                      type="button"
                      className="ac-link"
                      onClick={() => edit({ holidays: shown.holidays.filter((value) => value.date !== item.date) })}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="ac-muted">No holidays set.</p>
            )}
            <div className="ca-action-row">
              <label className="ca-field">
                Date
                <input
                  type="date"
                  value={holiday.date}
                  onChange={(e) => setHoliday({ ...holiday, date: e.target.value })}
                />
              </label>
              <label className="ca-field">
                Name
                <input
                  value={holiday.name}
                  maxLength={80}
                  onChange={(e) => setHoliday({ ...holiday, name: e.target.value })}
                />
              </label>
              <button
                type="button"
                className="ac-secondary"
                disabled={!holiday.date || shown.holidays.some((item) => item.date === holiday.date)}
                aria-describedby="holiday-why"
                onClick={() => {
                  edit({ holidays: [...shown.holidays, holiday].sort((a, b) => a.date.localeCompare(b.date)) });
                  setHoliday({ date: "", name: "" });
                }}
              >
                Add holiday
              </button>
              <Why
                id="holiday-why"
                text={
                  !holiday.date
                    ? "Choose the date first."
                    : shown.holidays.some((item) => item.date === holiday.date) && "That day is a holiday already."
                }
              />
            </div>
          </fieldset>
          <label className="ca-field">
            Why it changes (kept in the audit trail)
            <input value={why} maxLength={2000} onChange={(e) => setWhy(e.target.value)} />
          </label>
          <div className="ca-action-row">
            <button
              type="button"
              className="ac-primary"
              disabled={busy || !draft || !why.trim()}
              aria-describedby="calendar-why"
              onClick={() => void save()}
            >
              {busy ? "Saving…" : "Save the calendar"}
            </button>
            <Why
              id="calendar-why"
              text={(!draft && "Change something first.") || (!why.trim() && "Say why it changes first.")}
            />
            {saved && <small className="ac-muted">{saved}</small>}
          </div>
          <InlineError text={error} />
        </div>
      )}
    </Panel>
  );
}
