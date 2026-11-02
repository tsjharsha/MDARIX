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
import { useAiReady } from "../useAiStatus";
import { handQuestionToAsk } from "../../ask/pendingQuestion";
import { countOf } from "./common";
import { TrendHero } from "./TrendHero";
import { complaintListTab, insightComplaintFilters } from "../complaintList";
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
  numericColumns,
  rateText,
  toggleFilter,
  trendOf,
  unrecordedText,
  valueLabel,
  type Facet,
  type InsightAnswer,
  type InsightFilters,
  type InsightQuestion,
  type Insights,
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
/** What the panel says while it reads complaints just imported (item 9). */
export const READING_IMPORTED = "Reading the complaints you just imported… The insights update by themselves.";

export function InsightsPanel({
  insights,
  source,
  reading = false,
}: {
  insights: Insights | null;
  source: PanelSource;
  /** Complaints were just imported and the insights shown are not theirs yet: say so instead of showing them. */
  reading?: boolean;
}) {
  const { open, notify, work } = useWorkspace();
  const [filters, setFilters] = useState<InsightFilters>({});
  const [tab, setTab] = useState<Facet>("version");
  const [expanded, setExpanded] = useState<string | null>(null);
  // Read once: a person who asked their system for less motion sees every number and bar at its end state.
  const [still] = useState(prefersReducedMotion);
  // "Ask MDARIX to look further" only while AI answers: without it Ask finds evidence records but counts no complaints.
  const aiReady = useAiReady() === true;
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
      eyebrow={
        reading
          ? "From your data"
          : insights
            ? `From ${insights.scope} · ${countOf(insights.total_complaints, "complaint")}`
            : "Insights"
      }
      source={source}
    >
      {reading && (
        <p className="ac-note" role="status">
          {READING_IMPORTED}
        </p>
      )}
      {insights && !reading && (
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
          // The complaint list, with the panel's filters and its data's source (the sample or the imported data).
          onOpenComplaints={() =>
            open("Complaints", complaintListTab(insightComplaintFilters(filters, insights.source_system)))
          }
          onOpenCase={(item) => {
            work.setInvestigationId(item.id, item.product_id);
            open("Investigations");
          }}
          onAsk={
            aiReady
              ? (question) => {
                  handQuestionToAsk(question);
                  open("Intelligence", "Ask MDARIX");
                  notify("Your question is in Ask MDARIX: press Ask MDARIX to run it.");
                }
              : null
          }
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
  /** Null hides "Ask MDARIX to look further" (AI not ready). */
  onAsk: ((question: string) => void) | null;
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
          <HeadlineNumbers headline={headline} still={still} ofAll={filters.version ? records.length : null} />

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

          <TrendHero trend={trend} still={still} replayKey={described || "all"} />

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
      {value.toLocaleString("en-US")}
      {suffix}
    </>
  ) : (
    <AnimatedNumber value={value} suffix={suffix} compact={false} />
  );
}

function HeadlineNumbers({
  headline,
  still,
  ofAll,
}: {
  headline: ReturnType<typeof headlineOf>;
  still: boolean;
  /** With a version filter on, the version's share of all complaints (its share of itself is always 100%). */
  ofAll: number | null;
}) {
  const rate = headline.rate;
  const Arrow =
    rate?.direction === "up" || rate?.direction === "new"
      ? ArrowUpRight
      : rate?.direction === "down"
        ? ArrowDownRight
        : ArrowRight;
  const top = headline.topVersion;
  const share = top && ofAll ? Math.round((100 * top.complaints) / ofAll) : top?.share;
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
        label={ofAll ? "Share of all" : "Top version"}
        detail={
          top
            ? ofAll
              ? `${top.label}: ${top.complaints.toLocaleString()} of all ${countOf(ofAll, "complaint")}`
              : `${top.label}, ${countOf(top.complaints, "complaint")}`
            : "No version recorded"
        }
      >
        {top && share !== undefined ? <Count value={share} still={still} suffix="%" /> : "—"}
      </Stat>
      <Stat
        icon={<Arrow size={18} />}
        label="Recent rate"
        detail={
          rate
            ? rate.direction === "new"
              ? `Per month, the last ${RECENT_MONTHS} months; none before ${monthLabel(rate.since)}`
              : `Per month, the last ${RECENT_MONTHS} months; ${rateText(rate.earlier)} before (${
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
  onAsk: ((question: string) => void) | null;
}) {
  const answer = item.answer;
  const numeric = answer.table ? numericColumns(answer.table) : [];
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
            <table className="ac-table ms-cards">
              <thead>
                <tr>
                  {answer.table.columns.map((column, index) => (
                    <th scope="col" key={column} className={numeric[index] ? "num" : undefined}>
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {answer.table.rows.map((row, index) => (
                  <tr key={index}>
                    {row.map((cell, column) => (
                      <td
                        key={column}
                        className={numeric[column] ? "num" : undefined}
                        data-label={answer.table!.columns[column]}
                      >
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
        {onAsk && (
          <button type="button" className="ac-link" onClick={() => onAsk(item.question)}>
            <Bot size={15} aria-hidden="true" /> Ask MDARIX to look further
          </button>
        )}
      </div>
    </li>
  );
}
