import { useId, type ReactNode } from "react";
import { AlertTriangle, CircleCheck, Clock, Triangle } from "lucide-react";
import "./hero.css";

/*
 * The hero design's shared visuals (0.10.89, the owner-approved mock-up mdarix-hero-ui.html): clock rings, status and
 * harm pills, flags, device icons, stage dots, the ten-step progress arc and the dark monitor band. Each has an
 * accessible name; a visual whose words already stand beside it is marked decorative instead, so nothing is read twice.
 * Status is never colour alone: every ring and pill comes with a number, an icon and a word.
 */

export type Tone = "crit" | "warn" | "good" | "none" | "accent" | "harm";

/** A deadline's state by the time left: overdue, due within a week, or on track (the mock-up's three clock colours). */
export const clockStatus = (left: number): "crit" | "warn" | "good" =>
  left < 0 ? "crit" : left <= 7 ? "warn" : "good";

const fixed = (value: number) => value.toFixed(2);

/**
 * A legal clock as a ring: the share of the time still left, coloured by its state. The number in the middle and the
 * words beside it say the same, so the ring alone never carries the meaning.
 */
export function ClockRing({
  left,
  total,
  size = 40,
  stroke = 4,
  ticks = false,
  status,
  label,
  decorative = false,
  children,
}: {
  /** Time left (negative once overdue), in the unit of `total`. */
  left: number;
  total: number;
  size?: number;
  stroke?: number;
  /** One tick per unit around the ring, the big clock's. */
  ticks?: boolean;
  status?: "crit" | "warn" | "good";
  /** Its accessible name, e.g. "29 days left". */
  label: string;
  /** The words stand beside it: hidden from screen readers. */
  decorative?: boolean;
  /** Shown in the middle (the number). */
  children?: ReactNode;
}) {
  const state = status ?? clockStatus(left);
  const m = size / 2;
  const r = (size - stroke) / 2 - (ticks ? 12 : 1);
  const c = 2 * Math.PI * r;
  const share = total > 0 ? Math.max(0, Math.min(1, left / total)) : 0;
  const marks = ticks
    ? Array.from({ length: total }, (_, k) => {
        const a = (k / total) * 2 * Math.PI - Math.PI / 2;
        const [r1, r2] = [m - 3, m - 9];
        return (
          <line
            key={k}
            className={k >= total - left ? "hx-tick is-on" : "hx-tick"}
            x1={fixed(m + r1 * Math.cos(a))}
            y1={fixed(m + r1 * Math.sin(a))}
            x2={fixed(m + r2 * Math.cos(a))}
            y2={fixed(m + r2 * Math.sin(a))}
          />
        );
      })
    : null;
  return (
    <span
      className={`hx-clock hx-clock-${state}`}
      style={{ width: size, height: size }}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : label}
      aria-hidden={decorative || undefined}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        {marks}
        <circle className="hx-clock-track" cx={m} cy={m} r={r} fill="none" strokeWidth={stroke} />
        <circle
          className="hx-clock-val"
          cx={m}
          cy={m}
          r={r}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={fixed(c)}
          strokeDashoffset={fixed(c * (1 - share))}
          style={{ ["--hx-c" as string]: fixed(c) }}
          transform={`rotate(-90 ${m} ${m})`}
        />
      </svg>
      {children !== undefined && <span className="hx-clock-c">{children}</span>}
    </span>
  );
}

/**
 * The ten steps as a ring of ten segments: done, the current one, still to do; a tick in the middle once all are done.
 */
export function ProgressArc({
  done,
  total = 10,
  size = 44,
  tone = "dark",
  label,
  decorative = false,
}: {
  done: number;
  total?: number;
  size?: number;
  /** "dark" on the rail and the monitor band, "light" on a white surface. */
  tone?: "dark" | "light";
  label?: string;
  decorative?: boolean;
}) {
  const sw = size > 60 ? 7 : size > 30 ? 5 : 3;
  const m = size / 2;
  const r = m - sw / 2 - 1;
  const gap = size > 40 ? 0.012 : 0.02;
  const point = (a: number) => `${fixed(m + r * Math.cos(a))} ${fixed(m + r * Math.sin(a))}`;
  const finished = done >= total;
  const k = size * 0.32;
  return (
    <svg
      className={`hx-arc hx-arc-${tone}`}
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : (label ?? `${Math.min(done, total)} of ${total} steps completed`)}
      aria-hidden={decorative || undefined}
    >
      {Array.from({ length: total }, (_, index) => {
        const a0 = (index / total) * 2 * Math.PI - Math.PI / 2 + gap;
        const a1 = ((index + 1) / total) * 2 * Math.PI - Math.PI / 2 - gap;
        const state = index < done ? "is-done" : index === done ? "is-cur" : "is-todo";
        return (
          <path
            key={index}
            className={`hx-seg ${state}`}
            d={`M${point(a0)} A${fixed(r)} ${fixed(r)} 0 0 1 ${point(a1)}`}
            fill="none"
            strokeWidth={sw}
            strokeLinecap="round"
          />
        );
      })}
      {finished && size > 30 && (
        <path
          className="hx-seg is-done"
          d={`M${fixed(m - k * 0.55)} ${fixed(m + k * 0.02)} l${fixed(k * 0.38)} ${fixed(k * 0.38)} l${fixed(k * 0.72)} ${fixed(-k * 0.78)}`}
          fill="none"
          strokeWidth={Math.max(2.5, size / 16)}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}
    </svg>
  );
}

