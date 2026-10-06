import { useState, type ReactNode } from "react";
import { AlertOctagon, AlertTriangle, CheckCircle2, CircleDashed, Lock, XCircle } from "lucide-react";
import { compactNumber, type DayCount, type Slice, type Tone } from "./dashboardModel";

const TONE_LABEL: Record<Tone, string> = {
  good: "Healthy",
  warning: "Warning",
  serious: "Serious",
  critical: "Critical",
  neutral: "Info",
};

/** Status is never colour alone: every tone renders an icon plus a text label. */
export function ToneIcon({ tone, size = 16 }: { tone: Tone; size?: number }) {
  const Icon =
    tone === "good"
      ? CheckCircle2
      : tone === "warning"
        ? AlertTriangle
        : tone === "serious"
          ? AlertOctagon
          : tone === "critical"
            ? XCircle
            : CircleDashed;
  return <Icon className={`ac-tone-icon tone-${tone}`} size={size} aria-hidden="true" />;
}

export function ToneBadge({ tone, label }: { tone: Tone; label?: string }) {
  return (
    <span className={`ac-badge tone-${tone}`}>
      <ToneIcon tone={tone} size={14} />
      {label ?? TONE_LABEL[tone]}
    </span>
  );
}

export type PanelState = "loading" | "ready" | "error" | "forbidden";

/** What a data source reports to the panel that shows it (useResource in customer-admin/shared.tsx fits). */
export type PanelSource = {
  state: PanelState;
  error?: string;
  /** The server's error code (TRIAL_ENDED reads differently from a role that may not see the data). */
  code?: string;
  /** The id the server logged the failure under, for a problem report. */
  requestId?: string;
  reload?: () => void;
};

