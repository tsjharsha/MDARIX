import { useId, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { useCountUp } from "../../admin/console/motion";
import { RECENT_MONTHS, monthLabel, rateText, trendSummary, type Trend } from "../trialInsights";
import { heroGeometry, heroHeadline, versusText, type HeroGeometry } from "../trendHero";
import { countOf } from "./common";

// The chart's width before the card is measured (and in server-rendered markup).
const DEFAULT_WIDTH = 760;
// The line draws itself over DRAW_MS after LEAD_MS; each point pops as the line reaches it, the callout after the line.
const LEAD_MS = 150;
const DRAW_MS = 1400;

/** The card body's width in px, measured before paint so the chart never jumps once shown. */
function useWidth(fallback: number) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    const measure = () => setWidth(Math.round(node.clientWidth) || fallback);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [fallback]);
  return [ref, width] as const;
}

// When the ease-out line (roughly cubic) reaches a share of its length.
const reachedAt = (share: number) => LEAD_MS + DRAW_MS * (1 - Math.cbrt(1 - share));

function Figure({ value, decimals, still }: { value: number; decimals: 0 | 1; still: boolean }) {
  const counted = useCountUp(still ? null : value, 1100);
  const shown = still || counted === null ? value : counted;
  const text = (number: number) => (decimals ? rateText(number) : Math.round(number).toLocaleString());
  // The end value, hidden, holds the width: the words beside the number never move while it counts.
  return (
    <span className="uw-ins-hero-count">
      <span aria-hidden="true">{text(value)}</span>
      <span>{text(shown)}</span>
    </span>
  );
}

/**
 * Complaints per month as the panel's hero: the recent rate counting up beside a smooth area chart whose line draws
 * itself, the last three months as a band against the earlier average, and the peak called out. Every month has a
 * column that shows its numbers on hover, tap or keyboard focus (arrow keys move between months); the table view
 * holds the same numbers. `replayKey` (the filter) redraws the chart when the panel is filtered.
 */
export function TrendHero({ trend, still, replayKey }: { trend: Trend; still: boolean; replayKey: string }) {
  const [asTable, setAsTable] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const [ref, width] = useWidth(DEFAULT_WIDTH);
  const heading = useId();
  const geometry = useMemo(() => heroGeometry(trend, width), [trend, width]);
  const headline = heroHeadline(trend);
  const summary = trendSummary(trend);
  const Arrow =
    headline.direction === "up" || headline.direction === "new"
      ? ArrowUpRight
      : headline.direction === "down"
        ? ArrowDownRight
        : ArrowRight;
  return (
    <section className={`uw-ins-hero${still ? " is-still" : ""}`} aria-labelledby={heading}>
      <div className="uw-ins-hero-head">
        <div className="uw-ins-hero-copy">
          <h3 className="uw-ins-hero-eyebrow" id={heading}>
            Complaints per month
          </h3>
          <p className="uw-ins-hero-figure">
            <strong>
              <Figure value={headline.value} decimals={headline.decimals} still={still} />
            </strong>{" "}
            <span>{headline.unit}</span>
          </p>
          <p className="uw-ins-hero-delta">
            {headline.direction && (
              <span className="uw-ins-hero-arrow" aria-hidden="true">
                <Arrow size={15} />
              </span>
            )}
            {headline.detail}
          </p>
        </div>
        <button
          type="button"
          className="uw-ins-hero-toggle"
          onClick={() => setAsTable((value) => !value)}
          aria-pressed={asTable}
        >
          {asTable ? "Show chart" : "Show table"}
        </button>
      </div>
      <div className="uw-ins-hero-body" ref={ref}>
        {asTable ? (
          <div className="uw-ins-hero-table">
            <table>
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
                  <tr key={item.month} className={item.recent ? "is-recent" : undefined}>
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
        ) : trend.months.length ? (
          <HeroChart
            key={replayKey}
            trend={trend}
            geometry={geometry}
            summary={summary}
            active={active}
            onActive={setActive}
          />
        ) : (
          <p className="uw-ins-hero-empty">No complaint in view records a month.</p>
        )}
      </div>
    </section>
  );
}

