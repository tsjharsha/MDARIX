import { useId, useState, type CSSProperties, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { AnimatedNumber } from "../../admin/console/motion";
import { LOOP_SECONDS, loopDone, stationPoint, weakestLink, type LoopStation } from "../qualityLoop";
import "./qualityLoop.css";

const SIZE = 320;
const CENTER = SIZE / 2;
const RADIUS = 122;
// The comet's tail: dots a few degrees behind its head, fading out.
const TAIL = [0, 5, 10, 15, 20];

/**
 * The quality loop: a hero picture of the closed loop MDARIX keeps (complaint found, handled on time, reported,
 * investigated, trended, acted on, proven, risk file fed) with each station in its state. A pulse travels the loop;
 * stations that need attention pulse; the weakest link is named. The list beside it says the same in words and opens
 * each station's records. Under reduced motion the picture is still and complete.
 */
export function QualityLoop({
  stations,
  eyebrow,
  title,
  detail,
  doneLabel,
  onOpen,
  children,
  focusKey,
}: {
  stations: readonly LoopStation[];
  eyebrow: string;
  title: string;
  detail?: string;
  /** What a done station means here ("clear", "acted on"). */
  doneLabel: string;
  onOpen?: (station: LoopStation) => void;
  children?: ReactNode;
  /** The station to highlight first (else the weakest link). */
  focusKey?: string | null;
}) {
  const [active, setActive] = useState<string | null>(null);
  // Unique per loop, so two loops on one page keep their own glow.
  const glow = `ql-glow-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const done = loopDone(stations);
  const weakest = weakestLink(stations);
  const focus = active ?? focusKey ?? weakest?.key ?? null;
  const shown = stations.find((station) => station.key === focus) ?? null;
  const total = stations.length;
  const summary = total
    ? `${done} of ${total} ${doneLabel}.${weakest ? ` Weakest link: ${weakest.label}, ${weakest.stateLabel.toLowerCase()}.` : ""}`
    : "Reading your records";
  return (
    <section className="ql-hero" aria-label={eyebrow}>
      <div className="ql-copy">
        <p className="ql-eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
        {detail && <p className="ql-detail">{detail}</p>}
        {children && <div className="ql-actions">{children}</div>}
        {shown && (
          <p className="ql-focus" aria-live="polite">
            <span className={`ql-dot tone-${shown.tone}`} aria-hidden="true" />
            <strong>
              {shown.number}. {shown.label}
            </strong>{" "}
            {shown.caption}
          </p>
        )}
      </div>
      <div className="ql-visual">
        <svg
          className="ql-svg"
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          role="img"
          aria-label={`The quality loop. ${summary}`}
          style={{ "--ql-seconds": `${LOOP_SECONDS}s` } as CSSProperties}
        >
          <defs>
            <radialGradient id={glow} cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#5eead4" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#5eead4" stopOpacity="0" />
            </radialGradient>
          </defs>
          <circle className="ql-aura" cx={CENTER} cy={CENTER} r={RADIUS - 18} fill={`url(#${glow})`} />
          <circle className="ql-track" cx={CENTER} cy={CENTER} r={RADIUS} />
          <circle className="ql-flow" cx={CENTER} cy={CENTER} r={RADIUS} />
          <g className="ql-comet" aria-hidden="true">
            {TAIL.map((degrees, index) => {
              const angle = (-degrees * Math.PI) / 180 - Math.PI / 2;
              return (
                <circle
                  key={degrees}
                  cx={Math.round((CENTER + RADIUS * Math.cos(angle)) * 10) / 10}
                  cy={Math.round((CENTER + RADIUS * Math.sin(angle)) * 10) / 10}
                  r={6 - index}
                  opacity={1 - index * 0.18}
                />
              );
            })}
          </g>
          {stations.map((station, index) => {
            const point = stationPoint(index, total, RADIUS, CENTER, CENTER);
            const alarm = !station.done && (station.tone === "critical" || station.tone === "serious");
            return (
              <g
                key={station.key}
                className={`ql-station tone-${station.tone}${station.key === focus ? " is-focus" : ""}${alarm ? " is-alarm" : ""}`}
                transform={`translate(${point.x} ${point.y})`}
                style={{ "--ql-i": index } as CSSProperties}
                aria-hidden="true"
              >
                <circle className="ql-halo" r={22} />
                <circle className="ql-core" r={15} />
                <text className="ql-num" textAnchor="middle" dominantBaseline="central">
                  {station.number}
                </text>
              </g>
            );
          })}
          <g className="ql-center" aria-hidden="true">
            <text x={CENTER} y={CENTER - 6} textAnchor="middle" className="ql-center-value">
              {done}/{total}
            </text>
            <text x={CENTER} y={CENTER + 20} textAnchor="middle" className="ql-center-label">
              {doneLabel}
            </text>
          </g>
        </svg>
        <p className="ql-counter" aria-hidden="true">
          <AnimatedNumber value={total ? Math.round((done / total) * 100) : null} suffix="%" compact={false} /> of the
          loop {doneLabel}
        </p>
      </div>
      <ol className="ql-legend" aria-label="The stations of the loop">
        {stations.map((station) => (
          <li key={station.key}>
            <button
              type="button"
              className={`ql-step tone-${station.tone}${station.key === focus ? " is-focus" : ""}`}
              onMouseEnter={() => setActive(station.key)}
              onFocus={() => setActive(station.key)}
              onMouseLeave={() => setActive(null)}
              onClick={() => onOpen?.(station)}
              disabled={!onOpen || !station.opens}
            >
              <span className={`ql-dot tone-${station.tone}`} aria-hidden="true">
                {station.number}
              </span>
              <span className="ql-step-label">{station.label}</span>
              <span className="ql-step-value">
                {station.value === null || station.value === undefined ? "—" : station.value.toLocaleString()}
              </span>
              <span className="ql-step-state">{station.stateLabel}</span>
              {onOpen && station.opens && <ChevronRight size={14} aria-hidden="true" />}
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