export function Panel({
  title,
  eyebrow,
  state = "ready",
  error,
  code,
  requestId,
  onRetry,
  source,
  action,
  children,
  className = "",
}: {
  title: string;
  eyebrow?: string;
  state?: PanelState;
  error?: string;
  code?: string;
  requestId?: string;
  onRetry?: () => void;
  /** The resource behind the panel: its state, message, request id and reload in one prop. */
  source?: PanelSource;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const shown = source ?? { state, error, code, requestId, reload: onRetry };
  return (
    <section className={`ac-panel ${className}`} aria-busy={shown.state === "loading"}>
      <header className="ac-panel-head">
        <div>
          {eyebrow && <p className="ac-eyebrow">{eyebrow}</p>}
          <h2>{title}</h2>
        </div>
        {action}
      </header>
      {shown.state === "loading" && <div className="ac-skeleton" aria-label={`Loading ${title}`} />}
      {shown.state === "forbidden" &&
        (shown.code === "TRIAL_ENDED" ? (
          <div className="ac-empty">
            <Lock size={20} aria-hidden="true" />
            <strong>Your free trial has ended</strong>
            <span>{shown.error || "Contact us to continue with your data intact."}</span>
          </div>
        ) : (
          <div className="ac-empty">
            <Lock size={20} aria-hidden="true" />
            <strong>Not authorized</strong>
            <span>Your role cannot read this data.</span>
          </div>
        ))}
      {shown.state === "error" && (
        <Unavailable message={shown.error} requestId={shown.requestId} onRetry={shown.reload} />
      )}
      {shown.state === "ready" && children}
    </section>
  );
}

/** A failed load the person can act on: what went wrong, a retry, and the reference to quote to support. */
export function Unavailable({
  message,
  requestId,
  onRetry,
}: {
  message?: string;
  requestId?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="ac-empty tone-critical-text">
      <XCircle size={20} aria-hidden="true" />
      <strong>Unavailable</strong>
      <span>{message ?? "This source did not respond."}</span>
      {requestId && (
        <small className="ac-request-id">
          Reference for support: <code>{requestId}</code>
        </small>
      )}
      {onRetry && (
        <button type="button" className="ac-secondary" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function Empty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="ac-empty">
      <CircleDashed size={20} aria-hidden="true" />
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  );
}

export function StatTile({
  label,
  value,
  detail,
  icon,
  tone,
  onOpen,
}: {
  label: string;
  value: number | string | null;
  detail: string;
  icon: ReactNode;
  tone?: Tone;
  onOpen?: () => void;
}) {
  const body = (
    <>
      <span className="ac-stat-icon" aria-hidden="true">
        {icon}
      </span>
      <span className="ac-stat-label">{label}</span>
      <strong className="ac-stat-value">
        {value === null ? "—" : typeof value === "number" ? compactNumber(value) : value}
      </strong>
      <span className="ac-stat-detail">
        {tone && <ToneIcon tone={tone} size={14} />}
        {detail}
      </span>
    </>
  );
  return onOpen ? (
    <button type="button" className="ac-stat" onClick={onOpen}>
      {body}
    </button>
  ) : (
    <div className="ac-stat">{body}</div>
  );
}

/** Share-of-total ring (a meter, not a pie): one value against its whole. */
export function RingMeter({ value, total, label }: { value: number; total: number; label: string }) {
  const share = total ? value / total : 0;
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  return (
    <figure className="ac-ring" aria-label={`${label}: ${value} of ${total}`}>
      <svg viewBox="0 0 100 100" role="img" aria-hidden="true">
        <circle className="ac-ring-track" cx="50" cy="50" r={radius} />
        <circle
          className="ac-ring-fill"
          cx="50"
          cy="50"
          r={radius}
          strokeDasharray={`${circumference * share} ${circumference}`}
          transform="rotate(-90 50 50)"
        />
      </svg>
      <figcaption>
        <strong>{total ? `${Math.round(share * 100)}%` : "—"}</strong>
        <span>{label}</span>
      </figcaption>
    </figure>
  );
}

/** Horizontal bars, one row per category. Values are labelled directly, so every value is readable without hover. */
export function BarList({ items, colour = "tone" }: { items: Slice[]; colour?: "tone" | "series" }) {
  const max = Math.max(1, ...items.map((item) => item.count));
  const total = items.reduce((sum, item) => sum + item.count, 0);
  return (
    <ul className="ac-barlist">
      {items.map((item) => (
        <li key={item.key} title={`${item.label}: ${item.count} of ${total}`}>
          <span className="ac-barlist-label">
            {colour === "tone" && <ToneIcon tone={item.tone} size={15} />}
            {item.label}
          </span>
          <span className="ac-barlist-track" aria-hidden="true">
            <span
              className={`ac-barlist-fill ${colour === "tone" ? `fill-${item.tone}` : "fill-series"}`}
              style={{ width: `${item.count ? Math.max(2, (item.count / max) * 100) : 0}%` }}
            />
          </span>
          <strong className="ac-barlist-value">{item.count}</strong>
        </li>
      ))}
    </ul>
  );
}

function niceMax(value: number) {
  if (value <= 4) return value <= 2 ? 2 : 4;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((candidate) => candidate * magnitude >= value) ?? 10;
  return step * magnitude;
}

/** Single-series daily column chart with a per-column hover/focus readout and a table view. */
export function ColumnChart({ data, unit, caption }: { data: DayCount[]; unit: string; caption: string }) {
  const [active, setActive] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);
  const peak = Math.max(0, ...data.map((day) => day.count));
  const top = niceMax(peak);
  const peakIndex = peak ? data.findIndex((day) => day.count === peak) : -1;
  const total = data.reduce((sum, day) => sum + day.count, 0);
  const tickIndexes = new Set([0, Math.floor((data.length - 1) / 2), data.length - 1]);
  return (
    <div className="ac-columns">
      <div className="ac-columns-bar">
        <span>
          <strong>{total.toLocaleString()}</strong> {unit} · {caption}
        </span>
        <button type="button" className="ac-link" onClick={() => setAsTable((value) => !value)} aria-pressed={asTable}>
          {asTable ? "Show chart" : "Show table"}
        </button>
      </div>
      {asTable ? (
        <div className="ac-table-wrap">
          <table className="ac-table">
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col" className="num">
                  {unit}
                </th>
              </tr>
            </thead>
            <tbody>
              {data.map((day) => (
                <tr key={day.date}>
                  <td>{day.label}</td>
                  <td className="num">{day.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="ac-columns-chart" onMouseLeave={() => setActive(null)}>
          <div className="ac-columns-axis" aria-hidden="true">
            <span>{top.toLocaleString()}</span>
            <span>{(top / 2).toLocaleString()}</span>
            <span>0</span>
          </div>
          <div className="ac-columns-plot" role="list" aria-label={`${unit} per day`}>
            <span className="ac-gridline" style={{ bottom: "calc(var(--ac-tick-band) + var(--ac-plot-height))" }} />
            <span className="ac-gridline" style={{ bottom: "calc(var(--ac-tick-band) + var(--ac-plot-height) / 2)" }} />
            {data.map((day, index) => (
              <div
                className={`ac-column ${active === index ? "active" : ""}`}
                key={day.date}
                role="listitem"
                tabIndex={0}
                aria-label={`${day.label}: ${day.count} ${unit}`}
                onMouseEnter={() => setActive(index)}
                onFocus={() => setActive(index)}
                onBlur={() => setActive(null)}
              >
                <span className="ac-column-slot">
                  {index === peakIndex && active === null && (
                    <span className="ac-column-cap" style={{ bottom: `${(day.count / top) * 100}%` }}>
                      {day.count}
                    </span>
                  )}
                  <span className="ac-column-fill" style={{ height: `${(day.count / top) * 100}%` }} />
                  {active === index && (
                    <span
                      className={`ac-tooltip ${index >= data.length - 2 ? "edge-end" : index <= 1 ? "edge-start" : ""}`}
                      role="tooltip"
                    >
                      <strong>{day.count.toLocaleString()}</strong>
                      <span>{day.label}</span>
                    </span>
                  )}
                </span>
                <span className="ac-column-tick">{tickIndexes.has(index) ? day.label : ""}</span>
              </div>
            ))}
            <span className="ac-baseline" />
          </div>
        </div>
      )}
    </div>
  );
}
