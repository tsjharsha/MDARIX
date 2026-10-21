import { describe, expect, it } from "vitest";
import { stillUnfinished } from "../customer-admin/shared";
import { FINDING_SIGNALS_TEXT, importedText } from "./sections/ImportData";
import { inboxEmpty } from "./sections/SignalInbox";
import { storyHeadline, type TrialStory } from "./trialStory";
import type { SignalFilters } from "./signals";

// 0.10.40: an import answers before its signals are found (they follow within seconds). The import result says so,
// the signal inbox and the trial's story show "Finding signals…" and read again in the background until they are in.

const FILTERS = {
  status: "ALL",
  q: "",
  priorities: [],
  productId: "",
  origin: "",
  owner: "",
} as unknown as SignalFilters;

describe("signals found after the import answers", () => {
  it("says in the import result that signals are being found", () => {
    expect(importedText("Complaints", { created: 4993, updated: 0, signals: "FINDING" })).toBe(
      `Imported complaints: 4993 new, 0 updated. ${FINDING_SIGNALS_TEXT}`,
    );
    expect(FINDING_SIGNALS_TEXT).not.toMatch(/MVP|trial/);
    // Without complaints there are no signals to find, and nothing is said about them.
    expect(importedText("Products and versions", { created: 2, updated: 0 })).toBe(
      "Imported products and versions: 2 new, 0 updated.",
    );
  });

  it("shows Finding signals in an empty inbox while they are found, else the usual empty states", () => {
    expect(inboxEmpty(FILTERS, true).title).toBe("Finding signals…");
    expect(inboxEmpty({ ...FILTERS, q: "pump" }, true).title).toBe("Finding signals…");
    expect(inboxEmpty({ ...FILTERS, q: "pump" }, false).title).toBe("No matching signals");
    expect(inboxEmpty(FILTERS, false).title).toBe("No signals");
  });

  it("reads a resource again only while its data says it is not final", () => {
    const pending = (data: { detection_pending?: boolean }) => !!data.detection_pending;
    expect(stillUnfinished({ state: "ready", data: { detection_pending: true } }, pending)).toBe(true);
    expect(stillUnfinished({ state: "ready", data: { detection_pending: false } }, pending)).toBe(false);
    expect(stillUnfinished({ state: "loading", data: null }, pending)).toBe(false);
    expect(stillUnfinished({ state: "error", data: { detection_pending: true } }, pending)).toBe(false);
    expect(stillUnfinished({ state: "ready", data: { detection_pending: true } })).toBe(false);
  });

  it("leads the story with the trend chapter's Finding signals line, punctuated once", () => {
    const story: TrialStory = {
      as_of: "2026-10-21",
      signals_pending: true,
      acted: 0,
      total: 1,
      next: "TRENDS_TO_CASES",
      chapters: [
        {
          code: "TRENDS_TO_CASES",
          number: 3,
          title: "Turn a rising trend into a case",
          promise: "Signals count every complaint per product version.",
          pain: "",
          opens: { section: "Signals", tab: "Signal inbox" },
          finding: { value: null, text: "Finding signals in the complaints you just imported…", state: "NOT_SET" },
          acted: { done: false, count: 0 },
        },
      ],
    };
    expect(storyHeadline(story).detail).toBe(
      "Finding signals in the complaints you just imported. Signals count every complaint per product version.",
    );
  });
});
