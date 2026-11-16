import { describe, expect, it } from "vitest";
import { feedbackChoices, quietStart, readyForFeedback } from "./Feedback";

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

  it("asks earlier once the organization imported its own data, but not on the person's first 2 days", () => {
    const now = Date.parse("2026-10-10T12:00:00Z");
    const own = { products: 0, lots: 0, complaints: 4 };
    const at = (days: number) => new Date(now - days * DAY).toISOString();
    // Imported on the first day: not yet (UX-26, 0.10.37).
    expect(readyForFeedback({ starts_at: at(1), own_data: own }, now)).toBe(false);
    expect(readyForFeedback({ starts_at: at(2.5), own_data: own, me: { joined_at: at(2.5) } }, now)).toBe(true);
  });

  it("does not ask a colleague on their first screens, however old the trial is (UX-26)", () => {
    const now = Date.parse("2026-10-10T12:00:00Z");
    const at = (days: number) => new Date(now - days * DAY).toISOString();
    // Invited on day 5 of the trial and signed in an hour ago.
    expect(readyForFeedback({ starts_at: at(5), own_data: none, me: { joined_at: at(1 / 24) } }, now)).toBe(false);
    expect(readyForFeedback({ starts_at: at(5), own_data: none, me: { joined_at: at(1.9) } }, now)).toBe(false);
    // From the person's third day.
    expect(readyForFeedback({ starts_at: at(7), own_data: none, me: { joined_at: at(2) } }, now)).toBe(true);
  });
});

describe("what the feedback form asks about", () => {
  const values = (items: [string, string][]) => items.map(([value]) => value);
  const labels = (items: [string, string][]) => items.map(([, label]) => label);

  it("names the MVP's screens, not Product 360", () => {
    const { features } = feedbackChoices({ featureSet: "mvp", aiReady: true, isTrial: true });
    expect(labels(features)).not.toContain("Product 360");
    expect(labels(features)).not.toContain("Evidence library");
    expect(values(features)).toEqual([
      "GETTING_STARTED",
      "READINESS",
      "COMPLAINTS",
      "SIGNALS",
      "INVESTIGATIONS",
      "ASK_MDARIX",
      "DECISIONS",
      "RECORDS",
      "CSV_IMPORT",
    ]);
    // Getting started is a trial's screen only.
    const customer = feedbackChoices({ featureSet: "mvp", aiReady: true, isTrial: false });
    expect(values(customer.features)).not.toContain("GETTING_STARTED");
    // The full product still has Product 360.
    expect(labels(feedbackChoices({ featureSet: "full", aiReady: true, isTrial: false }).features)).toContain(
      "Product 360",
    );
  });

  it("asks about AI only while AI answers for the organization", () => {
    const on = feedbackChoices({ featureSet: "mvp", aiReady: true, isTrial: true });
    expect(values(on.ratings)).toContain("rating_ai_trust");
    expect(values(on.features)).toContain("ASK_MDARIX");
    for (const aiReady of [false, null]) {
      const off = feedbackChoices({ featureSet: "mvp", aiReady, isTrial: true });
      expect(values(off.ratings)).not.toContain("rating_ai_trust");
      expect(values(off.ratings)).toContain("rating_overall");
      expect(values(off.features)).not.toContain("ASK_MDARIX");
      const full = feedbackChoices({ featureSet: "full", aiReady, isTrial: false });
      expect(values(full.features)).not.toContain("ASK_MDARIX");
    }
  });
});

describe("the quiet start of a session", () => {
  it("asks for no feedback in the first 10 minutes of a browser session", () => {
    const kept = new Map<string, string>();
    const store = () => ({
      getItem: (key: string) => kept.get(key) ?? null,
      setItem: (key: string, value: string) => void kept.set(key, value),
    });
    const start = Date.parse("2026-11-17T10:00:00Z");
    expect(quietStart(store, start)).toBe(true);
    expect(quietStart(store, start + 9 * 60 * 1000)).toBe(true);
    expect(quietStart(store, start + 11 * 60 * 1000)).toBe(false);
    // Storage that cannot be read never hides the ask for ever.
    expect(
      quietStart(() => {
        throw new Error("blocked");
      }),
    ).toBe(false);
  });
});
