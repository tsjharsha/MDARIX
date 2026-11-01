import { useContext, useState } from "react";
import { Mail, MessagesSquare, PhoneCall, Plus, Send } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { Drawer, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { nowLocal } from "../authorityReports";
import { WorkspaceContext, useCan } from "../workspaceContext";
import { countOf } from "./common";
import { Hero, InlineError } from "./boardParts";
import {
  COMMUNICATIONS,
  REASON_MIN,
  attemptsText,
  communicationsTab,
  dueText,
  entryBody,
  entryProblem,
  evidenceLines,
  isRequest,
  isoOf,
  s4Text,
  statusTone,
  type CommunicationList,
  type Entry,
  type EntryForm,
  type Labels,
  type Party,
} from "../communications";

function useCanRecord() {
  const triage = useCan("signal.triage");
  const work = useCan("investigation.work");
  const request = useCan("evidence.request");
  const quality = useCan("quality.review");
  const review = useCan("regulatory.review");
  const approve = useCan("regulatory.approve");
  return triage || work || request || quality || review || approve;
}

/**
 * Complaints › Communications: every question to a reporter, distributor, hospital or service partner, with its
 * owner, reply due date and attempts, and every answer. On one complaint ("Communications?complaint=<id>") it is that
 * complaint's log. MDARIX sends nothing: people send from their own mail and record it here.
 */
export function Communications({ complaintId }: { complaintId?: string | null }) {
  const path = complaintId ? `${COMMUNICATIONS}?complaint_id=${complaintId}` : COMMUNICATIONS;
  const list = useResource<CommunicationList>(path);
  const [open, setOpen] = useState<string | null>(null);
  const canRecord = useCanRecord();
  const workspace = useContext(WorkspaceContext);
  const data = list.data;
  const counts = data?.counts;
  return (
    <div className="ac-overview">
      <Hero
        tone={counts?.overdue || counts?.unresolved ? "critical" : counts?.open ? "warning" : "good"}
        icon={<MessagesSquare size={28} />}
        eyebrow={data?.complaint ? `Communications · ${data.complaint.ref}` : "Communications"}
        title={
          counts
            ? counts.open
              ? `${countOf(counts.open, "open request")}, ${counts.overdue} overdue`
              : counts.unresolved
                ? `${countOf(counts.unresolved, "request")} unresolved after attempts`
                : "No request waits for a reply"
            : "Reading the log…"
        }
        detail="Every question to a reporter, distributor, hospital or service partner, with its owner, reply due date and every attempt. Send from your own mail or phone, then record it here."
      />
      {data && (
        <p className="uw-ma-starter" role="note">
          <Send size={15} aria-hidden="true" /> {data.never_sends}
        </p>
      )}
      <Panel
        eyebrow={data?.complaint ? data.complaint.identifier : "The log"}
        title={data?.complaint ? "This complaint's messages" : "Overdue and open first"}
        source={list}
      >
        {data?.complaint && <q className="uw-cr-text">{data.complaint.description}</q>}
        {data && (
          <p className="ac-muted">
            {s4Text(data.s4)} {counts?.unresolved ?? 0} unresolved after attempts. A request moves on after{" "}
            {data.attempts_limit} unanswered attempts.
          </p>
        )}
        {data?.items.length ? (
          <ul className="uw-cr-list">
            {data.items.map((entry) => (
              <li key={entry.id} className="uw-cr-card">
                <span className={`uw-cr-rail tone-${statusTone(entry)}`} aria-hidden="true" />
                <div className="uw-cr-body">
                  <div className="uw-cr-head">
                    <strong className="uw-cr-id">{entry.party?.name ?? "A party"}</strong>
                    <span className="uw-cr-meta">
                      {entry.party?.type_label} · {entry.direction_label.toLowerCase()} ·{" "}
                      {entry.purpose_label.toLowerCase()}
                      {entry.complaint_ref ? ` · ${entry.complaint_ref}` : ""}
                      {entry.intake_reference ? ` · ${entry.intake_reference}` : ""}
                      {entry.sample ? " · sample" : ""}
                    </span>
                    <ToneBadge
                      tone={statusTone(entry)}
                      label={entry.overdue ? `${entry.status_label}, overdue` : entry.status_label}
                    />
                  </div>
                  <p className="uw-cr-text">{entry.subject}</p>
                  <p className="uw-cr-meta">
                    {formatDate(entry.occurred_at)} · {entry.channel_label}
                    {entry.is_request ? ` · ${attemptsText(entry)}` : ""}
                    {dueText(entry) ? ` · ${dueText(entry)}` : ""}
                    {entry.owner ? ` · owner ${entry.owner}` : ""}
                    {entry.origin?.label ? ` · ${entry.origin.label}` : ""}
                  </p>
                  <div className="ca-action-row">
                    <button type="button" className="ac-secondary" onClick={() => setOpen(entry.id)}>
                      Open
                    </button>
                    {!complaintId && entry.complaint_id && (
                      <button
                        type="button"
                        className="ac-link"
                        onClick={() => workspace?.open("Complaints", communicationsTab(entry.complaint_id))}
                      >
                        This complaint's log
                      </button>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <Empty
            title="Nothing recorded yet"
            detail="A question you send, an answer you receive, and every attempt in between are recorded here."
          />
        )}
      </Panel>
      {data && canRecord && complaintId && (
        <RecordEntry complaintId={complaintId} data={data} onDone={(id) => (list.reload(), setOpen(id))} />
      )}
      {data && canRecord && !complaintId && (
        <p className="ac-muted">
          To record a message, open a complaint's log (from its card here, its market assessment or its reports).
        </p>
      )}
      {data && <Parties data={data} complaintId={complaintId ?? null} canRecord={canRecord} onDone={list.reload} />}
      {data && <AttemptsSetting value={data.attempts_limit} onDone={list.reload} />}
      {open && (
        <EntryDrawer
          id={open}
          labels={data?.labels}
          onClose={() => {
            setOpen(null);
            list.reload();
          }}
        />
      )}
    </div>
  );
}

const EMPTY: EntryForm = {
  partyId: "",
  direction: "SENT",
  purpose: "INFORMATION_REQUEST",
  subject: "",
  channel: "EMAIL",
  occurredAt: "",
  ownerId: "",
  replyDueOn: "",
  note: "",
  evidence: "",
  qmsReference: "",
};

function Options({ values }: { values: Record<string, string> }) {
  return (
    <>
      {Object.entries(values).map(([code, label]) => (
        <option key={code} value={code}>
          {label}
        </option>
      ))}
    </>
  );
}

function RecordEntry({
  complaintId,
  data,
  onDone,
}: {
  complaintId: string;
  data: CommunicationList;
  onDone: (id: string) => void;
}) {
  const [form, setForm] = useState<EntryForm>(() => ({ ...EMPTY, occurredAt: nowLocal() }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (patch: Partial<EntryForm>) => setForm((current) => ({ ...current, ...patch }));
  const problem = entryProblem(form);
  return (
    <Panel eyebrow="Record" title="Record a message sent or received">
      <form
        className="ca-form-grid uw-cm-form"
        aria-label="Record a message"
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          setError("");
          try {
            const made = await send<Entry>(COMMUNICATIONS, "POST", entryBody(form, complaintId));
            setForm({ ...EMPTY, occurredAt: nowLocal() });
            onDone(made.id);
          } catch (reason) {
            setError(errorText(reason, "The message was not recorded."));
          } finally {
            setBusy(false);
          }
        }}
      >
        <label className="ca-field">
          Party
          <select value={form.partyId} onChange={(event) => set({ partyId: event.target.value })}>
            <option value="">Choose…</option>
            {data.parties.map((party) => (
              <option key={party.id} value={party.id}>
                {party.type_label}: {party.name}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          Direction
          <select
            value={form.direction}
            onChange={(event) => set({ direction: event.target.value as EntryForm["direction"] })}
          >
            <Options values={data.labels.directions} />
          </select>
        </label>
        <label className="ca-field">
          Purpose
          <select value={form.purpose} onChange={(event) => set({ purpose: event.target.value })}>
            <Options values={data.labels.purposes} />
          </select>
        </label>
        <label className="ca-field">
          How
          <select value={form.channel} onChange={(event) => set({ channel: event.target.value })}>
            <Options values={data.labels.channels} />
          </select>
        </label>
        <label className="ca-field ca-wide">
          What was asked or said
          <input value={form.subject} onChange={(event) => set({ subject: event.target.value })} />
        </label>
        <label className="ca-field">
          {form.direction === "SENT" ? "Sent at" : "Received at"}
          <input
            type="datetime-local"
            value={form.occurredAt}
            onChange={(event) => set({ occurredAt: event.target.value })}
          />
        </label>
        {isRequest(form) && (
          <>
            <label className="ca-field">
              Owner
              <select value={form.ownerId} onChange={(event) => set({ ownerId: event.target.value })}>
                <option value="">Choose…</option>
                {data.colleagues.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="ca-field">
              Reply due
              <input
                type="date"
                value={form.replyDueOn}
                onChange={(event) => set({ replyDueOn: event.target.value })}
              />
            </label>
          </>
        )}
        <label className="ca-field ca-wide">
          Evidence (one reference per line)
          <textarea rows={2} value={form.evidence} onChange={(event) => set({ evidence: event.target.value })} />
        </label>
        <label className="ca-field">
          QMS record ID (formal response, field safety notice)
          <input value={form.qmsReference} onChange={(event) => set({ qmsReference: event.target.value })} />
        </label>
        <label className="ca-field ca-wide">
          Note
          <textarea rows={2} value={form.note} onChange={(event) => set({ note: event.target.value })} />
        </label>
        <div className="ca-action-row ca-wide">
          <button type="submit" className="ac-primary" disabled={busy || !!problem}>
            {busy ? "Recording…" : "Record it"}
          </button>
        </div>
        <InlineError text={problem && form.subject ? problem : error} />
      </form>
    </Panel>
  );
}

function Parties({
  data,
  complaintId,
  canRecord,
  onDone,
}: {
  data: CommunicationList;
  complaintId: string | null;
  canRecord: boolean;
  onDone: () => void;
}) {
  const [adding, setAdding] = useState(false);
  return (
    <Panel eyebrow="Parties" title="Reporters, distributors, hospitals and service partners">
      <p className="ac-muted">
        Each party may have a primary and a second contact. After {data.attempts_limit} unanswered attempts a request
        moves to the second contact where one is recorded, then shows "unresolved after attempts".
      </p>
      <ul className="uw-cm-parties">
        {data.parties.map((party) => (
          <li key={party.id}>
            <strong>{party.name}</strong> <span className="uw-cr-meta">{party.type_label}</span>
            <span className="uw-cr-meta">
              Primary: {contactText(party.primary)} · Second:{" "}
              {party.second ? contactText(party.second) : "none recorded"}
            </span>
          </li>
        ))}
      </ul>
      {canRecord &&
        (adding ? (
          <PartyForm data={data} complaintId={complaintId} onDone={() => (setAdding(false), onDone())} />
        ) : (
          <button type="button" className="ac-secondary" onClick={() => setAdding(true)}>
            <Plus size={15} aria-hidden="true" /> Add a party
          </button>
        ))}
    </Panel>
  );
}

const contactText = (contact: Party["primary"]) =>
  [contact.name, contact.details].filter(Boolean).join(", ") || "not recorded";

function PartyForm({
  data,
  complaintId,
  onDone,
}: {
  data: CommunicationList;
  complaintId: string | null;
  onDone: () => void;
}) {
  const [form, setForm] = useState({ type: "DISTRIBUTOR", name: "", p: "", pd: "", s: "", sd: "" });
  const [error, setError] = useState("");
  const set = (patch: Partial<typeof form>) => setForm((current) => ({ ...current, ...patch }));
  return (
    <form
      className="ca-form-grid"
      aria-label="Add a party"
      onSubmit={async (event) => {
        event.preventDefault();
        setError("");
        try {
          await send(`${COMMUNICATIONS}/parties`, "POST", {
            type: form.type,
            name: form.name,
            complaint_id: form.type === "REPORTER" ? complaintId : null,
            primary: { name: form.p, details: form.pd },
            second: form.s || form.sd ? { name: form.s, details: form.sd } : null,
          });
          onDone();
        } catch (reason) {
          setError(errorText(reason, "The party was not added."));
        }
      }}
    >
      <label className="ca-field">
        Type
        <select value={form.type} onChange={(event) => set({ type: event.target.value })}>
          <Options values={data.labels.party_types} />
        </select>
      </label>
      <label className="ca-field">
        Name
        <input value={form.name} onChange={(event) => set({ name: event.target.value })} />
      </label>
      <label className="ca-field">
        Primary contact
        <input value={form.p} onChange={(event) => set({ p: event.target.value })} />
      </label>
      <label className="ca-field">
        Primary contact's e-mail or phone
        <input value={form.pd} onChange={(event) => set({ pd: event.target.value })} />
      </label>
      <label className="ca-field">
        Second contact
        <input value={form.s} onChange={(event) => set({ s: event.target.value })} />
      </label>
      <label className="ca-field">
        Second contact's e-mail or phone
        <input value={form.sd} onChange={(event) => set({ sd: event.target.value })} />
      </label>
      <div className="ca-action-row ca-wide">
        <button type="submit" className="ac-primary" disabled={form.name.trim().length < 2}>
          Add the party
        </button>
      </div>
      <InlineError text={error} />
    </form>
  );
}

function AttemptsSetting({ value, onDone }: { value: number; onDone: () => void }) {
  const canSet = useCan("quality.review") || useCan("regulatory.approve");
  const [count, setCount] = useState(String(value));
  const [error, setError] = useState("");
  if (!canSet) return null;
  return (
    <Panel eyebrow="Setting" title="Unanswered attempts before a request moves on">
      <form
        className="ca-form-grid"
        aria-label="Attempts setting"
        onSubmit={async (event) => {
          event.preventDefault();
          setError("");
          try {
            await send(`${COMMUNICATIONS}/settings`, "PUT", { attempts_before_escalation: Number(count) });
            onDone();
          } catch (reason) {
            setError(errorText(reason, "The setting was not saved."));
          }
        }}
      >
        <label className="ca-field">
          Attempts (1 to 10; default 3)
          <input type="number" min={1} max={10} value={count} onChange={(event) => setCount(event.target.value)} />
        </label>
        <div className="ca-action-row">
          <button type="submit" className="ac-secondary" disabled={Number(count) === value}>
            Save
          </button>
        </div>
        <InlineError text={error} />
      </form>
    </Panel>
  );
}

/** One entry: the party and its contacts, every attempt, the replies, and what to record next. */
export function EntryDrawer({ id, labels, onClose }: { id: string; labels?: Labels; onClose: () => void }) {
  const resource = useResource<Entry>(`${COMMUNICATIONS}/${id}`);
  const [shown, setShown] = useState<Entry | null>(null);
  const entry = shown?.id === id ? shown : resource.data;
  const canRecord = useCanRecord();
  if (!entry) {
    return (
      <Drawer title="Communication" onClose={onClose}>
        <p className="ac-muted">
          {resource.error ? errorText(resource.error, "The entry could not be read.") : "Reading…"}
        </p>
      </Drawer>
    );
  }
  return (
    <Drawer
      title={`${entry.party?.name ?? "Communication"}${entry.complaint_ref ? `: ${entry.complaint_ref}` : ""}`}
      onClose={onClose}
    >
      <div className="uw-dp uw-cm">
        <div className="uw-cr-decision">
          <ToneBadge
            tone={statusTone(entry)}
            label={entry.overdue ? `${entry.status_label}, overdue` : entry.status_label}
          />
          <span className="uw-cr-meta">
            {entry.direction_label} · {entry.purpose_label} · {entry.channel_label} · {formatDate(entry.occurred_at)}
          </span>
        </div>
        <p className="uw-hint" role="note">
          <Send size={15} aria-hidden="true" /> {entry.never_sends}
        </p>
        <section className="ca-drawer-section" aria-label="What it is about">
          <h4>{entry.subject}</h4>
          <p className="uw-cr-meta">
            {entry.owner ? `Owner ${entry.owner}` : ""}
            {dueText(entry) ? ` · ${dueText(entry)}` : ""}
            {entry.origin?.label ? ` · ${entry.origin.label}` : ""}
          </p>
          {entry.is_request && <p className="uw-cr-meta">{attemptsText(entry)}</p>}
          {entry.party && (
            <p className="uw-cr-meta">
              {entry.party.type_label}. Primary: {contactText(entry.party.primary)}. Second:{" "}
              {entry.party.second ? contactText(entry.party.second) : "none recorded"}.
              {entry.status === "OPEN" && entry.current_contact === "SECOND" ? " Now asking the second contact." : ""}
            </p>
          )}
          {entry.note && <p>{entry.note}</p>}
          {entry.close_note && (
            <p>
              <strong>{entry.status_label}:</strong> {entry.close_note}
              {entry.closed_by ? ` (${entry.closed_by}, ${formatDate(entry.closed_at)})` : ""}
            </p>
          )}
          <p className="ac-muted">
            Logged {formatDate(entry.logged_at)} by {entry.logged_by}
            {entry.in_mdarix === true
              ? " · recorded in MDARIX"
              : entry.in_mdarix === false
                ? " · recorded later than one working hour"
                : ""}
            {entry.qms_reference ? ` · QMS record ${entry.qms_reference}` : ""}
          </p>
          {entry.evidence.length > 0 && <p className="uw-cr-meta">Evidence: {entry.evidence.join("; ")}</p>}
        </section>
        {entry.attempts.length > 0 && (
          <section className="ca-drawer-section" aria-label="Attempts">
            <h4>Attempts ({entry.attempts.length})</h4>
            <div className="uw-dg-scroll">
              <table className="uw-dg-table">
                <thead>
                  <tr>
                    <th scope="col">No.</th>
                    <th scope="col">When</th>
                    <th scope="col">How</th>
                    <th scope="col">Contact</th>
                    <th scope="col">Result</th>
                    <th scope="col">Logged</th>
                  </tr>
                </thead>
                <tbody>
                  {entry.attempts.map((attempt) => (
                    <tr key={attempt.number} className={attempt.unanswered ? "uw-cm-unanswered" : ""}>
                      <th scope="row">{attempt.number}</th>
                      <td>{formatDate(attempt.at)}</td>
                      <td>
                        {attempt.channel === "PHONE" ? (
                          <PhoneCall size={13} aria-hidden="true" />
                        ) : (
                          <Mail size={13} aria-hidden="true" />
                        )}{" "}
                        {attempt.channel_label}
                      </td>
                      <td>{attempt.contact_name}</td>
                      <td>
                        {attempt.unanswered && attempt.outcome === "SENT" ? "Sent, no reply" : attempt.outcome_label}
                        {attempt.note ? `: ${attempt.note}` : ""}
                      </td>
                      <td>
                        {formatDate(attempt.logged_at)} {attempt.in_mdarix === false ? "(late)" : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
        {(entry.replies ?? []).map((reply) => (
          <section key={reply.id} className="ca-drawer-section" aria-label="Reply">
            <h4>Reply received {formatDate(reply.occurred_at)}</h4>
            <p>{reply.subject}</p>
            <p className="uw-cr-meta">
              {reply.channel_label}
              {reply.evidence.length ? ` · Evidence: ${reply.evidence.join("; ")}` : ""}
              {reply.qms_reference ? ` · QMS record ${reply.qms_reference}` : ""}
            </p>
          </section>
        ))}
        {canRecord && entry.status === "OPEN" && labels && (
          <NextSteps entry={entry} labels={labels} onChanged={setShown} />
        )}
      </div>
    </Drawer>
  );
}

function NextSteps({ entry, labels, onChanged }: { entry: Entry; labels: Labels; onChanged: (entry: Entry) => void }) {
  const [attempt, setAttempt] = useState({ at: nowLocal(), channel: "PHONE", outcome: "NO_ANSWER", note: "" });
  const [reply, setReply] = useState({ at: nowLocal(), channel: "EMAIL", summary: "", evidence: "", qms: "" });
  const [close, setClose] = useState({ status: "CLOSED", note: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (path: string, body: unknown, failure: string) => {
    setBusy(true);
    setError("");
    try {
      onChanged(await send<Entry>(path, "POST", body));
    } catch (reason) {
      setError(errorText(reason, failure));
    } finally {
      setBusy(false);
    }
  };
  const base = `${COMMUNICATIONS}/${entry.id}`;
  return (
    <>
      <section className="ca-drawer-section" aria-label="Record an attempt">
        <h4>{entry.not_sent_yet ? "Record that you sent it" : "Record another attempt"}</h4>
        <div className="ca-form-grid">
          <label className="ca-field">
            When
            <input
              type="datetime-local"
              value={attempt.at}
              onChange={(event) => setAttempt({ ...attempt, at: event.target.value })}
            />
          </label>
          <label className="ca-field">
            How
            <select
              value={attempt.channel}
              onChange={(event) => setAttempt({ ...attempt, channel: event.target.value })}
            >
              <Options values={labels.channels} />
            </select>
          </label>
          <label className="ca-field">
            What happened
            <select
              value={attempt.outcome}
              onChange={(event) => setAttempt({ ...attempt, outcome: event.target.value })}
            >
              <Options values={labels.outcomes} />
            </select>
          </label>
          <label className="ca-field">
            Note
            <input value={attempt.note} onChange={(event) => setAttempt({ ...attempt, note: event.target.value })} />
          </label>
        </div>
        <div className="ca-action-row">
          <button
            type="button"
            className="ac-secondary"
            disabled={busy || !attempt.at}
            onClick={() =>
              void run(
                `${base}/attempts`,
                { at: isoOf(attempt.at), channel: attempt.channel, outcome: attempt.outcome, note: attempt.note },
                "The attempt was not recorded.",
              )
            }
          >
            Record the attempt
          </button>
        </div>
      </section>
      {!entry.not_sent_yet && (
        <section className="ca-drawer-section" aria-label="Record the reply">
          <h4>Record the reply</h4>
          <div className="ca-form-grid">
            <label className="ca-field">
              Received at
              <input
                type="datetime-local"
                value={reply.at}
                onChange={(event) => setReply({ ...reply, at: event.target.value })}
              />
            </label>
            <label className="ca-field">
              How
              <select value={reply.channel} onChange={(event) => setReply({ ...reply, channel: event.target.value })}>
                <Options values={labels.channels} />
              </select>
            </label>
            <label className="ca-field ca-wide">
              What they said
              <input value={reply.summary} onChange={(event) => setReply({ ...reply, summary: event.target.value })} />
            </label>
            <label className="ca-field">
              Evidence (one per line)
              <textarea
                rows={2}
                value={reply.evidence}
                onChange={(event) => setReply({ ...reply, evidence: event.target.value })}
              />
            </label>
            <label className="ca-field">
              QMS record ID
              <input value={reply.qms} onChange={(event) => setReply({ ...reply, qms: event.target.value })} />
            </label>
          </div>
          <div className="ca-action-row">
            <button
              type="button"
              className="ac-primary"
              disabled={busy || reply.summary.trim().length < 5}
              onClick={() =>
                void run(
                  `${base}/reply`,
                  {
                    received_at: isoOf(reply.at),
                    channel: reply.channel,
                    summary: reply.summary,
                    evidence: evidenceLines(reply.evidence),
                    qms_reference: reply.qms,
                  },
                  "The reply was not recorded.",
                )
              }
            >
              Record the reply
            </button>
          </div>
        </section>
      )}
      <section className="ca-drawer-section" aria-label="Close the request">
        <h4>Close the request</h4>
        <div className="ca-form-grid">
          <label className="ca-field">
            How it ends
            <select value={close.status} onChange={(event) => setClose({ ...close, status: event.target.value })}>
              <option value="CLOSED">No longer needed</option>
              <option value="UNRESOLVED">Unresolved after attempts</option>
            </select>
          </label>
          <label className="ca-field ca-wide">
            Why
            <input value={close.note} onChange={(event) => setClose({ ...close, note: event.target.value })} />
          </label>
        </div>
        <div className="ca-action-row">
          <button
            type="button"
            className="ac-secondary"
            disabled={busy || close.note.trim().length < REASON_MIN}
            onClick={() => void run(`${base}/close`, close, "The request was not closed.")}
          >
            Close it
          </button>
        </div>
      </section>
      <InlineError text={error} />
    </>
  );
}
