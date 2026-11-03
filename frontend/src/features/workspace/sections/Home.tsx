import type { RefObject } from "react";
import { ChevronRight } from "lucide-react";
import { DeadlineChip } from "../../../app/chips";
import { formatDateTime, formatDay, zoneName } from "../../../app/dates";
import { marketLabel } from "../../../app/labels";
import { placeOf } from "../../../app/linkTable";
import { useResource } from "../../customer-admin/shared";
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
  laneShare,
  legalClocks,
  nextActions,
  personaItems,
} from "../home";
import { IMPORTED_SOURCE } from "../complaintList";
import { openStep, shownRun, STORY_STEPS, useOneStory } from "../oneStory";
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
  const overdue = useResource<{ total: number }>(OVERDUE_PATH);
  const oversight = useResource<Oversight>(`${OVERSIGHT}?show=all`);
  const trends = useResource<TrendBoard>(trendPath("version"));
  const readiness = useResource<Readiness>(persona === "executive" ? READINESS_PATH : null);
  const items = personaItems(oversight.data?.items ?? [], persona);
  const rising = (trends.data?.items ?? []).filter((row) => row.result === "SIGNIFICANT" || row.result === "ELEVATED");
  const actions = nextActions(items);
  const clocks = persona === "regulatory" ? legalClocks(items) : [];
  const name = (session?.display_name ?? "").split(/\s+/)[0];
  const go = (item: OversightItem) => {
    if (!item.opens) return;
    const place = placeOf(item.opens);
    open(place.section as WorkspaceSection, place.tab);
  };
  const dueWeek = useResource<{ total: number }>(DUE_WEEK_PATH);
  const reading = oversight.state === "loading";
  const tenant = session?.current_tenant?.tenant_name;
  return (
    <div className="uw-home">
      <header className="uw-home-head">
        <div>
          <span className="uw-viewing">
            {isTrial
              ? `Home · ${dataSource === IMPORTED_SOURCE ? "your data" : "sample data"}`
              : `Viewing as ${personaLabel ?? persona}`}
          </span>
          <h1 ref={heading} tabIndex={-1}>
            {greeting()}
            {name ? `, ${name}` : ""}
          </h1>
          <p>{PERSONA_GREETING[persona] ?? PERSONA_GREETING.admin}</p>
        </div>
        <span className="uw-home-date">
          {/* The page's one time-zone note (0.10.82, U-15): the date line. */}
          {formatDay(new Date().toISOString())} · times in {zoneName()}
          {tenant ? ` · ${tenant}` : ""}
        </span>
      </header>

      {/* The story (0.10.82, D1.6): a slim banner on the sample, the hero of your most urgent complaint on your data,
          "Story complete" once its ten steps are done. Never a second retelling of Getting started. */}
      {isTrial && <HomeStory />}

      {/* Each tile is the count of the complaint list it opens (0.10.82, D1.6): one number, one list. */}
      <section className="uw-home-stats" aria-label="What needs attention">
        <Stat
          tone="over"
          value={overdue.state === "loading" ? null : (overdue.data?.total ?? null)}
          onOpen={() => open("Complaints", OVERDUE_VIEW)}
          title="Overdue"
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
          detail={dueWeek.state === "loading" ? "Reading…" : "Complaints with a deadline or target in the next 7 days"}
        />
        <Stat
          tone="risk"
          value={trends.state === "loading" ? null : rising.length}
          onOpen={() => open("Trends", "Trends to review")}
          title="At risk"
          detail={
            trends.state === "loading"
              ? "Reading…"
              : rising.length
                ? `${rising[0].name} is rising`
                : "No product rising against its history"
          }
        />
      </section>

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
              <ul className="uw-home-list">
                {actions.map((item) => (
                  <li key={item.key}>
                    <button type="button" className="uw-home-row" onClick={() => go(item)} disabled={!item.opens}>
                      <DeadlineChip item={item} />
                      <span className="uw-home-what">
                        <b>
                          {item.ref ? `${item.ref} · ` : ""}
                          {item.title}
                        </b>
                        <small>
                          {item.category_label} · Owner: {item.owner ?? "nobody yet"} · Due{" "}
                          {item.due_label ?? formatDateTime(item.due_at)}
                        </small>
                      </span>
                      <ChevronRight size={16} aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="ac-muted uw-card-pad">Nothing waits for this persona. New work appears here first.</p>
            )}
          </section>
        )}
        <div className="uw-home-side">
          {persona === "regulatory" && <LegalClocks clocks={clocks} onOpen={go} reading={reading} />}
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
                    <h2 className="uw-home-trend-title">{risingSentence(row)}</h2>
                    <TrendBars row={row} bare />
                    <p className="ac-muted">{comparisonLine(row)}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="ac-muted">No product is rising against its own history.</p>
            )}
            {personaTabs.includes("trends") && (
              <button type="button" className="ac-secondary" onClick={() => open("Trends")}>
                Open the trends
              </button>
            )}
          </section>
        </div>
      </div>

      {/* The bell's reminders and escalations, read and cleared here on the new navigation (0.10.81, H1). */}
      <div id="home-reminders">
        <RemindersPanel />
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
  onOpen,
}: {
  tone: "over" | "soon" | "risk";
  value: number | null;
  title: string;
  detail: string;
  /** Each tile opens its list (0.10.81, navigation M1). */
  onOpen: () => void;
}) {
  return (
    <button type="button" className={`uw-card uw-home-stat is-${tone}`} onClick={onOpen}>
      <b className="uw-home-num">{value === null ? "…" : value}</b>
      <strong>{title}</strong>
      <span>{detail}</span>
    </button>
  );
}

/**
 * The story on Home (0.10.82, D1.6), read from the same saved records as Getting started:
 * - on the sample, a slim "Continue the story" banner (never a second retelling of the story);
 * - on your data, the hero of your most urgent imported complaint and what the file did not say;
 * - once its ten steps are done, a "Story complete" card.
 */
export function HomeStory() {
  const { open, dataSource, chooseDataSource, startStory, session } = useWorkspace();
  const story = useOneStory();
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
        </div>
      </section>
    );
  const clock = event.data?.work?.due.find((item) => item.category === "REPORTING" || item.category === "OBLIGATION");
  const harm = run.complaint.death ? "a death" : run.complaint.serious_injury ? "a serious injury" : "a malfunction";
  const country = run.market_label;
  return (
    <section className="uw-card uw-home-hero" aria-labelledby="home-story-title">
      <div className="uw-home-hero-main">
        <span className="ac-eyebrow">Your data · your most urgent complaint</span>
        <h2 id="home-story-title">
          {run.complaint.ref} is {harm}
          {country ? ` in ${country}` : " with no incident country"}.
          {clock ? ` Its ${clock.key.endsWith(":facts") ? "shortest possible " : ""}clock ends ${dueDay(clock)}.` : ""}
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
                <small className="ac-muted">Due {item.due_label ?? formatDateTime(item.due_at)}</small>
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
