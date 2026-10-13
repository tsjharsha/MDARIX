// The quality loop (sections/QualityLoop.tsx): the inspection checks, or a trial's story chapters, as stations on one
// closed loop, in the order a complaint travels: found, handled on time, reported, investigated, trended, acted on,
// proven, fed into the risk file, and back. Pure rules; the server reads the records (/api/v1/readiness,
// /api/v1/trial/story).
import type { Tone } from "../admin/console/dashboardModel";
import { checkStateOf, type Readiness, type ReadinessCheck } from "./readiness";

export type LoopStation = {
  key: string;
  number: number;
  label: string;
  caption: string;
  value: number | null;
  tone: Tone;
  stateLabel: string;
  done?: boolean;
  opens?: { section: string; tab?: string | null } | null;
};

/** The inspection checks in the order a complaint travels through the quality system. */
export const LOOP_ORDER: ReadonlyArray<{ code: string; label: string; caption: string }> = [
  {
    code: "COMPLAINTS_TO_RECHECK",
    label: "Hidden complaints found",
    caption: "Cancelled, inquiry or No Fault Found records that carry signs of a complaint",
  },
  { code: "COMPLAINTS_PAST_TARGET", label: "Handled on time", caption: "Open complaints past your target days" },
  {
    code: "REPORTING_CLOCKS",
    label: "Reported in window",
    caption: "Reporting clocks due, overdue or missing answers",
  },
  {
    code: "HARM_CLOSED_WITHOUT_CASE",
    label: "Harm investigated",
    caption: "Death or serious injury closed without an investigation",
  },
  { code: "TRIAGE_OVERDUE", label: "Signals triaged", caption: "Signals waiting past their triage date" },
  { code: "TRENDS_WITHOUT_ACTION", label: "Trends acted on", caption: "Trends with no CAPA or risk review" },
  { code: "CAPA_EFFECTIVENESS", label: "CAPAs proven", caption: "CAPAs without a verified effect" },
  { code: "RISK_FILE_INPUT", label: "Risk file fed", caption: "Post-market data not yet in the risk file" },
];

const stationOf = (check: ReadinessCheck, number: number, label: string, caption: string): LoopStation => {
  const state = checkStateOf(check.state);
  return {
    key: check.code,
    number,
    label,
    caption,
    value: check.value,
    tone: state.tone,
    stateLabel: state.label,
    done: check.state === "CLEAR",
    opens: check.opens,
  };
};

/** The readiness checks as loop stations, in story order; a check the order does not know yet comes last. */
export function loopFromReadiness(data: Readiness | null | undefined): LoopStation[] {
  const checks = data?.checks ?? [];
  const byCode = new Map(checks.map((check) => [check.code, check]));
  const known = LOOP_ORDER.filter((step) => byCode.has(step.code)).map((step) => ({
    check: byCode.get(step.code) as ReadinessCheck,
    label: step.label,
    caption: step.caption,
  }));
  const extra = checks
    .filter((check) => !LOOP_ORDER.some((step) => step.code === check.code))
    .map((check) => ({ check, label: check.title, caption: check.detail }));
  return [...known, ...extra].map((item, index) => stationOf(item.check, index + 1, item.label, item.caption));
}

const TONE_RANK: Record<Tone, number> = { critical: 0, serious: 1, warning: 2, neutral: 3, good: 4 };

/** The weakest link: the first station in the worst state that is not done (null when every station is done). */
export function weakestLink(stations: readonly LoopStation[]): LoopStation | null {
  const open = stations.filter((station) => !station.done);
  if (!open.length) return null;
  return [...open].sort((left, right) => TONE_RANK[left.tone] - TONE_RANK[right.tone] || left.number - right.number)[0];
}

/** How many stations are done ("clear" for checks, "acted on" for a story). */
export const loopDone = (stations: readonly LoopStation[]) => stations.filter((station) => station.done).length;

/** Where station ``index`` of ``total`` sits on a circle of ``radius`` around (cx, cy): the first at the top, then
 * clockwise. Rounded to 0.1 so the markup is stable. */
export function stationPoint(index: number, total: number, radius: number, cx: number, cy: number) {
  const angle = (2 * Math.PI * index) / Math.max(1, total) - Math.PI / 2;
  const round = (value: number) => Math.round(value * 10) / 10;
  return { x: round(cx + radius * Math.cos(angle)), y: round(cy + radius * Math.sin(angle)) };
}

/** Seconds the pulse takes to travel the loop once: one full turn every 14 s, never faster on a busy loop. */
export const LOOP_SECONDS = 14;
