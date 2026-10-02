import { useId, useMemo, useState, type ReactNode } from "react";
import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { ToneIcon } from "./charts";
import type { Tone } from "./dashboardModel";
import { AnimatedNumber } from "./motion";

export type TrendPoint = { date: string; label: string; primary: number; secondary?: number };
/** One day of a dashboard series from the server: {date, ...counts}. */
export type DailyRow = { date: string } & Record<string, number | string>;

const dayLabel = (date: string) =>
  new Date(`${date}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

/**
 * Daily rows as chart points. With `totalOfAll`, the primary value is the day's total over `primary`, `secondary`
 * and `alsoCounted` (e.g. runs = completed + warnings + failed) and the secondary value is the `secondary` part.
 */
export const toPoints = (
  rows: DailyRow[] | undefined,
  primary: string,
  secondary?: string,
  totalOfAll = false,
  alsoCounted: string[] = [],
): TrendPoint[] =>
  (rows ?? []).map((row) => {
    const value = (key: string) => Number(row[key] ?? 0);
    const second = secondary ? value(secondary) : undefined;
    const first = totalOfAll
      ? value(primary) + (second ?? 0) + alsoCounted.reduce((sum, key) => sum + value(key), 0)
      : value(primary);
    return { date: String(row.date), label: dayLabel(String(row.date)), primary: first, secondary: second };
  });

const niceTop = (value: number) => {
  if (value <= 4) return Math.max(1, value <= 2 ? 2 : 4);
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((candidate) => candidate * magnitude >= value) ?? 10;
  return step * magnitude;
};

/** A path through the points, scaled to a width x height box (y grows downward). */
const linePath = (values: number[], width: number, height: number, top: number) =>
  values
    .map((value, index) => {
      const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
      const y = height - (Math.min(value, top) / top) * height;
      return `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

/** Change between the last half of a series and the half before it, in whole percent (null when not comparable). */
export const halfOverHalf = (values: number[]) => {
  const half = Math.floor(values.length / 2);
  if (!half) return null;
  const sum = (part: number[]) => part.reduce((total, value) => total + value, 0);
  const previous = sum(values.slice(values.length - 2 * half, values.length - half));
  const current = sum(values.slice(values.length - half));
  if (!previous) return current ? null : 0;
  return Math.round(((current - previous) / previous) * 100);
};

/** The change as a reader takes it in: "+12%", a multiple ("16×") when it is large, "New" from nothing. */
export const changeText = (change: number | null, previousWasZero = false) => {
  if (change === null) return previousWasZero ? "New" : "";
  if (Math.abs(change) >= 200) return `${Math.round(change / 100 + 1)}×`;
  return `${Math.abs(change)}%`;
};

/** A small trend line under a figure: the shape over the period, drawn in when it appears. */
export function Sparkline({ values, label }: { values: number[]; label: string }) {
  const top = Math.max(1, ...values);
  const path = linePath(values, 100, 28, top);
  const gradient = useId();
  return (
    <svg className="ac-spark" viewBox="0 0 100 30" preserveAspectRatio="none" role="img" aria-label={label}>
      <defs>
        <linearGradient id={gradient} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.22" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      {values.length > 1 && (
        <>
          <path className="ac-spark-area" d={`${path} L100,30 L0,30 Z`} fill={`url(#${gradient})`} />
          <path className="ac-spark-line" d={path} pathLength={1} vectorEffect="non-scaling-stroke" />
        </>
      )}
    </svg>
  );
}

