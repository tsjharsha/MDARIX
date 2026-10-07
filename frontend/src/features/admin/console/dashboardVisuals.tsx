import { useState, type ReactNode } from "react";
import { ToneIcon } from "./charts";
import { compactNumber, type Tone } from "./dashboardModel";
import { AnimatedNumber } from "./motion";
import { TrendChart, type TrendPoint } from "./trendCharts";

/* The platform administrator's dashboard visuals: the period switch, the platform pulse (how activity flows from
   customers to the audit trail), a donut for shares of a whole, and the activity explorer. Motion is decorative:
   every number and state is also written out, and nothing moves when the person asked for less motion. */

export const RANGES = [7, 30, 90] as const;
export type Range = (typeof RANGES)[number];

/** The period the dashboard's activity covers. */
export function RangeSwitch({ days, onChange }: { days: number; onChange: (days: Range) => void }) {
  return (
    <div className="ac-range" role="group" aria-label="Period">
      {RANGES.map((range) => (
        <button
          key={range}
          type="button"
          aria-pressed={days === range}
          className={days === range ? "selected" : ""}
          onClick={() => onChange(range)}
        >
          {range} days
        </button>
      ))}
    </div>
  );
}

export type PulseNode = {
  key: string;
  label: string;
  value: number | null;
  detail: string;
  icon: ReactNode;
  tone: Tone;
  /** How busy the flow into this step is, 0 (quiet) to 1 (busiest); sets how fast its link moves. */
  activity?: number;
  onOpen?: () => void;
};

/**
 * How work flows through the platform, left to right: customers own tenants, their people use them, data comes in,
 * AI assists, and everything is recorded. Each step shows its figure and state; the moving dots between steps show
 * how busy each flow was in the period (faster is busier). Each step opens its area.
 */
export function PlatformPulse({ nodes }: { nodes: PulseNode[] }) {
  return (
    <ol className="ac-pulse" aria-label="How activity flows through the platform">
      {nodes.map((node, index) => (
        <li key={node.key} className="ac-pulse-step" style={{ ["--step" as string]: index }}>
          {index > 0 && (
            <span
              className={`ac-pulse-link tone-${node.tone}${node.activity ? "" : " quiet"}`}
              style={{ ["--pulse-speed" as string]: `${pulseSeconds(node.activity)}s` }}
              aria-hidden="true"
            >
              <i />
              <i />
              <i />
            </span>
          )}
          <button
            type="button"
            className={`ac-pulse-node tone-${node.tone}`}
            onClick={node.onOpen}
            disabled={!node.onOpen}
          >
            <span className="ac-pulse-icon" aria-hidden="true">
              {node.icon}
              <span className="ac-pulse-state">
                <ToneIcon tone={node.tone} size={13} />
              </span>
            </span>
            <strong className="ac-pulse-value">
              <AnimatedNumber value={node.value} />
            </strong>
            <span className="ac-pulse-label">{node.label}</span>
            <small className="ac-pulse-detail">{node.detail}</small>
          </button>
        </li>
      ))}
    </ol>
  );
}

/** Seconds for one dot to cross a link: 1.4 s when busiest, 6 s when barely active. */
export const pulseSeconds = (activity = 0) => Math.round((6 - 4.6 * Math.max(0, Math.min(1, activity))) * 10) / 10;

/** Busyness 0..1 of a per-day rate against the busiest rate shown, on a square-root scale so small flows still move. */
export const busyness = (rate: number, busiest: number) =>
  rate > 0 && busiest > 0 ? Math.max(0.12, Math.sqrt(rate / busiest)) : 0;

// The categorical slots of the console's validated palette, in their documented order (slot 1 is --ac-series).
const CATEGORY_COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"];

export type Share = { key: string; label: string; count: number };

/** At most six slices; the rest fold into "Other" so every colour stays tellable apart. */
export const foldShares = (items: Share[], max = CATEGORY_COLOURS.length): Share[] => {
  const sorted = [...items].filter((item) => item.count > 0).sort((a, b) => b.count - a.count);
  if (sorted.length <= max) return sorted;
  const kept = sorted.slice(0, max - 1);
  const rest = sorted.slice(max - 1).reduce((sum, item) => sum + item.count, 0);
  return [...kept, { key: "__other", label: "Other", count: rest }];
};

/**
 * A share of a whole as a ring with its legend beside it. Every slice is labelled with its count and share in the
 * legend (never colour alone); pointing at a slice or its legend row shows it in the middle.
 */
