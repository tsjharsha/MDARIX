import { useState } from "react";
import { CheckCircle2, Clock, FileWarning, Flag, Link2, Siren } from "lucide-react";
import { Empty, Panel, StatTile, ToneBadge } from "../../admin/console/charts";
import { Drawer, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { useCan, useTabParam } from "../workspaceContext";
import { DeadlineChip, HarmChip, StateChip, type Harm } from "../../../app/chips";
import { deadlineLabel } from "../../../app/dates";
import { AlsoKnownAs, countOf } from "./common";
import { ChipFilter, Hero, InlineError } from "./boardParts";
import {
  INTAKE,
  REASON_MIN,
  TRIAGE,
  clockTone,
  daysEarlier,
  deadlineText,
  fromLocalInput,
  hoursText,
  tierTone,
  toLocalInput,
  type Guide,
  type TriageItem,
  type TriageList,
} from "../intake";
import { reportsTab } from "../authorityReports";

/** The second look's rule: triage, opening cases or quality review may write. */
export function useCanTriage() {
  const triage = useCan("signal.triage");
  const create = useCan("investigation.create");
  const quality = useCan("quality.review");
  return triage || create || quality;
}

const SHOWS = [
  { value: "open" as const, label: "To triage" },
  { value: "done" as const, label: "Triaged" },
];

/**
 * Complaints › Triage: before every other queue, each event flagged or escalated by hand and not yet triaged (urgent
 * intakes, flagged calls, flagged imported complaints and set-aside rows that suggest harm), with both clocks: the
 * triage target from when it reached MDARIX, and each market's provisional deadline from awareness (T-G19).
 */
export function Triage({ onOpenTab }: { onOpenTab?: (tab: string) => void }) {
  const [show, setShow] = useState<"open" | "done">("open");
  // The item whose panel is open is part of the address (Triage?item=<key>): Back closes it, refresh keeps it.
  const [openKey, setOpenKey] = useTabParam("item");
  // A complaint's page opens its triage item by the complaint (Triage?complaint=<id>, 0.10.68).
  const [complaint] = useTabParam("complaint");
  const list = useResource<TriageList>(`${TRIAGE}?show=${show}`);
  const summary = list.data?.summary;
  const items = list.data?.items ?? [];
  const wanted = openKey ?? (complaint ? `COMPLAINT:${complaint}` : null);
  const open = wanted ? (items.find((item) => item.key === wanted) ?? null) : null;
  const setOpen = (item: TriageItem | null) => setOpenKey(item ? item.key : null);
  const overdue = items.filter((item) => item.triage_clock.state === "OVERDUE").length;
  return (
    <div className="ac-overview">
      <Hero
        tone={summary ? (summary.open ? "critical" : "good") : "neutral"}
        icon={<Siren size={28} />}
        eyebrow="Triage"
        title={
          summary
            ? summary.open
              ? `${countOf(summary.open, "event")} to triage`
              : "Nothing waits for triage"
            : "The triage list"
        }
        detail="Urgent intakes, flagged calls and records that suggest harm come here first, set-aside import rows included. Regulatory clocks count from awareness, not from when a record reached MDARIX."
      >
        {onOpenTab && (
          <button type="button" className="ac-secondary" onClick={() => onOpenTab("First contact")}>
            Log a call or an urgent intake
          </button>
        )}
      </Hero>
      <div className="uw-cr-stats">
        <StatTile
          label="To triage"
          value={summary ? summary.open : null}
          detail="Flagged or escalated, not yet triaged"
          icon={<Flag size={18} />}
          tone={summary?.open ? "critical" : undefined}
          onOpen={() => setShow("open")}
        />
        <StatTile
          label="Past the triage target"
          value={list.data ? (show === "open" ? overdue : null) : null}
          detail="24 hours from when it reached MDARIX"
          icon={<Clock size={18} />}
          tone={overdue ? "warning" : undefined}
          onOpen={() => setShow("open")}
        />
        <StatTile
          label="Awareness conflicts"
          value={summary ? summary.conflicts : null}
          detail="A linked source knew earlier"
          icon={<Link2 size={18} />}
          onOpen={() => setShow("open")}
        />
        <StatTile
          label="Triaged"
          value={summary ? summary.done : null}
          detail="With a triage record"
          icon={<CheckCircle2 size={18} />}
          onOpen={() => setShow("done")}
        />
      </div>
      <Panel
        eyebrow="Triage list"
        title={show === "open" ? "Most urgent first" : "Triaged, with their records"}
        source={list}
      >
        <div className="uw-cr-toolbar">
          <ChipFilter label="Which events" options={SHOWS} value={show} onChange={setShow} />
        </div>
        {items.length ? (
          <ul className="uw-cr-list">
            {items.map((item) => (
              <TriageCard key={item.key} item={item} onOpen={() => setOpen(item)} onOpenTab={onOpenTab} />
            ))}
          </ul>
        ) : (
          <Empty
            title={show === "open" ? "Nothing to triage" : "Nothing triaged yet"}
            detail="A flagged call, an urgent intake or a record that suggests harm appears here at once."
            action={
              onOpenTab && (
                <button type="button" className="ac-secondary" onClick={() => onOpenTab("First contact")}>
                  Log a call or an urgent intake
                </button>
              )
            }
          />
        )}
        {list.data && (
          <p className="uw-ma-starter" role="note">
            <FileWarning size={15} aria-hidden="true" /> Provisional deadlines use the shortest category the facts do
            not yet exclude, per market. {list.data.starter_mark}
          </p>
        )}
      </Panel>
      {open && list.data && (
        <TriageDrawer
          item={open}
          people={list.data.people}
          onClose={() => setOpen(null)}
          onDone={() => {
            setOpen(null);
            list.reload();
          }}
        />
      )}
    </div>
  );
}

/** The harm a flag names, for its chip's shape; null for a flag that names no harm (an urgent intake, by hand). */
const flagHarm = (code: string): Harm | null =>
  code === "DEATH"
    ? "critical"
    : code === "SERIOUS_INJURY" || code === "HARM_LEVEL"
      ? "serious"
      : ["MALFUNCTION", "HARM_UNKNOWN", "HARM_WORDS"].includes(code)
        ? "none"
        : null;

function TriageCard({
  item,
  onOpen,
  onOpenTab,
}: {
  item: TriageItem;
  onOpen: () => void;
  onOpenTab?: (tab: string) => void;
}) {
  const first = item.deadlines[0];
  return (
    <li className="uw-cr-card">
      <span className={`uw-cr-rail tone-${tierTone(item.tier)}`} aria-hidden="true" />
      <div className="uw-cr-body">
        <div className="uw-cr-head">
          <strong className="uw-cr-id">{item.ref}</strong>
          <span className="uw-cr-meta">
            {item.identifier && item.identifier !== item.ref ? `${item.identifier} · ` : ""}
            {item.source}
            {item.product_name ? ` · ${item.product_name}` : ""}
            {item.lot ? ` · ${item.lot}` : ""}
          </span>
          <ToneBadge tone={tierTone(item.tier)} label={item.tier_label} />
          {item.awareness.unresolved && <ToneBadge tone="warning" label="Awareness unresolved" />}
          {item.conflict.length > 0 && <ToneBadge tone="critical" label="Awareness conflict" />}
          {item.record?.completed_at && <ToneBadge tone="good" label="Triaged" />}
        </div>
        {item.words && <q className="uw-cr-text uw-cr-clip">{item.words}</q>}
        <ul className="uw-cr-chips" aria-label="Why it is flagged">
          {item.flags.map((flag, index) => (
            <li key={`${flag.code}-${index}`}>
              {flagHarm(flag.code) ? (
                <HarmChip harm={flagHarm(flag.code)!} label={flag.label} />
              ) : (
                <StateChip label={flag.label} />
              )}
            </li>
          ))}
        </ul>
        <p className="uw-cr-due">
          <DeadlineChip item={item.triage_clock} prefix="Triage" />
          {first && !first.not_reportable && (
            <DeadlineChip item={first} prefix={first.role === "SIGNED" ? "Report" : "Report, provisional"} />
          )}
        </p>
        <p className="uw-cr-meta">
          Aware {formatDate(item.awareness.at)} ({item.awareness.source_label}
          {item.awareness.linked_ref ? `: ${item.awareness.linked_ref}` : ""}) · reached MDARIX {item.delay.text} later
        </p>
        {first && (
          <p className="uw-cr-meta">
            {first.role === "SIGNED" ? "Deadline" : "Provisional deadline"}: {first.label},{" "}
            {first.not_reportable ? "concluded not reportable" : deadlineLabel(first)}
            {item.deadlines.length > 1 && first.own ? " · other markets only if also reportable" : ""}
            {first.role === "OWN_NO_WINDOW" ? " · no reporting window for the event's own market" : ""}
            {first.role === "NO_COUNTRY" ? " · no country recorded" : ""}
          </p>
        )}
        {item.linked.length > 0 && (
          <p className="uw-cr-meta">Linked into one event with {item.linked.map((link) => link.ref).join(", ")}</p>
        )}
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={onOpen}>
            {item.record?.completed_at ? "See the triage record" : "Triage"}
          </button>
          {onOpenTab && item.kind === "COMPLAINT" && (
            <>
              <button type="button" className="ac-link" onClick={() => onOpenTab("Reportability")}>
                Next: assess per market
              </button>
              <button type="button" className="ac-link" onClick={() => onOpenTab(reportsTab(item.id))}>
                Its reports
              </button>
            </>
          )}
        </div>
      </div>
    </li>
  );
}

type RecordForm = {
  severity: string;
  threat: boolean;
  remedial: boolean;
  eventOwner: string;
  triageOwner: string;
  backup: string;
  action: string;
  noAction: string;
  aware: string;
  awareNote: string;
};

function TriageDrawer({
  item,
  people,
  onClose,
  onDone,
}: {
  item: TriageItem;
  people: TriageList["people"];
  onClose: () => void;
  onDone: () => void;
}) {
  const guide = useResource<Guide>(`${INTAKE}/guide`);
  const canWrite = useCanTriage();
  const record = item.record;
  const [form, setForm] = useState<RecordForm>({
    severity: record?.severity ?? "",
    threat: record?.public_health_threat ?? false,
    remedial: record?.remedial_action ?? false,
    eventOwner: people[0]?.id ?? "",
    triageOwner: people[0]?.id ?? "",
    backup: "",
    action: record?.immediate_action ?? "",
    noAction: record?.no_action_reason ?? "",
    aware: toLocalInput(item.awareness.at),
    awareNote: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (patch: Partial<RecordForm>) => setForm((current) => ({ ...current, ...patch }));
  const needsAwareness = item.awareness.unresolved || item.conflict.length > 0;
  const problem = !form.severity
    ? "Assess the severity"
    : !form.eventOwner || !form.triageOwner
      ? "Name the event owner and the triage owner"
      : form.action.trim().length < REASON_MIN && form.noAction.trim().length < REASON_MIN
        ? `Record the immediate action, or why none is needed (at least ${REASON_MIN} characters)`
        : needsAwareness && !form.aware
          ? "Confirm the awareness time"
          : null;
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      await send(`${TRIAGE}/${item.kind}/${item.id}/record`, "POST", {
        severity: form.severity,
        public_health_threat: form.threat,
        remedial_action: form.remedial,
        event_owner: form.eventOwner,
        triage_owner: form.triageOwner,
        backup_owner: form.backup,
        immediate_action: form.action,
        no_action_reason: form.noAction,
        awareness_confirmed_at:
          needsAwareness || form.aware !== toLocalInput(item.awareness.at) ? fromLocalInput(form.aware) : null,
        awareness_note: form.awareNote,
      });
      onDone();
    } catch (reason) {
      setError(errorText(reason, "The triage record was not saved"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Drawer title={`Triage ${item.ref}`} onClose={onClose}>
      <div className="uw-dp">
        <AlsoKnownAs id={item.business_id} shown={item.ref} />
        {item.words && <q className="uw-cr-text">{item.words}</q>}
        {item.problems && item.problems.length > 0 && (
          <p className="uw-hint">
            Set aside at import: {item.problems.join("; ")}. It reaches triage while still set aside.
          </p>
        )}
        <section className="ca-drawer-section">
          <h3>Why it is here</h3>
          <ul>
            {item.flags.map((flag, index) => (
              <li key={`${flag.code}-${index}`}>{flag.label}</li>
            ))}
          </ul>
        </section>
        <section className="ca-drawer-section">
          <h3>Two clocks</h3>
          <p>
            <strong>Triage target:</strong> {item.triage_clock.target_hours} hours from{" "}
            {formatDate(item.triage_clock.from)} (when it reached MDARIX or was reopened): due{" "}
            {formatDate(item.triage_clock.due_at)}, {hoursText(item.triage_clock)}.
          </p>
          <p>
            <strong>Regulatory clocks</strong> count from awareness: {formatDate(item.awareness.at)} (
            {item.awareness.source_label}
            {item.awareness.linked_ref ? `: ${item.awareness.linked_ref}` : ""}). It reached MDARIX {item.delay.text}{" "}
            later.
          </p>
          {item.awareness.label && <p className="uw-hint">{item.awareness.label}.</p>}
          {item.conflict.map((conflict) => (
            <p key={conflict.link} className="uw-hint" role="alert">
              Awareness conflict: a linked source knew {daysEarlier(conflict.before, conflict.after)} days earlier.
              Every deadline below now counts from {formatDate(conflict.after)}. Confirm the awareness time to clear it.
            </p>
          ))}
          <div className="uw-tr-scroll">
            <table className="uw-tr-table">
              <thead>
                <tr>
                  <th scope="col">Market</th>
                  <th scope="col">Category</th>
                  <th scope="col">Deadline</th>
                </tr>
              </thead>
              <tbody>
                {item.deadlines.map((deadline) => (
                  <tr key={deadline.market}>
                    <td>
                      {deadline.label}
                      <small className="ac-muted uw-tr-role">{deadline.role_label}</small>
                    </td>
                    <td>
                      {deadline.not_reportable
                        ? deadline.basis
                        : deadline.role === "SIGNED"
                          ? `${deadline.basis}, signed`
                          : `${deadline.tier_label}: ${deadline.basis}`}
                    </td>
                    <td>
                      <span className={`uw-clock tone-${clockTone(deadline.state ?? "")}`}>
                        {deadlineText(deadline)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        {record?.completed_at ? (
          <section className="ca-drawer-section">
            <h3>
              <CheckCircle2 size={15} aria-hidden="true" /> Triage record
            </h3>
            <p>
              Severity {record.severity_label} · event owner {record.event_owner_name} · triage owner{" "}
              {record.triage_owner_name}
              {record.backup_owner_name ? ` · backup ${record.backup_owner_name}` : ""}
            </p>
            <p>{record.immediate_action ?? `No immediate action: ${record.no_action_reason}`}</p>
            <p className="uw-cr-meta">
              {record.completed_by} · {formatDate(record.completed_at)}
              {record.public_health_threat ? " · possible serious public health threat" : ""}
            </p>
          </section>
        ) : null}
        {canWrite && (!record?.completed_at || item.conflict.length > 0) && (
          <form
            className="ca-drawer-section"
            onSubmit={(event) => {
              event.preventDefault();
              if (!problem) void submit();
            }}
          >
            <h3>The triage record</h3>
            <div className="ca-form-grid">
              <label className="ca-field">
                Severity (harm-severity scale)
                <select value={form.severity} onChange={(event) => set({ severity: event.target.value })}>
                  <option value="">Choose…</option>
                  {(guide.data?.levels ?? []).map((level) => (
                    <option key={level.code} value={level.code}>
                      {level.label}
                    </option>
                  ))}
                </select>
              </label>
              <PersonSelect
                label="Event owner"
                people={people}
                value={form.eventOwner}
                onChange={(v) => set({ eventOwner: v })}
              />
              <PersonSelect
                label="Triage owner"
                people={people}
                value={form.triageOwner}
                onChange={(v) => set({ triageOwner: v })}
              />
              <PersonSelect
                label="Backup (where you have a second person)"
                people={people}
                value={form.backup}
                optional
                onChange={(v) => set({ backup: v })}
              />
            </div>
            <label className="ca-check">
              <input
                type="checkbox"
                checked={form.threat}
                onChange={(event) => set({ threat: event.target.checked })}
              />
              Possible serious public health threat (its 2-day clock applies until a signed decision excludes it)
            </label>
            <label className="ca-check">
              <input
                type="checkbox"
                checked={form.remedial}
                onChange={(event) => set({ remedial: event.target.checked })}
              />
              Remedial action may be needed to prevent an unreasonable risk of substantial harm (US: 5 work days)
            </label>
            <label className="ca-field">
              Immediate action
              <textarea value={form.action} onChange={(event) => set({ action: event.target.value })} rows={2} />
            </label>
            <label className="ca-field">
              Or why none is needed
              <textarea value={form.noAction} onChange={(event) => set({ noAction: event.target.value })} rows={2} />
            </label>
            <div className="ca-form-grid">
              <label className="ca-field">
                Awareness time {needsAwareness ? "(confirm it)" : ""}
                <input
                  type="datetime-local"
                  value={form.aware}
                  onChange={(event) => set({ aware: event.target.value })}
                />
              </label>
              <label className="ca-field">
                Why, if later than the earliest known
                <input value={form.awareNote} onChange={(event) => set({ awareNote: event.target.value })} />
              </label>
            </div>
            {problem && <p className="uw-hint">{problem}</p>}
            <div className="ca-action-row">
              <button type="submit" className="ac-primary" disabled={busy || !!problem}>
                {busy ? "Saving…" : "Save the triage record"}
              </button>
            </div>
            <InlineError text={error} />
          </form>
        )}
      </div>
    </Drawer>
  );
}

function PersonSelect({
  label,
  people,
  value,
  optional,
  onChange,
}: {
  label: string;
  people: TriageList["people"];
  value: string;
  optional?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="ca-field">
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">{optional ? "None" : "Choose…"}</option>
        {people.map((person) => (
          <option key={person.id} value={person.id}>
            {person.name}
          </option>
        ))}
      </select>
    </label>
  );
}

/**
 * "Escalate to triage": any trial user can send a record to triage by hand, from any queue, whatever the automatic
 * flag says (T-G19, TA-19.4). Asks for a reason; the record then leads the triage list.
 */
export function EscalateButton({
  kind,
  id,
  label = "Escalate to triage",
  onDone,
}: {
  kind: "INTAKE" | "COMPLAINT" | "QUARANTINE";
  id: string;
  label?: string;
  onDone?: () => void;
}) {
  const canWrite = useCanTriage();
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  const [error, setError] = useState("");
  if (!canWrite) return null;
  if (state === "done") return <span className="uw-cr-meta">Escalated: it leads the triage list</span>;
  if (!asking)
    return (
      <button type="button" className="ac-link" onClick={() => setAsking(true)}>
        <Siren size={13} aria-hidden="true" /> {label}
      </button>
    );
  const short = reason.trim().length < REASON_MIN;
  return (
    <span className="uw-escalate">
      <input
        aria-label="Why it needs triage"
        placeholder="Why it needs triage"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
      />
      <button
        type="button"
        className="ac-secondary"
        disabled={short || state === "busy"}
        onClick={async () => {
          setState("busy");
          setError("");
          try {
            await send(`${TRIAGE}/escalate`, "POST", { kind, id, reason: reason.trim() });
            setState("done");
            onDone?.();
          } catch (failure) {
            setState("idle");
            setError(errorText(failure, "Not escalated"));
          }
        }}
      >
        Escalate
      </button>
      <button type="button" className="ac-link" onClick={() => setAsking(false)}>
        Cancel
      </button>
      <InlineError text={error} />
    </span>
  );
}
