import { useEffect, useState, type RefObject } from "react";
import { Check, ChevronRight, History, MoreHorizontal, Send } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { DeadlineChip, HarmChip } from "../../../app/chips";
import { marketLabel } from "../../../app/labels";
import { tabParts } from "../../../app/linkTable";
import { offeredTab } from "../../../app/featureSet";
import { chooseCase, renamed, useCan, useOpenTarget, useWorkspace } from "../workspaceContext";
import { tabParam, withTabParam } from "../workspaceAddress";
import {
  CHECK_TONES,
  EVENT_TONES,
  eventPath,
  type ActivityItem,
  type CheckItem,
  type EventView,
  type Opens,
  type RelatedGroup,
} from "../oversight";
import { communicationsTab } from "../communications";
import { reportsTab } from "../authorityReports";
import { DecisionRecord, OwnerPicker, ReadyForm } from "./Oversight";
import { ProblemCode, useImdrfLinks } from "./ProblemCode";
import { InlineError } from "./boardParts";
import { type Lane } from "./WowCharts";
import { WhyAsked } from "../../shared/Basis";
import { COMPLAINT_STEP_WHY } from "../whyAsked";
import { ServiceWork, serviceText } from "./ServiceWork";
import { ShortStoryPanel, useShortStory } from "./ShortStory";
import { InlineTriage } from "./Triage";
import { FLAGSHIP } from "../entrance";

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
 * One complaint's page (the new navigation, 0.10.68; /app/complaints/<ref>), in the record page's shape (0.10.74,
 * Release C part C2, the approved design's viewRecord):
 * - a highlights panel: the reference, product, version, lot, chips (harm, each market's deadline, its state), owner,
 *   markets and "also known as";
 * - the path: the stage line as chevrons;
 * - Details (what happened, each step and who signs it, ready to close) · Related (the linked records) · Activity (the
 *   complaint's own audit events in plain words);
 * - a right rail: Next step (one main button), Legal clocks, Who signs and Service work.
 * Every step of the complaint opens from here, each saying who may sign it before the work starts. The former sections'
 * addresses still open: Summary and Decisions & actions on Details, Evidence on Related, History on Activity.
 */
export function ComplaintPage({ tab, heading }: { tab?: string; heading?: RefObject<HTMLHeadingElement | null> }) {
  const { open, reportTab, shownTab, story } = useWorkspace();
  const ref = tabParam(tab, "ref") ?? "";
  const resource = useResource<EventView>(ref ? eventPath(ref) : null);
  const [shown, setShown] = useState<EventView | null>(null);
  const view = shown ?? resource.data;
  const [active, setActive] = useState<ComplaintSection>(() => sectionOf(tab));
  // Ready to close is shown when it is the next step or signed; before that it is revealed on request (one main button).
  const [readyShown, setReadyShown] = useState(false);
  const links = useImdrfLinks([view?.event.problem_code]);
  const storyShown = story === "short" && view?.event.ref === FLAGSHIP;
  const shortStory = useShortStory(storyShown);
  // A link by the complaint's id (stage 6's Oversight?event=<id>) is rewritten to the reference people read; a former
  // section's name to the one that holds it now.
  const readable = view?.event.ref;
  useEffect(() => {
    const now = shownTab ?? tab;
    if (readable && readable !== ref) reportTab?.(withTabParam(renamed(now, active), "ref", readable), "replace");
    else if (tabParts(now).name && tabParts(now).name !== active) reportTab?.(renamed(now, active), "replace");
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
              <button type="button" className="ac-secondary" onClick={() => open("Complaints", "All complaints")}>
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
  const { event } = view;
  const work = view.work;
  const step = nextStep(view);
  const blocked = view.checklist.filter((item) => item.result === "BLOCKED");
  const harm = event.harm ? HARM[event.harm] : null;
  // Triage is done here, on the page (0.10.72, B3): its panel replaces the button that opened the triage list. The
  // short story records the triage in its own step 2.
  const triageHere =
    !storyShown && step?.opens?.target?.tab === "Triage" && step.opens.target.record?.id === event.complaint_id;
  const openHere = (opens: Opens | null) =>
    triageHere && opens?.target?.tab === "Triage"
      ? document.getElementById("cp-triage")?.scrollIntoView({ behavior: "smooth", block: "start" })
      : go(opens);
  // Once the short story reaches its intake decision summary, the summary leads and the rest of the page folds under
  // "The full complaint record" (0.10.72, Addendum 2).
  const summaryLeads = storyShown && (shortStory.data?.current ?? 0) >= 3;
  const markets = (work?.markets?.length ? work.markets : [event.market]).filter(Boolean) as string[];
  const ordered = [...blocked, ...view.checklist.filter((item) => item.result !== "BLOCKED")];
  const readyNow = (!!step && !step.opens) || !!view.ready;
  const record = (
    <>
      <nav className="uw-crumbs" aria-label="Where you are">
        <button type="button" className="ac-link" onClick={() => open("Complaints")}>
          Complaints
        </button>
        <span aria-hidden="true">›</span>
        <span>{event.ref}</span>
      </nav>
      <header className="uw-card uw-highlights" aria-label="The complaint at a glance">
        <div className="uw-hl-top">
          <div className="uw-hl-title">
            <p className="ac-eyebrow">
              Complaint · {[event.product, event.version].filter(Boolean).join(" · ") || "product not recorded"}
            </p>
            <h1 ref={heading} tabIndex={-1}>
              {event.ref}
            </h1>
            <p className="uw-cp-what">{headline(event.description)}</p>
          </div>
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
        </div>
        {view.service?.header && (
          // Completing the service never closes the complaint (0.10.71, A5): the quality work is still open.
          <p className="uw-cp-service" role="status">
            <strong>{view.service.header}</strong> · Quality owner:{" "}
            {work?.owner_name ?? event.owner_name ?? "not named yet"}
            {step ? ` · Next: ${step.label}` : ""}
          </p>
        )}
        <dl className="uw-hl-fields">
          <div>
            <dt>Owner</dt>
            <dd>{work?.owner_name ?? event.owner_name ?? "Not named yet"}</dd>
          </div>
          <div>
            <dt>Markets</dt>
            <dd>{markets.map(marketLabel).join(", ") || "—"}</dd>
          </div>
          <div>
            <dt>Lot</dt>
            <dd className="uw-mono">{event.lot ?? "—"}</dd>
          </div>
          <div>
            <dt>Also known as</dt>
            <dd className="uw-mono">
              {event.business_id && event.business_id !== event.ref ? event.business_id : "—"}
            </dd>
          </div>
        </dl>
        <StagePath stages={view.stages} />
      </header>
      {/* The short story's step to do now (0.10.71, A4), from what was saved on this record. */}
      {storyShown && !summaryLeads && <ShortStoryPanel view={view} onChanged={changed} />}
      {triageHere && <InlineTriage complaintId={event.complaint_id} onDone={() => resource.reload()} />}
      <div className="uw-rec">
        <section className="uw-card uw-rec-main" aria-label="The complaint's record">
          <div className="uw-subtabs" role="tablist" aria-label="Complaint sections">
            {COMPLAINT_SECTIONS.map((name) => (
              <button
                key={name}
                type="button"
                role="tab"
                id={`cp-tab-${name}`}
                aria-selected={active === name}
                aria-controls="cp-panel"
                onClick={() => choose(name)}
              >
                {SECTION_LABELS[name]}
              </button>
            ))}
          </div>
          <div className="uw-rec-body" role="tabpanel" id="cp-panel" aria-labelledby={`cp-tab-${active}`}>
            {active === "Summary" && (
              <>
                <dl className="uw-rec-facts">
                  <dt>What happened</dt>
                  <dd>{event.description || "No description recorded."}</dd>
                  <dt>Harm</dt>
                  <dd>{harm ? harm.label : "None recorded"}</dd>
                  <dt>Problem</dt>
                  <dd>
                    {event.problem_code ? <ProblemCode code={event.problem_code} links={links} /> : "None recorded"}
                  </dd>
                  <dt>Awareness</dt>
                  <dd>
                    {formatDate(event.awareness_at)}
                    <small>The legal clocks count from here.</small>
                  </dd>
                  <dt>In your QMS</dt>
                  <dd>{event.status_in_qms}</dd>
                  <dt>Service work</dt>
                  <dd>{serviceText(view)}</dd>
                </dl>
                <section className="uw-rec-part" aria-label="Each step, and who signs it">
                  <h2>
                    {blocked.length ? "What needs attention, and who signs each step" : "Each step, and who signs it"}
                  </h2>
                  <ul className="uw-ov-checks">
                    {ordered.map((item) => (
                      <CheckRow key={item.code} item={item} view={view} onOpen={openHere} onChanged={changed} />
                    ))}
                  </ul>
                  <OwnerPicker view={view} onChanged={changed} />
                </section>
                {readyNow || readyShown ? (
                  <section className="uw-rec-part" id="cp-ready" aria-label="Ready to close">
                    <h2>Ready to close</h2>
                    <WhyAsked why={COMPLAINT_STEP_WHY.READY} />
                    <WhoSigns view={view} code="READY" />
                    <ReadyForm view={view} onChanged={changed} />
                    {view.changed_since_signed && (
                      <p className="tone-warning">
                        Something changed since "ready to close" was signed: read the checklist and sign again.
                      </p>
                    )}
                    <p className="ac-note">{view.never_closes}</p>
                  </section>
                ) : (
                  <p className="uw-rec-part">
                    <button type="button" className="ac-link" onClick={() => setReadyShown(true)}>
                      Ready to close: signed once every step is done
                    </button>
                  </p>
                )}
              </>
            )}
            {active === "Related" && <Related view={view} onOpen={go} onChanged={changed} />}
            {active === "Activity" && <Activity reference={event.ref} />}
          </div>
        </section>
        <Rail
          view={view}
          step={step}
          triageHere={triageHere}
          storyShown={storyShown}
          onStep={() => {
            if (step?.opens) return go(step.opens);
            choose("Summary");
            document.getElementById("cp-ready")?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
          onChanged={changed}
        />
      </div>
    </>
  );
  return (
    <div className="uw-cp">
      {summaryLeads ? (
        <>
          <p className="ac-eyebrow">Complaint</p>
          <h1 ref={heading} tabIndex={-1} className="uw-cp-title">
            {event.ref}
          </h1>
          <ShortStoryPanel view={view} onChanged={changed} />
          <details className="uw-more uw-cp-full">
            <summary>The full complaint record</summary>
            {record}
          </details>
        </>
      ) : (
        record
      )}
    </div>
  );
}

/** The page's three sections (the first keeps the address name Summary, so every link to it still lands). */
export const COMPLAINT_SECTIONS = ["Summary", "Related", "Activity"] as const;
type ComplaintSection = (typeof COMPLAINT_SECTIONS)[number];
const SECTION_LABELS: Record<ComplaintSection, string> = {
  Summary: "Details",
  Related: "Related",
  Activity: "Activity",
};
/** The sections before 0.10.74, and the one that holds each now. */
const FORMER_SECTIONS: Record<string, ComplaintSection> = {
  Evidence: "Related",
  "Decisions & actions": "Summary",
  History: "Activity",
  Details: "Summary",
};

/** The section a link names: its own, a former one's home, else Details. */
export function sectionOf(tab: string | undefined): ComplaintSection {
  const name = tabParts(tab).name;
  return FORMER_SECTIONS[name] ?? offeredTab(name, COMPLAINT_SECTIONS, "Summary");
}

/** The stage line as chevrons (the record page's path): done, now, later, not needed. */
export function StagePath({ stages }: { stages: EventView["stages"] }) {
  return (
    <ol className="uw-path" aria-label="Stage">
      {stages.map((stage) => {
        const state =
          stage.state === "DONE"
            ? "done"
            : stage.state === "CURRENT"
              ? "now"
              : stage.state === "NOT_NEEDED"
                ? "skip"
                : "later";
        return (
          <li key={stage.code} className={`is-${state}`} aria-current={state === "now" ? "step" : undefined}>
            {state === "done" && <Check size={13} aria-hidden="true" />}
            <span>{stage.label}</span>
            <span className="sr-only">
              {state === "done" ? ": done" : state === "now" ? ": now" : state === "skip" ? ": not needed" : ": later"}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** The right rail: the next step (one main button), the legal clocks, who signs and the service work. */
function Rail({
  view,
  step,
  triageHere,
  storyShown,
  onStep,
  onChanged,
}: {
  view: EventView;
  step: ReturnType<typeof nextStep>;
  triageHere: boolean;
  storyShown: boolean;
  onStep: () => void;
  onChanged: (view: EventView) => void;
}) {
  const blocked = view.checklist.filter((item) => item.result === "BLOCKED");
  const lanes = legalLanes(view);
  const clocked = new Set(
    (view.work?.due ?? []).filter((item) => LEGAL.includes(item.category)).map((item) => item.market),
  );
  const without = (view.work?.markets ?? []).filter((market) => !clocked.has(market)).map(marketLabel);
  const code = blocked[0]?.code ?? "READY";
  const signers = view.signers?.[code];
  return (
    <aside className="uw-rail" aria-label="What to do next">
      <section className="uw-card uw-card-pad uw-rail-next">
        <h2>Next step</h2>
        {triageHere ? (
          <>
            <b>{step?.label}</b>
            <p className="ac-muted">The triage record is below the highlights.</p>
          </>
        ) : step ? (
          <>
            <b>{step.label}</b>
            <p className="ac-muted">{attentionText(blocked, true)}</p>
            <button
              type="button"
              // While the short story shows its step, that step's button is the page's one main button (0.10.71).
              // Sign ready to close is the form's own button in Details: the rail's is then secondary.
              className={storyShown || !step.opens ? "ac-secondary" : "ac-primary"}
              onClick={onStep}
            >
              {step.label} <ChevronRight size={15} aria-hidden="true" />
            </button>
          </>
        ) : (
          <p className="ac-muted">
            {blocked.length
              ? "Nothing to do: closed in your QMS, signed ready to close with its reason."
              : "Nothing to do: every MDARIX decision on it is signed."}
          </p>
        )}
      </section>
      <section className="uw-card uw-card-pad uw-rail-clocks" aria-label="Legal clocks">
        <h2>Legal clocks</h2>
        {lanes.map((lane) => (
          <div key={lane.key} className="uw-rail-clock">
            <div className="uw-home-clock-line">
              <b>{lane.market}</b>
              <span className={`ms-chip ms-chip-deadline is-${lane.overdue ? "overdue" : "soon"}`}>
                {lane.stateText}
              </span>
            </div>
            <span className={`uw-home-lane${lane.overdue ? " is-over" : ""}`} aria-hidden="true">
              <i style={{ width: `${laneUsed(lane)}%` }} />
            </span>
            <small>
              {lane.dueText} · {lane.note}
            </small>
          </div>
        ))}
        {without.length > 0 && <p className="ac-muted">No legal clock running: {without.join(", ")}.</p>}
        {!lanes.length && !without.length && <p className="ac-muted">No market to report to.</p>}
        <p className="ac-note">Each clock counts from awareness. Starter rules, for your consultant to confirm.</p>
      </section>
      <section className="uw-card uw-card-pad uw-rail-signs" aria-label="Who signs">
        <h2>Who signs</h2>
        <p className="ac-muted">{STEP_NAMES[code] ?? "This step"}:</p>
        {signers?.people.length ? (
          <ul className="uw-rail-signers">
            {signers.people.map((person) => (
              <li key={person.id} className="ms-chip">
                {person.name}
              </li>
            ))}
          </ul>
        ) : (
          <p className="ac-muted">Nobody in your organization yet: an administrator gives a colleague the role.</p>
        )}
        {signers?.second_person && <p className="ac-note">Never the person who prepared it.</p>}
        {view.record_people?.practice_note && <p className="ac-note">{view.record_people.practice_note}</p>}
      </section>
      <section className="uw-card uw-card-pad uw-rail-service">
        <ServiceWork view={view} onChanged={onChanged} title="Service work" />
      </section>
    </aside>
  );
}

/** What each step is, for "Who signs". */
const STEP_NAMES: Record<string, string> = {
  TRIAGE: "The triage record",
  FIRST_CONTACT: "The first-contact check",
  MARKETS: "Each market's conclusion",
  OBLIGATIONS: "The authority report's approval",
  DECISION: "The disposition or the investigation's decision",
  CAPA: "The CAPA's effectiveness",
  READY: "Ready to close",
};

/** How much of the way from awareness to the deadline is used (full once overdue, a sliver at least). */
function laneUsed(lane: Lane): number {
  if (lane.overdue) return 100;
  const from = Date.parse(lane.from);
  const to = Date.parse(lane.to);
  if (!Number.isFinite(from) || !Number.isFinite(to) || to <= from) return 4;
  return Math.round(Math.min(100, Math.max(4, ((Date.now() - from) / (to - from)) * 100)));
}

/** Related: the records linked to the complaint, each kind in one or two lines and one way to open it. */
function Related({
  view,
  onOpen,
  onChanged,
}: {
  view: EventView;
  onOpen: (opens: Opens | null) => void;
  onChanged: (view: EventView) => void;
}) {
  const { open, work, notify } = useWorkspace();
  const id = view.event.complaint_id;
  const markets = view.checklist.find((item) => item.code === "MARKETS");
  const action = (group: RelatedGroup): { label: string; run: () => void } | null => {
    if (group.key === "communications")
      return { label: "Open the log", run: () => open("Complaints", communicationsTab(id)) };
    if (group.key === "reports") return { label: "Open the reports", run: () => open("Complaints", reportsTab(id)) };
    if (group.key === "assessments" && markets?.opens)
      return { label: "Open the assessments", run: () => onOpen(markets.opens) };
    if (group.key === "investigations" && group.items?.length) {
      const first = group.items[0];
      return {
        label: `Open ${first.ref}`,
        run: () =>
          void chooseCase(work, first.ref).then((found) =>
            found
              ? open("Investigations", "Summary")
              : notify(`${first.ref} could not be opened right now.`, "critical"),
          ),
      };
    }
    return null;
  };
  return (
    <>
      <ul className="uw-related">
        {(view.related ?? []).map((group) => {
          const go = action(group);
          return (
            <li key={group.key}>
              <span>
                <b>{group.label}</b>
                {group.lines.map((line, index) => (
                  <small key={index}>{line}</small>
                ))}
              </span>
              {go && (
                <button type="button" className="ac-secondary" onClick={go.run}>
                  {go.label}
                </button>
              )}
            </li>
          );
        })}
      </ul>
      <section className="uw-rec-part" aria-label="What was signed, and when">
        <h2>What was signed, and when</h2>
        <DecisionRecord view={view} onChanged={onChanged} />
      </section>
    </>
  );
}

/** Activity: the complaint's own audit events, newest first, in plain words; the record's own start last. */
function Activity({ reference }: { reference: string }) {
  const { open } = useWorkspace();
  const found = useResource<{ items: ActivityItem[]; more: boolean }>(`${eventPath(reference)}/activity`);
  const items = found.data?.items ?? [];
  return (
    <section className="uw-rec-part" aria-label="Activity">
      {found.state === "loading" && !found.data && (
        <p className="ac-muted" role="status">
          Reading the record's activity…
        </p>
      )}
      {found.state === "error" && <InlineError text={errorText(found.error, "The activity could not be read.")} />}
      {found.data && (
        <ol className="uw-timeline">
          {items.map((item, index) => (
            <li key={`${item.at}-${index}`}>
              <time dateTime={item.at ?? undefined}>{item.at ? formatDate(item.at) : "—"}</time>
              <span>
                <b>{item.title}</b>
                {item.who && <small> · {item.who}</small>}
                {item.from_record && <small> · from the complaint record</small>}
                {item.reason && <small className="uw-timeline-reason">{item.reason}</small>}
              </span>
            </li>
          ))}
        </ol>
      )}
      {found.data?.more && <p className="ac-muted">The 100 newest are shown; the audit trail has every one.</p>}
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" onClick={() => open("Records", "Audit trail")}>
          <History size={15} aria-hidden="true" /> The audit trail
        </button>
      </div>
    </section>
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
  // One action per row (0.10.72, B3): "Send to" a colleague sits behind the row's More menu, shown only when a
  // colleague may sign the step.
  return (
    <details className="uw-row-more">
      <summary aria-label="More: send this step to a colleague">
        <MoreHorizontal size={16} aria-hidden="true" />
      </summary>
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
    </details>
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
