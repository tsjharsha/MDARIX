import { useState, type ReactNode } from "react";
import { WhyAsked } from "../../shared/Basis";
import { TRIAGE_WHY } from "../whyAsked";
import { CheckCircle2, Clock, FileWarning, Flag, Link2, Siren } from "lucide-react";
import { Empty, Panel, StatTile, ToneBadge } from "../../admin/console/charts";
import { Drawer, errorText, formatDate, humanize, send, useResource } from "../../customer-admin/shared";
import { useCan, useIsTrial, useTabParam, useWorkspace } from "../workspaceContext";
import { withTabParam } from "../workspaceAddress";
import { DeadlineChip, HarmChip, StateChip, type Harm } from "../../../app/chips";
import { awarenessText, deadlineLabel } from "../../../app/dates";
import { AlsoKnownAs, countOf } from "./common";
import { ChipFilter, Hero, InlineError } from "./boardParts";
import {
  CONTAINMENT,
  INTAKE,
  REASON_MIN,
  TRIAGE,
  clockTone,
  harmRank,
  harmScale,
  triageBody,
  triageDowngrade,
  triageProblem,
  triageSpeed,
  type TriageForm,
  daysEarlier,
  deadlineText,
  awarenessInput,
  hoursText,
  tierTone,
  type Guide,
  type TriageItem,
  type TriageList,
} from "../intake";
import { reportsTab } from "../authorityReports";

/** Who may triage (B2 step 4, OD-4): the server's complaint.triage permission. */
export function useCanTriage() {
  return useCan("complaint.triage");
}

