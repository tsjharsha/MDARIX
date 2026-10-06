// Where a case's Decision view opens (Phase 6): the "Decision" tab of Investigations (and of Decisions), optionally on
// one follow-up action or one impact assessment ("Decision?follow_up=…", "Decision?assessment=…"), or for a case
// chosen outside the context bar ("Decision?case=…", from the approvals queue). Kept free of other imports so the task
// rules can use it without an import cycle.

export const DECISION_TAB = "Decision";

// A record reference as it may travel in a tab name; anything else is ignored.
const REF = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

export type DecisionTabTarget = { followUp: string | null; assessment: string | null; caseId: string | null };

const valid = (value: string | null | undefined) => {
  const text = String(value ?? "").trim();
  return REF.test(text) ? text : null;
};

/** The Decision tab, opened on a follow-up, an impact assessment or a case when a valid reference is given. */
export function decisionTab(
  target: { followUp?: string | null; assessment?: string | null; caseId?: string | null } = {},
): string {
  const params = new URLSearchParams();
  const followUp = valid(target.followUp);
  const assessment = valid(target.assessment);
  const caseId = valid(target.caseId);
  if (caseId) params.set("case", caseId);
  if (followUp) params.set("follow_up", followUp);
  else if (assessment) params.set("assessment", assessment);
  const query = params.toString();
  return query ? `${DECISION_TAB}?${query}` : DECISION_TAB;
}

/** What a tab name passed to Investigations or Decisions asks the Decision tab to open (see decisionTab). */
export function parseDecisionTab(value: string | null | undefined): DecisionTabTarget {
  const none = { followUp: null, assessment: null, caseId: null };
  const text = String(value ?? "");
  const mark = text.indexOf("?");
  if (mark < 0 || text.slice(0, mark) !== DECISION_TAB) return none;
  const params = new URLSearchParams(text.slice(mark + 1));
  return {
    followUp: valid(params.get("follow_up")),
    assessment: valid(params.get("assessment")),
    caseId: valid(params.get("case")),
  };
}

/** The tab part of a tab name ("Decision?follow_up=…" is the Decision tab). */
export const tabName = (value: string | null | undefined) => {
  const text = String(value ?? "");
  const mark = text.indexOf("?");
  return mark < 0 ? text : text.slice(0, mark);
};