const TONE_ICON = { crit: AlertTriangle, warn: Clock, good: CircleCheck } as const;

/** A status in a pill: always an icon and a word, never the colour alone. */
export function StatusPill({
  tone,
  icon,
  children,
  className,
}: {
  tone: Tone;
  /** An icon of its own; the crit, warn and good pills have one by default. */
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const Default = tone in TONE_ICON ? TONE_ICON[tone as keyof typeof TONE_ICON] : null;
  return (
    <span className={`hx-pill hx-pill-${tone}${className ? ` ${className}` : ""}`}>
      {icon ?? (Default && <Default size={14} aria-hidden="true" />)}
      <span>{children}</span>
    </span>
  );
}

export type Harm = "DEATH" | "SERIOUS_INJURY" | "MALFUNCTION" | "NONE";
const HARM: Record<Harm, { label: string; bars: number }> = {
  DEATH: { label: "Death", bars: 3 },
  SERIOUS_INJURY: { label: "Serious injury", bars: 2 },
  MALFUNCTION: { label: "Malfunction", bars: 1 },
  NONE: { label: "No harm reported", bars: 0 },
};

/** Harm in its own hue, with its severity as bars, an icon and the word (the page's own word when it gives one). */
export function HarmBadge({ harm, label }: { harm: Harm; label?: string }) {
  const { label: word, bars } = HARM[harm];
  return (
    <span className={`hx-pill ${bars ? "hx-pill-harm" : "hx-pill-good"} hx-harm`}>
      {bars > 0 && (
        <span className="hx-sev" aria-hidden="true">
          {[1, 2, 3].map((n) => (
            <i key={n} className={n <= bars ? "is-on" : undefined} />
          ))}
        </span>
      )}
      {bars ? (
        <Triangle size={12} fill="currentColor" aria-hidden="true" />
      ) : (
        <CircleCheck size={14} aria-hidden="true" />
      )}
      <span>{label ?? word}</span>
    </span>
  );
}

/** A country's two-letter code from the names and codes the records use ("US", "USA", "United States", "Germany"). */
export function flagCode(country: string | null | undefined): string | null {
  const key = (country ?? "").trim().toLowerCase();
  if (!key) return null;
  const NAMES: Record<string, string> = {
    us: "US",
    usa: "US",
    "united states": "US",
    "united states of america": "US",
    gb: "GB",
    uk: "GB",
    "united kingdom": "GB",
    "great britain": "GB",
    "northern ireland": "GB",
    ca: "CA",
    canada: "CA",
    in: "IN",
    india: "IN",
    de: "DE",
    germany: "DE",
    fr: "FR",
    france: "FR",
    eu: "EU",
    "european union": "EU",
  };
  return NAMES[key] ?? (/^[a-z]{2}$/.test(key) ? key.toUpperCase() : null);
}

const COUNTRY_NAME: Record<string, string> = {
  US: "United States",
  GB: "United Kingdom",
  CA: "Canada",
  IN: "India",
  DE: "Germany",
  FR: "France",
  EU: "European Union",
};

// The US canton's twelve stars at 20 px, as the mock-up draws them.
const US_STARS = [
  [1.6, 1.4],
  [3.9, 1.4],
  [6.2, 1.4],
  [2.75, 3.1],
  [5.05, 3.1],
  [7.35, 3.1],
  [1.6, 4.8],
  [3.9, 4.8],
  [6.2, 4.8],
  [2.75, 6.4],
  [5.05, 6.4],
  [7.35, 6.4],
];

/** The flag's drawing (20 x 14); a country without one gets its code on a neutral tile. */
function flagArt(code: string): ReactNode {
  switch (code) {
    case "US":
      return (
        <>
          <rect width="20" height="14" fill="#fff" />
          {[0, 2, 4, 6, 8, 10, 12].map((n) => (
            <rect key={n} y={n * 1.077} width="20" height="1.077" fill="#b22234" />
          ))}
          <rect width="9" height="7.54" fill="#3c3b6e" />
          {US_STARS.map(([x, y]) => (
            <circle key={`${x}-${y}`} cx={x} cy={y} r=".45" fill="#fff" />
          ))}
        </>
      );
    case "GB":
      return (
        <>
          <rect width="20" height="14" fill="#012169" />
          <path d="M0 0l20 14M20 0L0 14" stroke="#fff" strokeWidth="2.8" />
          <path d="M0 0l20 14M20 0L0 14" stroke="#c8102e" strokeWidth="1.1" />
          <path d="M10 0v14M0 7h20" stroke="#fff" strokeWidth="4" />
          <path d="M10 0v14M0 7h20" stroke="#c8102e" strokeWidth="2.2" />
        </>
      );
    case "CA":
      return (
        <>
          <rect width="20" height="14" fill="#fff" />
          <rect width="5" height="14" fill="#d52b1e" />
          <rect x="15" width="5" height="14" fill="#d52b1e" />
          <path
            d="M10 3l.8 1.6 1-.4-.3 2.2 1.3-1 .4.9 1.2-.2-.5 1.5.6.3-2.4 1.8.3.9-2.2-.3V12h-.4v-1.7l-2.2.3.3-.9-2.4-1.8.6-.3-.5-1.5 1.2.2.4-.9 1.3 1-.3-2.2 1 .4z"
            fill="#d52b1e"
          />
        </>
      );
    case "IN":
      return (
        <>
          <rect width="20" height="4.67" fill="#ff9933" />
          <rect y="4.67" width="20" height="4.67" fill="#fff" />
          <rect y="9.33" width="20" height="4.67" fill="#138808" />
          <circle cx="10" cy="7" r="1.7" fill="none" stroke="#000080" strokeWidth=".55" />
          <circle cx="10" cy="7" r=".35" fill="#000080" />
        </>
      );
    case "DE":
      return (
        <>
          <rect width="20" height="4.67" fill="#000" />
          <rect y="4.67" width="20" height="4.67" fill="#dd0000" />
          <rect y="9.33" width="20" height="4.67" fill="#ffce00" />
        </>
      );
    case "FR":
      return (
        <>
          <rect width="6.67" height="14" fill="#002395" />
          <rect x="6.67" width="6.67" height="14" fill="#fff" />
          <rect x="13.33" width="6.67" height="14" fill="#ed2939" />
        </>
      );
    case "EU":
      return (
        <>
          <rect width="20" height="14" fill="#003399" />
          {Array.from({ length: 12 }, (_, k) => {
            const a = (k / 12) * 2 * Math.PI;
            return (
              <circle key={k} cx={fixed(10 + 4 * Math.cos(a))} cy={fixed(7 + 4 * Math.sin(a))} r=".55" fill="#ffcc00" />
            );
          })}
        </>
      );
    default:
      return (
        <>
          <rect width="20" height="14" fill="#e6ebf2" />
          <text x="10" y="10" textAnchor="middle" fontSize="7" fontWeight="700" fill="#39475c">
            {code}
          </text>
        </>
      );
  }
}

/** A country's flag, named for screen readers (decorative where the country's name is written beside it). */
export function Flag({
  country,
  decorative = false,
  size = 20,
}: {
  country: string | null | undefined;
  decorative?: boolean;
  size?: number;
}) {
  const code = flagCode(country);
  if (!code) return null;
  return (
    <svg
      className="hx-flag"
      width={size}
      height={(size * 14) / 20}
      viewBox="0 0 20 14"
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : (COUNTRY_NAME[code] ?? country ?? code)}
      aria-hidden={decorative || undefined}
    >
      {flagArt(code)}
    </svg>
  );
}

