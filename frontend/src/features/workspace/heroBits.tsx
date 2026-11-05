import { CircleCheck, Clock } from "lucide-react";
import { DeadlineChip } from "../../app/chips";
import { displayTimeZone } from "../../app/dates";
import { ClockRing, DeviceIcon, Flag, StageDots, clockStatus, deviceKind } from "../shared/hero/HeroVisuals";
import { initials } from "./HybridShell";
import { isLegalDeadline } from "./home";

/*
 * The hero design's cells for the new navigation's lists and pages (0.10.90): a deadline as a clock ring beside its
 * words, the product with its device, the country with its flag, the owner with initials, the stage with its dots.
 * The words are the page's own; the graphics only add a visual signal beside them.
 */

type Due = {
  key: string;
  category?: string | null;
  due_at: string;
  due_label?: string;
  state: string;
  hours_left: number;
};

/** A deadline's ring: days left of a 30-day window, or hours left of a day in its last day. */
export function ringOf(item: { hours_left: number; state: string }) {
  const overdue = item.state === "OVERDUE" || item.hours_left < 0;
  if (!overdue && item.hours_left < 24) {
    const hours = Math.max(0, Math.floor(item.hours_left));
    return { left: hours, total: 24, shown: `${hours}h`, status: "warn" as const };
  }
  const days = overdue ? -Math.max(1, Math.ceil(-item.hours_left / 24)) : Math.floor(item.hours_left / 24);
  return { left: days, total: 30, shown: overdue ? "!" : String(days), status: clockStatus(days) };
}

const WORD = { crit: null, warn: "Due soon", good: "On track" } as const;

/** A legal clock as the mock-up's clock pill: the ring, the time left in words and its state in a word. */
export function ClockPill({ item, prefix }: { item: Due; prefix?: string }) {
  const ring = ringOf(item);
  const word = WORD[ring.status];
  return (
    <span className={`hx-clockpill is-${ring.status}`}>
      <ClockRing left={ring.left} total={ring.total} status={ring.status} size={40} stroke={4} label="" decorative>
        {ring.shown}
      </ClockRing>
      <span className="hx-clockpill-t">
        <DeadlineChip item={item} prefix={prefix} />
        {word && (
          <small className={`hx-st-${ring.status}`}>
            {ring.status === "good" ? (
              <CircleCheck size={12} aria-hidden="true" />
            ) : (
              <Clock size={12} aria-hidden="true" />
            )}
            {word}
          </small>
        )}
      </span>
    </span>
  );
}

/** The complaint's stages in order, as the server names them (oversight/closure.py STAGES); a report is assessed at
 * the market step. */
export const STAGES = [
  "Triage",
  "Market assessment",
  "Investigation",
  "Decision",
  "Ready to close",
  "Closed in the QMS",
];
export const stageIndex = (stage: string | null | undefined) =>
  stage === "Report" ? 1 : STAGES.indexOf(String(stage ?? ""));

export function StageCell({ stage }: { stage: string | null | undefined }) {
  const at = stageIndex(stage);
  if (!stage) return <>—</>;
  return (
    <span className="hx-stagecell">
      {at >= 0 && <StageDots stages={STAGES} current={at} decorative />}
      <span>{stage}</span>
    </span>
  );
}

export function ProductCell({ name, children }: { name: string | null | undefined; children: React.ReactNode }) {
  return (
    <span className="hx-prod">
      <span className="hx-prod-pic">
        <DeviceIcon kind={deviceKind(name)} size={26} decorative />
      </span>
      <span>{children}</span>
    </span>
  );
}

export function CountryCell({ country, children }: { country: string | null | undefined; children: React.ReactNode }) {
  return (
    <span className="hx-mkt">
      <Flag country={country} decorative />
      {children}
    </span>
  );
}

export function OwnerCell({ name }: { name: string | null | undefined }) {
  return (
    <span className={`hx-owner${name ? "" : " is-none"}`}>
      <span className="hx-who" aria-hidden="true">
        {name ? initials(name) : ""}
      </span>
      <span>{name ?? "Not named"}</span>
    </span>
  );
}

