/*
 * One way to show dates and times in the application. Days use the month's name ("3 Oct 2026"), so 03/10 and 10/03
 * can never be confused across countries; times always name their time zone, which matters for audit trails and
 * electronic signatures. The browser's language and time zone are used; ``formatUtc`` gives the server's UTC record.
 */

type DateInput = string | number | Date | null | undefined;

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
  return date ? date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : fallback;
}

/** "3 Oct 2026, 14:05 GMT+5:30": date, time and the time zone it is in. */
export function formatDateTime(value: DateInput, fallback = "—"): string {
  const date = toDate(value);
  return date
    ? date.toLocaleString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZoneName: "short",
      })
    : fallback;
}

/** "14:05:12 GMT+5:30" for events within the current screen (for example a connection check). */
export function formatTime(value: DateInput, fallback = "—"): string {
  const date = toDate(value);
  return date
    ? date.toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZoneName: "short",
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
