import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../app/apiClient";
import { REFRESH_FOR_MS, STATUS_REFRESH_MS, whenNoLongerPending } from "../customer-admin/shared";
import { FINDING_SIGNALS_NOW } from "./signals";
import { findingSignals, storyHeadline, type TrialStory } from "./trialStory";

// 0.10.44: right after an import whose signals are being found, Getting started read the whole story at once. That
// read could only say "Finding signals", and with the server busy finding them it took seconds and slowed the finding
// down. The page now asks the small detection status until the signals are in, then reads the story once; meanwhile
// the trend chapter says the signals are being found, as the server's story does.

const reads = vi.hoisted(() => ({ answers: [] as unknown[], paths: [] as string[] }));

vi.mock("../../app/apiClient", async (original) => ({
  ...(await original<typeof import("../../app/apiClient")>()),
  requestJson: (path: string) => {
    reads.paths.push(path);
    const next = reads.answers.length > 1 ? reads.answers.shift() : reads.answers[0];
    return next instanceof Error ? Promise.reject(next) : Promise.resolve(next);
  },
}));

const story: TrialStory = {
  as_of: "2026-10-22",
  signals_pending: false,
  acted: 1,
  total: 2,
  next: "TRENDS_TO_CASES",
  chapters: [
    {
      code: "YOUR_DATA",
      number: 1,
      title: "Bring your own data",
      promise: "Import your complaints.",
      pain: "",
      opens: { section: "Getting started" },
      finding: { value: 37, text: "37 complaints of your own imported", state: "CLEAR" },
      acted: { done: true, count: 1 },
    },
    {
      code: "TRENDS_TO_CASES",
      number: 3,
      title: "Turn a rising trend into a case",
      promise: "Signals count every complaint per product version.",
      pain: "",
      opens: { section: "Signals" },
      finding: { value: 1, text: "1 signal waiting for a decision or a case", state: "ATTENTION" },
      acted: { done: false, count: 0 },
    },
  ],
};

const wait = async (ms: number) => {
  await vi.advanceTimersByTimeAsync(ms);
};

afterEach(() => {
  vi.useRealTimers();
  reads.answers = [];
  reads.paths = [];
});

describe("Getting started after an import whose signals are being found", () => {
  it("shows the trend chapter finding signals, and leaves the other chapters as they were", () => {
    const shown = findingSignals(story);
    expect(shown.signals_pending).toBe(true);
    expect(shown.chapters[1].finding).toEqual({ value: null, text: FINDING_SIGNALS_NOW, state: "NOT_SET" });
    expect(shown.chapters[0]).toBe(story.chapters[0]);
    expect(storyHeadline(shown).detail).toContain("Finding signals in the complaints you just imported.");
    // The story itself is not changed.
    expect(story.chapters[1].finding.text).toBe("1 signal waiting for a decision or a case");
  });

  it("asks the small status until the signals are in, then reads the story once", async () => {
    vi.useFakeTimers();
    reads.answers = [{ pending: true }, { pending: true }, { pending: false }];
    const done = vi.fn();
    whenNoLongerPending("/api/v1/triage/detection", done);
    await wait(0);
    expect(done).not.toHaveBeenCalled();
    await wait(STATUS_REFRESH_MS);
    expect(done).not.toHaveBeenCalled();
    await wait(STATUS_REFRESH_MS);
    expect(done).toHaveBeenCalledTimes(1);
    expect(reads.paths).toEqual(Array(3).fill("/api/v1/triage/detection"));
    await wait(STATUS_REFRESH_MS * 3);
    expect(reads.paths).toHaveLength(3);
    expect(done).toHaveBeenCalledTimes(1);
  });

  it("asks again after a passing failure, reads the story at once after a refusal, and gives up waiting in time", async () => {
    vi.useFakeTimers();
    reads.answers = [new ApiError("busy", 503), { pending: false }];
    const afterFailure = vi.fn();
    whenNoLongerPending("/api/v1/triage/detection", afterFailure);
    await wait(0);
    expect(afterFailure).not.toHaveBeenCalled();
    await wait(STATUS_REFRESH_MS);
    expect(afterFailure).toHaveBeenCalledTimes(1);

    reads.answers = [new ApiError("Not allowed", 403)];
    const refused = vi.fn();
    whenNoLongerPending("/api/v1/triage/detection", refused);
    await wait(0);
    expect(refused).toHaveBeenCalledTimes(1);

    reads.answers = [{ pending: true }];
    const late = vi.fn();
    whenNoLongerPending("/api/v1/triage/detection", late);
    await wait(REFRESH_FOR_MS + STATUS_REFRESH_MS * 2);
    expect(late).toHaveBeenCalledTimes(1);

    reads.answers = [{ pending: true }];
    const left = vi.fn();
    const stop = whenNoLongerPending("/api/v1/triage/detection", left);
    await wait(0);
    stop();
    reads.answers = [{ pending: false }];
    await wait(STATUS_REFRESH_MS * 2);
    expect(left).not.toHaveBeenCalled();
  });
});
