import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../app/apiClient";
import { RETRY_DELAYS_MS, isTransientFailure, readResource } from "../customer-admin/shared";
import { TRIAL_PROGRESS_PATH, TRIAL_STORY_PATH } from "./trialStory";

// 0.10.43: when Getting started's story reload failed during or after an import (a 5xx, no answer), the page kept the
// story from before the import and never read it again. The story's resource now retries (useResource ``retry``,
// readResource): a passing failure is read again after a growing wait, in the background, with no error shown in
// between; a refusal is not retried, and the retries stop after RETRY_DELAYS_MS.

const api = vi.hoisted(() => ({ answers: [] as Array<() => Promise<unknown>>, calls: [] as Array<unknown[]> }));

vi.mock("../../app/apiClient", async (original) => ({
  ...(await original<typeof import("../../app/apiClient")>()),
  requestJson: (...args: unknown[]) => {
    api.calls.push(args);
    const next = api.answers.shift();
    return next ? next() : Promise.reject(new Error("no answer prepared"));
  },
}));

const failing = (status: number) => () => Promise.reject(new ApiError("failed", status));
const answering = (data: unknown) => () => Promise.resolve(data);
const afterStory = { as_of: "2026-10-21", signals_pending: true, chapters: [] };

beforeEach(() => {
  vi.useFakeTimers();
  api.answers = [];
  api.calls = [];
});
afterEach(() => vi.useRealTimers());

describe("the story's reload after an import retries a passing failure", () => {
  it("reads again after a server error and a lost connection, then shows the new story without an error", async () => {
    api.answers = [failing(502), failing(0), answering(afterStory)];
    const applied: unknown[] = [];
    readResource(TRIAL_STORY_PATH, (result) => applied.push(result), true);
    await vi.advanceTimersByTimeAsync(0);
    expect(applied).toEqual([]); // no error shown for the first failure
    await vi.advanceTimersByTimeAsync(RETRY_DELAYS_MS[0]);
    expect(api.calls).toHaveLength(2);
    expect(applied).toEqual([]);
    await vi.advanceTimersByTimeAsync(RETRY_DELAYS_MS[1]);
    expect(applied).toEqual([{ state: "ready", data: afterStory }]);
    // The first read is the person's; the retries are background reads (they do not keep an idle session alive).
    expect(api.calls.map((call) => call[1])).toEqual([{}, { background: true }, { background: true }]);
    expect(api.calls.every((call) => call[0] === TRIAL_STORY_PATH)).toBe(true);
  });

  it("waits longer each time and gives up after the last wait, showing the failure then", async () => {
    api.answers = Array.from({ length: RETRY_DELAYS_MS.length + 1 }, () => failing(503));
    const applied: Array<{ state: string }> = [];
    readResource(TRIAL_STORY_PATH, (result) => applied.push(result), true);
    for (const delay of RETRY_DELAYS_MS) {
      await vi.advanceTimersByTimeAsync(delay - 1);
      expect(applied).toEqual([]);
      await vi.advanceTimersByTimeAsync(1);
    }
    await vi.advanceTimersByTimeAsync(0);
    expect(api.calls).toHaveLength(RETRY_DELAYS_MS.length + 1);
    expect(applied.map((result) => result.state)).toEqual(["error"]);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(api.calls).toHaveLength(RETRY_DELAYS_MS.length + 1); // bounded: no more reads
    expect([...RETRY_DELAYS_MS]).toEqual([...RETRY_DELAYS_MS].sort((a, b) => a - b));
    expect(RETRY_DELAYS_MS.reduce((sum, delay) => sum + delay, 0)).toBeLessThanOrEqual(30_000);
  });

  it("does not retry a refusal, or any failure without retry, and stops when the page closes", async () => {
    api.answers = [failing(403)];
    const refused: Array<{ state: string }> = [];
    readResource(TRIAL_STORY_PATH, (result) => refused.push(result), true);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(refused.map((result) => result.state)).toEqual(["forbidden"]);
    expect(api.calls).toHaveLength(1);

    api.calls = [];
    api.answers = [failing(500)];
    const plain: Array<{ state: string }> = [];
    readResource(TRIAL_PROGRESS_PATH, (result) => plain.push(result));
    await vi.advanceTimersByTimeAsync(30_000);
    expect(plain.map((result) => result.state)).toEqual(["error"]);
    expect(api.calls).toHaveLength(1);

    api.calls = [];
    api.answers = [failing(500), answering(afterStory)];
    const closed: unknown[] = [];
    const stop = readResource(TRIAL_STORY_PATH, (result) => closed.push(result), true);
    await vi.advanceTimersByTimeAsync(0);
    stop();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(api.calls).toHaveLength(1);
    expect(closed).toEqual([]);
  });

  it("counts no answer, server errors and too many requests as passing, never a refusal", () => {
    for (const status of [0, 429, 500, 502, 503, 504]) expect(isTransientFailure(new ApiError("x", status))).toBe(true);
    for (const status of [400, 401, 403, 404, 409, 422])
      expect(isTransientFailure(new ApiError("x", status))).toBe(false);
    expect(isTransientFailure(new TypeError("Failed to fetch"))).toBe(true);
  });
});
