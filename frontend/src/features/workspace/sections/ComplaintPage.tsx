import { useEffect, useState, type RefObject } from "react";
import { ChevronRight, History, Send } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { Tabs, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { DeadlineChip, HarmChip } from "../../../app/chips";
import { marketLabel } from "../../../app/labels";
import { NEW_PLACES } from "../../../app/linkTable";
import { offeredTab } from "../../../app/featureSet";
import { renamed, useCan, useOpenTarget, useWorkspace } from "../workspaceContext";
import { tabParam, withTabParam } from "../workspaceAddress";
import { CHECK_TONES, EVENT_TONES, eventPath, type CheckItem, type EventView, type Opens } from "../oversight";
import { communicationsTab } from "../communications";
import { reportsTab } from "../authorityReports";
import { DecisionRecord, OwnerPicker, ReadyForm } from "./Oversight";
import { ProblemCode, useImdrfLinks } from "./ProblemCode";
import { InlineError } from "./boardParts";
import { ChartOrTable, ClockLanes, type Lane } from "./WowCharts";
import { WhyAsked } from "../../shared/Basis";
import { COMPLAINT_STEP_WHY } from "../whyAsked";
import { ServiceWork, serviceText } from "./ServiceWork";
import { ShortStoryPanel } from "./ShortStory";
import { FLAGSHIP } from "../entrance";

export const COMPLAINT_SECTIONS = NEW_PLACES.Complaint.tabs;
type ComplaintSection = (typeof COMPLAINT_SECTIONS)[number];

/** Which checklist items each section of the page holds (closure.py's codes). */
const EVIDENCE_ITEMS = ["FIRST_CONTACT", "REQUESTS", "TASKS"];
const DECISION_ITEMS = ["TRIAGE", "MARKETS", "OBLIGATIONS", "DECISION", "CAPA"];

const HARM = {
  DEATH: { harm: "critical", label: "Death" },
  SERIOUS_INJURY: { harm: "serious", label: "Serious injury" },
  PATIENT_INVOLVED: { harm: "none", label: "Patient involved" },
} as const;

/** "Short words from the description": the header's one line on what happened. */
export const headline = (text: string | null | undefined, max = 140) => {
  const words = (text ?? "").replace(/\s+/g, " ").trim();
  if (!words) return "No description recorded";
  return words.length > max ? `${words.slice(0, max - 1).trimEnd()}…` : words;
};

const LEGAL = ["REPORTING", "OBLIGATION"];

/** One chip per market's legal deadline, then one per kind of the organization's own target (a triage target, a
 * reply due), each the nearest. */
export function deadlineChips(due: NonNullable<EventView["work"]>["due"]) {
  const seen = new Set<string>();
  return due.filter((item) => {
    const key = LEGAL.includes(item.category) ? `market:${item.market ?? ""}` : item.category;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** The one main button: the checklist's next action, else signing "ready to close", else nothing to do. */
export function nextStep(view: Pick<EventView, "summary" | "state" | "blocked">): {
  label: string;
  opens: Opens | null;
} | null {
  if (view.summary.next_action) return { label: view.summary.next_action.label, opens: view.summary.next_action.opens };
  if (view.state === "READY_TO_SIGN") return { label: "Sign ready to close", opens: null };
  return null;
}

/**
 * The header's "Needs attention" (exported for its test): what is open, in what it lacks ("On the triage list: its
 * triage record is not complete"), not the check's goal ("Triage is complete", which read as done). A finished event
 * (no next step) says its open items were signed with its reason.
 */
export function attentionText(blocked: Array<{ detail: string }>, hasStep: boolean): string {
  if (!blocked.length) return "Nothing open";
  if (!hasStep)
    return `Nothing: ${blocked.length === 1 ? "1 item was" : `${blocked.length} items were`} signed open, with a reason`;
  return `${blocked.length} open: ${blocked[0].detail}`;
}

/**
 * One complaint's page (the new navigation, 0.10.68; /app/complaints/<ref>): the Oversight event checklist promoted
 * to a page. Its header answers five questions (what happened, what needs attention, owner, due, next action);
 * its sections are Summary, Evidence, Decisions & actions and History. Every step of the complaint opens from here
 * (triage, the first contact, the market assessments, the reports, communications, the disposition, the
 * investigation, the CAPA and ready to close), each saying who may sign it before the work starts.
 */
export function ComplaintPage({ tab, heading }: { tab?: string; heading?: RefObject<HTMLHeadingElement | null> }) {
  const { open, reportTab, shownTab, story } = useWorkspace();
  const ref = tabParam(tab, "ref") ?? "";
  const resource = useResource<EventView>(ref ? eventPath(ref) : null);
  const [shown, setShown] = useState<EventView | null>(null);
  const view = shown ?? resource.data;
  const [active, setActive] = useState<ComplaintSection>(() => offeredTab(tab, COMPLAINT_SECTIONS, "Summary"));
  const links = useImdrfLinks([view?.event.problem_code]);
  // A link by the complaint's id (stage 6's Oversight?event=<id>) is rewritten to the reference people read.
  const readable = view?.event.ref;
  useEffect(() => {
    if (readable && readable !== ref) reportTab?.(withTabParam(shownTab ?? tab, "ref", readable), "replace");
  }, [readable]);
  const go = useOpenTarget();
  const choose = (next: ComplaintSection) => {
    setActive(next);
    reportTab?.(renamed(shownTab ?? tab, next));
  };
  if (!view)
    return (
      <Panel eyebrow="Complaint" title={ref || "Complaint"} source={resource}>
        {resource.state === "error" && (
          <Empty
            title="This complaint could not be opened"
            detail={errorText(resource.error, "It is not in your organization, or your role cannot open it.")}
            action={
              <button type="button" className="ac-secondary" onClick={() => open("Complaints", "Complaint list")}>
                Open the complaint list
              </button>
            }
          />
        )}
      </Panel>
    );
  const changed = (next: EventView) => {
    setShown(next);
    resource.reload();
  };
  const { event, summary } = view;
  const work = view.work;
  const step = nextStep(view);
  const blocked = view.checklist.filter((item) => item.result === "BLOCKED");
  const nearest = work?.due[0] ?? null;
  const harm = event.harm ? HARM[event.harm] : null;
  const storyShown = story === "short" && event.ref === FLAGSHIP;
  return (
    <div className="uw-cp">
      <header className="uw-cp-head" aria-label="The complaint at a glance">
        <p className="ac-eyebrow">
          Complaint ·{" "}
          {[event.product, event.version, event.lot ? `Lot ${event.lot}` : null].filter(Boolean).join(" · ")}
        </p>
        <h1 ref={heading} tabIndex={-1}>
          {event.ref}
        </h1>
        <p className="uw-cp-what">{headline(event.description)}</p>
        <div className="uw-cp-chips">
          {harm && <HarmChip harm={harm.harm} label={harm.label} />}
          {deadlineChips(work?.due ?? []).map((item) => (
            <DeadlineChip
              key={item.key}
              item={item}
              prefix={LEGAL.includes(item.category) && item.market ? marketLabel(item.market) : item.category_label}
            />
          ))}
          <ToneBadge tone={EVENT_TONES[view.state]} label={view.state_label} />
        </div>
        {view.service?.header && (
          // Completing the service never closes the complaint (0.10.71, A5): the quality work is still open.
          <p className="uw-cp-service" role="status">
            <strong>{view.service.header}</strong> · Quality owner:{" "}
            {work?.owner_name ?? event.owner_name ?? "not named yet"}
            {step ? ` · Next: ${step.label}` : ""}
          </p>
        )}
        <dl className="uw-cp-facts">
          <div>
            <dt>Needs attention</dt>
            <dd>{attentionText(blocked, !!step)}</dd>
          </div>
          <div>
            <dt>Owner</dt>
            <dd>{work?.owner_name ?? event.owner_name ?? "Not named yet"}</dd>
          </div>
          <div>
            <dt>Due</dt>
            <dd>
              {nearest ? `${nearest.title}, ${nearest.due_label ?? formatDate(nearest.due_at)}` : "Nothing dated"}
            </dd>
          </div>
          <div>
            <dt>Stage</dt>
            <dd>{work?.stage ?? "—"}</dd>
          </div>
        </dl>
        <div className="ca-action-row">
          {step ? (
            <button
              type="button"
              // Ready to close is signed by the form in Decisions & actions: shown there, it is that form's button. While
              // the short story shows its step, that step's button is the one main button (0.10.71).
              className={
                storyShown || (!step.opens && active === "Decisions & actions") ? "ac-secondary" : "ac-primary"
              }
              onClick={() => (step.opens ? go(step.opens) : choose("Decisions & actions"))}
            >
              {step.label} <ChevronRight size={15} aria-hidden="true" />
            </button>
          ) : (
            <p className="ac-muted">
              {blocked.length
                ? "Nothing to do: closed in your QMS, signed ready to close with its reason."
                : "Nothing to do: every MDARIX decision on it is signed."}
            </p>
          )}
        </div>
      </header>
      {/* The short story's step to do now (0.10.71, A4), from what was saved on this record. */}
      {storyShown && <ShortStoryPanel view={view} onChanged={changed} />}
      <Tabs tabs={COMPLAINT_SECTIONS} active={active} onChange={choose} label="Complaint sections">
        {active === "Summary" && (
          <>
            <Panel eyebrow="Summary" title="What happened">
              <p>{event.description || "No description recorded."}</p>
              <dl className="uw-ov-summary">
                <dt>Problem code</dt>
                <dd>
                  {event.problem_code ? <ProblemCode code={event.problem_code} links={links} /> : "None recorded"}
                </dd>
                <dt>Product, version, lot</dt>
                <dd>{[event.product, event.version, event.lot].filter(Boolean).join(" · ") || "—"}</dd>
                <dt>Markets</dt>
                <dd>{(work?.markets ?? [event.market]).filter(Boolean).map(marketLabel).join(", ") || "—"}</dd>
                <dt>Awareness</dt>
                <dd>{formatDate(event.awareness_at)}</dd>
                <dt>In your QMS</dt>
                <dd>{event.status_in_qms}</dd>
                <dt>Service work</dt>
                <dd>{serviceText(view)}</dd>
                {event.business_id && event.business_id !== event.ref && (
                  <>
                    <dt>Also known as</dt>
                    <dd>{event.business_id}</dd>
                  </>
                )}
              </dl>
            </Panel>
            <LegalClocks view={view} />
            <Panel eyebrow="Summary" title="Stage">
              <ol className="uw-ov-stages">
                {view.stages.map((stage) => (
                  <li key={stage.code} className={`stage-${stage.state.toLowerCase()}`}>
                    {stage.label}
                    {stage.state === "NOT_NEEDED" && <span className="ac-muted">: not needed</span>}
                  </li>
                ))}
              </ol>
              <p className="ac-muted">
                A summary, not a gate: reporting, investigation and containment can run at once.
              </p>
            </Panel>
            <Panel eyebrow="Summary" title={blocked.length ? "What needs attention" : "Nothing needs attention"}>
              {blocked.length ? (
                <ul className="uw-ov-checks">
                  {blocked.map((item) => (
                    <CheckRow key={item.code} item={item} view={view} onOpen={go} onChanged={changed} />
                  ))}
                </ul>
              ) : (
                <p className="ac-muted">Every step on this complaint is done or not needed.</p>
              )}
            </Panel>
          </>
        )}
        {active === "Evidence" && (
          <Panel eyebrow="Evidence" title="What the record holds">
            <ul className="uw-ov-checks">
              {view.checklist
                .filter((item) => EVIDENCE_ITEMS.includes(item.code))
                .map((item) => (
                  <CheckRow key={item.code} item={item} view={view} onOpen={go} onChanged={changed} />
                ))}
            </ul>
            <div className="ca-action-row">
              <button
                type="button"
                className="ac-secondary"
                onClick={() => open("Complaints", communicationsTab(event.complaint_id))}
              >
                Communications log
              </button>
              <button
                type="button"
                className="ac-secondary"
                onClick={() => open("Complaints", reportsTab(event.complaint_id))}
              >
                Authority reports
              </button>
            </div>
            <p className="ac-muted">
              {summary.open_requests
                ? `${summary.open_requests} ${summary.open_requests === 1 ? "question is" : "questions are"} still open with the reporter or a partner.`
                : "No question is open with the reporter or a partner."}
            </p>
          </Panel>
        )}
        {active === "Decisions & actions" && (
          <>
            <Panel eyebrow="Decisions & actions" title="Each step, and who signs it">
              <ul className="uw-ov-checks">
                {view.checklist
                  .filter((item) => DECISION_ITEMS.includes(item.code))
                  .map((item) => (
                    <CheckRow key={item.code} item={item} view={view} onOpen={go} onChanged={changed} />
                  ))}
              </ul>
              <OwnerPicker view={view} onChanged={changed} />
              <ServiceWork view={view} onChanged={changed} />
            </Panel>
            <Panel eyebrow="Decisions & actions" title="Ready to close">
              <WhyAsked why={COMPLAINT_STEP_WHY.READY} />
              <WhoSigns view={view} code="READY" />
              <ReadyForm view={view} onChanged={changed} />
              {view.changed_since_signed && (
                <p className="tone-warning">
                  Something changed since "ready to close" was signed: read the checklist and sign again.
                </p>
              )}
              <p className="ac-note">{view.never_closes}</p>
            </Panel>
          </>
        )}
        {active === "History" && (
          <Panel eyebrow="History" title="What was signed, and when">
            <DecisionRecord view={view} onChanged={changed} />
            <div className="ca-action-row">
              <button type="button" className="ac-secondary" onClick={() => open("Records", "Audit trail")}>
                <History size={15} aria-hidden="true" /> The audit trail
              </button>
            </div>
          </Panel>
        )}
      </Tabs>
    </div>
  );
}

/** One step: its state, what it is, who signs it, the button that opens it and "Send to" a colleague who may sign. */
function CheckRow({
  item,
  view,
  onOpen,
  onChanged,
}: {
  item: CheckItem;
  view: EventView;
  onOpen: (opens: Opens | null) => void;
  onChanged: (view: EventView) => void;
}) {
  const open = item.result === "BLOCKED" || item.result === "INFO";
  return (
    <li>
      <ToneBadge tone={CHECK_TONES[item.result]} label={item.result_label} />
      <span>
        <strong>{item.label}.</strong> {item.detail}
        {open && <WhyAsked why={COMPLAINT_STEP_WHY[item.code]} />}
        {open && <WhoSigns view={view} code={item.code} />}
      </span>
      <span className="uw-cp-step-actions">
        {item.opens && open && (
          <button type="button" className="ac-secondary" onClick={() => onOpen(item.opens)}>
            {item.action ?? "Open"} <ChevronRight size={13} aria-hidden="true" />
          </button>
        )}
        {item.result === "BLOCKED" && <SendTo view={view} code={item.code} onSent={() => onChanged(view)} />}
      </span>
    </li>
  );
}

/** "Who signs: Asha Rao, Ravi K (you)": the colleagues who may sign this step, told before the work starts (7.8). */
export function WhoSigns({ view, code }: { view: Pick<EventView, "signers">; code: string }) {
  const signers = view.signers?.[code];
  if (!signers) return null;
  const names = signers.people.map((person) => person.name);
  return (
    <small className="uw-who-signs">
      {" "}
      Who signs:{" "}
      {names.length
        ? `${names.join(", ")}${signers.you ? " (you among them)" : ""}`
        : "nobody in your organization yet: an administrator gives a colleague the role"}
      {signers.second_person && ", never the person who prepared it"}.
    </small>
  );
}

/** "Send to <colleague>": the step becomes a task in that person's My work (only a colleague who may sign it). */
function SendTo({ view, code, onSent }: { view: EventView; code: string; onSent: () => void }) {
  const { session, notify } = useWorkspace();
  const canSend =
    useCan("signal.triage") || useCan("investigation.work") || useCan("quality.review") || useCan("regulatory.review");
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const others = (view.signers?.[code]?.people ?? []).filter((person) => person.id !== session?.user_id);
  if (!canSend || !others.length) return null;
  const hint = `send-hint-${code}`;
  return (
    <span className="uw-cp-send">
      <label className="ca-field">
        <span className="sr-only">Send this step to</span>
        <select value={to} onChange={(event) => setTo(event.target.value)} aria-describedby={hint}>
          <option value="">Send to…</option>
          {others.map((person) => (
            <option key={person.id} value={person.id}>
              {person.name}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="ac-secondary"
        disabled={!to || busy}
        aria-describedby={hint}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            const sent = await send<{ to: string }>(`${eventPath(view.event.complaint_id)}/send`, "POST", {
              step: code,
              to_user_id: to,
            });
            notify(`Sent to ${sent.to}: it is in their My work.`);
            setTo("");
            onSent();
          } catch (reason) {
            setError(errorText(reason, "The step was not sent."));
          } finally {
            setBusy(false);
          }
        }}
      >
        <Send size={14} aria-hidden="true" /> Send
      </button>
      <small id={hint} className="sr-only">
        {to ? "Sends this step to their My work." : "Choose a colleague who may sign this step first."}
      </small>
      <InlineError text={error} />
    </span>
  );
}

/**
 * Legal clocks as one lane per market (wow screen 2): from the awareness day to each market's legal deadline (stage
 * 2's one deadline per market), today marked; the markets assessed without a clock are named below.
 */
export function legalLanes(view: Pick<EventView, "event" | "work">): Lane[] {
  return deadlineChips(view.work?.due ?? [])
    .filter((item) => LEGAL.includes(item.category) && item.market)
    .map((item) => ({
      key: item.key,
      market: marketLabel(item.market!),
      from: view.event.awareness_at ?? item.due_at,
      to: item.due_at,
      note: item.title,
      dueText: `Due ${item.due_label ?? formatDate(item.due_at)}`,
      stateText:
        item.state === "OVERDUE"
          ? "Overdue"
          : item.hours_left < 48
            ? `${Math.max(0, Math.round(item.hours_left))} hours left`
            : `${Math.floor(item.hours_left / 24)} days left`,
      overdue: item.state === "OVERDUE",
    }));
}

function LegalClocks({ view }: { view: EventView }) {
  const lanes = legalLanes(view);
  const clocked = new Set(
    (view.work?.due ?? []).filter((item) => LEGAL.includes(item.category)).map((item) => item.market),
  );
  const without = (view.work?.markets ?? []).filter((market) => !clocked.has(market)).map(marketLabel);
  if (!lanes.length && !without.length) return null;
  return (
    <Panel eyebrow="Summary" title="Legal clocks, market by market">
      {lanes.length > 0 && (
        <ChartOrTable
          title={`From the day you became aware (${formatDate(view.event.awareness_at)}) to each deadline`}
          chart={<ClockLanes lanes={lanes} />}
          table={
            <table className="uw-wow-table">
              <caption className="sr-only">Legal clocks, market by market</caption>
              <thead>
                <tr>
                  <th scope="col">Market</th>
                  <th scope="col">Clock</th>
                  <th scope="col">Deadline</th>
                  <th scope="col">Time left</th>
                </tr>
              </thead>
              <tbody>
                {lanes.map((lane) => (
                  <tr key={lane.key}>
                    <th scope="row">{lane.market}</th>
                    <td>{lane.note}</td>
                    <td>{lane.dueText}</td>
                    <td>{lane.stateText}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          }
          note="Each clock counts from the day you became aware; starter rules, for your consultant to confirm."
        />
      )}
      {without.length > 0 && <p className="ac-muted">No legal clock running: {without.join(", ")}.</p>}
    </Panel>
  );
}
