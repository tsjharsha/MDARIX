import { useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Bot,
  ChevronDown,
  FileWarning,
  HeartPulse,
  Inbox,
  Layers,
  X,
} from "lucide-react";
import { BarList, Empty, Panel, type PanelSource } from "../../admin/console/charts";
import type { Slice } from "../../admin/console/dashboardModel";
import { AnimatedNumber, prefersReducedMotion } from "../../admin/console/motion";
import { Tabs } from "../../customer-admin/shared";
import { useWorkspace } from "../workspaceContext";
import { countOf } from "./common";
import {
  FACETS,
  FACET_NAMES,
  FACET_TABS,
  RECENT_MONTHS,
  activeFilters,
  applyFilters,
  breakdown,
  clearFilter,
  filterText,
  headlineOf,
  monthLabel,
  monthSeries,
  rateText,
  toggleFilter,
  trendOf,
  trendSummary,
  unrecordedText,
  valueLabel,
  type Facet,
  type InsightAnswer,
  type InsightFilters,
  type InsightQuestion,
  type Insights,
  type Trend,
} from "../trialInsights";

// Bars a breakdown tab shows before it says how many more values there are.
const BARS_SHOWN = 8;
// Complaint IDs listed under the filter before "and N more".
const IDS_SHOWN = 40;

const slices = (items: { label: string; count: number }[]): Slice[] =>
  items.map((item) => ({ key: item.label, label: item.label, count: item.count, tone: "neutral" }));

/**
 * Getting started › Automatic insights: headline numbers that count up, the monthly trend with the last three months
 * against the months before, breakdowns whose bars filter the whole panel, and questions to ask next that answer
 * themselves from the records (rules on the server, no AI). One request (GET /api/v1/trial/insights) feeds it all.
 */
export function InsightsPanel({ insights, source }: { insights: Insights | null; source: PanelSource }) {
  const { open, notify, work } = useWorkspace();
  const [filters, setFilters] = useState<InsightFilters>({});
  const [tab, setTab] = useState<Facet>("version");
  const [expanded, setExpanded] = useState<string | null>(null);
  // Read once: a person who asked their system for less motion sees every number and bar at its end state.
  const [still] = useState(prefersReducedMotion);
  // New data (an import, the sample removed) starts unfiltered: a value filtered on may no longer exist.
  const [loaded, setLoaded] = useState(insights);
  if (insights !== loaded) {
    setLoaded(insights);
    setFilters({});
    setExpanded(null);
  }
  return (
    <Panel
      title="Automatic insights"
      eyebrow={insights ? `From ${insights.scope} · ${countOf(insights.total_complaints, "complaint")}` : "Insights"}
      source={source}
    >
      {insights && (
        <InsightsBody
          insights={insights}
          filters={filters}
          onFilter={(facet, value) => setFilters((current) => toggleFilter(current, facet, value))}
          onClear={(facet) => setFilters((current) => (facet ? clearFilter(current, facet) : {}))}
          tab={tab}
          onTab={setTab}
          expanded={expanded}
          onExpand={(key) => setExpanded((current) => (current === key ? null : key))}
          still={still}
          onOpenComplaints={(text) => {
            open("Complaints");
            if (text)
              notify(
                `Complaints opened. It has no filter for ${text} yet; the IDs are listed under Automatic insights.`,
              );
          }}
          onOpenCase={(item) => {
            work.setInvestigationId(item.id, item.product_id);
            open("Investigations");
          }}
          onAsk={(question) => {
            void navigator.clipboard?.writeText(question).catch(() => undefined);
            open("Intelligence", "Ask MDARIX");
            notify(`Question copied. Paste it into Ask MDARIX: "${question}"`);
          }}
        />
      )}
    </Panel>
  );
}

