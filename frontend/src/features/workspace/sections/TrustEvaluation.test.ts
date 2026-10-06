import { describe, expect, it } from "vitest";
import { pollDelay, runFinished, runOutcome, runPath, runRequest } from "./TrustEvaluation";

describe("evaluation runs started from the Trust page", () => {
  it("follows a run until it is PASS, FAIL or ERROR", () => {
    expect(runFinished("RUNNING")).toBe(false);
    expect(["PASS", "FAIL", "ERROR"].every(runFinished)).toBe(true);
    expect(runPath("abc")).toBe("/api/v1/evaluations/runs/abc");
    expect(pollDelay(0)).toBe(3000);
    expect(pollDelay(100)).toBe(15000);
    expect(runRequest(true)).toEqual({ scenario_ids: ["VS001"] });
    expect(runRequest(false)).toEqual({});
  });

  it("shows no result while running and only computed results afterwards", () => {
    expect(runOutcome(null)).toBeNull();
    expect(runOutcome({ evaluation_run_id: "1", status: "RUNNING", results: { total: 15, passed: 15 } })).toBeNull();
    expect(runOutcome({ evaluation_run_id: "1", status: "PASS", results: { total: 1, passed: 1 } })).toEqual({
      tone: "good",
      text: "Every scenario passed: 1 of 1.",
    });
    expect(runOutcome({ evaluation_run_id: "1", status: "FAIL", results: { total: 15, passed: 9 } })?.text).toBe(
      "9 of 15 scenarios passed.",
    );
    expect(runOutcome({ evaluation_run_id: "1", status: "ERROR", results: { error: "RUN_ABANDONED" } })).toEqual({
      tone: "critical",
      text: "The run could not complete (RUN_ABANDONED); nothing was scored.",
    });
  });
});
