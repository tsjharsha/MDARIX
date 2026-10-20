import { describe, expect, it } from "vitest";
import { ApiError } from "../../app/apiClient";
import {
  analysisFrom,
  briefFrom,
  challengeSetFrom,
  counterfactualFrom,
  failureChainsFrom,
  hasSavedResults,
  hypothesisSetFrom,
  loadSavedResults,
  unknownSetFrom,
} from "./savedResults";

const base = "/api/v1/investigations/inv-1";
const analysis = { analysis_id: "a1", status: "COMPLETED", observations: [] };
const hypothesisSet = { hypothesis_set_id: "h1", status: "COMPLETED", hypotheses: [] };
const challengeSet = { challenge_set_id: "c1", challenges: [] };
const unknownSet = { unknown_set_id: "u1", unknowns: [] };
const failureChainSet = { failure_chain_set_id: "f1", chains: [] };
const brief = { id: "b1", business_id: "BRF000001", brief_version: 2, title: "Brief", content: {}, provenance: {} };
const scenario = (status: string, label: string) => ({ id: label, status, result: { label, invariants: [] } });

/** A fake reader: each path answers with its payload, or fails with the given error. */
const reader = (answers: Record<string, unknown>) => {
  const calls: string[] = [];
  const get = (path: string) => {
    calls.push(path);
    if (!(path in answers)) return Promise.reject(new ApiError("Not found", 404, "NOT_FOUND"));
    const answer = answers[path];
    return answer instanceof Error ? Promise.reject(answer) : Promise.resolve(answer);
  };
  return { calls, get };
};

describe("saved AI result mapping", () => {
  it("reads each result out of the same envelope the run routes return", () => {
    expect(analysisFrom({ analysis, persisted: true })).toEqual(analysis);
    expect(hypothesisSetFrom({ hypothesis_set: hypothesisSet, persisted: true })).toEqual(hypothesisSet);
    expect(challengeSetFrom({ challenge_set: challengeSet, persisted: true })).toEqual(challengeSet);
    expect(unknownSetFrom({ unknown_set: unknownSet, persisted: true })).toEqual(unknownSet);
    expect(failureChainsFrom({ failure_chain_set: failureChainSet, persisted: true })).toEqual(failureChainSet);
    expect(briefFrom(brief)).toEqual(brief);
  });

  it("treats a missing or malformed payload as nothing saved", () => {
    expect(analysisFrom(null)).toBeNull();
    expect(analysisFrom({})).toBeNull();
    expect(analysisFrom({ analysis: "text" })).toBeNull();
    expect(hypothesisSetFrom([])).toBeNull();
    expect(briefFrom({ title: "No version" })).toBeNull();
    expect(briefFrom(undefined)).toBeNull();
  });

  it("shows the newest saved scenario with its status, and nothing when none is saved", () => {
    expect(counterfactualFrom([scenario("SUCCESS", "newest"), scenario("INSUFFICIENT_EVIDENCE", "older")])).toEqual({
      result: { label: "newest", invariants: [] },
      status: "SUCCESS",
    });
    expect(counterfactualFrom([{ id: "x", status: "", result: { label: "no status" } }])?.status).toBe("SUCCESS");
    expect(counterfactualFrom([])).toBeNull();
    expect(counterfactualFrom({ result: {} })).toBeNull();
    expect(counterfactualFrom([{ id: "x", status: "SUCCESS" }])).toBeNull();
  });
});

describe("loadSavedResults", () => {
  it("reads the latest result of every step and keeps the ids later steps build on", async () => {
    const { calls, get } = reader({
      [`${base}/analysis/latest?missing=empty`]: { analysis, persisted: true },
      [`${base}/hypotheses?missing=empty`]: { hypothesis_set: hypothesisSet, persisted: true },
      [`${base}/challenges?missing=empty`]: { challenge_set: challengeSet, persisted: true },
      [`${base}/unknowns?missing=empty`]: { unknown_set: unknownSet, persisted: true },
      [`${base}/failure-chains?missing=empty`]: { failure_chain_set: failureChainSet, persisted: true },
      [`${base}/briefs/latest?missing=empty`]: brief,
      [`${base}/counterfactuals`]: [scenario("SUCCESS", "newest")],
    });
    const saved = await loadSavedResults("inv-1", get);
    expect(calls.sort()).toEqual(
      [
        "analysis/latest?missing=empty",
        "briefs/latest?missing=empty",
        "challenges?missing=empty",
        "counterfactuals",
        "failure-chains?missing=empty",
        "hypotheses?missing=empty",
        "unknowns?missing=empty",
      ].map((path) => `${base}/${path}`),
    );
    // Generate Hypotheses sends the analysis on screen; the challenger sends the hypothesis set on screen.
    expect(saved.analysis?.analysis_id).toBe("a1");
    expect(saved.hypothesisSet?.hypothesis_set_id).toBe("h1");
    expect(saved.challengeSet).toEqual(challengeSet);
    expect(saved.unknownSet).toEqual(unknownSet);
    expect(saved.failureChains).toEqual(failureChainSet);
    expect(saved.brief?.brief_version).toBe(2);
    expect(saved.counterfactual?.status).toBe("SUCCESS");
    expect(hasSavedResults(saved)).toBe(true);
  });

  it("keeps the results it could read when others are missing, forbidden or failing", async () => {
    const { get } = reader({
      [`${base}/analysis/latest?missing=empty`]: { analysis, persisted: true },
      [`${base}/hypotheses?missing=empty`]: new ApiError("Forbidden", 403, "FORBIDDEN"),
      [`${base}/challenges?missing=empty`]: new ApiError("MDARIX could not be reached.", 0, "NETWORK_ERROR"),
      [`${base}/counterfactuals`]: [],
    });
    const saved = await loadSavedResults("inv-1", get);
    expect(saved.analysis).toEqual(analysis);
    expect(saved.hypothesisSet).toBeNull();
    expect(saved.challengeSet).toBeNull();
    expect(saved.unknownSet).toBeNull();
    expect(saved.failureChains).toBeNull();
    expect(saved.brief).toBeNull();
    expect(saved.counterfactual).toBeNull();
  });

  it("asks for nothing-saved answers as 200, and leaves out the parked counterfactual under mvp (UX-15)", async () => {
    const { calls, get } = reader({
      // What the server answers with ?missing=empty for a step never run (backend/app/saved_results.py).
      [`${base}/analysis/latest?missing=empty`]: { analysis: null, persisted: false },
      [`${base}/hypotheses?missing=empty`]: { hypothesis_set: null, persisted: false },
      [`${base}/challenges?missing=empty`]: { challenge_set: null, persisted: false },
      [`${base}/unknowns?missing=empty`]: { unknown_set: null, persisted: false },
      [`${base}/failure-chains?missing=empty`]: { failure_chain_set: null, persisted: false },
      [`${base}/briefs/latest?missing=empty`]: { brief: null, persisted: false },
    });
    const saved = await loadSavedResults("inv-1", get, { counterfactuals: false });
    expect(calls).toHaveLength(6);
    expect(calls.some((path) => path.includes("counterfactuals"))).toBe(false);
    expect(calls.every((path) => path.endsWith("?missing=empty"))).toBe(true);
    expect(hasSavedResults(saved)).toBe(false);
  });

  it("reports nothing saved for a case with no AI runs yet", async () => {
    const saved = await loadSavedResults("inv-1", reader({}).get);
    expect(Object.values(saved).every((value) => value === null)).toBe(true);
    expect(hasSavedResults(saved)).toBe(false);
  });
});
