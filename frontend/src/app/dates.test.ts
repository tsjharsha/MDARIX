import { describe, expect, it } from "vitest";
import { daysUntil, formatDateTime, formatDay, formatUtc, isDateOnly, localDay } from "./dates";

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