/** The complaint list at a glance: by legal clock (7 days or less, more, none), late communications, deaths and
 * serious injuries. */
export function listGlance(
  rows: ReadonlyArray<{ death?: boolean; serious_injury?: boolean; work?: { due: Due[] } | null }>,
) {
  const out = { soon: 0, later: 0, none: 0, lateReplies: 0, serious: 0, deaths: 0 };
  for (const row of rows) {
    const due = row.work?.due ?? [];
    const legal = due.filter((item) => isLegalDeadline({ key: item.key, category: item.category ?? "" }));
    const nearest = legal[0] ?? due[0];
    if (!nearest) out.none += 1;
    else if (nearest.state === "OVERDUE" || nearest.hours_left <= 7 * 24) out.soon += 1;
    else out.later += 1;
    if (due.some((item) => item !== nearest && item.state === "OVERDUE" && /COMMUNICATION/i.test(item.category ?? "")))
      out.lateReplies += 1;
    if (row.death) out.deaths += 1;
    else if (row.serious_injury) out.serious += 1;
  }
  return out;
}

const DAY = 86_400_000;

/** The ruler's ten days, three before today and six after, in the zone times are shown in. */
export function rulerDays(now = new Date(), zone = displayTimeZone()) {
  const clock = now.toLocaleTimeString("en-GB", { hour12: false, timeZone: zone }).split(":").map(Number);
  // shortcut: a day is 24 h here, so a ruler that spans a clock change is out by an hour; fine for a 10-day glance.
  const start = now.getTime() - ((clock[0] % 24) * 3600 + clock[1] * 60 + (clock[2] || 0)) * 1000 - 3 * DAY;
  const labels = Array.from({ length: 10 }, (_, k) =>
    new Date(start + k * DAY + DAY / 2).toLocaleDateString("en-GB", {
      weekday: "short",
      day: "numeric",
      timeZone: zone,
    }),
  );
  const at = (when: number) => (when - start) / (10 * DAY);
  return { start, labels, at, now: at(now.getTime()) };
}

/**
 * The next actions' deadlines on a ten-day ruler (the hero design's timeline): "Now", the day names, the overdue
 * stretch shaded, and one marker per day and state with how many fall there. Named in words for screen readers.
 */
export function DeadlineRuler({ items, now = new Date() }: { items: ReadonlyArray<Due>; now?: Date }) {
  const ruler = rulerDays(now);
  const groups = new Map<string, { pos: number; day: number; status: "crit" | "warn" | "good"; n: number }>();
  for (const item of items) {
    const status = ringOf(item).status;
    const pos = Math.max(0, ruler.at(new Date(item.due_at).getTime()));
    if (pos > 1) continue;
    const day = Math.min(9, Math.floor(pos * 10));
    const key = `${day}-${status}`;
    const group = groups.get(key) ?? { pos, day, status, n: 0 };
    group.n += 1;
    groups.set(key, group);
  }
  const marks = [...groups.values()].sort((a, b) => a.pos - b.pos);
  if (!marks.length) return null;
  const late = marks.filter((mark) => mark.status === "crit");
  const said = marks
    .map((mark) => `${mark.n} ${mark.status === "crit" ? "overdue since" : "due"} ${ruler.labels[mark.day]}`)
    .join(", ");
  const pct = (value: number) => `${(value * 100).toFixed(2)}%`;
  return (
    <div className="hx-ruler" role="img" aria-label={`Deadlines on a timeline: ${said}`}>
      <div className="hx-ruler-days">
        {ruler.labels.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>
      {late.length > 0 && (
        <span
          className="hx-ruler-od"
          style={{ left: pct(late[0].pos), width: pct(Math.max(0, ruler.now - late[0].pos)) }}
        />
      )}
      <span className="hx-ruler-now" style={{ left: pct(ruler.now) }}>
        <em>Now</em>
      </span>
      {marks.map((mark) => (
        <span
          key={`${mark.day}-${mark.status}`}
          className={`hx-ruler-mk is-${mark.status}`}
          style={{ left: pct(mark.pos) }}
        >
          {mark.n}
        </span>
      ))}
    </div>
  );
}