export type DeviceKind = "monitor" | "pump" | "vent" | "generic";

/** The kind of device a product name describes: a patient monitor, an infusion pump, a respiratory controller, or any
 * other (an imported product). */
export function deviceKind(name: string | null | undefined): DeviceKind {
  const text = (name ?? "").toLowerCase();
  if (/monitor|oximet|spo2/.test(text)) return "monitor";
  if (/pump|infusion/.test(text)) return "pump";
  if (/respirat|ventilat|breath/.test(text)) return "vent";
  return "generic";
}

const DEVICE_NAME: Record<DeviceKind, string> = {
  monitor: "Patient monitor",
  pump: "Infusion pump",
  vent: "Respiratory controller",
  generic: "Medical device",
};

/** A device drawn on the 48 grid (the mock-up's monitor, pump and respiratory controller; a generic box otherwise). */
export function DeviceIcon({
  kind,
  size = 28,
  label,
  decorative = false,
}: {
  kind: DeviceKind;
  size?: number;
  label?: string;
  decorative?: boolean;
}) {
  const s = { stroke: "currentColor", fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg
      className="hx-device"
      width={size}
      height={size}
      viewBox="0 0 48 48"
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : (label ?? DEVICE_NAME[kind])}
      aria-hidden={decorative || undefined}
    >
      {kind === "monitor" && (
        <>
          <rect x="5" y="7" width="38" height="27" rx="5" {...s} strokeWidth="2.2" />
          <rect x="9" y="11" width="30" height="19" rx="2.5" fill="currentColor" opacity=".14" />
          <path d="M11 21h5l2-5 3 10 3-8 2 3h12" {...s} strokeWidth="2" />
          <path d="M24 34v6M16 41h16" {...s} strokeWidth="2.2" />
        </>
      )}
      {kind === "pump" && (
        <>
          <path
            d="M7 3h7v9c0 2-1.5 3.5-3.5 3.5S7 14 7 12z"
            fill="currentColor"
            fillOpacity=".14"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinejoin="round"
          />
          <path d="M10.5 15.5v4M10.5 22v4" {...s} strokeWidth="1.8" />
          <path d="M10.5 26c0 3 2 4 6 4" {...s} strokeWidth="1.8" />
          <rect x="16" y="14" width="27" height="26" rx="4" {...s} strokeWidth="2.2" />
          <rect x="20" y="18" width="19" height="8" rx="1.5" fill="currentColor" fillOpacity=".18" />
          <path d="M22.5 22h3l1.2-2 1.8 4 1.2-2h6" {...s} strokeWidth="1.5" />
          <path d="M21 31h4M21 35h4M29 31h4M29 35h4" {...s} strokeWidth="2" />
          <rect x="36" y="30" width="4" height="7" rx="1" fill="currentColor" />
          <path d="M22 40v4M37 40v4" {...s} strokeWidth="2.2" />
        </>
      )}
      {kind === "vent" && (
        <>
          <rect x="4" y="11" width="32" height="26" rx="5" {...s} strokeWidth="2.2" />
          <circle cx="15" cy="24" r="6" {...s} strokeWidth="2" />
          <path d="M15 24l3-3" {...s} strokeWidth="2" />
          <rect x="24" y="17" width="8" height="6" rx="1.5" fill="currentColor" opacity=".3" />
          <path d="M24 29h8" {...s} strokeWidth="2" />
          <path d="M36 18c6 0 8 3 8 7s-2 8-8 8" {...s} strokeWidth="2.2" strokeDasharray="3 2.5" />
          <circle cx="10" cy="40" r="2.2" fill="currentColor" />
          <circle cx="30" cy="40" r="2.2" fill="currentColor" />
        </>
      )}
      {kind === "generic" && (
        <>
          <rect x="8" y="10" width="32" height="28" rx="6" {...s} strokeWidth="2.2" />
          <rect x="13" y="15" width="22" height="10" rx="2" fill="currentColor" opacity=".14" />
          <path d="M15 20h4l2-3 3 6 2-3h7" {...s} strokeWidth="1.8" />
          <circle cx="17" cy="31" r="2" fill="currentColor" />
          <path d="M23 31h12" {...s} strokeWidth="2" />
        </>
      )}
    </svg>
  );
}