/** A headline figure with an icon, a counting number, the change over the period and a trend line. */
export function KpiTile({
  label,
  value,
  suffix,
  detail,
  icon,
  tone,
  series,
  seriesLabel,
  onOpen,
  goodWhenUp = true,
}: {
  label: string;
  value: number | null;
  suffix?: string;
  detail: string;
  icon: ReactNode;
  tone?: Tone;
  series?: number[];
  seriesLabel?: string;
  onOpen?: () => void;
  /** Whether a rise is good news; null when the direction is neither (the change is shown in grey). */
  goodWhenUp?: boolean | null;
}) {
  const change = series ? halfOverHalf(series) : null;
  const half = series ? Math.floor(series.length / 2) : 0;
  const previousWasZero =
    !!series && half > 0 && series.slice(series.length - 2 * half, series.length - half).every((value) => !value);
  const showChange = change !== null || (previousWasZero && !!series?.slice(-half).some(Boolean));
  const direction = change === null || change === 0 ? "flat" : change > 0 ? "up" : "down";
  const changeTone =
    direction === "flat" || goodWhenUp === null ? "flat" : (direction === "up") === goodWhenUp ? "better" : "worse";
  const body = (
    <>
      <span className="ac-kpi-head">
        <span className="ac-stat-icon" aria-hidden="true">
          {icon}
        </span>
        <span className="ac-kpi-label">{label}</span>
        {showChange && (
          <span
            className={`ac-kpi-change ${change === null && goodWhenUp !== null ? (goodWhenUp ? "better" : "worse") : changeTone}`}
            title="Last half of the period against the half before"
          >
            {direction === "up" || change === null ? (
              <ArrowUpRight size={13} aria-hidden="true" />
            ) : direction === "down" ? (
              <ArrowDownRight size={13} aria-hidden="true" />
            ) : (
              <ArrowRight size={13} aria-hidden="true" />
            )}
            {changeText(change, previousWasZero)}
          </span>
        )}
      </span>
      <strong className="ac-kpi-value">
        <AnimatedNumber value={value} suffix={suffix} />
      </strong>
      <span className="ac-stat-detail">
        {tone && <ToneIcon tone={tone} size={14} />}
        {detail}
      </span>
      {series && series.length > 1 && <Sparkline values={series} label={seriesLabel ?? `${label} trend`} />}
    </>
  );
  return onOpen ? (
    <button type="button" className="ac-kpi" onClick={onOpen}>
      {body}
    </button>
  ) : (
    <div className="ac-kpi">{body}</div>
  );
}

/**
 * Daily activity as an area with an optional second line (for example failures), its own scale, a hover readout
 * per day and a table view. One chart per measure: measures of different size are never put on a shared axis.
 */