function HeroChart({
  trend,
  geometry: g,
  summary,
  active,
  onActive,
}: {
  trend: Trend;
  geometry: HeroGeometry;
  summary: string;
  active: number | null;
  onActive: (index: number | null) => void;
}) {
  // Unique per chart, so two cards on one page keep their own gradients.
  const id = `ih-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const hits = useRef<(HTMLButtonElement | null)[]>([]);
  // The month that takes Tab (roving focus): the latest, until another is focused.
  const [current, setCurrent] = useState(g.points.length - 1);
  const n = g.points.length;
  const split = g.band ? g.band.x : g.plot.right;
  const blend = g.step * 0.15;
  const focusMonth = (index: number) => {
    const next = Math.max(0, Math.min(n - 1, index));
    setCurrent(next);
    hits.current[next]?.focus();
  };
  const onKey = (event: KeyboardEvent, index: number) => {
    const moves: Record<string, number> = { ArrowLeft: index - 1, ArrowRight: index + 1, Home: 0, End: n - 1 };
    if (event.key in moves) {
      event.preventDefault();
      focusMonth(moves[event.key]);
    } else if (event.key === "Escape") onActive(null);
  };
  const shown = active === null ? null : g.points[active];
  const peakParts = g.peak ? g.peak.text.split(" · ") : [];
  return (
    <div className="uw-ins-hero-plot" style={{ height: g.height }}>
      <svg
        className="uw-ins-hero-svg"
        width={g.width}
        height={g.height}
        viewBox={`0 0 ${g.width} ${g.height}`}
        role="img"
        aria-label={summary}
      >
        <defs>
          <linearGradient id={`${id}-fill`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" className="uw-ins-hero-stop-recent" stopOpacity="0.34" />
            <stop offset="100%" className="uw-ins-hero-stop-recent" stopOpacity="0" />
          </linearGradient>
          <linearGradient id={`${id}-fill-before`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" className="uw-ins-hero-stop-before" stopOpacity="0.3" />
            <stop offset="100%" className="uw-ins-hero-stop-before" stopOpacity="0" />
          </linearGradient>
          <linearGradient id={`${id}-stroke`} gradientUnits="userSpaceOnUse" x1="0" x2={g.width} y1="0" y2="0">
            <stop
              offset={(split - blend) / g.width}
              className={g.band ? "uw-ins-hero-stop-before" : "uw-ins-hero-stop-recent"}
            />
            <stop offset={(split + blend) / g.width} className="uw-ins-hero-stop-recent" />
          </linearGradient>
          <linearGradient id={`${id}-band`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" className="uw-ins-hero-stop-recent" stopOpacity="0.16" />
            <stop offset="100%" className="uw-ins-hero-stop-recent" stopOpacity="0.03" />
          </linearGradient>
          <clipPath id={`${id}-before`}>
            <rect x="0" y="0" width={split} height={g.height} />
          </clipPath>
          <clipPath id={`${id}-recent`}>
            <rect x={split} y="0" width={Math.max(0, g.width - split)} height={g.height} />
          </clipPath>
        </defs>

        {g.yTicks.map((tick, index) => (
          <g key={tick.label} className={index ? "uw-ins-hero-grid" : "uw-ins-hero-axis"}>
            <line x1={g.plot.left} x2={g.plot.right} y1={tick.y} y2={tick.y} />
            <text x={g.plot.left - 10} y={tick.y + 4} textAnchor="end">
              {tick.label}
            </text>
          </g>
        ))}

        {g.band && (
          <g className="uw-ins-hero-band">
            <rect
              x={g.band.x}
              y="2"
              width={g.band.width}
              height={g.plot.bottom - 2}
              rx="12"
              fill={`url(#${id}-band)`}
            />
            <line x1={g.band.x + 12} x2={g.band.x + g.band.width - 12} y1="2.5" y2="2.5" />
            <text x={g.band.labelX} y={g.band.labelY}>
              {g.band.label}
            </text>
          </g>
        )}

        <g className="uw-ins-hero-area">
          <path d={g.area} fill={`url(#${id}-fill-before)`} clipPath={`url(#${id}-before)`} />
          <path d={g.area} fill={`url(#${id}-fill)`} clipPath={`url(#${id}-recent)`} />
        </g>

        {g.average && (
          <g className="uw-ins-hero-average">
            {g.average.y !== null && <line x1={g.plot.left} x2={g.plot.right} y1={g.average.y} y2={g.average.y} />}
            <text x={g.average.labelX} y={g.average.labelY} textAnchor={g.average.anchor}>
              {g.average.label}
            </text>
          </g>
        )}

        {n > 1 && <path className="uw-ins-hero-line" d={g.line} pathLength={1} stroke={`url(#${id}-stroke)`} />}

        {shown && (
          <line className="uw-ins-hero-cross" x1={shown.x} x2={shown.x} y1={g.plot.top - 6} y2={g.plot.bottom} />
        )}

        {g.points.map((point, index) => (
          <circle
            key={point.month}
            className={`uw-ins-hero-dot${point.recent || !g.band ? " is-recent" : ""}${index === active ? " is-active" : ""}`}
            cx={point.x}
            cy={point.y}
            r={index === active ? 6 : 4.5}
            style={{ animationDelay: `${Math.round(reachedAt(n > 1 ? index / (n - 1) : 1) + 60)}ms` } as CSSProperties}
          />
        ))}

        {g.peak && (
          <g className="uw-ins-hero-peak" style={{ animationDelay: `${LEAD_MS + DRAW_MS + 120}ms` }}>
            <line x1={g.peak.leader.x} x2={g.peak.leader.x} y1={g.peak.leader.y1} y2={g.peak.leader.y2} />
            <rect
              x={g.peak.box.x}
              y={g.peak.box.y}
              width={g.peak.box.width}
              height={g.peak.box.height}
              rx={g.peak.box.height / 2}
            />
            <text x={g.peak.box.x + g.peak.box.width / 2} y={g.peak.box.y + 17} textAnchor="middle">
              <tspan className="uw-ins-hero-peak-value">{peakParts[0]}</tspan>
              {peakParts.slice(1).map((part) => (
                <tspan key={part}>{` · ${part}`}</tspan>
              ))}
            </text>
          </g>
        )}

        {g.xTicks.map((tick) => (
          <text key={tick.label} className="uw-ins-hero-tick" x={tick.x} y={g.height - 8} textAnchor="middle">
            {tick.label}
          </text>
        ))}
      </svg>

      <div className="uw-ins-hero-hits" onPointerLeave={() => onActive(null)}>
        {g.points.map((point, index) => {
          const versus = versusText(point.complaints, trend);
          return (
            <button
              key={point.month}
              type="button"
              ref={(node) => {
                hits.current[index] = node;
              }}
              tabIndex={index === current ? 0 : -1}
              style={{
                left: g.plot.left + g.step * index,
                top: g.plot.top - 10,
                width: g.step,
                height: g.plot.bottom - g.plot.top + 10,
              }}
              aria-label={`${monthLabel(point.month)}: ${countOf(point.complaints, "complaint")}${
                point.recent ? `, one of the last ${RECENT_MONTHS} months` : ""
              }${versus ? `. ${versus}.` : "."}`}
              onPointerEnter={() => onActive(index)}
              onFocus={() => {
                setCurrent(index);
                onActive(index);
              }}
              onBlur={() => onActive(null)}
              onClick={() => onActive(index)}
              onKeyDown={(event) => onKey(event, index)}
            />
          );
        })}
      </div>

      {shown && (
        <div
          className={`uw-ins-hero-tip${shown.x > g.width / 2 ? " is-left" : ""}`}
          style={{ left: shown.x, top: g.plot.top - 6 }}
          aria-hidden="true"
        >
          <strong>{countOf(shown.complaints, "complaint")}</strong>
          <span>
            {monthLabel(shown.month)}
            {shown.recent ? ` · last ${RECENT_MONTHS} months` : ""}
          </span>
          {versusText(shown.complaints, trend) && <span>{versusText(shown.complaints, trend)}</span>}
        </div>
      )}
    </div>
  );
}