/** Who may escalate to triage by hand: any workspace role that may log a Case or triage (the server takes any role). */
export function useCanEscalate() {
  const log = useCan("case.log");
  const triage = useCan("complaint.triage");
  return log || triage;
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
  // A story opens its record by the reference people read (Triage?ref=SAMPLE-URG-01, 0.10.71).
  const [ref] = useTabParam("ref");
  // A call's next action on Home opens its own card (Triage?intake=<id>, 0.10.82, navigation M5).
  const [intake] = useTabParam("intake");
  const { reportTab, shownTab } = useWorkspace();
  const list = useResource<TriageList>(`${TRIAGE}?show=${show}`);
  const summary = list.data?.summary;
  const items = list.data?.items ?? [];
  const wanted =
    openKey ??
    (complaint ? `COMPLAINT:${complaint}` : null) ??
    (intake ? `INTAKE:${intake}` : null) ??
    (ref ? (items.find((item) => item.ref === ref || item.identifier === ref)?.key ?? null) : null);
  const open = wanted ? (items.find((item) => item.key === wanted) ?? null) : null;
  const setOpen = (item: TriageItem | null) => {
    if (item || !reportTab || !shownTab) return setOpenKey(item ? item.key : null);
    // Closing clears every parameter that opens the panel, in one address change: complaint= or ref= left behind
    // would open it again at once (0.10.79).
    reportTab(
      ["item", "complaint", "ref", "intake"].reduce((tab, name) => withTabParam(tab, name, null), shownTab),
      "push",
    );
  };
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
          detail="Fast track within hours; routine by the end of the next working day"
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
          {item.speed_label && !item.record?.completed_at && (
            <ToneBadge tone={item.speed === "FAST" ? "critical" : "neutral"} label={item.speed_label} />
          )}
          {item.acknowledgement?.overdue && <ToneBadge tone="critical" label="Acknowledgement overdue" />}
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
          Aware {awarenessText(item.awareness.at, item.awareness.date_only)} ({item.awareness.source_label}
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

function TriageDrawer({
  item,
  people,
  onClose,
  onDone,
  inline = false,
}: {
  item: TriageItem;
  people: TriageList["people"];
  onClose: () => void;
  onDone: () => void;
  /** On the complaint's own page (0.10.72, B3): a panel there, not a drawer over the triage list. */
  inline?: boolean;
}) {
  const guide = useResource<Guide>(`${INTAKE}/guide`);
  const canWrite = useCanTriage();
  const trial = useIsTrial();
  const { navigation, open } = useWorkspace();
  const record = item.record;
  const levels = guide.data?.levels ?? [];
  const scale = harmScale(levels);
  const awareField = awarenessInput(item.awareness);
  const prefill = item.speed === "ROUTINE" && !record?.completed_at ? (item.routine_prefill ?? null) : null;
  // "Change something" on the routine card, or "Update triage" on a saved record, opens the full form.
  const [editing, setEditing] = useState(!prefill && !record?.completed_at);
  const [showVersions, setShowVersions] = useState(false);
  // A former colleague is never pre-filled: the server takes owners from the active team only.
  const active = (id: string | null | undefined) => (people.some((person) => person.id === id) ? id : null);
  const owner = active(record?.triage_owner) ?? active(prefill?.triage_owner) ?? people[0]?.id ?? "";
  const [form, setForm] = useState<TriageForm>({
    severity: record?.severity ?? prefill?.severity ?? "",
    potential: record?.potential_severity ?? "",
    threat: record?.public_health_threat ?? false,
    threatReason: "",
    remedial: record?.remedial_action ?? false,
    remedialReason: "",
    eventOwner: active(record?.event_owner) ?? owner,
    triageOwner: owner,
    backup: active(record?.backup_owner) ?? "",
    containment: record?.containment?.choices ?? prefill?.containment ?? [],
    text:
      record?.containment?.text ??
      record?.immediate_action ??
      record?.no_action_reason ??
      prefill?.no_action_reason ??
      "",
    aware: awareField.initial,
    awareNote: "",
    changeReason: "",
    password: "",
    mfa: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (patch: Partial<TriageForm>) => setForm((current) => ({ ...current, ...patch }));
  const needsAwareness = item.awareness.unresolved || item.conflict.length > 0;
  const laterAware = awareField.later(form.aware);
  const pace = triageSpeed(item, levels, form);
  const signs = laterAware || (trial && triageDowngrade(record, levels, form, pace));
  const problem = triageProblem(item, levels, form, { people: people.length, needsAwareness, laterAware, signs });
  const floor = harmRank(levels, item.severity_floor);
  const base = `${TRIAGE}/${item.kind}/${item.id}`;
  // The next step, always (stage 8): on the new navigation a triaged complaint opens its page, whose main button is
  // its next action (done on that page already, it stays there).
  const next = () => {
    if (navigation === "new" && item.kind === "COMPLAINT" && !inline)
      open("Complaint", `Summary?ref=${encodeURIComponent(item.ref)}`);
  };
  const run = async (path: string, body: unknown, failure: string, after?: () => void) => {
    setBusy(true);
    setError("");
    try {
      await send(path, "POST", body);
      onDone();
      after?.();
    } catch (reason) {
      setError(errorText(reason, failure));
    } finally {
      setBusy(false);
    }
  };
  const awareness = needsAwareness || form.aware !== awareField.initial ? awareField.moment(form.aware) : null;
  const submit = () =>
    run(`${base}/record`, triageBody(form, record, awareness), "The triage record was not saved", next);
  const Frame = inline ? InlineFrame : Drawer;
  const ack = item.acknowledgement;
  const label = (code: string | null | undefined) => scale.find((level) => level.code === code)?.label ?? code;
  return (
    <Frame title={`Triage ${item.ref}`} onClose={onClose}>
      <div className="uw-dp">
        <AlsoKnownAs id={item.business_id} shown={item.ref} />
        {item.speed_label && (
          <p>
            <strong>
              {item.speed_label} · due {hoursText(item.triage_clock)}
            </strong>{" "}
            <span className="uw-cr-meta">{item.speed_why}</span>
          </p>
        )}
        {item.words && <q className="uw-cr-text">{item.words}</q>}
        {item.problems && item.problems.length > 0 && (
          <p className="uw-hint">
            Set aside at import: {item.problems.join("; ")}. It reaches triage while still set aside.
          </p>
        )}
        {ack?.required && (
          <p className={ack.overdue ? "uw-hint" : "uw-cr-meta"} role={ack.overdue ? "alert" : undefined}>
            {ack.done
              ? `Acknowledged by ${ack.acknowledged_by}.`
              : `${ack.overdue ? "Acknowledgement overdue since" : "A named owner acknowledges it by"} ${formatDate(ack.due_at)}.`}{" "}
            {!ack.done && canWrite && (
              <button
                type="button"
                className="ac-secondary"
                disabled={busy}
                onClick={() => void run(`${base}/acknowledge`, {}, "Not acknowledged")}
              >
                Acknowledge
              </button>
            )}
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
            <strong>Regulatory clocks</strong> count from awareness:{" "}
            {awarenessText(item.awareness.at, item.awareness.date_only)} ({item.awareness.source_label}
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
              {record.version ? ` · version ${record.version}` : ""}
            </h3>
            <p>
              Harm now {record.severity_label ?? label(record.severity) ?? "—"}
              {record.potential_severity ? ` · if it happened again ${label(record.potential_severity)}` : ""} · event
              owner {record.event_owner_name} · triage owner {record.triage_owner_name}
              {record.backup_owner_name ? ` · backup ${record.backup_owner_name}` : ""}
            </p>
            <p>
              {record.containment?.choices?.length
                ? `${record.containment.choices.map((code) => CONTAINMENT.find((c) => c.code === code)?.label ?? code).join(", ")}: `
                : ""}
              {record.immediate_action ?? record.no_action_reason}
            </p>
            <p className="uw-cr-meta">
              {record.completed_by} · {formatDate(record.completed_at)}
              {record.public_health_threat ? " · possible serious public health threat" : ""}
              {record.threat_excluded_at ? ` · threat excluded ${formatDate(record.threat_excluded_at)}` : ""}
            </p>
            <div className="ca-action-row">
              {canWrite && !editing && (
                <button type="button" className="ac-secondary" onClick={() => setEditing(true)}>
                  Update triage
                </button>
              )}
              <button type="button" className="ac-link" onClick={() => setShowVersions((shown) => !shown)}>
                Versions
              </button>
              {canWrite && record.public_health_threat && (
                <ExcludeThreat path={`${base}/exclude-threat`} onDone={onDone} />
              )}
            </div>
            {showVersions && <TriageVersions path={`${base}/versions`} />}
          </section>
        ) : null}
        {canWrite && prefill && !editing && (
          <section className="ca-drawer-section">
            <h3>Routine triage · due {formatDate(item.triage_clock.due_at)}</h3>
            <ul>
              <li>Owner: {people.find((person) => person.id === prefill.triage_owner)?.name ?? "you"}</li>
              <li>Harm now: {prefill.harm_now_label}</li>
              <li>Immediate action: {prefill.no_action_reason}</li>
            </ul>
            <div className="ca-action-row">
              <button
                type="button"
                className="ac-primary"
                disabled={busy}
                onClick={() =>
                  void run(
                    `${base}/confirm`,
                    { seen_version: record?.version ?? 0 },
                    "The triage was not confirmed",
                    next,
                  )
                }
              >
                {busy ? "Saving…" : "Confirm triage"}
              </button>
              <button type="button" className="ac-secondary" onClick={() => setEditing(true)}>
                Change something
              </button>
            </div>
          </section>
        )}
        {canWrite && (editing || item.conflict.length > 0) && (
          <form
            className="ca-drawer-section"
            onSubmit={(event) => {
              event.preventDefault();
              if (!problem) void submit();
            }}
          >
            <h3>{record?.completed_at ? "Update triage" : "The triage record"}</h3>
            <div className="ca-form-grid">
              <label className="ca-field">
                Harm now
                <WhyAsked why={TRIAGE_WHY.severity} />
                <select value={form.severity} onChange={(event) => set({ severity: event.target.value })}>
                  <option value="">Choose…</option>
                  {scale.map((level) => (
                    <option
                      key={level.code}
                      value={level.code}
                      disabled={floor >= 0 && harmRank(levels, level.code) < floor}
                    >
                      {level.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="ca-field">
                Harm if it happened again{item.facts?.malfunction ? "" : " (optional)"}
                <select value={form.potential} onChange={(event) => set({ potential: event.target.value })}>
                  <option value="">Choose…</option>
                  {scale.map((level) => (
                    <option key={level.code} value={level.code}>
                      {level.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {item.floor_note && <p className="uw-hint">{item.floor_note}</p>}
            <div className="ca-form-grid">
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
                label={pace === "FAST" && people.length >= 2 ? "Backup" : "Backup (where you have a second person)"}
                people={people.filter((person) => person.id !== form.triageOwner)}
                value={form.backup}
                optional
                onChange={(v) => set({ backup: v })}
              />
            </div>
            <WhyAsked why={TRIAGE_WHY.owners} />
            <fieldset className="ca-field">
              <legend>Containment</legend>
              {CONTAINMENT.map((choice) => (
                <label key={choice.code} className="ca-check">
                  <input
                    type="checkbox"
                    checked={form.containment.includes(choice.code)}
                    onChange={(event) =>
                      set({
                        // "None needed" stands alone; choosing an action clears it.
                        containment: !event.target.checked
                          ? form.containment.filter((code) => code !== choice.code)
                          : choice.code === "NONE_NEEDED"
                            ? ["NONE_NEEDED"]
                            : [...form.containment.filter((code) => code !== "NONE_NEEDED"), choice.code],
                      })
                    }
                  />
                  {choice.label}
                </label>
              ))}
            </fieldset>
            <label className="ca-field">
              What was done, or why nothing is needed
              <WhyAsked why={TRIAGE_WHY.action} />
              <textarea value={form.text} onChange={(event) => set({ text: event.target.value })} rows={2} />
            </label>
            <label className="ca-check">
              <input
                type="checkbox"
                checked={form.threat}
                onChange={(event) => set({ threat: event.target.checked })}
              />
              Possible serious public health threat (its 2-day clock applies until a signed decision excludes it)
            </label>
            {item.facts?.death && !form.threat && (
              <label className="ca-field">
                A death is recorded: why is it not a possible serious public health threat?
                <input value={form.threatReason} onChange={(event) => set({ threatReason: event.target.value })} />
              </label>
            )}
            <label className="ca-check">
              <input
                type="checkbox"
                checked={form.remedial}
                onChange={(event) => set({ remedial: event.target.checked })}
              />
              Remedial action may be needed to prevent an unreasonable risk of substantial harm (US: 5 work days)
            </label>
            {record?.remedial_action && !form.remedial && (
              <label className="ca-field">
                Why remedial action is no longer thought to be needed
                <input value={form.remedialReason} onChange={(event) => set({ remedialReason: event.target.value })} />
              </label>
            )}
            <div className="ca-form-grid">
              <label className="ca-field">
                {awareField.day ? "Awareness date (time not recorded)" : "Awareness time"}{" "}
                {needsAwareness ? "(confirm it)" : ""}
                <WhyAsked why={TRIAGE_WHY.awareness} />
                <input
                  type={awareField.type}
                  value={form.aware}
                  onChange={(event) => set({ aware: event.target.value })}
                />
              </label>
              {/* Asked as soon as it is needed (0.10.84, M7), never after a refused save. */}
              {laterAware && (
                <label className="ca-field">
                  Why is it later than the earliest known? Who knew, and for whom
                  <input value={form.awareNote} onChange={(event) => set({ awareNote: event.target.value })} />
                </label>
              )}
            </div>
            {laterAware && <p className="uw-hint">A later awareness lengthens every clock: it is signed.</p>}
            {record?.completed_at && (
              <label className="ca-field">
                Why the triage changes
                <input value={form.changeReason} onChange={(event) => set({ changeReason: event.target.value })} />
              </label>
            )}
            {signs && (
              <div className="ca-form-grid">
                <label className="ca-field">
                  Your password (signature)
                  <input
                    type="password"
                    autoComplete="current-password"
                    value={form.password}
                    onChange={(event) => set({ password: event.target.value })}
                  />
                </label>
                <label className="ca-field">
                  Code from your authenticator app (if asked)
                  <input
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    value={form.mfa}
                    onChange={(event) => set({ mfa: event.target.value })}
                  />
                </label>
              </div>
            )}
            {problem && <p className="uw-hint">{problem}</p>}
            <div className="ca-action-row">
              <button type="submit" className="ac-primary" disabled={busy || !!problem} title={problem || undefined}>
                {busy ? "Saving…" : "Save the triage"}
              </button>
            </div>
          </form>
        )}
        <InlineError text={error} />
      </div>
    </Frame>
  );
}

type TriageVersion = {
  version: number;
  changed_by: string;
  changed_at: string;
  change_reason: string | null;
  changed_fields: Record<string, { old: unknown; new: unknown }> | null;
  signed: boolean;
};

/** "Versions": who changed what, old → new (spec 4.7). */
function TriageVersions({ path }: { path: string }) {
  const versions = useResource<{ items: TriageVersion[] }>(path);
  const items = versions.data?.items ?? [];
  if (!items.length) return <p className="uw-cr-meta">{versions.data ? "No versions yet." : "Loading…"}</p>;
  return (
    <ol>
      {items.map((row) => (
        <li key={row.version}>
          <strong>Version {row.version}</strong> · {row.changed_by} · {formatDate(row.changed_at)}
          {row.signed ? " · signed" : ""}
          {row.change_reason ? `: ${row.change_reason}` : ""}
          {row.changed_fields && Object.keys(row.changed_fields).length > 0 && (
            <ul className="uw-cr-meta">
              {Object.entries(row.changed_fields).map(([name, change]) => (
                <li key={name}>
                  {humanize(name)}: {humanize(change.old)} → {humanize(change.new)}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ol>
  );
}

/** "Exclude the threat": a reason, the password and the code (TR-06); the history keeps both. */
function ExcludeThreat({ path, onDone }: { path: string; onDone: () => void }) {
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!asking)
    return (
      <button type="button" className="ac-link" onClick={() => setAsking(true)}>
        Exclude the threat
      </button>
    );
  return (
    <div className="ca-form-grid">
      <label className="ca-field">
        Why the threat is excluded
        <input value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      <label className="ca-field">
        Your password (signature)
        <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
      </label>
      <label className="ca-field">
        Code (if asked)
        <input inputMode="numeric" value={code} onChange={(event) => setCode(event.target.value)} />
      </label>
      <div className="ca-action-row">
        <button
          type="button"
          className="ac-primary"
          disabled={busy || reason.trim().length < REASON_MIN || !password}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await send(path, "POST", { reason: reason.trim(), password, mfa_code: code.trim() || null });
              onDone();
            } catch (failure) {
              setError(errorText(failure, "The threat was not excluded"));
            } finally {
              setBusy(false);
            }
          }}
        >
          Sign and exclude
        </button>
        <button type="button" className="ac-link" onClick={() => setAsking(false)}>
          Cancel
        </button>
      </div>
      <InlineError text={error} />
    </div>
  );
}

function InlineFrame({ title, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <section className="uw-cp-triage ac-panel" id="cp-triage" aria-labelledby="cp-triage-title">
      <h2 id="cp-triage-title">{title}</h2>
      {children}
    </section>
  );
}

/** The triage record on the complaint's own page (0.10.72, B3): its triage panel, saved there. */
export function InlineTriage({ complaintId, onDone }: { complaintId: string; onDone: () => void }) {
  const list = useResource<TriageList>(TRIAGE);
  const item = list.data?.items.find((row) => row.kind === "COMPLAINT" && row.id === complaintId);
  if (!list.data || !item) return null;
  return <TriageDrawer item={item} people={list.data.people} onClose={() => undefined} onDone={onDone} inline />;
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
  const canWrite = useCanEscalate();
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