export function Donut({ items, unit, onSelect }: { items: Share[]; unit: string; onSelect?: (key: string) => void }) {
  const [active, setActive] = useState<string | null>(null);
  const shares = foldShares(items);
  const total = shares.reduce((sum, item) => sum + item.count, 0);
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const gap = shares.length > 1 ? 1.6 : 0; // a surface gap between slices
  let offset = 0;
  const focus = shares.find((item) => item.key === active);
  return (
    <div className="ac-donut">
      <svg
        viewBox="0 0 100 100"
        role="img"
        aria-label={`${unit}: ${shares.map((s) => `${s.label} ${s.count}`).join(", ")}`}
      >
        <circle className="ac-donut-track" cx="50" cy="50" r={radius} />
        {shares.map((item, index) => {
          const length = total ? (item.count / total) * circumference : 0;
          const dash = Math.max(0, length - gap);
          const slice = (
            <circle
              key={item.key}
              className={`ac-donut-slice${active && active !== item.key ? " dim" : ""}`}
              cx="50"
              cy="50"
              r={radius}
              stroke={CATEGORY_COLOURS[index]}
              strokeDasharray={`${dash} ${circumference - dash}`}
              strokeDashoffset={-offset}
              transform="rotate(-90 50 50)"
              onMouseEnter={() => setActive(item.key)}
              onMouseLeave={() => setActive(null)}
            />
          );
          offset += length;
          return slice;
        })}
        <text className="ac-donut-value" x="50" y="49" textAnchor="middle">
          {compactNumber(focus ? focus.count : total)}
        </text>
        <text className="ac-donut-caption" x="50" y="61" textAnchor="middle">
          {focus ? `${Math.round((focus.count / Math.max(1, total)) * 100)}% · ${shorten(focus.label)}` : unit}
        </text>
      </svg>
      <ul className="ac-donut-legend">
        {shares.map((item, index) => {
          const body = (
            <>
              <span className="ac-donut-key" style={{ background: CATEGORY_COLOURS[index] }} aria-hidden="true" />
              <span className="ac-donut-name">{item.label}</span>
              <strong>{item.count.toLocaleString()}</strong>
              <small>{total ? Math.round((item.count / total) * 100) : 0}%</small>
            </>
          );
          return (
            <li
              key={item.key}
              className={active === item.key ? "active" : ""}
              onMouseEnter={() => setActive(item.key)}
              onMouseLeave={() => setActive(null)}
            >
              {onSelect && item.key !== "__other" ? (
                <button
                  type="button"
                  onClick={() => onSelect(item.key)}
                  onFocus={() => setActive(item.key)}
                  onBlur={() => setActive(null)}
                >
                  {body}
                </button>
              ) : (
                <span>{body}</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

const shorten = (label: string) => (label.length > 14 ? `${label.slice(0, 13)}…` : label);

export type ExplorerSeries = {
  key: string;
  label: string;
  points: TrendPoint[];
  primaryLabel: string;
  secondaryLabel?: string;
  unit: string;
  /** Show the latest value as the headline instead of the period total (a running count). */
  summary?: "total" | "last";
  /** One line in plain words under the switch. */
  explain: string;
};

/** One large chart with a switch between measures: the person picks what to look at, one measure per axis. */
export function ActivityExplorer({ series }: { series: ExplorerSeries[] }) {
  const [chosen, setChosen] = useState(series[0]?.key);
  const current = series.find((item) => item.key === chosen) ?? series[0];
  if (!current) return null;
  return (
    <div className="ac-explorer">
      <div className="ac-explorer-switch" role="tablist" aria-label="Measure">
        {series.map((item) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={item.key === current.key}
            className={item.key === current.key ? "selected" : ""}
            onClick={() => setChosen(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <p className="ac-muted ac-explorer-explain">{current.explain}</p>
      <TrendChart
        key={current.key}
        data={current.points}
        primaryLabel={current.primaryLabel}
        secondaryLabel={current.secondaryLabel}
        unit={current.unit}
        summary={current.summary}
      />
    </div>
  );
}

/** A running count over the period: the count before it plus each day's additions. */
export const cumulative = (points: TrendPoint[], endTotal: number): TrendPoint[] => {
  const added = points.reduce((sum, point) => sum + point.primary, 0);
  let running = Math.max(0, endTotal - added);
  return points.map((point) => {
    running += point.primary;
    return { ...point, primary: running, secondary: undefined };
  });
};
