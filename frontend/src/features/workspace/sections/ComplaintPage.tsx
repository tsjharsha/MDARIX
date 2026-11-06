import { useEffect, useState, type ReactNode, type RefObject } from "react";
import { Check, ChevronRight, Clock, Globe, History, MoreHorizontal, Package, Send, UserRound } from "lucide-react";
import { ClockRing, Flag, deviceKind } from "../../shared/hero/HeroVisuals";
import { InfusionPumpArt, PatientMonitorArt } from "../../shared/hero/HeroArt";
import { ringOf } from "../heroBits";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { errorText, formatDate, notFound, send, useResource } from "../../customer-admin/shared";
import { DeadlineChip, HarmChip } from "../../../app/chips";
import { marketLabel } from "../../../app/labels";
import { tabParts } from "../../../app/linkTable";
import { offeredTab } from "../../../app/featureSet";
import { chooseCase, renamed, useCan, useIsTrial, useOpenTarget, useWorkspace } from "../workspaceContext";
import { tabParam, withTabParam } from "../workspaceAddress";
import {
  CHECK_TONES,
  eventPath,
  type ActivityItem,
  type CheckItem,
  type EventView,
  type Opens,
  type RelatedGroup,
} from "../oversight";
import { communicationsTab } from "../communications";
import { reportPlace, reportsTab } from "../authorityReports";
import { DecisionRecord, OwnerPicker, ReadyForm } from "./Oversight";
import { ProblemCode, useImdrfLinks } from "./ProblemCode";
import { InlineError } from "./boardParts";
import { type Lane } from "./WowCharts";
import { WhyAsked } from "../../shared/Basis";
import { COMPLAINT_STEP_WHY } from "../whyAsked";
import { ServiceWork, serviceText } from "./ServiceWork";
import { ShortStoryPanel, useShortStory } from "./ShortStory";
import { InlineTriage } from "./Triage";
import { TRIAGE, type TriageList } from "../intake";
import { treePlace } from "./DecisionTrees";
import { FLAGSHIP } from "../entrance";
import { requestJson } from "../../../app/apiClient";
import { awarenessText, zoneName, zoneless } from "../../../app/dates";
import { ReportingFacts } from "./ReportingFacts";
import { StoryPill } from "./OneStory";
import { dueDay } from "./Home";
import { isLegalDeadline } from "../home";
import { openStep, runOf, useOneStory, useVisited, type StoryRun } from "../oneStory";

/**
 * The harm in words (0.10.82, D1.7; U-18): "Death", "Serious injury", "No harm reported" or "Not known yet", never
 * "Patient involved", which is its own line.
 */
export function harmOf(event: Pick<EventView["event"], "harm" | "harm_words">): {
  harm: "critical" | "serious" | "none";
  label: string;
} {
  const tone = event.harm === "DEATH" ? "critical" : event.harm === "SERIOUS_INJURY" ? "serious" : "none";
  const label =
    event.harm_words ??
    (event.harm === "DEATH" ? "Death" : event.harm === "SERIOUS_INJURY" ? "Serious injury" : "No harm reported");
  return { harm: tone, label };
}

/** The header's one clock: the nearest legal clock, else the nearest of the organization's own targets. */
export const oneClock = (due: NonNullable<EventView["work"]>["due"]) =>
  due.find((item) => isLegalDeadline(item)) ?? due[0] ?? null;

/** Whose clock it is: a market's; while a fact is missing, "Shortest possible" (no country yet) or the incident
 * country's market, provisional (only the awareness date missing: 0.10.84, H3; never a market's firm deadline, 0.10.81
 * F4); else the target's kind. ``country``: the complaint's market once its country is known. */
export const clockPrefix = (item: NonNullable<EventView["work"]>["due"][number], country: string | null = null) =>
  item.key.endsWith(":facts")
    ? country
      ? `${marketLabel(country)}, provisional`
      : "Shortest possible"
    : isLegalDeadline(item) && item.market
      ? marketLabel(item.market)
      : item.category_label;

