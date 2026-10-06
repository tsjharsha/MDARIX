import { describe, expect, it } from "vitest";
import { formatDateTime, formatDay, formatUtc, isDateOnly } from "./dates";

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
});
