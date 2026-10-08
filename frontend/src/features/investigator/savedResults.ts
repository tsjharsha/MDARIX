import type {
  ChallengeSet,
  FailureChainSet,
  HypothesisSet,
  InvestigationAnalysis,
  InvestigationBrief,
  UnknownSet,
} from "../../app/types";

/** A saved scenario result and the status it finished with, as the counterfactual panel shows it. */
export type SavedCounterfactual = { result: Record<string, any>; status: string };

/**
 * The latest saved AI results for one investigation, in the shapes the workspace panel renders. Each is null when
 * nothing is saved yet or it could not be read, so one missing or forbidden result never hides the others.
 */
export type SavedResults = {
  analysis: InvestigationAnalysis | null;
  hypothesisSet: HypothesisSet | null;
  challengeSet: ChallengeSet | null;
  unknownSet: UnknownSet | null;
  failureChains: FailureChainSet | null;
  brief: InvestigationBrief | null;
  counterfactual: SavedCounterfactual | null;
};

const isObject = (value: unknown): value is Record<string, any> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

// The read routes answer with the same envelope as the run routes ({analysis: ...}, {hypothesis_set: ...}, ...).
const field = <T>(payload: unknown, key: string): T | null =>
  isObject(payload) && isObject(payload[key]) ? (payload[key] as T) : null;

export const analysisFrom = (payload: unknown) => field<InvestigationAnalysis>(payload, "analysis");
export const hypothesisSetFrom = (payload: unknown) => field<HypothesisSet>(payload, "hypothesis_set");
export const challengeSetFrom = (payload: unknown) => field<ChallengeSet>(payload, "challenge_set");
export const unknownSetFrom = (payload: unknown) => field<UnknownSet>(payload, "unknown_set");
export const failureChainsFrom = (payload: unknown) => field<FailureChainSet>(payload, "failure_chain_set");

/** The latest brief route returns the brief itself, like the generate route. */
export const briefFrom = (payload: unknown): InvestigationBrief | null =>
  isObject(payload) && typeof payload.brief_version === "number" ? (payload as InvestigationBrief) : null;

/** The scenario list comes newest first; the panel shows the newest one, like after a run. */
export function counterfactualFrom(payload: unknown): SavedCounterfactual | null {
  if (!Array.isArray(payload) || !payload.length) return null;
  const latest = payload[0];
  if (!isObject(latest) || !isObject(latest.result)) return null;
  return {
    result: latest.result,
    status: typeof latest.status === "string" && latest.status ? latest.status : "SUCCESS",
  };
}

export const hasSavedResults = (saved: SavedResults) => Object.values(saved).some(Boolean);

/**
 * Read the latest saved result of every AI step in parallel. Reading never runs AI again. A step with nothing
 * saved (404), one the role may not read, or one that fails to load simply comes back empty.
 */
export async function loadSavedResults(
  investigationId: string,
  get: (path: string) => Promise<unknown>,
): Promise<SavedResults> {
  const base = `/api/v1/investigations/${investigationId}`;
  const read = <T>(path: string, map: (payload: unknown) => T | null): Promise<T | null> =>
    get(`${base}/${path}`).then(map, () => null);
  const [analysis, hypothesisSet, challengeSet, unknownSet, failureChains, brief, counterfactual] = await Promise.all([
    read("analysis/latest", analysisFrom),
    read("hypotheses", hypothesisSetFrom),
    read("challenges", challengeSetFrom),
    read("unknowns", unknownSetFrom),
    read("failure-chains", failureChainsFrom),
    read("briefs/latest", briefFrom),
    read("counterfactuals", counterfactualFrom),
  ]);
  return { analysis, hypothesisSet, challengeSet, unknownSet, failureChains, brief, counterfactual };
}