/** Each step of the checklist by its name (its state follows in words). */
const CHECK_NAMES: Record<string, string> = {
  TRIAGE: "Triage record",
  FIRST_CONTACT: "First-contact check",
  MARKETS: "Market assessments",
  OBLIGATIONS: "Authority reports",
  DECISION: "Disposition or investigation decision",
  REQUESTS: "Information requests",
  TASKS: "Tasks on the event",
  CAPA: "CAPA",
};

/** "Short words from the description": the header's one line on what happened. */
export const headline = (text: string | null | undefined, max = 140) => {
  const words = (text ?? "").replace(/\s+/g, " ").trim();
  if (!words) return "No description recorded";
  return words.length > max ? `${words.slice(0, max - 1).trimEnd()}…` : words;
};

/** One chip per market's legal deadline, then one per kind of the organization's own target (a triage target, a
 * reply due), each the nearest. */
export function deadlineChips(due: NonNullable<EventView["work"]>["due"]) {
  const seen = new Set<string>();
  return due.filter((item) => {
    const key = isLegalDeadline(item) ? `market:${item.market ?? ""}` : item.category;
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
  const { open, reportTab, shownTab, story, startStory, isTrial } = useWorkspace();
  // The ten-step story (0.10.82, D1.5): on its own complaint, its step is the rail's Next step, and a slim pill.
  const ref = tabParam(tab, "ref") ?? "";
  const oneStory = useOneStory(!!ref && !!isTrial);
  const resource = useResource<EventView>(ref ? eventPath(ref) : null);
  const [shown, setShown] = useState<EventView | null>(null);
  const view = shown ?? resource.data;
  const storyRun = runOf(oneStory.data, view?.event.ref);
  // An urgent call that is not a complaint yet has no complaint page: it is found on the triage list (U-20).
  const calls = useResource<TriageList>(resource.state === "error" ? TRIAGE : null);
  const call = calls.data?.items.find((item) => item.kind === "INTAKE" && item.ref === ref);
  const [active, setActive] = useState<ComplaintSection>(() => sectionOf(tab));
  // Ready to close is shown when it is the next step or signed; before that it is revealed on request (one main button).
  const [readyShown, setReadyShown] = useState(false);
  const links = useImdrfLinks([view?.event.problem_code]);
  // Story step 1 counts once this complaint has loaded (0.10.88: never on a page that failed to load).
  useVisited({ step: "call", complaintId: resource.data?.event.complaint_id }, resource.state === "ready");
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
      // A call found on the triage list is shown as such, and a complaint that is not there offers the list (the panel
      // shows its children only when ready; a passing failure keeps the panel's Retry).
      <Panel eyebrow="Complaint" title={ref || "Complaint"} source={call || notFound(resource) ? undefined : resource}>
        {resource.state === "error" && call && (
          <Empty
            title={`${ref} is a call, not a complaint yet`}
            detail="It waits on the triage list: triage it there, and decide whether it is a complaint."
            action={
              <button
                type="button"
                className="ac-primary"
                onClick={() => open("Complaints", `To triage?${new URLSearchParams({ ref })}`)}
              >
                Triage it
              </button>
            }
          />
        )}
        {resource.state === "error" && !call && (
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
  const harm = harmOf(event);
  // Each missing fact is asked in Details (0.10.82, D1.7): the awareness in the triage record while triage is here, else
  // beside the country; the rail's Legal clocks say so once (0.10.87). The decision tree asks the same facts again
  // where its outcome needs them.
  const needs = event.needs ?? [];
  const needed = (fact: string) => needs.some((need) => need.fact === fact);
  const clock = oneClock(work?.due ?? []);
  const reports = view.related?.find((group) => group.key === "reports")?.items ?? [];
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
  // The stage reads "Report" once every conclusion is signed (0.10.85, D3.2): it opens the report itself.
  const reportStage =
    reports.length > 0 && view.stages.some((stage) => stage.code === "MARKETS" && stage.label === "Report");
  const record = (
    <>
      <div className="uw-topline">
        <nav className="uw-crumbs" aria-label="Where you are">
          {/* The reference is the page's heading (0.10.87): the crumb is the way back. */}
          <button type="button" className="ac-link" onClick={() => open("Complaints")}>
            Complaints
          </button>
        </nav>
        <span className="uw-topline-end">
          {/* The organization's time zone, named once for the page (0.10.85, D3.6). */}
          <span className="ac-page-zone">Times in {zoneName()}</span>
          {/* While a short story runs, its bar counts the steps: the walkthrough's pill would be a second count. */}
          {storyRun && !story && <StoryPill run={storyRun} />}
        </span>
      </div>
      <header className="uw-card uw-highlights uw-cp-head" aria-label="The complaint at a glance">
        {/* The hero design's monitor band (0.10.90): the reference, the harm and the reporter's words, the device, and
            the one legal clock as a ring with its line beneath. */}
        <div className="hx-monitor uw-cp-band">
          <div className="hx-monitor-in uw-cp-bandgrid">
            <div className="uw-cp-bandmain">
              <div className="uw-hl-top">
                <div className="uw-hl-title">
                  <p className="ac-eyebrow">
                    Complaint · {[event.product, event.version].filter(Boolean).join(" · ") || "product not recorded"}
                  </p>
                  <h1 ref={heading} tabIndex={-1}>
                    {event.ref}
                  </h1>
                </div>
              </div>
              {/* The record's hero (0.10.85, D3.3): the reporter's words and the harm. */}
              <figure className="uw-cp-words">
                <blockquote>“{event.description || "No description recorded."}”</blockquote>
                <figcaption>
                  {event.sample ? "The reporter's words (fictional sample)" : "The reporter's words, from your record"}
                </figcaption>
              </figure>
              <div className="uw-cp-chips">
                <HarmChip harm={harm.harm} label={harm.label} />
              </div>
            </div>
            <DeviceArt product={event.product} />
            {/* One clock line (0.10.82, D1.7): the nearest legal clock, its time left and its day; a clock waiting
                for the country or the awareness date is the shortest possible one, never a market's (0.10.81). */}
            {clock && (
              <BigClock item={clock} market={needed("COUNTRY") ? null : event.market}>
                <DeadlineChip
                  item={clock}
                  prefix={clockPrefix(clock, needed("COUNTRY") ? null : event.market)}
                  suffix={`due ${dueDay(clock)}`}
                />
              </BigClock>
            )}
          </div>
        </div>
        <div className="uw-card uw-cp-facts">
          {view.service?.header && (
            // Completing the service never closes the complaint (0.10.71, A5): the quality work is still open.
            <p className="uw-cp-service" role="status">
              {/* The owner and the next step are the fields and the card below (0.10.87). */}
              <strong>{view.service.header}</strong>
            </p>
          )}
          <dl className="uw-hl-fields">
            <div>
              <dt>
                <UserRound size={16} aria-hidden="true" />
                Owner
              </dt>
              <dd>{work?.owner_name ?? event.owner_name ?? "Not named yet"}</dd>
            </div>
            <div>
              <dt>
                <Globe size={16} aria-hidden="true" />
                Markets
              </dt>
              <dd>
                {needed("COUNTRY") ? (
                  // The rail's Legal clocks say where the missing facts are asked (0.10.87).
                  <span className="ac-muted">Not recorded</span>
                ) : (
                  <>
                    {markets.map((market) => (
                      <Flag key={market} country={market} decorative />
                    ))}{" "}
                    {markets.map(marketLabel).join(", ") || "—"}
                  </>
                )}
              </dd>
            </div>
            <div>
              <dt>
                <Clock size={16} aria-hidden="true" />
                Awareness
              </dt>
              <dd>
                {needed("AWARENESS_DATE") ? (
                  <span className="ac-muted">Not recorded</span>
                ) : (
                  awarenessText(event.awareness_at, event.awareness_date_only)
                )}
              </dd>
            </div>
            <div>
              <dt>
                <Package size={16} aria-hidden="true" />
                Lot
              </dt>
              <dd className="uw-mono">{event.lot ?? "—"}</dd>
            </div>
          </dl>
          {/* The progress steps are links (0.10.82, D1.8): Market assessment opens the tree, Report the report. */}
          <StagePath
            stages={view.stages}
            links={{
              TRIAGE: triageHere ? () => openHere(step?.opens ?? null) : undefined,
              MARKETS: reportStage
                ? () => {
                    const place = reportPlace(reports[0].id);
                    open(place.section, place.tab);
                  }
                : markets[0]
                  ? () => {
                      const place = treePlace(markets[0], event.complaint_id);
                      open(place.section, place.tab);
                    }
                  : undefined,
            }}
            after={{
              MARKETS:
                reports.length && !reportStage ? (
                  <span className="uw-stageline-extra">
                    <button
                      type="button"
                      className="ac-link"
                      onClick={() => {
                        const place = reportPlace(reports[0].id);
                        open(place.section, place.tab);
                      }}
                    >
                      Report
                    </button>
                  </span>
                ) : null,
            }}
          />
        </div>
        {/* The record's one Next step, under its facts (0.10.90, the hero design). */}
        <NextStepCard
          view={view}
          step={step}
          triageHere={triageHere}
          storyShown={storyShown}
          storyRun={storyRun}
          onStory={(run) => {
            startStory?.(null);
            void openStep(run, run.current, open);
          }}
          onStep={() => {
            if (step?.opens) return go(step.opens);
            choose("Summary");
            document.getElementById("cp-ready")?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
          onShowTriage={active === "Summary" ? undefined : () => choose("Summary")}
        />
      </header>
      {/* The short story's step to do now (0.10.71, A4), from what was saved on this record. */}
      {storyShown && !summaryLeads && <ShortStoryPanel view={view} onChanged={changed} />}
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
                {/* Triage is done here when it is the next step (0.10.72, B3), first in Details beside the rail. */}
                {triageHere &&
                  (storyRun && !storyRun.finished && storyRun.current !== 1 ? (
                    // The story is on another step: the triage form folds until it is asked for (0.10.85, D3.3).
                    <details className="uw-more uw-cp-fold">
                      <summary>Triage record: not complete yet</summary>
                      <InlineTriage complaintId={event.complaint_id} onDone={() => resource.reload()} />
                    </details>
                  ) : (
                    <InlineTriage complaintId={event.complaint_id} onDone={() => resource.reload()} />
                  ))}
                {/* The facts the reporting steps need, asked once (0.10.81's ask; 0.10.82, D1.7: here, not twice). */}
                <ReportingFacts
                  complaintId={event.complaint_id}
                  needs={triageHere ? needs.filter((need) => need.fact !== "AWARENESS_DATE") : needs}
                  quiet={triageHere}
                  onSaved={() => void requestJson<EventView>(eventPath(event.ref)).then(changed)}
                />
                <dl className="uw-rec-facts">
                  <dt>Patient involved</dt>
                  <dd>{event.patient_involved == null ? "Not recorded" : event.patient_involved ? "Yes" : "No"}</dd>
                  <dt>Problem</dt>
                  <dd>
                    {event.problem_code ? <ProblemCode code={event.problem_code} links={links} /> : "None recorded"}
                  </dd>
                  <dt>Decision path</dt>
                  <dd>
                    {markets.length
                      ? markets.map((market, index) => (
                          <span key={market}>
                            {index > 0 && " · "}
                            <button
                              type="button"
                              className="ac-link"
                              onClick={() => {
                                const place = treePlace(market, event.complaint_id);
                                open(place.section, place.tab);
                              }}
                            >
                              {marketLabel(market)}
                            </button>
                          </span>
                        ))
                      : needed("COUNTRY")
                        ? "Incident country not recorded"
                        : "None of your reporting markets applies"}
                    <small>Each market's tree: the question, the answer, the clause and the outcome.</small>
                  </dd>
                  <dt>In your QMS</dt>
                  <dd>{event.status_in_qms}</dd>
                </dl>
                <details className="uw-rec-part uw-cp-fold">
                  <summary>
                    <h2>
                      {blocked.length
                        ? `Each step, and who signs it · ${blocked.length} open`
                        : "Each step, and who signs it · nothing open"}
                    </h2>
                  </summary>
                  <ul className="uw-ov-checks">
                    {ordered.map((item) => (
                      <CheckRow key={item.code} item={item} view={view} onOpen={openHere} onChanged={changed} />
                    ))}
                  </ul>
                  <OwnerPicker view={view} onChanged={changed} />
                </details>
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
        <Rail view={view} onChanged={changed} />
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

/** "Stage 2 of 6", from the stage marked current (else the first not done; every stage done: the last). */
export function stageCount(stages: EventView["stages"]): string {
  const at = stages.findIndex((stage) => stage.state === "CURRENT");
  const open = stages.findIndex((stage) => stage.state !== "DONE" && stage.state !== "NOT_NEEDED");
  const index = at >= 0 ? at : open >= 0 ? open : stages.length - 1;
  return `Stage ${index + 1} of ${stages.length}`;
}

/**
 * The page's one progress indicator (0.10.82, D1.5): one status line, "Stage 2 of 6 · Triage › Market assessment ›
 * …", the current stage marked (on a phone only the current one shows). A stage with a place of its own is a link
 * (D1.8): ``links`` gives what opening it does, ``after`` what follows its name (the report beside its assessment).
 */
export function StagePath({
  stages,
  links = {},
  after = {},
}: {
  stages: EventView["stages"];
  links?: Record<string, (() => void) | undefined>;
  after?: Record<string, ReactNode>;
}) {
  return (
    <div className="uw-stageline">
      <b className="uw-stageline-count">{stageCount(stages)} ·</b>
      <ol className="uw-stageline-ol" aria-label="Stage">
        {stages.map((stage) => {
          const state =
            stage.state === "DONE"
              ? "done"
              : stage.state === "CURRENT"
                ? "now"
                : stage.state === "NOT_NEEDED"
                  ? "skip"
                  : "later";
          const go = links[stage.code];
          return (
            <li key={stage.code} className={`is-${state}`} aria-current={state === "now" ? "step" : undefined}>
              {state === "done" && <Check size={13} aria-hidden="true" />}
              {go ? (
                <button type="button" className="ac-link" onClick={go}>
                  {stage.label}
                </button>
              ) : (
                <span>{stage.label}</span>
              )}
              {after[stage.code]}
              <span className="sr-only">
                {state === "done"
                  ? ": done"
                  : state === "now"
                    ? ": now"
                    : state === "skip"
                      ? ": not needed"
                      : ": later"}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** The device's illustration in the band: the patient monitor or the infusion pump; none for another device. */
function DeviceArt({ product }: { product: string | null | undefined }) {
  const kind = deviceKind(product);
  if (kind !== "monitor" && kind !== "pump") return null;
  return <div className="uw-cp-devart">{kind === "monitor" ? <PatientMonitorArt /> : <InfusionPumpArt />}</div>;
}

/** The legal clock as the band's big ring: one tick per day of the window, the days left in the middle, its line and
 * its market's flag beneath (the hero design). */
function BigClock({
  item,
  market,
  children,
}: {
  item: { hours_left: number; state: string };
  market: string | null;
  children: ReactNode;
}) {
  const ring = ringOf(item);
  const unit = ring.total === 24 ? "hours left" : ring.left < 0 ? "days overdue" : "days left";
  return (
    <div className="uw-cp-bigclock">
      <ClockRing
        left={ring.left}
        total={ring.total}
        status={ring.status}
        size={210}
        stroke={14}
        ticks
        label=""
        decorative
      >
        <b className="uw-num">{Math.abs(ring.left)}</b>
        <span className="uw-cp-bigclock-u">{unit}</span>
      </ClockRing>
      <p className="uw-cp-clockcap">
        {market && <Flag country={market} decorative />}
        {children}
      </p>
    </div>
  );
}

/** The record's one Next step (one main button), in its hero (0.10.85, D3.3; the rail's first card before). */
function NextStepCard({
  view,
  step,
  triageHere,
  storyShown,
  storyRun,
  onStory,
  onStep,
  onShowTriage,
}: {
  view: EventView;
  /** The ten-step story's run when this complaint is its record: its step is the Next step (0.10.82, D1.5). */
  storyRun?: StoryRun | null;
  onStory?: (run: StoryRun) => void;
  step: ReturnType<typeof nextStep>;
  /** Opens Details, where the triage record is, when another section is shown. */
  onShowTriage?: () => void;
  triageHere: boolean;
  storyShown: boolean;
  onStep: () => void;
}) {
  const blocked = view.checklist.filter((item) => item.result === "BLOCKED");
  return (
    <section className="uw-cp-next" aria-label="Next step">
      <h2>Next step</h2>
      {storyRun && !storyRun.finished && !triageHere && !storyShown && onStory ? (
        <>
          <b>
            Story step {storyRun.current + 1}: {STORY_ACTIONS[storyRun.current][0]}
          </b>
          <p className="ac-muted">{STORY_ACTIONS[storyRun.current][1]}</p>
          <button type="button" className="ac-primary" onClick={() => onStory(storyRun)}>
            {STORY_ACTIONS[storyRun.current][2]} <ChevronRight size={15} aria-hidden="true" />
          </button>
        </>
      ) : triageHere ? (
        <>
          <b>{step?.label}</b>
          <p className="ac-muted">The triage record is first in Details, below.</p>
          {onShowTriage && (
            <button type="button" className="ac-secondary" onClick={onShowTriage}>
              Show the triage record
            </button>
          )}
        </>
      ) : step ? (
        <>
          <b>{step.label}</b>
          <p className="ac-muted">{attentionText(blocked, true)}</p>
          <button
            type="button"
            // While the short story shows its step, that step's button is the page's one main button (0.10.71).
            // Sign ready to close is the form's own button in Details: this one is then secondary.
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
  );
}

/** The right rail: the legal clocks, who signs and the service work (the last two fold on a phone's long page). */
/** Nobody may sign the step yet: who changes that. A free trial has no administrator; its owner invites a colleague
 * (0.10.92, A12). */
export const noSignerYet = (isTrial: boolean) =>
  isTrial
    ? "nobody in your organization yet: invite a colleague in Team"
    : "nobody in your organization yet: an administrator gives a colleague the role";

function Rail({ view, onChanged }: { view: EventView; onChanged: (view: EventView) => void }) {
  const isTrial = useIsTrial();
  const blocked = view.checklist.filter((item) => item.result === "BLOCKED");
  const lanes = legalLanes(view);
  const clocked = new Set((view.work?.due ?? []).filter((item) => isLegalDeadline(item)).map((item) => item.market));
  // A clock waiting for a fact stands for every market (0.10.84): none of them is "without a clock" meanwhile.
  const waiting = (view.work?.due ?? []).some((item) => item.key.endsWith(":facts"));
  const without = waiting ? [] : (view.work?.markets ?? []).filter((market) => !clocked.has(market)).map(marketLabel);
  const code = blocked[0]?.code ?? "READY";
  const signers = view.signers?.[code];
  return (
    <aside className="uw-rail" aria-label="Clocks, signers and service work">
      <details className="uw-card uw-card-pad uw-rail-clocks uw-cp-fold" open={!onPhone()}>
        <summary>
          <h2>Legal clocks</h2>
        </summary>
        {!!view.event.needs?.length && (
          <p className="ac-muted">
            Provisional: {view.event.needs.map((need) => need.label.toLowerCase()).join(" and ")} asked in Details.
          </p>
        )}
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
        {!lanes.length && !without.length && !view.event.needs?.length && (
          <p className="ac-muted">No market to report to.</p>
        )}
        <p className="ac-note">Each clock counts from awareness. Starter rules, for your consultant to confirm.</p>
      </details>
      <details className="uw-card uw-card-pad uw-rail-signs uw-cp-fold" open={!onPhone()}>
        <summary>
          <h2>Who signs</h2>
        </summary>
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
          <p className="ac-muted">{noSignerYet(isTrial).replace(/^n/, "N")}.</p>
        )}
        {signers?.second_person && <p className="ac-note">Never the person who prepared it.</p>}
        {view.record_people?.practice_note && <p className="ac-note">{view.record_people.practice_note}</p>}
      </details>
      <details className="uw-card uw-card-pad uw-rail-service uw-cp-fold" open={!onPhone()}>
        <summary>
          <h2>Service work</h2>
          <span className="ac-muted">{serviceText(view)}</span>
        </summary>
        {/* The fold's summary says the heading and the state once (0.10.91: they were said twice). */}
        <ServiceWork view={view} onChanged={onChanged} title="Service work" headless />
      </details>
    </aside>
  );
}

/** A phone's width: the rail's long cards start folded there. */
const onPhone = () =>
  typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(max-width: 640px)").matches
    : false;

/** Each story step on the rail: what it is, one line, and its one button (Getting started's step card's action). */
const STORY_ACTIONS: Array<[string, string, string]> = [
  ["read the call", "The reporter's words are on this page; the awareness time starts every clock.", "Read the call"],
  ["triage", "Severity, owner and the first action.", "Open the triage"],
  ["the decision tree", "Facts from the record arrive to confirm; judgement questions are yours.", "Open the tree"],
  ["reportable or not", "Sign the conclusion: your role decides who signs, never the persona.", "Go to the outcome"],
  ["the form", "Created when you signed “reportable”.", "Open the report"],
  ["fill what is missing", "Each field still empty names its form box.", "Open the missing fields"],
  ["approval", "A second person approves.", "Open the approval"],
  ["PDF and submission", "MDARIX never submits: you record what you sent.", "Open the PDF step"],
  ["records", "The signed record, ready for an inspector.", "Open Records"],
  ["trends", "Is it happening elsewhere?", "Open Trends"],
];

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
    if (group.key === "reports" && group.items?.length === 1) {
      // One report: its own page in the Reports tab (0.10.75, C3).
      const place = reportPlace(group.items[0].id);
      return { label: "Open the report", run: () => open(place.section, place.tab) };
    }
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
        {/* The step's name, then its state in words: never a goal beside a state that denies it (U-19, D1.7). */}
        <strong>{CHECK_NAMES[item.code] ?? item.label}:</strong> {item.detail}
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
  const isTrial = useIsTrial();
  const signers = view.signers?.[code];
  if (!signers) return null;
  const names = signers.people.map((person) => person.name);
  return (
    <small className="uw-who-signs">
      {" "}
      Who signs: {names.length ? `${names.join(", ")}${signers.you ? " (you among them)" : ""}` : noSignerYet(isTrial)}
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
    .filter((item) => isLegalDeadline(item) && item.market)
    .map((item) => ({
      key: item.key,
      market: marketLabel(item.market!),
      from: view.event.awareness_at ?? item.due_at,
      to: item.due_at,
      note: item.title,
      dueText: `Due ${item.due_label ? zoneless(item.due_label) : formatDate(item.due_at)}`,
      stateText:
        item.state === "OVERDUE"
          ? "Overdue"
          : item.hours_left < 48
            ? `${Math.max(0, Math.round(item.hours_left))} hours left`
            : `${Math.floor(item.hours_left / 24)} days left`,
      overdue: item.state === "OVERDUE",
    }));
}
