import { describe, expect, it } from "vitest";
import {
  daysUntil,
  deadlineLabel,
  formatDateTime,
  formatDay,
  formatUtc,
  isDateOnly,
  localDay,
  timeLeft,
} from "./dates";

describe("dates", () => {
  it("names the month so day and month cannot be confused", () => {
    expect(formatDay("2026-10-03T08:35:12Z")).toMatch(/Oct/);
  });

  it("always states the time zone of a time", () => {
    expect(formatDateTime("2026-10-03T08:35:12Z")).toMatch(/(GMT|UTC|[A-Z]{2,5})/);
  });

  it("gives the exact recorded UTC time for audit and signatures", () => {
    expect(formatUtc("2026-10-03T08:35:12.345Z")).toBe("2026-10-03 08:35:12 UTC");
  });

  it("shows a dash for a missing or unreadable date", () => {
    expect(formatDay(null)).toBe("—");
    expect(formatDateTime("not a date")).toBe("—");
  });

  it("shows a calendar date as that day wherever the reader is, never the day before", () => {
    expect(isDateOnly("2026-03-04")).toBe(true);
    expect(isDateOnly("2026-03-04T00:00:00Z")).toBe(false);
    expect(formatDay("2026-03-04")).toBe(
      new Date(2026, 2, 4).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }),
    );
  });

  it("counts calendar days from today where the person is (DEV-020)", () => {
    const justAfterMidnight = new Date(2026, 9, 20, 1, 5);
    expect(localDay(justAfterMidnight)).toBe("2026-10-20");
    expect(daysUntil("2027-01-18", justAfterMidnight)).toBe(90);
    expect(daysUntil("2026-10-20", new Date(2026, 9, 20, 23, 59))).toBe(0);
    expect(daysUntil("2026-10-19", justAfterMidnight)).toBe(-1);
    // Across the March change to summer time, where the reader has one, a day is still a day.
    expect(daysUntil("2026-04-05", new Date(2026, 2, 25, 9))).toBe(11);
    expect(daysUntil("2026-10-20T10:00:00Z", justAfterMidnight)).toBeNull();
    expect(daysUntil(null, justAfterMidnight)).toBeNull();
  });
});

describe("timeLeft: one way to say the time left (J40)", () => {
  const now = new Date("2026-11-01T12:00:00Z");
  const due = (iso: string, state?: string) => ({ due_at: iso, state });

  it("counts whole days to the deadline's own day, then hours on the last day", () => {
    expect(timeLeft(due("2026-11-07T18:29:59Z", "RUNNING"), now)).toBe("6 days left");
    expect(timeLeft(due("2026-11-02T18:29:59Z", "DUE_SOON"), now)).toBe("1 day left");
    expect(timeLeft(due("2026-11-01T18:29:59Z", "DUE_SOON"), now)).toBe("6 h left");
    expect(timeLeft(due("2026-10-30T18:29:59Z", "OVERDUE"), now)).toBe("1 day overdue");
    expect(timeLeft(due("2026-11-01T09:00:00Z", "OVERDUE"), now)).toBe("3 h overdue");
  });

  it("never says '1 days' and never puts time left beside an overdue state", () => {
    expect(timeLeft({ days_left: 1 }, now)).toBe("1 day left");
    expect(timeLeft(due("2026-11-01T12:40:00Z", "OVERDUE"), now)).toBe("Overdue");
    expect(timeLeft(due("2026-11-01T11:00:00Z", "RUNNING"), now)).toBe("Due now");
    expect(timeLeft({ days_left: 0 }, now)).toBe("Due today");
    expect(timeLeft({ days_left: -3 }, now)).toBe("3 days overdue");
  });

  it("gives the same text for the same deadline whichever screen asks", () => {
    const deadline = { due_at: "2026-11-04T22:59:59Z", due_date: "2026-11-04", days_left: 3, state: "DUE_SOON" };
    // 0.10.62: the watch counted to the day where the person is ("2 days left"), Reports from the UTC date (3).
    expect(timeLeft(deadline, now)).toBe(timeLeft({ ...deadline, days_left: 2 }, now));
    expect(deadlineLabel({ due_label: "Wed 4 Nov 2026, 23:59 CET", due_date: "2026-11-04" })).toBe(
      "Wed 4 Nov 2026, 23:59 CET",
    );
  });
});