export function TrendChart({
  data,
  primaryLabel,
  secondaryLabel,
  unit,
}: {
  data: TrendPoint[];
  primaryLabel: string;
  secondaryLabel?: string;
  unit: string;
}) {
  const [active, setActive] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);
  const gradient = useId();
  const primary = data.map((point) => point.primary);
  const secondary = secondaryLabel ? data.map((point) => point.secondary ?? 0) : null;
  const top = niceTop(Math.max(0, ...primary, ...(secondary ?? [])));
  const width = 600;
  const height = 160;
  const primaryPath = useMemo(() => linePath(primary, width, height, top), [primary, top]);
  const secondaryPath = useMemo(() => (secondary ? linePath(secondary, width, height, top) : ""), [secondary, top]);
  const total = primary.reduce((sum, value) => sum + value, 0);
  const secondaryTotal = secondary?.reduce((sum, value) => sum + value, 0) ?? 0;
  const point = active === null ? null : data[active];
  const left = active === null ? 0 : data.length > 1 ? (active / (data.length - 1)) * 100 : 50;
  const ticks = data.length ? [0, Math.floor((data.length - 1) / 2), data.length - 1] : [];
  return (
    <div className="ac-trend">
      <div className="ac-trend-bar">
        <span className="ac-trend-legend">
          <span className="ac-key key-primary" aria-hidden="true" />
          <strong>
            <AnimatedNumber value={total} compact={false} />
          </strong>{" "}
          {primaryLabel}
          {secondaryLabel && (
            <>
              <span className="ac-key key-secondary" aria-hidden="true" />
              <strong>{secondaryTotal.toLocaleString()}</strong> {secondaryLabel}
            </>
          )}
        </span>
        <button type="button" className="ac-link" onClick={() => setAsTable((value) => !value)} aria-pressed={asTable}>
          {asTable ? "Show chart" : "Show table"}
        </button>
      </div>
      {asTable ? (
        <div className="ac-table-wrap ac-trend-table">
          <table className="ac-table">
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col" className="num">
                  {primaryLabel}
                </th>
                {secondaryLabel && (
                  <th scope="col" className="num">
                    {secondaryLabel}
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr key={row.date}>
                  <td>{row.label}</td>
                  <td className="num">{row.primary}</td>
                  {secondaryLabel && <td className="num">{row.secondary ?? 0}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="ac-trend-chart">
          <div className="ac-trend-axis" aria-hidden="true">
            <span>{top.toLocaleString()}</span>
            <span>{(top / 2).toLocaleString()}</span>
            <span>0</span>
          </div>
          <div className="ac-trend-plot" onMouseLeave={() => setActive(null)}>
            <svg
              viewBox={`0 0 ${width} ${height}`}
              preserveAspectRatio="none"
              role="img"
              aria-label={`${unit} per day`}
            >
              <defs>
                <linearGradient id={gradient} x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="var(--ac-series)" stopOpacity="0.28" />
                  <stop offset="100%" stopColor="var(--ac-series)" stopOpacity="0.02" />
                </linearGradient>
              </defs>
              <line className="ac-trend-grid" x1="0" x2={width} y1="0.5" y2="0.5" />
              <line className="ac-trend-grid" x1="0" x2={width} y1={height / 2} y2={height / 2} />
              <path
                className="ac-trend-area"
                d={`${primaryPath} L${width},${height} L0,${height} Z`}
                fill={`url(#${gradient})`}
              />
              <path className="ac-trend-line" d={primaryPath} pathLength={1} vectorEffect="non-scaling-stroke" />
              {secondary && (
                <path
                  className="ac-trend-line secondary"
                  d={secondaryPath}
                  pathLength={1}
                  vectorEffect="non-scaling-stroke"
                />
              )}
              <line className="ac-trend-base" x1="0" x2={width} y1={height - 0.5} y2={height - 0.5} />
              {data.map((row, index) => (
                <rect
                  key={row.date}
                  className="ac-trend-hit"
                  x={data.length > 1 ? (index / (data.length - 1)) * width - width / (2 * (data.length - 1)) : 0}
                  y="0"
                  width={data.length > 1 ? width / (data.length - 1) : width}
                  height={height}
                  onMouseEnter={() => setActive(index)}
                />
              ))}
            </svg>
            {point && (
              <>
                <span className="ac-trend-cross" style={{ left: `${left}%` }} aria-hidden="true">
                  <span className="ac-trend-dot" style={{ bottom: `${(Math.min(point.primary, top) / top) * 100}%` }} />
                  {secondary && (
                    <span
                      className="ac-trend-dot secondary"
                      style={{ bottom: `${(Math.min(point.secondary ?? 0, top) / top) * 100}%` }}
                    />
                  )}
                </span>
                <span
                  className={`ac-tooltip ac-trend-tip ${left > 75 ? "edge-end" : left < 25 ? "edge-start" : ""}`}
                  style={{ left: `${left}%` }}
                  role="tooltip"
                >
                  <span>{point.label}</span>
                  <strong>
                    {point.primary.toLocaleString()} {primaryLabel}
                  </strong>
                  {secondaryLabel && (
                    <strong className="secondary">
                      {(point.secondary ?? 0).toLocaleString()} {secondaryLabel}
                    </strong>
                  )}
                </span>
              </>
            )}
            <div className="ac-trend-ticks" aria-hidden="true">
              {ticks.map((index) => (
                <span key={index} style={{ left: `${data.length > 1 ? (index / (data.length - 1)) * 100 : 50}%` }}>
                  {data[index]?.label}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
