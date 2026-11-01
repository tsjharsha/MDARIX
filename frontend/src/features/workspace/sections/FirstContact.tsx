import { useState } from "react";
import {
  CheckCircle2,
  ClipboardList,
  Copy,
  FileWarning,
  Hourglass,
  Link2,
  PhoneCall,
  Siren,
  Unlink,
  Wrench,
} from "lucide-react";
import { Empty, Panel, StatTile, ToneBadge } from "../../admin/console/charts";
import { Drawer, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { useWorkspace } from "../workspaceContext";
import { countOf } from "./common";
import { ChipFilter, Hero, InlineError } from "./boardParts";
import { EscalateButton, useCanTriage } from "./Triage";
import {
  INTAKE,
  OUTCOME_TONES,
  REASON_MIN,
  STATE_LABELS,
  INTAKE_SHOWS,
  answerChoices,
  blankAnswers,
  daysEarlier,
  fromLocalInput,
  linkBody,
  signProblem,
  toLocalInput,
  unanswered,
  type Answers,
  type Duplicate,
  type Guide,
  type IntakeItem,
  type IntakeList,
  type IntakeState,
  type Outcome,
} from "../intake";

const ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

/**
 * Complaints › First contact: the calls the service desk logged and the urgent intakes, each with the first-contact
 * check (complaint, service only, both or pending, by the starter guide's table), the follow-ups, the QMS-complaint
 * task and the QA review of every "service only"; and the possible duplicates across sources, to link or dismiss.
 */
export function FirstContact({ onOpenTab }: { onOpenTab?: (tab: "Triage") => void }) {
  const [show, setShow] = useState<"all" | IntakeState>("all");
  const [logging, setLogging] = useState<"CONTACT" | "URGENT" | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const list = useResource<IntakeList>(`${INTAKE}?show=${show}`);
  const guide = useResource<Guide>(`${INTAKE}/guide`);
  const canWrite = useCanTriage();
  const summary = list.data?.summary;
  const items = list.data?.items ?? [];
  return (
    <div className="ac-overview">
      <Hero
        tone={summary ? (summary.to_sign + summary.pending + summary.review ? "warning" : "good") : "neutral"}
        icon={<PhoneCall size={28} />}
        eyebrow="First contact"
        title={
          summary
            ? summary.all
              ? `${countOf(summary.all, "call")} and urgent intakes`
              : "No call logged yet"
            : "Reading the calls…"
        }
        detail="A service call can hide a complaint. Log the caller's words, answer the ten questions, and the table gives complaint, service only, both or pending. A harm answer or a harm word goes to triage at once. Awareness is the time of the call."
      >
        {canWrite && (
          <div className="uw-entry-actions">
            <button type="button" className="ac-primary" onClick={() => setLogging("CONTACT")}>
              <PhoneCall size={15} aria-hidden="true" /> Log a call
            </button>
            <button type="button" className="ac-secondary" onClick={() => setLogging("URGENT")}>
              <Siren size={15} aria-hidden="true" /> Urgent intake
            </button>
            {onOpenTab && (
              <button type="button" className="ac-link" onClick={() => onOpenTab("Triage")}>
                Open the triage list
              </button>
            )}
          </div>
        )}
      </Hero>
      <div className="uw-cr-stats">
        <StatTile
          label="To sign"
          value={summary ? summary.to_sign : null}
          detail="Due the same working day"
          icon={<ClipboardList size={18} />}
          tone={summary?.to_sign ? "warning" : undefined}
          onOpen={() => setShow("to_sign")}
        />
        <StatTile
          label="Pending"
          value={summary ? summary.pending : null}
          detail="Waiting on a follow-up with the caller"
          icon={<Hourglass size={18} />}
          onOpen={() => setShow("pending")}
        />
        <StatTile
          label="QA review due"
          value={summary ? summary.review : null}
          detail="Every service only is reviewed in the trial"
          icon={<CheckCircle2 size={18} />}
          onOpen={() => setShow("review")}
        />
        <StatTile
          label="Possible duplicates"
          value={list.data ? list.data.duplicates : null}
          detail="The same event from two sources"
          icon={<Copy size={18} />}
          tone={list.data?.duplicates ? "warning" : undefined}
          onOpen={() => document.getElementById("first-contact-duplicates")?.scrollIntoView({ behavior: "smooth" })}
        />
      </div>
      <Panel eyebrow="First contact" title="Calls and urgent intakes, newest first" source={list}>
        <div className="uw-cr-toolbar">
          <ChipFilter
            label="Which calls"
            options={INTAKE_SHOWS}
            value={show}
            counts={summary as Record<string, number> | undefined}
            onChange={setShow}
          />
        </div>
        {items.length ? (
          <ul className="uw-cr-list">
            {items.map((item) => (
              <IntakeCard key={item.id} item={item} onOpen={() => setOpen(item.id)} onChanged={list.reload} />
            ))}
          </ul>
        ) : (
          <Empty title="Nothing here" detail="Log a call or an urgent intake to see the check at work." />
        )}
        {guide.data && (
          <p className="uw-ma-starter" role="note">
            <FileWarning size={15} aria-hidden="true" /> Guide {guide.data.version}. {guide.data.starter_mark}
          </p>
        )}
      </Panel>
      <Duplicates onChanged={list.reload} />
      {logging && guide.data && (
        <LogDrawer
          kind={logging}
          guide={guide.data}
          onClose={() => setLogging(null)}
          onLogged={(id) => {
            setLogging(null);
            list.reload();
            setOpen(id);
          }}
        />
      )}
      {open && guide.data && (
        <CheckDrawer id={open} guide={guide.data} onClose={() => setOpen(null)} onChanged={list.reload} />
      )}
    </div>
  );
}

function IntakeCard({ item, onOpen, onChanged }: { item: IntakeItem; onOpen: () => void; onChanged: () => void }) {
  const outcome = item.signed?.classification ?? item.suggestion;
  const tone = item.kind === "URGENT" ? "critical" : outcome ? OUTCOME_TONES[outcome] : "neutral";
  const followUp = item.tasks.find((task) => task.type === "FIRST_CONTACT_FOLLOW_UP" && task.open);
  return (
    <li className="uw-cr-card">
      <span className={`uw-cr-rail tone-${tone}`} aria-hidden="true" />
      <div className="uw-cr-body">
        <div className="uw-cr-head">
          <strong className="uw-cr-id">{item.reference}</strong>
          <span className="uw-cr-meta">
            {item.kind_label}
            {item.product_name ? ` · ${item.product_name}` : ""}
            {item.lot ? ` · ${item.lot}` : ""} · {formatDate(item.created_at)}
          </span>
          {item.kind === "URGENT" ? (
            <ToneBadge tone="critical" label="Urgent intake: a complaint" />
          ) : item.signed ? (
            <ToneBadge tone={tone} label={item.signed.classification_label ?? ""} />
          ) : (
            <ToneBadge tone="warning" label={`Suggested: ${item.suggestion_label ?? "answer the questions"}`} />
          )}
          {item.state && item.state !== "complaint" && <span className="uw-cr-meta">{STATE_LABELS[item.state]}</span>}
          {item.flagged && <ToneBadge tone="serious" label="Triage flag" />}
        </div>
        <q className="uw-cr-text uw-cr-clip">{item.reporter_words}</q>
        <p className="uw-cr-meta">
          Aware {formatDate(item.awareness.at)} ({item.awareness.source_label})
          {item.awareness.label ? ` · ${item.awareness.label}` : ""}
          {followUp ? ` · follow-up due ${formatDate(followUp.due_at)}${followUp.overdue ? " (overdue)" : ""}` : ""}
          {item.qms_task ? ` · ${item.qms_task.label}${item.qms_task.overdue ? " (overdue)" : ""}` : ""}
        </p>
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={onOpen}>
            {item.kind === "URGENT" ? "Open" : item.signed ? "Open the check" : "Check and sign"}
          </button>
          {!item.flagged && item.kind !== "URGENT" && <EscalateButton kind="INTAKE" id={item.id} onDone={onChanged} />}
        </div>
      </div>
    </li>
  );
}

// Logging a call or an urgent intake ---------------------------------------------------------------------------------

type LogForm = {
  words: string;
  reporterType: string;
  site: string;
  country: string;
  product: string;
  lot: string;
  serial: string;
  requested: string;
  environment: string;
  userType: string;
  received: string;
  event: string;
  firstKnowledge: string;
  party: string;
  awareness: string;
  zone: string;
  answers: Answers;
  unknowns: string;
};

function LogDrawer({
  kind,
  guide,
  onClose,
  onLogged,
}: {
  kind: "CONTACT" | "URGENT";
  guide: Guide;
  onClose: () => void;
  onLogged: (id: string) => void;
}) {
  const { work } = useWorkspace();
  const [form, setForm] = useState<LogForm>({
    words: "",
    reporterType: "",
    site: "",
    country: "",
    product: "",
    lot: "",
    serial: "",
    requested: "NONE",
    environment: "UNKNOWN",
    userType: "UNKNOWN",
    received: toLocalInput(new Date().toISOString()),
    event: "",
    firstKnowledge: "",
    party: "",
    awareness: "",
    zone: ZONE,
    answers: blankAnswers(guide.questions),
    unknowns: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (patch: Partial<LogForm>) => setForm((current) => ({ ...current, ...patch }));
  const problem = form.words.trim().length < REASON_MIN ? "Write down the caller's words, as they said them" : null;
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const saved = await send<IntakeItem>(INTAKE, "POST", {
        kind,
        reporter_words: form.words,
        reporter_type: form.reporterType,
        reporter_site: form.site,
        country: form.country,
        product_id: form.product || null,
        lot: form.lot,
        serial_number: form.serial,
        requested: form.requested,
        use_environment: form.environment,
        user_type: form.userType,
        received_at: fromLocalInput(form.received),
        received_zone: form.zone,
        event_at: fromLocalInput(form.event),
        event_zone: form.event ? form.zone : "",
        first_knowledge_at: fromLocalInput(form.firstKnowledge),
        first_knowledge_zone: form.firstKnowledge ? form.zone : "",
        first_knowledge_party: form.party,
        awareness_at: kind === "URGENT" ? fromLocalInput(form.awareness) : null,
        awareness_zone: form.zone,
        answers: kind === "CONTACT" ? form.answers : {},
        unknowns: form.unknowns,
      });
      onLogged(saved.id);
    } catch (reason) {
      setError(errorText(reason, "Not saved"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Drawer title={kind === "CONTACT" ? "Log a call" : "Urgent intake"} onClose={onClose}>
      <form
        className="uw-dp"
        onSubmit={(event) => {
          event.preventDefault();
          if (!problem) void submit();
        }}
      >
        {kind === "URGENT" ? (
          <p className="uw-hint">
            An urgent intake is a complaint by definition. It goes to triage at once, with its clock running from
            awareness; the QMS complaint follows. Leave awareness empty if nobody has confirmed it: the clock then runs
            from first knowledge or receipt, marked provisional.
          </p>
        ) : (
          <p className="uw-hint">
            Awareness is the time of the call. It never moves, even if the call is reclassified.
          </p>
        )}
        <label className="ca-field">
          The caller's words, as they said them
          <textarea rows={4} value={form.words} onChange={(event) => set({ words: event.target.value })} />
        </label>
        <div className="ca-form-grid">
          <label className="ca-field">
            Product
            <select value={form.product} onChange={(event) => set({ product: event.target.value })}>
              <option value="">Not named</option>
              {work.products.map((product) => (
                <option key={product.id} value={product.id}>
                  {product.name}
                </option>
              ))}
            </select>
          </label>
          <label className="ca-field">
            Lot
            <input value={form.lot} onChange={(event) => set({ lot: event.target.value })} />
          </label>
          <label className="ca-field">
            Serial number
            <input value={form.serial} onChange={(event) => set({ serial: event.target.value })} />
          </label>
          <label className="ca-field">
            What was asked for
            <select value={form.requested} onChange={(event) => set({ requested: event.target.value })}>
              {guide.requests.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label className="ca-field">
            Who called (hospital, distributor, user…)
            <input value={form.reporterType} onChange={(event) => set({ reporterType: event.target.value })} />
          </label>
          <label className="ca-field">
            Site (no person's name)
            <input value={form.site} onChange={(event) => set({ site: event.target.value })} />
          </label>
          <label className="ca-field">
            Country
            <input value={form.country} onChange={(event) => set({ country: event.target.value })} />
          </label>
          <label className="ca-field">
            Use environment
            <select value={form.environment} onChange={(event) => set({ environment: event.target.value })}>
              {guide.use_environments.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label className="ca-field">
            User type
            <select value={form.userType} onChange={(event) => set({ userType: event.target.value })}>
              {guide.user_types.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <section className="ca-drawer-section">
          <h4>Times ({form.zone})</h4>
          <div className="ca-form-grid">
            <label className="ca-field">
              {kind === "CONTACT" ? "Time of the call (awareness)" : "Received"}
              <input
                type="datetime-local"
                value={form.received}
                onChange={(event) => set({ received: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Event
              <input
                type="datetime-local"
                value={form.event}
                onChange={(event) => set({ event: event.target.value })}
              />
            </label>
            {kind === "URGENT" && (
              <>
                <label className="ca-field">
                  First knowledge (anyone acting for you)
                  <input
                    type="datetime-local"
                    value={form.firstKnowledge}
                    onChange={(event) => set({ firstKnowledge: event.target.value })}
                  />
                </label>
                <label className="ca-field">
                  Who knew first
                  <select value={form.party} onChange={(event) => set({ party: event.target.value })}>
                    <option value="">Not known</option>
                    <option value="MANUFACTURER">Our own staff</option>
                    <option value="DISTRIBUTOR">A distributor</option>
                    <option value="SERVICE_AGENT">A service agent</option>
                  </select>
                </label>
                <label className="ca-field">
                  Awareness (if confirmed)
                  <input
                    type="datetime-local"
                    value={form.awareness}
                    onChange={(event) => set({ awareness: event.target.value })}
                  />
                </label>
              </>
            )}
            <label className="ca-field">
              Time zone
              <input value={form.zone} onChange={(event) => set({ zone: event.target.value })} />
            </label>
          </div>
        </section>
        {kind === "CONTACT" && (
          <section className="ca-drawer-section">
            <h4>The first-contact questions</h4>
            <p className="uw-hint">{guide.note}</p>
            <Questions guide={guide} answers={form.answers} onChange={(answers) => set({ answers })} />
            <label className="ca-field">
              10. What is still unknown and needs a follow-up with the caller?
              <textarea rows={2} value={form.unknowns} onChange={(event) => set({ unknowns: event.target.value })} />
            </label>
          </section>
        )}
        {problem && <p className="uw-hint">{problem}</p>}
        <div className="ca-action-row">
          <button type="submit" className="ac-primary" disabled={busy || !!problem}>
            {busy ? "Saving…" : kind === "CONTACT" ? "Save the call" : "Send to triage"}
          </button>
        </div>
        <InlineError text={error} />
      </form>
    </Drawer>
  );
}

function Questions({
  guide,
  answers,
  disabled,
  onChange,
}: {
  guide: Guide;
  answers: Answers;
  disabled?: boolean;
  onChange: (answers: Answers) => void;
}) {
  return (
    <ol className="uw-fc-questions">
      {guide.questions
        .filter((question) => !question.free_text)
        .map((question) => {
          const current = answers[question.id] ?? { answer: null, note: "" };
          const harm = question.not_stated && (current.answer === "YES" || current.answer === "UNKNOWN");
          return (
            <li key={question.id} className={`uw-fc-question${harm ? " is-flag" : ""}`}>
              <strong>
                {question.id.replace("Q", "")}. {question.text}
              </strong>
              <div className="uw-fc-answers" role="radiogroup" aria-label={`Question ${question.id.replace("Q", "")}`}>
                {answerChoices(guide, question).map((choice) => (
                  <label key={choice.code}>
                    <input
                      type="radio"
                      name={question.id}
                      disabled={disabled}
                      checked={current.answer === choice.code}
                      onChange={() => onChange({ ...answers, [question.id]: { ...current, answer: choice.code } })}
                    />
                    {choice.label}
                  </label>
                ))}
              </div>
              {(current.answer === "NOT_APPLICABLE" || current.note) && (
                <input
                  aria-label={`Question ${question.id.replace("Q", "")}: reason or evidence`}
                  placeholder="Reason or evidence (needed for Not applicable)"
                  disabled={disabled}
                  value={current.note}
                  onChange={(event) =>
                    onChange({ ...answers, [question.id]: { ...current, note: event.target.value } })
                  }
                />
              )}
              {harm && <span className="uw-cr-meta">Raises the triage flag at once.</span>}
            </li>
          );
        })}
    </ol>
  );
}

// The check -----------------------------------------------------------------------------------------------------------

function CheckDrawer({
  id,
  guide,
  onClose,
  onChanged,
}: {
  id: string;
  guide: Guide;
  onClose: () => void;
  onChanged: () => void;
}) {
  const item = useResource<IntakeItem>(`${INTAKE}/${id}`);
  const data = item.data;
  const reload = () => {
    item.reload();
    onChanged();
  };
  return (
    <Drawer title={data ? `${data.kind_label} ${data.reference}` : "Loading…"} onClose={onClose}>
      {data ? (
        <CheckBody key={`${data.version}-${data.signed?.id ?? ""}`} item={data} guide={guide} onChanged={reload} />
      ) : null}
      <InlineError text={item.state === "error" ? "This call could not be read" : ""} />
    </Drawer>
  );
}

function CheckBody({ item, guide, onChanged }: { item: IntakeItem; guide: Guide; onChanged: () => void }) {
  const canWrite = useCanTriage();
  const [answers, setAnswers] = useState<Answers>({ ...blankAnswers(guide.questions), ...item.answers });
  const [editing, setEditing] = useState(item.draft || item.version === 0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (work: () => Promise<unknown>, fallback: string) => {
    setBusy(true);
    setError("");
    try {
      await work();
      onChanged();
    } catch (reason) {
      setError(errorText(reason, fallback));
    } finally {
      setBusy(false);
    }
  };
  const followUp = item.tasks.find((task) => task.type === "FIRST_CONTACT_FOLLOW_UP" && task.open);
  const review = item.signed?.classification === "SERVICE_ONLY" && !item.signed.review_outcome;
  return (
    <div className="uw-dp">
      <q className="uw-cr-text">{item.reporter_words}</q>
      <p className="uw-cr-meta">
        {[
          item.product_name,
          item.lot,
          item.requested_label && `asked for: ${item.requested_label}`,
          item.reporter_type,
          item.reporter_site,
          item.country,
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
      <section className="ca-drawer-section">
        <h4>Times</h4>
        <ul>
          {(
            [
              ["Event", item.times.event],
              ["First knowledge", item.times.first_knowledge],
              ["Received", item.times.received],
              ["Awareness", item.times.awareness],
              ["Reached MDARIX", item.times.available],
            ] as const
          ).map(([label, time]) => (
            <li key={label}>
              {label}:{" "}
              {time?.at
                ? `${formatDate(time.at)}${time.zone && time.zone !== "UTC" ? ` (entered in ${time.zone})` : ""}`
                : "not recorded"}
            </li>
          ))}
        </ul>
        <p>
          Clocks count from {formatDate(item.awareness.at)}: {item.awareness.source_label}.
          {item.awareness.label ? ` ${item.awareness.label}.` : ""}
        </p>
      </section>
      {item.flags.length > 0 && (
        <section className="ca-drawer-section">
          <h4>
            <Siren size={15} aria-hidden="true" /> On the triage list now
          </h4>
          <ul className="uw-cr-chips">
            {item.flags.map((flag, index) => (
              <li key={`${flag.code}-${index}`} className="uw-cr-chip tone-serious">
                {flag.label}
              </li>
            ))}
          </ul>
          <p className="uw-hint">Safety never waits for the check or a signature.</p>
        </section>
      )}
      {item.kind !== "URGENT" && (
        <section className="ca-drawer-section">
          <h4>The first-contact check</h4>
          {item.suggestion && (
            <p className="uw-fc-outcome">
              The table gives: <strong>{item.suggestion_label}</strong> (row {item.outcome_row}).
              {item.signed && ` Signed: ${item.signed.classification_label}, version ${item.signed.version}.`}
            </p>
          )}
          <Questions guide={guide} answers={answers} disabled={!editing || !canWrite} onChange={setAnswers} />
          <details className="uw-ma-history">
            <summary>The outcomes table (fixed)</summary>
            <ol>
              {guide.table.map((row) => (
                <li key={row.row} className={row.row === item.outcome_row ? "is-taken" : undefined}>
                  {row.answers}: <strong>{row.outcome}</strong>
                </li>
              ))}
            </ol>
          </details>
          {canWrite && (
            <div className="ca-action-row">
              {editing ? (
                <button
                  type="button"
                  className="ac-secondary"
                  disabled={busy}
                  onClick={() =>
                    run(
                      () => send(`${INTAKE}/${item.id}/check`, "PUT", { answers, seen_version: item.version }),
                      "The answers were not saved",
                    )
                  }
                >
                  {item.signed ? "Save as a new version" : "Save the answers"}
                </button>
              ) : (
                <button type="button" className="ac-link" onClick={() => setEditing(true)}>
                  New information: answer again (a new version; awareness stays)
                </button>
              )}
            </div>
          )}
        </section>
      )}
      {canWrite && item.draft && item.version > 0 && (
        <SignForm item={item} guide={guide} answers={answers} onSigned={onChanged} />
      )}
      {followUp && canWrite && <FollowUp item={item} dueAt={followUp.due_at} onDone={onChanged} />}
      {item.qms_task && (
        <section className="ca-drawer-section">
          <h4>
            <Wrench size={15} aria-hidden="true" /> QMS complaint
          </h4>
          <p>
            {item.qms_task.label}
            {item.qms_ref ? `: ${item.qms_ref}` : ""}
            {item.qms_task.open && item.qms_task.due_at ? ` · due ${formatDate(item.qms_task.due_at)}` : ""}
            {item.qms_task.overdue ? " (overdue)" : ""}. Reporting never waits for it.
          </p>
          {item.qms_task.open && canWrite && <QmsForm id={item.id} onDone={onChanged} />}
        </section>
      )}
      {review && canWrite && <ReviewForm item={item} onDone={onChanged} />}
      {item.history && item.history.length > 0 && (
        <details className="uw-ma-history" open>
          <summary>Signed versions ({item.history.length})</summary>
          <ul>
            {item.history.map((version) => (
              <li key={version.id}>
                Version {version.version}: {version.classification_label} · {version.signed_by} ·{" "}
                {formatDate(version.signed_at)}
                {version.override_reason ? ` · ${version.override_reason}` : ""}
                {version.reason ? ` · ${version.reason}` : ""}
                {version.review_outcome
                  ? ` · QA review ${version.review_outcome.toLowerCase()} by ${version.reviewed_by}${version.same_person ? " (same person)" : ""}`
                  : ""}
                {version.superseded ? " · superseded" : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
      {item.links && item.links.length > 0 && <Links links={item.links} onChanged={onChanged} />}
      {item.duplicates && item.duplicates.length > 0 && (
        <section className="ca-drawer-section">
          <h4>
            <Copy size={15} aria-hidden="true" /> Possible duplicate
          </h4>
          {item.duplicates.map((pair) => (
            <DuplicatePair key={`${pair.left.id}-${pair.right.id}`} pair={pair} onDone={onChanged} />
          ))}
        </section>
      )}
      <InlineError text={error} />
    </div>
  );
}

function SignForm({
  item,
  guide,
  answers,
  onSigned,
}: {
  item: IntakeItem;
  guide: Guide;
  answers: Answers;
  onSigned: () => void;
}) {
  const [form, setForm] = useState({
    classification: (item.suggestion ?? "") as Outcome | "",
    override: "",
    reason: "",
    ticket: item.service_ticket ?? "",
    password: "",
    code: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const saved = JSON.stringify(answers) === JSON.stringify({ ...blankAnswers(guide.questions), ...item.answers });
  const problem = saved ? signProblem(item, form, unanswered(item.answers, guide.questions)) : "Save the answers first";
  return (
    <form
      className="ca-drawer-section uw-dp-sign"
      onSubmit={async (event) => {
        event.preventDefault();
        if (problem) return;
        setBusy(true);
        setError("");
        try {
          await send(`${INTAKE}/${item.id}/check/sign`, "POST", {
            classification: form.classification,
            override_reason: form.override,
            reason: form.reason,
            service_ticket: form.ticket,
            seen_version: item.version,
            password: form.password,
            mfa_code: form.code || null,
          });
          onSigned();
        } catch (reason) {
          setError(errorText(reason, "Not signed"));
        } finally {
          setBusy(false);
        }
      }}
    >
      <h4>
        <CheckCircle2 size={15} aria-hidden="true" /> Sign as the coordinator
      </h4>
      <label className="ca-field">
        Classification
        <select
          value={form.classification}
          onChange={(event) => setForm({ ...form, classification: event.target.value as Outcome })}
        >
          {guide.outcomes
            .filter(
              (outcome) =>
                (outcome.code !== "SERVICE_ONLY" && outcome.code !== "PENDING_CONFIRM") ||
                outcome.code === item.suggestion,
            )
            .map((outcome) => (
              <option key={outcome.code} value={outcome.code}>
                {outcome.label}
                {outcome.code === item.suggestion ? " (suggested)" : ""}
              </option>
            ))}
        </select>
      </label>
      {form.classification !== item.suggestion && (
        <label className="ca-field">
          Why you override the suggestion
          <input value={form.override} onChange={(event) => setForm({ ...form, override: event.target.value })} />
        </label>
      )}
      {form.classification === "SERVICE_ONLY" && (
        <label className="ca-field">
          The written reason for "service only" (it goes to the QA review)
          <input value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} />
        </label>
      )}
      {form.classification === "BOTH" && (
        <label className="ca-field">
          Service ticket
          <input value={form.ticket} onChange={(event) => setForm({ ...form, ticket: event.target.value })} />
        </label>
      )}
      <div className="ca-form-grid">
        <label className="ca-field">
          Your password
          <input
            type="password"
            autoComplete="current-password"
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Authenticator code
          <input
            inputMode="numeric"
            autoComplete="one-time-code"
            value={form.code}
            onChange={(event) => setForm({ ...form, code: event.target.value })}
          />
        </label>
      </div>
      {problem && <p className="uw-hint">{problem}</p>}
      <div className="ca-action-row">
        <button type="submit" className="ac-primary" disabled={busy || !!problem}>
          {busy ? "Signing…" : "Sign the check"}
        </button>
      </div>
      <InlineError text={error} />
    </form>
  );
}

function FollowUp({ item, dueAt, onDone }: { item: IntakeItem; dueAt: string | null; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const close = async (outcome: "ANSWERED" | "UNRESOLVED") => {
    setError("");
    try {
      await send(`${INTAKE}/${item.id}/follow-up`, "POST", { outcome, note });
      onDone();
    } catch (reason) {
      setError(errorText(reason, "Not saved"));
    }
  };
  const short = note.trim().length < REASON_MIN;
  return (
    <section className="ca-drawer-section">
      <h4>
        <Hourglass size={15} aria-hidden="true" /> Follow-up with the caller
      </h4>
      <p>
        Due {formatDate(dueAt)}. Ask about every Unknown and Not stated answer. Until the communications log arrives,
        this is a dated task on the check.
      </p>
      <label className="ca-field">
        What the caller said, or what you tried
        <input value={note} onChange={(event) => setNote(event.target.value)} />
      </label>
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" disabled={short} onClick={() => close("ANSWERED")}>
          Answered: I will update the answers
        </button>
        <button type="button" className="ac-link" disabled={short} onClick={() => close("UNRESOLVED")}>
          Unresolved after attempts
        </button>
      </div>
      <InlineError text={error} />
    </section>
  );
}

function QmsForm({ id, onDone }: { id: string; onDone: () => void }) {
  const [ref, setRef] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const post = async (body: object) => {
    setError("");
    try {
      await send(`${INTAKE}/${id}/qms`, "POST", body);
      onDone();
    } catch (failure) {
      setError(errorText(failure, "Not saved"));
    }
  };
  return (
    <div className="ca-form-grid">
      <label className="ca-field">
        QMS complaint ID (closes when an upload brings it)
        <input value={ref} onChange={(event) => setRef(event.target.value)} />
      </label>
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" disabled={!ref.trim()} onClick={() => post({ qms_ref: ref })}>
          Save the ID
        </button>
      </div>
      <label className="ca-field">
        Or: why no QMS complaint is needed
        <input value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      <div className="ca-action-row">
        <button
          type="button"
          className="ac-link"
          disabled={reason.trim().length < REASON_MIN}
          onClick={() => post({ not_needed_reason: reason })}
        >
          No QMS complaint needed
        </button>
      </div>
      <InlineError text={error} />
    </div>
  );
}

function ReviewForm({ item, onDone }: { item: IntakeItem; onDone: () => void }) {
  const [form, setForm] = useState({ outcome: "AGREED", note: "", password: "", code: "" });
  const [error, setError] = useState("");
  const words = [...(item.fault_words ?? []), ...(item.harm_words ?? [])];
  const problem =
    form.note.trim().length < REASON_MIN
      ? `Say what you checked (at least ${REASON_MIN} characters)`
      : !form.password
        ? "Enter your password to sign"
        : null;
  return (
    <form
      className="ca-drawer-section"
      onSubmit={async (event) => {
        event.preventDefault();
        if (problem) return;
        setError("");
        try {
          await send(`${INTAKE}/${item.id}/check/review`, "POST", {
            outcome: form.outcome,
            note: form.note,
            password: form.password,
            mfa_code: form.code || null,
          });
          onDone();
        } catch (reason) {
          setError(errorText(reason, "Not signed"));
        }
      }}
    >
      <h4>QA review of "service only"</h4>
      <p>
        Every service-only call is reviewed in the trial. Ideally by someone other than the signer; the record says if
        it is the same person.
        {words.length ? ` The words match the starter lists: ${words.join(", ")}.` : ""}
      </p>
      <div className="uw-fc-answers">
        <label>
          <input
            type="radio"
            checked={form.outcome === "AGREED"}
            onChange={() => setForm({ ...form, outcome: "AGREED" })}
          />
          Agree: service only
        </label>
        <label>
          <input
            type="radio"
            checked={form.outcome === "RECLASSIFIED"}
            onChange={() => setForm({ ...form, outcome: "RECLASSIFIED" })}
          />
          Disagree: it is a complaint (awareness stays the time of the call)
        </label>
      </div>
      <label className="ca-field">
        What you checked
        <input value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} />
      </label>
      <div className="ca-form-grid">
        <label className="ca-field">
          Your password
          <input
            type="password"
            autoComplete="current-password"
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Authenticator code
          <input
            inputMode="numeric"
            value={form.code}
            onChange={(event) => setForm({ ...form, code: event.target.value })}
          />
        </label>
      </div>
      {problem && <p className="uw-hint">{problem}</p>}
      <div className="ca-action-row">
        <button type="submit" className="ac-primary" disabled={!!problem}>
          Sign the review
        </button>
      </div>
      <InlineError text={error} />
    </form>
  );
}

// Duplicates and links -----------------------------------------------------------------------------------------------

type DuplicateList = {
  items: Duplicate[];
  window_days: number;
  links: {
    id: string;
    state: "LINKED" | "DISMISSED" | "UNLINKED";
    left: { ref: string };
    right: { ref: string };
    reason: string;
    decided_at: string;
    awareness_before: string | null;
    awareness_after: string | null;
    conflict: boolean;
    undo_reason: string | null;
  }[];
};

function Duplicates({ onChanged }: { onChanged: () => void }) {
  const list = useResource<DuplicateList>(`${INTAKE}/duplicates`);
  const reload = () => {
    list.reload();
    onChanged();
  };
  const items = list.data?.items ?? [];
  const links = list.data?.links ?? [];
  return (
    <Panel
      id="first-contact-duplicates"
      eyebrow="Duplicates"
      title="Possible duplicates across uploads, the sample, calls and urgent intakes"
      source={list}
    >
      <p className="uw-hint">
        Same product and lot or serial number, events within {list.data?.window_days ?? 2} days, and the same site or
        country. Link them into one event, or dismiss the warning, with a reason. A link uses the earliest awareness of
        its sources and recomputes every deadline from it.
      </p>
      {items.length ? (
        items.map((pair) => <DuplicatePair key={`${pair.left.id}-${pair.right.id}`} pair={pair} onDone={reload} />)
      ) : (
        <Empty title="No possible duplicate" detail="A warning shows when two sources describe the same event." />
      )}
      {links.length > 0 && (
        <details className="uw-ma-history" open>
          <summary>Decisions ({links.length})</summary>
          <ul>
            {links.map((link) => (
              <LinkRow key={link.id} link={link} onDone={reload} />
            ))}
          </ul>
        </details>
      )}
    </Panel>
  );
}

function DuplicatePair({ pair, onDone }: { pair: Duplicate; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const decide = async (decision: "LINKED" | "DISMISSED") => {
    setError("");
    try {
      await send(`${INTAKE}/links`, "POST", linkBody(pair, decision, reason));
      onDone();
    } catch (failure) {
      setError(errorText(failure, "Not saved"));
    }
  };
  const earlier = Date.parse(pair.left.awareness_at) < Date.parse(pair.right.awareness_at) ? pair.left : pair.right;
  const later = earlier === pair.left ? pair.right : pair.left;
  return (
    <div className="ca-drawer-section">
      <p>
        <ToneBadge tone="warning" label="Possible duplicate" /> {pair.reasons.join(" · ")}
      </p>
      <div className="uw-fc-pair">
        {[pair.left, pair.right].map((side) => (
          <div key={side.id}>
            <strong>{side.ref}</strong> <span className="uw-cr-meta">{side.source}</span>
            <q className="uw-cr-text uw-cr-clip">{side.words}</q>
            <p className="uw-cr-meta">
              Aware {formatDate(side.awareness_at)} ({side.awareness_source})
            </p>
          </div>
        ))}
      </div>
      {earlier.awareness_at !== later.awareness_at && (
        <p className="uw-hint">
          Linking moves {later.ref}'s awareness {daysEarlier(later.awareness_at, earlier.awareness_at)} days earlier, to{" "}
          {earlier.ref}'s: an awareness conflict on the triage list until it is confirmed.
        </p>
      )}
      <label className="ca-field">
        Why
        <input value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      <div className="ca-action-row">
        <button
          type="button"
          className="ac-primary"
          disabled={reason.trim().length < REASON_MIN}
          onClick={() => decide("LINKED")}
        >
          <Link2 size={14} aria-hidden="true" /> Link into one event
        </button>
        <button
          type="button"
          className="ac-link"
          disabled={reason.trim().length < REASON_MIN}
          onClick={() => decide("DISMISSED")}
        >
          Not the same: dismiss
        </button>
      </div>
      <InlineError text={error} />
    </div>
  );
}

function LinkRow({ link, onDone }: { link: DuplicateList["links"][number]; onDone: () => void }) {
  const [undoing, setUndoing] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const label = link.state === "LINKED" ? "Linked" : link.state === "DISMISSED" ? "Dismissed" : "Link undone";
  return (
    <li>
      {label}: {link.left.ref} and {link.right.ref} · {formatDate(link.decided_at)} · {link.reason}
      {link.conflict && link.state === "LINKED"
        ? ` · awareness ${daysEarlier(link.awareness_before, link.awareness_after)} days earlier`
        : ""}
      {link.undo_reason ? ` · undone: ${link.undo_reason}` : ""}
      {link.state === "LINKED" &&
        (undoing ? (
          <span className="uw-escalate">
            <input
              aria-label="Why the link is undone"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
            <button
              type="button"
              className="ac-secondary"
              disabled={reason.trim().length < REASON_MIN}
              onClick={async () => {
                setError("");
                try {
                  await send(`${INTAKE}/links/${link.id}/undo`, "POST", { reason });
                  onDone();
                } catch (failure) {
                  setError(errorText(failure, "Not undone"));
                }
              }}
            >
              Undo the link
            </button>
          </span>
        ) : (
          <>
            {" "}
            <button type="button" className="ac-link" onClick={() => setUndoing(true)}>
              <Unlink size={13} aria-hidden="true" /> Undo
            </button>
          </>
        ))}
      <InlineError text={error} />
    </li>
  );
}

function Links({ links, onChanged }: { links: NonNullable<IntakeItem["links"]>; onChanged: () => void }) {
  return (
    <section className="ca-drawer-section">
      <h4>
        <Link2 size={15} aria-hidden="true" /> Linked records
      </h4>
      <ul>
        {links.map((link) => (
          <LinkRow
            key={link.id}
            link={{ ...link, left: { ref: "This call" }, right: { ref: link.other.ref } }}
            onDone={onChanged}
          />
        ))}
      </ul>
    </section>
  );
}
