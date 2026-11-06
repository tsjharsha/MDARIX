import type { RefObject } from "react";
import {
  AlertCircle,
  CalendarClock,
  Check,
  ChevronRight,
  Clock,
  FileText,
  GitFork,
  MessageCircle,
  PenLine,
  Phone,
  SearchCheck,
  Send,
  Stethoscope,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { DeviceIcon, MonitorBand, ProgressArc, deviceKind } from "../../shared/hero/HeroVisuals";
import { DeadlineRuler, ringOf } from "../heroBits";
import { DeadlineChip } from "../../../app/chips";
import { formatDateTime, formatDay, zoneName, zoneless } from "../../../app/dates";
import { marketLabel } from "../../../app/labels";
import { placeOf } from "../../../app/linkTable";
import { useResource, type Resource } from "../../customer-admin/shared";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { OVERSIGHT, eventPath, type EventView, type Oversight, type OversightItem } from "../oversight";
import { READINESS_PATH, readinessHeadline, type Readiness } from "../readiness";
import { comparisonLine, risingSentence, trendPath, type TrendBoard } from "../signalAi";
import {
  DUE_WEEK_PATH,
  DUE_WEEK_VIEW,
  OVERDUE_PATH,
  OVERDUE_VIEW,
  PERSONA_GREETING,
  greeting,
  inData,
  isLegalDeadline,
  laneShare,
  legalClocks,
  nextActions,
  personaItems,
  withSource,
} from "../home";
import { IMPORTED_SOURCE } from "../complaintList";
import { openStep, shownRun, STORY_STEPS, useOneStory, type OneStory } from "../oneStory";
import { TrendBars } from "./OneStory";
import { MyWorkMore } from "./MyWork";
import { RemindersPanel } from "./Reminders";

/**
 * Home (0.10.73, Release C part C1; My work's place on the new navigation): what needs attention within the first
 * screen, for the persona the person views as. Overdue · Due this week · At risk from the organization's own dated
 * items and trend check; the next actions most urgent first, each with its reason, owner and deadline; one sentence
 * per rising trend; the Regulatory Leader's legal clocks; the Executive's readiness line. Admin's (and the Quality
 * Leader's) Home keeps Release A's one-event card and the short story. All of My work stays one click below.
 */
export function HomeSection({ tab, heading }: { tab?: string; heading: RefObject<HTMLHeadingElement | null> }) {
  const { session, persona = "admin", personaLabel, personaTabs = [], isTrial, open, dataSource } = useWorkspace();
  // Home follows the Sample · Your data switch (0.10.84, M5): its tiles, next actions and trends count the data shown.
  const overdue = useResource<{ total: number }>(withSource(OVERDUE_PATH, dataSource));
  const oversight = useResource<Oversight>(`${OVERSIGHT}?show=all`);
  const trends = useResource<TrendBoard>(trendPath("version"));
  const readiness = useResource<Readiness>(persona === "executive" ? READINESS_PATH : null);
  const story = useOneStory(!!isTrial);
  const items = personaItems(oversight.data?.items ?? [], persona).filter((item) =>
    inData(item.ref, dataSource, !!item.complaint_id),
  );
  const rising = (trends.data?.items ?? []).filter(
    (row) => (row.result === "SIGNIFICANT" || row.result === "ELEVATED") && inData(row.product.identifier, dataSource),
  );
  // The complaint the hero names is always in the list, first among those due at the same time.
  const hero = shownRun(story.data, dataSource);
  const actions = nextActions(items, 5, hero?.run === "yours" ? hero.complaint.id : null);
  // The Regulatory Leader's legal clocks, and the administrator's (the trial's owner sees every clock; 0.10.92, A9).
  const showsClocks = persona === "regulatory" || persona === "admin";
  const clocks = showsClocks ? legalClocks(items) : [];
  const name = (session?.display_name ?? "").split(/\s+/)[0];
  const go = (item: OversightItem) => {
    if (!item.opens) return;
    const place = placeOf(item.opens);
    open(place.section as WorkspaceSection, place.tab);
  };
  const dueWeek = useResource<{ total: number }>(withSource(DUE_WEEK_PATH, dataSource));
  const reading = oversight.state === "loading";
  return (
    <div className="uw-home">
      <header className="uw-home-head">
        <div>
          {/* In a trial the top bar names the data and the tab names the page (0.10.87): no eyebrow. */}
          {!isTrial && <span className="uw-viewing">Viewing as {personaLabel ?? persona}</span>}
          <h1 ref={heading} tabIndex={-1}>
            {greeting()}
            {name ? `, ${name}` : ""}
          </h1>
          <p>{PERSONA_GREETING[persona] ?? PERSONA_GREETING.admin}</p>
        </div>
        <span className="uw-home-date">
          {/* The page's one time-zone note (0.10.82, U-15): the date line. */}
          {/* The organization is on the top bar (0.10.87). */}
          {formatDay(new Date().toISOString())} · times in {zoneName()}
        </span>
      </header>

      {/* The hero design's monitor band (0.10.90): the story beside the three readouts. */}
      <MonitorBand className={`uw-home-band${isTrial && hero ? "" : " is-stats-only"}`}>
        {/* The story (0.10.82, D1.6): a slim banner on the sample, the hero of your most urgent complaint on your data,
          "Story complete" once its ten steps are done. Never a second retelling of Getting started. */}
        {isTrial && <HomeStory story={story} />}

        {/* Each tile is the count of the complaint list it opens (0.10.82, D1.6): one number, one list. */}
        <section className="uw-home-stats" aria-label="What needs attention">
          <Stat
            tone="over"
            value={overdue.state === "loading" ? null : (overdue.data?.total ?? null)}
            onOpen={() => open("Complaints", OVERDUE_VIEW)}
            title="Overdue"
            short={overdue.data?.total ? "Act on these first" : "Nothing late"}
            // Never an all-clear before the data has arrived (0.10.81, U-07).
            detail={
              overdue.state === "loading"
                ? "Reading…"
                : overdue.data?.total
                  ? "Complaints past a deadline or target: act on these first"
                  : "Nothing past its time"
            }
          />
          <Stat
            tone="soon"
            value={dueWeek.state === "loading" ? null : (dueWeek.data?.total ?? null)}
            onOpen={() => open("Complaints", DUE_WEEK_VIEW)}
            title="Due this week"
            short="Next 7 days"
            detail={
              dueWeek.state === "loading" ? "Reading…" : "Complaints with a deadline or target in the next 7 days"
            }
          />
          <Stat
            tone="risk"
            value={trends.state === "loading" ? null : rising.length}
            // The trend check, where the count is (0.10.84, L3): the signal inbox lists a signal's own complaints.
            onOpen={() => open("Trends", "Trend check")}
            title="At risk"
            short={rising.length ? "A product rising" : "Nothing rising"}
            detail={
              trends.state === "loading"
                ? "Reading…"
                : rising.length
                  ? // The Trends card below names the product and its rise (0.10.87): the tile says only how many.
                    "Products rising against their history"
                  : "No product rising against its history"
            }
          />
        </section>
      </MonitorBand>

      <div className="uw-home-grid">
        {persona === "executive" ? (
          <ReadinessLine data={readiness.data} onOpen={() => open("Records", "Inspection readiness")} />
        ) : (
          <section className="uw-card" aria-labelledby="home-next">
            <div className="uw-card-head">
              <h2 id="home-next">Your next actions</h2>
              <span className="ac-muted">Most urgent first</span>
            </div>
            {reading ? (
              <p className="ac-muted uw-card-pad" role="status">
                Reading what needs attention…
              </p>
            ) : actions.length ? (
              <>
                <DeadlineRuler items={actions} />
                <ul className="uw-home-list">
                  {actions.map((item) => (
                    <li key={item.key}>
                      <button
                        type="button"
                        className={`uw-home-row is-${ringOf(item).status}`}
                        onClick={() => go(item)}
                        disabled={!item.opens}
                      >
                        <ActionIcon item={item} />
                        <DeadlineChip item={item} />
                        <span className="uw-home-what">
                          <b>
                            {item.ref ? `${item.ref} · ` : ""}
                            {/* The reference once (U-21): "Reply due from Reporter of SAMPLE-RV-08" repeated it. */}
                            {item.ref ? item.title.replace(` of ${item.ref}`, "") : item.title}
                          </b>
                          <small>
                            {item.category_label} · {item.owner ? `Owner: ${item.owner}` : "No owner yet"} · Due{" "}
                            {item.due_label ? zoneless(item.due_label) : formatDateTime(item.due_at)}
                          </small>
                        </span>
                        <ChevronRight size={16} aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="ac-muted uw-card-pad">Nothing waits for this persona. New work appears here first.</p>
            )}
          </section>
        )}
        <div className="uw-home-side">
          {showsClocks && <LegalClocks clocks={clocks} onOpen={go} reading={reading} />}
          {(persona === "investigator" || persona === "risk") && <OpenInvestigations />}
          <section className="uw-card uw-card-pad uw-home-trend" aria-labelledby="home-trend">
            <span className="ac-eyebrow" id="home-trend">
              Trends
            </span>
            {trends.state === "loading" ? (
              <p className="ac-muted">Reading the trend check…</p>
            ) : rising.length ? (
              <ul>
                {rising.slice(0, 2).map((row) => (
                  <li key={row.key}>
                    {/* Observed against expected, as bars (0.10.82, D1.6, the approved design's trend card). */}
                    <div className="uw-home-trend-head">
                      <span className="uw-home-trend-pic" aria-hidden="true">
                        <DeviceIcon kind={deviceKind(row.product.name)} size={36} decorative />
                      </span>
                      <h2 className="uw-home-trend-title">{risingSentence(row)}</h2>
                    </div>
                    <TrendBars row={row} bare />
                    <p className="ac-muted">{comparisonLine(row)}</p>
                    {typeof row.ratio === "number" && (
                      // The rise as one big figure, the sentence above says it in words (the hero design's card).
                      <span className="uw-home-ratio" aria-hidden="true">
                        {row.ratio.toFixed(1)}×
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="ac-muted">No product is rising against its own history.</p>
            )}
            {personaTabs.includes("trends") && (
              <button
                type="button"
                className="ac-secondary"
                onClick={() =>
                  open(
                    "Trends",
                    rising[0]?.product.identifier
                      ? `Trend check?${new URLSearchParams({ product: rising[0].product.identifier })}`
                      : "Trend check",
                  )
                }
              >
                Open the trends
              </button>
            )}
          </section>
          {/* The bell's reminders and escalations, read and cleared here on the new navigation (0.10.81, H1); in the
              side column under the trends (0.10.90, the hero design). */}
          <div id="home-reminders">
            <RemindersPanel />
          </div>
        </div>
      </div>
      <MyWorkMore tab={tab} />
    </div>
  );
}

function Stat({
  tone,
  value,
  title,
  detail,
  short,
  onOpen,
}: {
  tone: "over" | "soon" | "risk";
  value: number | null;
  title: string;
  detail: string;
  /** The tile's one line of meaning on a phone, where the full line does not fit (0.10.85, D3.7; U-12). */
  short?: string;
  /** Each tile opens its list (0.10.81, navigation M1). */
  onOpen: () => void;
}) {
  return (
    <button type="button" className={`uw-card uw-home-stat is-${tone}`} onClick={onOpen}>
      <b className="uw-home-num">{value === null ? "…" : value}</b>
      <strong>{title}</strong>
      <span className="uw-home-long">{detail}</span>
      {short && value !== null && <span className="uw-home-short">{short}</span>}
      <span className="uw-home-vis" aria-hidden="true">
        {tone === "over" ? <AlertCircle size={22} /> : tone === "soon" ? <Clock size={22} /> : <TrendingUp size={22} />}
      </span>
    </button>
  );
}

/**
 * The story on Home (0.10.82, D1.6), read from the same saved records as Getting started:
 * - on the sample, a slim "Continue the story" banner (never a second retelling of the story);
 * - on your data, the hero of your most urgent imported complaint and what the file did not say;
 * - once its ten steps are done, a "Story complete" card.
 */
export function HomeStory({ story }: { story: Resource<OneStory> }) {
  const { open, dataSource, chooseDataSource, startStory, session } = useWorkspace();
  const run = shownRun(story.data, dataSource);
  const event = useResource<EventView>(run && run.run === "yours" ? eventPath(run.complaint.ref) : null);
  if (!run) return null;
  const go = () => {
    startStory?.(null);
    void openStep(run, Math.min(run.current, STORY_STEPS - 1), (section, tab) => open(section, tab));
  };
  if (run.run === "sample" && !run.finished)
    return (
      <section className="uw-card uw-home-banner" aria-label="The sample story">
        <ProgressArc done={run.steps.filter((step) => step.done || step.skipped).length} size={56} decorative />
        <span>
          <span className="ms-chip is-sample">Sample story</span>{" "}
          <b>
            Step {run.current + 1} of {STORY_STEPS}: {run.steps[run.current].label}
          </b>{" "}
          <span className="ac-muted">· {run.complaint.ref}</span>
        </span>
        <button type="button" className="ac-primary" onClick={go}>
          Continue the story <ChevronRight size={15} aria-hidden="true" />
        </button>
      </section>
    );
  if (run.finished)
    return (
      <section className="uw-card uw-home-hero" aria-labelledby="home-story-title">
        <div className="uw-home-hero-main">
          <span className="ac-eyebrow">Story complete · {run.complaint.ref}</span>
          <h2 id="home-story-title">
            {run.run === "sample"
              ? "The sample complaint went from the call to a recorded submission and the trend check."
              : `Your first complaint went from the call to ${
                  run.conclusion === "NOT_REPORTABLE" ? "a signed “not reportable” conclusion" : "a recorded submission"
                }.`}
          </h2>
          <p className="ac-muted">Every missing fact was asked at the step that needed it. Nothing was guessed.</p>
          <div className="ca-action-row">
            {run.run === "sample" && story.data?.yours ? (
              <button type="button" className="ac-primary" onClick={() => chooseDataSource?.(IMPORTED_SOURCE)}>
                Do the same with your data <ChevronRight size={15} aria-hidden="true" />
              </button>
            ) : run.run === "sample" && !session?.sample_only ? (
              <button type="button" className="ac-primary" onClick={() => open("Import your data")}>
                Do the same with your data <ChevronRight size={15} aria-hidden="true" />
              </button>
            ) : (
              <button type="button" className="ac-primary" onClick={() => open("Records")}>
                See the record <ChevronRight size={15} aria-hidden="true" />
              </button>
            )}
          </div>
          {run.run === "sample" && <StoryTrack />}
        </div>
      </section>
    );
  // The legal clock only, never an approval task's due date (0.10.84, H2): the rule Home's legal clocks use.
  const clock = event.data?.work?.due.find(isLegalDeadline);
  const harm = run.complaint.death ? "a death" : run.complaint.serious_injury ? "a serious injury" : "a malfunction";
  const country = run.market_label;
  return (
    <section className="uw-card uw-home-hero" aria-labelledby="home-story-title">
      <div className="uw-home-hero-main">
        <span className="ac-eyebrow">Your data · your most urgent complaint</span>
        <h2 id="home-story-title">
          {run.complaint.ref} is {harm}
          {country ? ` in ${country}` : " with no incident country"}.
          {clock
            ? ` Its ${clock.key.endsWith(":facts") ? (run.market ? "provisional " : "shortest possible ") : ""}clock ends ${dueDay(clock)}.`
            : ""}
        </h2>
        {run.complaint.description && (
          <blockquote className="uw-entrance-words">“{run.complaint.description}”</blockquote>
        )}
        <div className="ca-action-row">
          <button type="button" className="ac-primary" onClick={go}>
            Walk it through · step {run.current + 1} of {STORY_STEPS} <ChevronRight size={15} aria-hidden="true" />
          </button>
        </div>
      </div>
      <aside className="uw-home-hero-side" aria-label="What your file did not say">
        <span className="ac-eyebrow">What your file did not say</span>
        <ol>
          {run.needs.length ? (
            run.needs.map((need) => (
              <li key={need.fact}>
                <span className="uw-home-step" aria-hidden="true">
                  ?
                </span>
                <span>
                  {need.label}
                  <small>Asked on the complaint page: {need.rule.split(";")[0]}</small>
                </span>
              </li>
            ))
          ) : (
            <li>
              <span className="uw-home-step" aria-hidden="true">
                ✓
              </span>
              <span>
                Every fact the reporting steps need is given
                <small>Nothing was guessed</small>
              </span>
            </li>
          )}
        </ol>
      </aside>
    </section>
  );
}

/** The finished sample story's five moments, all done (the hero design's story track). */
const TRACK: ReadonlyArray<[LucideIcon, string]> = [
  [Phone, "The call"],
  [GitFork, "Decision tree"],
  [PenLine, "Signed"],
  [Send, "Recorded"],
  [TrendingUp, "Trend check"],
];

function StoryTrack() {
  return (
    <ol className="uw-strack" aria-label="Story steps, all done">
      {TRACK.map(([Icon, label]) => (
        <li key={label}>
          <span className="uw-strack-n">
            <Icon size={18} aria-hidden="true" />
            <span className="uw-strack-ok">
              <Check size={11} strokeWidth={3} aria-hidden="true" />
            </span>
          </span>
          {label}
        </li>
      ))}
    </ol>
  );
}

/** A next action's kind as an icon in its deadline's colour: a reply, a triage, a report, an investigation. */
function ActionIcon({ item }: { item: OversightItem }) {
  const kind = `${item.category} ${item.category_label}`;
  const Icon = /communicat|reply/i.test(kind)
    ? MessageCircle
    : /triage|first contact/i.test(kind)
      ? /CALL/.test(item.ref ?? "")
        ? Phone
        : Stethoscope
      : /report/i.test(kind)
        ? FileText
        : /investigat/i.test(kind)
          ? SearchCheck
          : CalendarClock;
  return (
    <span className={`uw-home-aic is-${ringOf(item).status}`} aria-hidden="true">
      <Icon size={18} />
    </span>
  );
}

/** "Thu 5 Nov" from a due item's label ("Thu 5 Nov 2026, 23:59 IST"). */
export const dueDay = (item: { due_label?: string; due_at: string }) =>
  (item.due_label ?? formatDay(item.due_at)).split(",")[0].replace(/ \d{4}$/, "");

/** The Regulatory Leader's legal clocks: each market's deadline, soonest first, with how much time is used. */
export function LegalClocks({
  clocks,
  onOpen,
  reading = false,
}: {
  clocks: OversightItem[];
  onOpen: (item: OversightItem) => void;
  reading?: boolean;
}) {
  return (
    <section className="uw-card" aria-labelledby="home-clocks">
      <div className="uw-card-head">
        <h2 id="home-clocks">Legal clocks</h2>
        <span className="ac-muted">Soonest first</span>
      </div>
      {clocks.length ? (
        <ul className="uw-home-clocks">
          {clocks.map((item) => (
            <li key={item.key}>
              <button type="button" onClick={() => onOpen(item)} disabled={!item.opens}>
                <span className="uw-home-clock-line">
                  <b>
                    {marketLabel(item.market)}
                    {item.ref ? ` · ${item.ref}` : ""}
                  </b>
                  <DeadlineChip item={item} />
                </span>
                <span
                  className={`uw-home-lane${item.state === "OVERDUE" ? " is-over" : ""}`}
                  role="img"
                  aria-label={`${laneShare(item)}% of a 30-day window used`}
                >
                  <i style={{ width: `${laneShare(item)}%` }} />
                </span>
                <small className="ac-muted">
                  Due {item.due_label ? zoneless(item.due_label) : formatDateTime(item.due_at)}
                </small>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="ac-muted uw-card-pad" role={reading ? "status" : undefined}>
          {reading ? "Reading the legal clocks…" : "No legal clock is running."}
        </p>
      )}
    </section>
  );
}

type CaseRow = {
  id: string;
  business_id?: string | null;
  investigation_question?: string | null;
  product_id?: string | null;
  status?: string | null;
  workflow_state_label?: string | null;
  owner_name?: string | null;
};

/** The Investigator's and Risk Reviewer's open investigations: the question, where it stands, its owner. */
function OpenInvestigations() {
  const { open, work } = useWorkspace();
  const cases = useResource<{ records: CaseRow[] }>("/api/v1/data-plane/investigations?limit=20");
  const rows = (cases.data?.records ?? [])
    .filter((row) => !/^(CLOSED|CANCELLED)$/i.test(String(row.status ?? "")))
    .slice(0, 3);
  if (cases.state !== "ready" || !rows.length) return null;
  return (
    <section className="uw-card uw-card-pad uw-home-trend" aria-labelledby="home-cases">
      <span className="ac-eyebrow" id="home-cases">
        Open investigations
      </span>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>
            <p>
              <strong>
                {row.business_id ? `${row.business_id} · ` : ""}
                {row.investigation_question ?? "An investigation"}
              </strong>
            </p>
            <p className="ac-muted">
              {[row.workflow_state_label, row.owner_name ? `Owner: ${row.owner_name}` : null]
                .filter(Boolean)
                .join(" · ")}
            </p>
            <button
              type="button"
              className="ac-secondary"
              onClick={() => {
                work.setInvestigationId(row.id, row.product_id ?? undefined);
                open("Investigations", "Summary");
              }}
            >
              Open the investigation
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The Executive's readiness line: the inspection checks in one sentence, and where they open. */
function ReadinessLine({ data, onOpen }: { data: Readiness | null; onOpen: () => void }) {
  const line = readinessHeadline(data);
  return (
    <section className="uw-card uw-card-pad uw-home-ready" aria-labelledby="home-ready">
      <span className="ac-eyebrow">Inspection readiness</span>
      <h2 id="home-ready">{line.title}</h2>
      {line.detail && <p className="ac-muted">{line.detail}</p>}
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" onClick={onOpen}>
          Open inspection readiness
        </button>
      </div>
    </section>
  );
}
