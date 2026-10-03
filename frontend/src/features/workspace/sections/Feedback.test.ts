import { describe, expect, it } from "vitest";
import { readyForFeedback } from "./Feedback";

const DAY = 24 * 3600 * 1000;
const none = { products: 0, lots: 0, complaints: 0 };

describe("when to ask a trial user for feedback", () => {
  it("does not ask on the first days of a trial", () => {
    const now = Date.parse("2026-10-10T12:00:00Z");
    expect(readyForFeedback({ starts_at: new Date(now - DAY).toISOString(), own_data: none }, now)).toBe(false);
  });

  it("asks from day 3", () => {
    const now = Date.parse("2026-10-10T12:00:00Z");
    expect(readyForFeedback({ starts_at: new Date(now - 3 * DAY).toISOString(), own_data: none }, now)).toBe(true);
  });

  it("asks earlier once the person imported their own data", () => {
    const now = Date.parse("2026-10-10T12:00:00Z");
    const own = { products: 0, lots: 0, complaints: 4 };
    expect(readyForFeedback({ starts_at: new Date(now - DAY).toISOString(), own_data: own }, now)).toBe(true);
  });
});
