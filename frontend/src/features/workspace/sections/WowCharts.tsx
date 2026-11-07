import { useId, useState, type ReactNode } from "react";
import { BarChart3, Table2 } from "lucide-react";

/**
 * Small charts of the stage 8 "wow" screens, in the design system's tokens (workspace.css .uw-wow-*): every bar and
 * marker carries its number and words, never colour alone, and every chart has a table view with the same numbers.
 */

/** A chart with its table view: one toggle, the chart by default. */
export function ChartOrTable({
  title,
  chart,
  table,
  note,
}: {
  title: string;
  chart: ReactNode;
  table: ReactNode;
  note?: ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  const heading = useId();
  return (
    <section className="uw-wow" aria-labelledby={heading}>
      <div className="uw-wow-head">
        <h3 id={heading}>{title}</h3>
        <button type="button" className="ac-link" aria-pressed={asTable} onClick={() => setAsTable(!asTable)}>
          {asTable ? <BarChart3 size={14} aria-hidden="true" /> : <Table2 size={14} aria-hidden="true" />}{" "}
          {asTable ? "Chart view" : "Table view"}
        </button>
      </div>
      {asTable ? table : chart}
      {note && <p className="ac-muted uw-wow-note">{note}</p>}
    </section>
  );
}

export type BarRow = {
  key: string;
  label: string;
  value: number;
  /** The words beside the bar ("9 in the last 30 days"). */
  valueText: string;
  /** A reference to compare with (the earlier average), drawn as a marker with its own words. */
  reference?: number | null;
  referenceText?: string | null;
  /** Stands out (a significant rise, the lot the case is about): a stronger bar and a word, not colour alone. */
  flag?: string | null;
};

/** Horizontal bars, each with its number in words, and an optional reference marker per row. */
export function Bars({ rows, label }: { rows: BarRow[]; label: string }) {
  const max = Math.max(1, ...rows.map((row) => Math.max(row.value, row.reference ?? 0)));
  const pct = (value: number) => `${Math.max(0, Math.min(100, (100 * value) / max))}%`;
  return (
    <ul className="uw-wow-bars" aria-label={label}>
      {rows.map((row) => (
        <li key={row.key} className={row.flag ? "is-flag" : undefined}>
          <span className="uw-wow-label">
            {row.label}
            {row.flag && <strong className="uw-wow-flag"> · {row.flag}</strong>}
          </span>
          <span className="uw-wow-track" aria-hidden="true">
            <span className="uw-wow-bar" style={{ width: pct(row.value) }} />
            {row.reference != null && <span className="uw-wow-ref" style={{ left: pct(row.reference) }} />}
          </span>
          <span className="uw-wow-value">
            {row.valueText}
            {row.referenceText && <small> · {row.referenceText}</small>}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** The same rows as a table: label, value, reference. */
export function BarsTable({
  rows,
  caption,
  columns,
}: {
  rows: BarRow[];
  caption: string;
  columns: [string, string, string?];
}) {
  return (
    <table className="uw-wow-table">
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr>
          <th scope="col">{columns[0]}</th>
          <th scope="col">{columns[1]}</th>
          {columns[2] && <th scope="col">{columns[2]}</th>}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key}>
            <th scope="row">
              {row.label}
              {row.flag ? ` (${row.flag})` : ""}
            </th>
            <td>{row.valueText}</td>
            {columns[2] && <td>{row.referenceText ?? "—"}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export type Lane = {
  key: string;
  market: string;
  /** Where the clock starts (awareness) and ends (the legal deadline), ISO times. */
  from: string;
  to: string;
  /** What the clock is ("United States (FDA): 30-day report"). */
  note?: string;
  dueText: string;
  stateText: string;
  overdue: boolean;
  /** Seven days or less left (0.10.92, A15): only then is the lane amber, as the clock ring's "Due soon". */
  soon?: boolean;
};

/**
 * Legal clocks as one lane per market (wow screen 2): each from the awareness day to its deadline, today marked on
 * every lane, the deadline and the days left in words.
 */
export function ClockLanes({ lanes, now = new Date() }: { lanes: Lane[]; now?: Date }) {
  const start = Math.min(...lanes.map((lane) => Date.parse(lane.from)), now.getTime());
  const end = Math.max(...lanes.map((lane) => Date.parse(lane.to)), now.getTime());
  const span = Math.max(1, end - start);
  const at = (time: number) => `${(100 * (time - start)) / span}%`;
  return (
    <ul className="uw-wow-lanes" aria-label="Legal clocks, one lane per market">
      {lanes.map((lane) => (
        <li key={lane.key} className={lane.overdue ? "is-overdue" : lane.soon ? "is-soon" : undefined}>
          <span className="uw-wow-label">
            <strong>{lane.market}</strong>
            {lane.note && <small className="uw-wow-sub">{lane.note}</small>}
          </span>
          <span className="uw-wow-lane" aria-hidden="true">
            <span
              className="uw-wow-clock"
              style={{
                left: at(Date.parse(lane.from)),
                width: `calc(${at(Date.parse(lane.to))} - ${at(Date.parse(lane.from))})`,
              }}
            />
            <span className="uw-wow-today" style={{ left: at(now.getTime()) }} />
            <span className="uw-wow-due" style={{ left: at(Date.parse(lane.to)) }} />
          </span>
          <span className="uw-wow-value">
            {lane.dueText}
            <small> · {lane.stateText}</small>
          </span>
        </li>
      ))}
      <li className="uw-wow-legend" aria-hidden="true">
        <span />
        <span>
          <i className="uw-wow-key-today" /> today · <i className="uw-wow-key-due" /> legal deadline
        </span>
        <span />
      </li>
    </ul>
  );
}