/**
 * Where a complaint is among its stages, as dots: done, current, still to do. Its name says the stage in words.
 */
export function StageDots({
  stages,
  current,
  decorative = false,
}: {
  stages: readonly string[];
  /** The current stage's index. */
  current: number;
  decorative?: boolean;
}) {
  return (
    <span
      className="hx-stage"
      role={decorative ? undefined : "img"}
      aria-label={
        decorative ? undefined : `Stage ${current + 1} of ${stages.length}: ${stages[current] ?? "not started"}`
      }
      aria-hidden={decorative || undefined}
    >
      {stages.map((name, index) => (
        <i key={name} className={index < current ? "is-on" : index === current ? "is-cur" : undefined} />
      ))}
    </span>
  );
}

/**
 * The dark "monitor" band that opens a hero screen: a navy field with an ECG-paper grid and a teal glow. A region named
 * by its heading (labelledBy) or its label.
 */
export function MonitorBand({
  label,
  labelledBy,
  className,
  children,
}: {
  label?: string;
  labelledBy?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={`hx-monitor${className ? ` ${className}` : ""}`}
      aria-label={labelledBy ? undefined : label}
      aria-labelledby={labelledBy}
    >
      <div className="hx-monitor-in">{children}</div>
    </section>
  );
}

/** A unique id for an SVG gradient, so two illustrations on one page never share one. */
export const useArtId = (name: string) => `${name}-${useId().replace(/:/g, "")}`;