/** The panel's content for given filters, tab and open question (exported so its test can render each state). */
export function InsightsBody({
  insights,
  filters,
  onFilter,
  onClear,
  tab,
  onTab,
  expanded,
  onExpand,
  still,
  onOpenComplaints,
  onOpenCase,
  onAsk,
}: {
  insights: Insights;
  filters: InsightFilters;
  onFilter: (facet: Facet, value: string) => void;
  onClear: (facet?: Facet) => void;
  tab: Facet;
  onTab: (tab: Facet) => void;
  expanded: string | null;
  onExpand: (key: string) => void;
  still: boolean;
  onOpenComplaints: (filterText: string) => void;
  onOpenCase: (item: InsightAnswer["cases"][number]) => void;
  onAsk: (question: string) => void;
}) {
  const records = insights.records;
  const labels = insights.version_labels ?? {};
  const series = useMemo(() => monthSeries((records ?? []).map((record) => record.month)), [records]);
  const shown = useMemo(() => applyFilters(records ?? [], filters), [records, filters]);
  if (insights.total_complaints === 0)
    return <Empty title="No complaints yet" detail="Upload complaints to see where they concentrate." />;
  const active = activeFilters(filters);
  const headline = headlineOf(shown, series, labels);
  const trend = trendOf(shown, series);
  const tabs = FACETS.map((facet) => FACET_TABS[facet]);
  const facetOf = (label: string) => FACETS.find((facet) => FACET_TABS[facet] === label) ?? "version";
  const parts = breakdown(shown, tab, labels);
  const described = filterText(filters, labels);
  return (
    <div className={`uw-ins${still ? " is-still" : ""}`}>
      {insights.findings.length > 0 && (
        <ul className="uw-trial-findings">
          {insights.findings.map((finding) => (
            <li key={finding}>{finding}</li>
          ))}
        </ul>
      )}
      {records && (
        <>
          <HeadlineNumbers headline={headline} still={still} />

          <div className="uw-ins-filterbar" aria-live="polite">
            {active.length ? (
              <>
                <span>
                  Showing {countOf(shown.length, "complaint")} of {records.length.toLocaleString()}:
                </span>
                {active.map(({ facet, value }) => (
                  <span className="uw-ins-chip" key={facet}>
                    {FACET_NAMES[facet]}: {valueLabel(facet, value, labels)}
                    <button
                      type="button"
                      onClick={() => onClear(facet)}
                      aria-label={`Clear the filter ${valueLabel(facet, value, labels)}`}
                    >
                      <X size={14} aria-hidden="true" />
                    </button>
                  </span>
                ))}
                <button type="button" className="ac-link" onClick={() => onClear()}>
                  Clear all
                </button>
              </>
            ) : (
              <span className="ac-muted">
                All {countOf(records.length, "complaint")}. Click a bar to see only its complaints; bars on different
                tabs combine.
              </span>
            )}
            <button type="button" className="ac-link uw-ins-open" onClick={() => onOpenComplaints(described)}>
              Open these complaints <ArrowRight size={14} aria-hidden="true" />
            </button>
          </div>
          {active.length > 0 && (
            <details className="uw-ins-ids">
              <summary>List the {countOf(shown.length, "complaint")}</summary>
              <p>
                {shown
                  .slice(0, IDS_SHOWN)
                  .map((record) =>
                    record.ref && record.ref !== record.id ? `${record.id} (${record.ref})` : record.id,
                  )
                  .join(", ")}
                {shown.length > IDS_SHOWN && ` and ${(shown.length - IDS_SHOWN).toLocaleString()} more`}
              </p>
            </details>
          )}

          <div>
            <h3 className="uw-trial-subhead">Complaints per month</h3>
            <MonthlyTrend trend={trend} still={still} />
          </div>

          <div>
            <h3 className="uw-trial-subhead">Where complaints concentrate</h3>
            <Tabs
              tabs={tabs}
              active={FACET_TABS[tab]}
              onChange={(label) => onTab(facetOf(label))}
              label="Complaints by"
              counts={Object.fromEntries(
                FACETS.map((facet) => [FACET_TABS[facet], breakdown(shown, facet, labels).items.length]),
              )}
            >
              {parts.items.length ? (
                <ul className="uw-ins-bars">
                  {parts.items.slice(0, BARS_SHOWN).map((item, index) => {
                    const max = parts.items[0].count;
                    const pressed = filters[tab] === item.key;
                    return (
                      <li key={item.key}>
                        <button
                          type="button"
                          aria-pressed={pressed}
                          className={pressed ? "is-on" : ""}
                          onClick={() => onFilter(tab, item.key)}
                          title={pressed ? "Click again to clear this filter" : "Show only these complaints"}
                        >
                          <span className="uw-ins-bar-label">{item.label}</span>
                          <span className="uw-ins-bar-track" aria-hidden="true">
                            <span
                              className="uw-ins-bar-fill"
                              style={{ width: `${Math.max(2, (item.count / max) * 100)}%`, ["--i" as string]: index }}
                            />
                          </span>
                          <strong className="uw-ins-bar-value">{item.count.toLocaleString()}</strong>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="uw-trial-note">
                  No complaint {active.length ? "in this filter " : ""}records a {FACET_NAMES[tab].toLowerCase()}.
                </p>
              )}
              {parts.items.length > BARS_SHOWN && (
                <p className="uw-trial-note">
                  And {countOf(parts.items.length - BARS_SHOWN, "more value")} with fewer complaints.
                </p>
              )}
              {parts.unrecorded > 0 && parts.items.length > 0 && (
                <p className="uw-trial-note">{unrecordedText(tab, parts.unrecorded)}</p>
              )}
            </Tabs>
          </div>
        </>
      )}

      {insights.questions?.length ? (
        <div>
          <h3 className="uw-trial-subhead">Questions to ask next</h3>
          <p className="uw-trial-note">
            Answered from all {countOf(insights.total_complaints, "complaint")} by fixed rules, not by AI
            {active.length ? "; the filter above does not change them" : ""}.
          </p>
          <ul className="uw-ins-questions">
            {insights.questions.map((item) => (
              <QuestionItem
                key={item.key}
                item={item}
                open={expanded === item.key}
                onToggle={() => onExpand(item.key)}
                onOpenCase={onOpenCase}
                onAsk={onAsk}
              />
            ))}
          </ul>
        </div>
      ) : null}
      <p className="uw-trial-note">{insights.note}</p>
    </div>
  );
}

function Count({ value, still, suffix = "" }: { value: number; still: boolean; suffix?: string }) {
  return still ? (
    <>
      {value.toLocaleString()}
      {suffix}
    </>
  ) : (
    <AnimatedNumber value={value} suffix={suffix} compact={false} />
  );
}

function HeadlineNumbers({ headline, still }: { headline: ReturnType<typeof headlineOf>; still: boolean }) {
  const rate = headline.rate;
  const Arrow = rate?.direction === "up" ? ArrowUpRight : rate?.direction === "down" ? ArrowDownRight : ArrowRight;
  return (
    <div className="uw-ins-stats">
      <Stat icon={<Inbox size={18} />} label="Complaints" detail="In view">
        <Count value={headline.total} still={still} />
      </Stat>
      <Stat icon={<HeartPulse size={18} />} label="With harm" detail="Death or serious injury reported">
        <Count value={headline.harm} still={still} />
      </Stat>
      <Stat icon={<AlertTriangle size={18} />} label="Malfunctions" detail="Malfunction reported">
        <Count value={headline.malfunction} still={still} />
      </Stat>
      <Stat
        icon={<Layers size={18} />}
        label="Top version"
        detail={
          headline.topVersion
            ? `${headline.topVersion.label}, ${countOf(headline.topVersion.complaints, "complaint")}`
            : "No version recorded"
        }
      >
        {headline.topVersion ? <Count value={headline.topVersion.share} still={still} suffix="%" /> : "—"}
      </Stat>
      <Stat
        icon={<Arrow size={18} />}
        label="Recent rate"
        detail={
          rate
            ? `Per month, the last ${RECENT_MONTHS} months; ${rateText(rate.earlier)} before (${
                rate.direction === "up" ? "up" : rate.direction === "down" ? "down" : "no change"
              })`
            : "Needs four months or more to compare"
        }
      >
        {rate ? rateText(rate.recent) : "—"}
      </Stat>
    </div>
  );
}

function Stat({
  icon,
  label,
  detail,
  children,
}: {
  icon: ReactNode;
  label: string;
  detail: string;
  children: ReactNode;
}) {
  return (
    <div className="ac-stat uw-ins-stat">
      <span className="ac-stat-icon" aria-hidden="true">
        {icon}
      </span>
      <span className="ac-stat-label">{label}</span>
      <strong className="ac-stat-value">{children}</strong>
      <span className="ac-stat-detail">{detail}</span>
    </div>
  );
}

/** Columns per month, the last three highlighted against a dashed line at the earlier months' average. */
export function MonthlyTrend({ trend, still }: { trend: Trend; still: boolean }) {
  const [asTable, setAsTable] = useState(false);
  const peak = Math.max(1, ...trend.months.map((item) => item.complaints), trend.earlierAverage ?? 0);
  const summary = trendSummary(trend);
  return (
    <div className="uw-ins-trend">
      <div className="uw-ins-trend-bar">
        <span className="uw-ins-legend">
          {trend.recentAverage !== null && (
            <>
              <span>
                <i className="uw-ins-key is-recent" aria-hidden="true" /> Last {RECENT_MONTHS} months
              </span>
              <span>
                <i className="uw-ins-key" aria-hidden="true" /> Before
              </span>
              <span>
                <i className="uw-ins-key is-line" aria-hidden="true" /> Average before:{" "}
                {rateText(trend.earlierAverage ?? 0)} per month
              </span>
            </>
          )}
        </span>
        <button type="button" className="ac-link" onClick={() => setAsTable((value) => !value)} aria-pressed={asTable}>
          {asTable ? "Show chart" : "Show table"}
        </button>
      </div>
      {asTable ? (
        <div className="ac-table-wrap">
          <table className="ac-table">
            <caption className="ca-sr-only">{summary}</caption>
            <thead>
              <tr>
                <th scope="col">Month</th>
                <th scope="col" className="num">
                  Complaints
                </th>
              </tr>
            </thead>
            <tbody>
              {trend.months.map((item) => (
                <tr key={item.month}>
                  <td>
                    {monthLabel(item.month)}
                    {item.recent ? ` (last ${RECENT_MONTHS} months)` : ""}
                  </td>
                  <td className="num">{item.complaints}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <figure className="uw-ins-plot" role="img" aria-label={summary}>
          {trend.earlierAverage !== null && (
            <span
              className="uw-ins-average"
              // Above the 22px tick band, at the average's share of the 40px-shorter plot height.
              style={{ bottom: `calc(22px + (100% - 40px) * ${trend.earlierAverage / peak})` }}
              aria-hidden="true"
            />
          )}
          {trend.months.map((item, index) => (
            <span
              key={item.month}
              className={`uw-ins-month${item.recent ? " is-recent" : ""}`}
              title={`${monthLabel(item.month)}: ${countOf(item.complaints, "complaint")}`}
              aria-hidden="true"
            >
              <span className="uw-ins-month-value" style={{ bottom: `${(item.complaints / peak) * 100}%` }}>
                {item.complaints}
              </span>
              <span
                className="uw-ins-month-fill"
                style={{ height: `${(item.complaints / peak) * 100}%`, ["--i" as string]: index }}
              />
              <span className="uw-ins-month-tick">{monthLabel(item.month).replace(" 20", " '")}</span>
            </span>
          ))}
        </figure>
      )}
    </div>
  );
}

/** One question: the question as a button, its answer below it once opened. */
export function QuestionItem({
  item,
  open,
  onToggle,
  onOpenCase,
  onAsk,
}: {
  item: InsightQuestion;
  open: boolean;
  onToggle: () => void;
  onOpenCase: (item: InsightAnswer["cases"][number]) => void;
  onAsk: (question: string) => void;
}) {
  const answer = item.answer;
  const id = `uw-ins-answer-${item.key}`;
  return (
    <li className={open ? "is-open" : ""}>
      <button type="button" className="uw-ins-question" aria-expanded={open} aria-controls={id} onClick={onToggle}>
        <ChevronDown size={16} aria-hidden="true" />
        <span>{item.question}</span>
      </button>
      <div id={id} className="uw-ins-answer" hidden={!open}>
        <p className="uw-ins-summary">{answer.summary}</p>
        {answer.bars?.length ? <BarList colour="series" items={slices(answer.bars)} /> : null}
        {answer.table && answer.table.rows.length > 0 && (
          <div className="ac-table-wrap">
            <table className="ac-table">
              <thead>
                <tr>
                  {answer.table.columns.map((column) => (
                    <th scope="col" key={column}>
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {answer.table.rows.map((row, index) => (
                  <tr key={index}>
                    {row.map((cell, column) => (
                      <td key={column} className={typeof cell === "number" ? "num" : undefined}>
                        {typeof cell === "number" ? cell.toLocaleString() : cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {answer.facts.length > 0 && (
          <ul className="uw-ins-facts">
            {answer.facts.map((fact) => (
              <li key={fact}>{fact}</li>
            ))}
          </ul>
        )}
        {answer.ids.length > 0 && (
          <p className="uw-ins-used">
            <b>Complaints used:</b> {answer.ids.join(", ")}
            {answer.ids_total > answer.ids.length &&
              ` and ${(answer.ids_total - answer.ids.length).toLocaleString()} more`}
          </p>
        )}
        {answer.cases.length > 0 && (
          <p className="uw-ins-used">
            <b>Investigations:</b>{" "}
            {answer.cases.map((item) => (
              <button type="button" className="ac-link" key={item.id} onClick={() => onOpenCase(item)}>
                {item.business_id}
              </button>
            ))}
          </p>
        )}
        <p className="uw-ins-basis">
          <b>Based on:</b> {answer.basis}
        </p>
        {answer.missing.length > 0 && (
          <div className="uw-ins-missing">
            <b>
              <FileWarning size={14} aria-hidden="true" /> Not in the records
            </b>
            <ul>
              {answer.missing.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
        )}
        <button type="button" className="ac-link" onClick={() => onAsk(item.question)}>
          <Bot size={15} aria-hidden="true" /> Ask MDARIX to look further
        </button>
      </div>
    </li>
  );
}
