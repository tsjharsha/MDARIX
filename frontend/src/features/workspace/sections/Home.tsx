import type { RefObject } from "react";
import { ChevronRight } from "lucide-react";
import { DeadlineChip } from "../../../app/chips";
import { formatDateTime, formatDay } from "../../../app/dates";
import { marketLabel } from "../../../app/labels";
import { placeOf } from "../../../app/linkTable";
import { useResource } from "../../customer-admin/shared";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { FLAGSHIP, SHORT } from "../entrance";
import { OVERSIGHT, eventPath, type EventView, type Oversight, type OversightItem } from "../oversight";
import { READINESS_PATH, readinessHeadline, type Readiness } from "../readiness";
import { comparisonLine, risingSentence, trendPath, type TrendBoard } from "../signalAi";
import {
  HERO_PERSONAS,
  PERSONA_GREETING,
  greeting,
  homeCounts,
  laneShare,
  legalClocks,
  nextActions,
  personaItems,
} from "../home";
import { ResumeShortStory } from "./ShortStory";
import { MyWorkMore } from "./MyWork";

/**
 * Home (0.10.73, Release C part C1; My work's place on the new navigation): what needs attention within the first
 * screen, for the persona the person views as. Overdue · Due this week · At risk from the organization's own dated
 * items and trend check; the next actions most urgent first, each with its reason, owner and deadline; one sentence
 * per rising trend; the Regulatory Leader's legal clocks; the Executive's readiness line. Admin's (and the Quality
 * Leader's) Home keeps Release A's one-event card and the short story. All of My work stays one click below.
 */
export function HomeSection({ tab, heading }: { tab?: string; heading: RefObject<HTMLHeadingElement | null> }) {
  const { session, persona = "admin", personaLabel, personaTabs = [], isTrial, open } = useWorkspace();
  const oversight = useResource<Oversight>(`${OVERSIGHT}?show=all`);
  const trends = useResource<TrendBoard>(trendPath("version"));
  const readiness = useResource<Readiness>(persona === "executive" ? READINESS_PATH : null);
  const items = personaItems(oversight.data?.items ?? [], persona);
  const counts = homeCounts(items);
  const rising = (trends.data?.items ?? []).filter((row) => row.result === "SIGNIFICANT" || row.result === "ELEVATED");
  const actions = nextActions(items);
  const clocks = persona === "regulatory" ? legalClocks(items) : [];
  const name = (session?.display_name ?? "").split(/\s+/)[0];
  const go = (item: OversightItem) => {
    if (!item.opens) return;
    const place = placeOf(item.opens);
    open(place.section as WorkspaceSection, place.tab);
  };
  const reading = oversight.state === "loading";
  const tenant = session?.current_tenant?.tenant_name;
  return (
    <div className="uw-home">
      <header className="uw-home-head">
        <div>
          <span className="uw-viewing">Viewing as {personaLabel ?? persona}</span>
          <h1 ref={heading} tabIndex={-1}>
            {greeting()}
            {name ? `, ${name}` : ""}
          </h1>
          <p>{PERSONA_GREETING[persona] ?? PERSONA_GREETING.admin}</p>
        </div>
        <span className="uw-home-date">
          {formatDay(new Date().toISOString())}
          {tenant ? ` · ${tenant}` : ""}
        </span>
      </header>

      {isTrial && HERO_PERSONAS.includes(persona) && <HomeHero />}

      <section className="uw-home-stats" aria-label="What needs attention">
        <Stat
          tone="over"
          value={reading ? null : counts.overdue}
          title="Overdue"
          detail={counts.overdue ? "Past their time: act on these first" : "Nothing past its time"}
        />
        <Stat
          tone="soon"
          value={reading ? null : counts.week}
          title="Due this week"
          detail="Deadlines in the next 7 days"
        />
        <Stat
          tone="risk"
          value={trends.state === "loading" ? null : rising.length}
          title="At risk"
          detail={rising.length ? `${rising[0].name} is rising` : "No product rising against its history"}
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
          {persona === "regulatory" && <LegalClocks clocks={clocks} onOpen={go} />}
          {(persona === "investigator" || persona === "risk") && <OpenInvestigations />}
          <section className="uw-card uw-card-pad uw-home-trend" aria-labelledby="home-trend">
            <span className="ac-eyebrow" id="home-trend">
              Trends
            </span>
            {trends.state === "loading" ? (
              <p className="ac-muted">Reading the trend check…</p>
            ) : rising.length ? (
              <ul>
                {rising.slice(0, 3).map((row) => (
                  <li key={row.key}>
                    <p>
                      <strong>{risingSentence(row)}</strong>
                    </p>
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

      <MyWorkMore tab={tab} />
    </div>
  );
}

function Stat({
  tone,
  value,
  title,
  detail,
}: {
  tone: "over" | "soon" | "risk";
  value: number | null;
  title: string;
  detail: string;
}) {
  return (
    <div className={`uw-card uw-home-stat is-${tone}`}>
      <b className="uw-home-num">{value === null ? "…" : value}</b>
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  );
}

/** The sample event first (Release A's one-event card, retitled in Release B), with its four steps beside it. */
function HomeHero() {
  const { open, startStory } = useWorkspace();
  const event = useResource<EventView>(eventPath(FLAGSHIP));
  const words = event.data?.event.description;
  if (event.state === "error") return null;
  return (
    <>
      <ResumeShortStory />
      <section className="uw-card uw-home-hero" aria-labelledby="home-hero-title">
        <div className="uw-home-hero-main">
          <span className="ac-eyebrow">Start here · sample event · {FLAGSHIP}</span>
          <h2 id="home-hero-title">{SHORT.title}</h2>
          <blockquote className="uw-entrance-words">{words ? `“${words}”` : "Reading the sample event…"}</blockquote>
          <div className="ca-action-row">
            <button
              type="button"
              className="ac-primary"
              disabled={!words}
              onClick={() => {
                startStory?.(SHORT.key);
                open(SHORT.start.section as WorkspaceSection, SHORT.start.tab);
              }}
            >
              Review this sample event <ChevronRight size={15} aria-hidden="true" />
            </button>
            <button type="button" className="ac-link" onClick={() => open("Getting started")}>
              More stories
            </button>
          </div>
          <p className="uw-entrance-tag">Fictional manufacturer · Sample data only</p>
        </div>
        <aside className="uw-home-hero-side" aria-label={`${SHORT.steps.length} steps`}>
          <span className="ac-eyebrow">{SHORT.steps.length} steps</span>
          <ol>
            {SHORT.steps.map((step, index) => (
              <li key={step.label}>
                <span className="uw-home-step" aria-hidden="true">
                  {index + 1}
                </span>
                <span>
                  {step.label}
                  {index === SHORT.steps.length - 1 && <small>The record you can hand to a colleague</small>}
                </span>
              </li>
            ))}
          </ol>
        </aside>
      </section>
    </>
  );
}

/** The Regulatory Leader's legal clocks: each market's deadline, soonest first, with how much time is used. */
function LegalClocks({ clocks, onOpen }: { clocks: OversightItem[]; onOpen: (item: OversightItem) => void }) {
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
        <p className="ac-muted uw-card-pad">No legal clock is running.</p>
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
