/*
 * One way to show dates and times in the application. Days use the month's name ("3 Oct 2026"), so 03/10 and 10/03
 * can never be confused across countries. A time is shown without its zone, and each screen names the zone once
 * (``zoneName``, in the workspace's page head) instead of "GMT+5:30" on every timestamp (V3). The browser's language and
 * time zone are used; ``formatUtc`` gives the server's UTC record, as audit trails and signatures keep it.
 */

type DateInput = string | number | Date | null | undefined;

// The organization's time zone (its working calendar in Settings), set by the new navigation's workspace (0.10.85,
// D3.6): every time shown is in it, the page head names it once, and each deadline label drops its zone. Unset (the
// classic navigation, a test), times are the browser's as before.
let displayZone: string | undefined;

/** Show every time in this zone (an IANA name); null goes back to the browser's. */
export function setDisplayZone(zone: string | null | undefined): void {
  displayZone = zone || undefined;
}

/** A deadline label without its trailing zone ("Wed 2 Dec 2026, 23:59 IST" -> "Wed 2 Dec 2026, 23:59"), once the
 * page names the organization's zone; as it is otherwise. */
export const zoneless = (label: string): string =>
  displayZone ? label.replace(/\s+(?:[A-Z]{2,5}|GMT[+-]\d{1,2}(?::\d{2})?)$/, "") : label;

// One style per kind on every screen (0.10.72): "3 Oct 2026" and "3 Oct 2026, 14:05", as the legal deadlines read
// ("Tue 1 Dec 2026, 23:59 IST"), whatever the browser's language ("Nov 1, 2026, 10:54 PM" sat beside them before).
const DAY_FIRST = "en-GB";

// A calendar date without a time ("2026-03-04", a *_date field). JavaScript reads it as midnight UTC, which is the
// day before anywhere west of Greenwich; it is read as that day where the person is instead.
const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Whether a value is a calendar date without a time of day. */
export const isDateOnly = (value: unknown) => typeof value === "string" && DATE_ONLY.test(value.trim());

function toDate(value: DateInput): Date | null {
  if (value === null || value === undefined || value === "") return null;
  const day = typeof value === "string" ? DATE_ONLY.exec(value.trim()) : null;
  const date = day
    ? new Date(Number(day[1]), Number(day[2]) - 1, Number(day[3]))
    : value instanceof Date
      ? value
      : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "3 Oct 2026" (or the reader's order of day, month and year). */
export function formatDay(value: DateInput, fallback = "—"): string {
  const date = toDate(value);
  // A calendar date stays that day; a moment reads in the organization's zone once it is set.
  const zone = typeof value === "string" && DATE_ONLY.test(value.trim()) ? undefined : displayZone;
  return date
    ? date.toLocaleDateString(DAY_FIRST, { day: "numeric", month: "short", year: "numeric", timeZone: zone })
    : fallback;
}

/** An awareness as it was given (0.10.81, U-06): a day without a time reads "29 Oct 2026, time not recorded" (the
 * server keeps such a day at 12:00 UTC, so its UTC day is the day given); a moment reads with its time. */
export function awarenessText(value: string | null | undefined, dateOnly?: boolean | null): string {
  if (!value) return "—";
  if (!dateOnly) return formatDateTime(value);
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  return `${formatDay(new Date(year, month - 1, day))}, time not recorded`;
}

/** "3 Oct 2026, 14:05": date and time where the person is (the screen names the zone once, ``zoneName``). */
export function formatDateTime(value: DateInput, fallback = "—"): string {
  const date = toDate(value);
  return date
    ? date.toLocaleString(DAY_FIRST, {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
        timeZone: displayZone,
      })
    : fallback;
}

/** The reader's time zone in words ("India Standard Time"), said once per screen for the times on it. */
export function zoneName(now = new Date()): string {
  const part = new Intl.DateTimeFormat("en-GB", { timeZoneName: "long", timeZone: displayZone })
    .formatToParts(now)
    .find((item) => item.type === "timeZoneName");
  return part?.value ?? displayZone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/** "14:05:12" for events within the current screen (for example a connection check). */
export function formatTime(value: DateInput, fallback = "—"): string {
  const date = toDate(value);
  return date
    ? date.toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : fallback;
}

/** "2026-10-03 08:35:12 UTC": the exact recorded time, as kept in the audit trail and on signatures. */
export function formatUtc(value: DateInput, fallback = "—"): string {
  const date = toDate(value);
  return date ? `${date.toISOString().slice(0, 19).replace("T", " ")} UTC` : fallback;
}

/** Today's calendar date where the person is ("2026-10-20"): in India the UTC date is still the day before until 05:30. */
export function localDay(now = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/**
 * Calendar days from today, where the person is, to a calendar date ("2027-01-18"); negative once it has passed, null
 * for anything but a calendar date. The server counts from the UTC date, which said "Due in 91 days" for a 90-day check
 * planned just after midnight in India (validation finding DEV-020, FUN-15).
 */
export function daysUntil(day: unknown, now = new Date()): number | null {
  if (!isDateOnly(day)) return null;
  const date = toDate(day as string);
  if (!date) return null;
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  // Rounded: a day across a daylight-saving change is 23 or 25 hours long.
  return Math.round((date.getTime() - today.getTime()) / 86_400_000);
}

/** What a due time or deadline needs for {@link timeLeft}: the server's state, and its end or its day. */
export type DueLike = {
  state?: string | null;
  due_at?: string | null;
  due_date?: string | null;
  days_left?: number | null;
  hours_left?: number | null;
};

const amount = (value: number, unit: "day" | "h") =>
  unit === "h" ? `${value} h` : `${value} ${value === 1 ? "day" : "days"}`;

/**
 * The one way MDARIX says how much time is left (J40): "3 days left", "1 day left", "5 h left", "Due today",
 * "2 days overdue", "3 h overdue". Overdue comes from the server's state when it gives one, so "1 h left" never stands
 * beside "Overdue". From the end of the day (``due_at``) when there is one: whole days are the days to the deadline's
 * own day in its time zone; the last day counts in hours. A calendar day without an end counts days where the person
 * is.
 */
export function timeLeft(item: DueLike, now = new Date()): string {
  const end = item.due_at ? Date.parse(item.due_at) : Number.NaN;
  const ms = Number.isFinite(end)
    ? end - now.getTime()
    : typeof item.hours_left === "number"
      ? item.hours_left * 3_600_000
      : Number.NaN;
  if (Number.isFinite(ms)) {
    const overdue = item.state ? item.state === "OVERDUE" : ms <= 0;
    if (overdue && ms > 0) return "Overdue";
    if (!overdue && ms <= 0) return "Due now";
    const hours = Math.abs(ms) / 3_600_000;
    const text = hours < 24 ? amount(Math.max(1, Math.round(hours)), "h") : amount(Math.floor(hours / 24), "day");
    return overdue ? `${text} overdue` : `${text} left`;
  }
  const days = daysUntil(item.due_date, now) ?? item.days_left;
  if (typeof days !== "number") return "";
  const overdue = item.state ? item.state === "OVERDUE" : days < 0;
  if (overdue) return days < 0 ? `${amount(-days, "day")} overdue` : "Overdue";
  if (days <= 0) return "Due today";
  return `${amount(days, "day")} left`;
}

/** A legal deadline as the server writes it, with its time zone ("Mon 30 Nov 2026, 23:59 IST"); its day otherwise. */
export const deadlineLabel = (item: { due_label?: string | null; due_date?: string | null } | null | undefined) =>
  item?.due_label ? zoneless(item.due_label) : formatDay(item?.due_date);
