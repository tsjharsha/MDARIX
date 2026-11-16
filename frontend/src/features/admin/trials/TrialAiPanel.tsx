import { useState } from "react";
import { Sparkles } from "lucide-react";
import { Panel, ToneBadge } from "../console/charts";
import { errorText, send, useResource } from "../../customer-admin/shared";
import "../../shared/statement-kind.css";
import "./trialAi.css";
import { TrialAiMetrics } from "./TrialAiMetrics";

/*
 * Part 4 of Trial organizations (TO-1 spec 3.6.1): AI per trial and the per-person AI switch, as one self-contained
 * panel for the slot `data-slot="trial-ai"` on a trial's page (`TrialDetail.tsx`, passed to `TrialOrganizations` as
 * `trialAiPanel`). Only a Platform Administrator reaches it; the server checks that again on every change and audits
 * each one (TRIAL_USER_AI_ACCESS_CHANGED). A person has AI only when the trial switched AI on AND their switch is Active.
 */

export const AI_ACCESS_REASON_MIN = 10;

export type TrialAiPerson = { user_id: string; display_name: string | null; active: boolean };
export type TrialAiAccessList = { organization_on: boolean; trial_chain_on: boolean; items: TrialAiPerson[] };

const trialPath = (tenantId: string) => `/api/v1/platform-admin/trial-organizations/${encodeURIComponent(tenantId)}`;
export const aiAccessPath = (tenantId: string) => `${trialPath(tenantId)}/users/ai-access`;

/** The people a change to `target` would change (unchanged people are not sent, so nothing is audited for them). */
export const peopleToChange = (people: TrialAiPerson[], target: boolean, only?: string) =>
  people.filter((person) => person.active !== target && (!only || person.user_id === only));

export function aiAccessReasonProblem(reason: string): string | null {
  return reason.trim().length >= AI_ACCESS_REASON_MIN
    ? null
    : `Give a reason of at least ${AI_ACCESS_REASON_MIN} characters; it is kept in the trial's audit trail.`;
}

/** The request for a change: one user (single route) or everyone in the trial (bulk route). */
export function aiAccessRequest(tenantId: string, target: boolean, reason: string, only?: string) {
  const body = { active: target, reason: reason.trim() };
  return only
    ? { path: `${trialPath(tenantId)}/users/${encodeURIComponent(only)}/ai-access`, body }
    : { path: `${trialPath(tenantId)}/ai-access`, body };
}

type Pending = { target: boolean; only?: string };

export function TrialAiPanel({
  detail,
  onChanged,
}: {
  detail: { tenant_id: string; ai?: { line?: string | null } | null };
  onChanged: () => void;
}) {
  const list = useResource<TrialAiAccessList>(aiAccessPath(detail.tenant_id));
  const people = list.data?.items ?? [];
  const [pending, setPending] = useState<Pending | null>(null);
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const changing = pending ? peopleToChange(people, pending.target, pending.only) : [];
  const open = (next: Pending) => {
    setPending(next);
    setReason("");
    setProblem(null);
  };
  const save = async () => {
    if (!pending) return;
    const reasonProblem = aiAccessReasonProblem(reason);
    if (reasonProblem) return setProblem(reasonProblem);
    if (!changing.length) return setPending(null);
    const request = aiAccessRequest(detail.tenant_id, pending.target, reason, pending.only);
    setBusy(true);
    try {
      await send(request.path, "PUT", request.body);
      setPending(null);
      list.reload();
      onChanged();
    } catch (error) {
      setProblem(errorText(error, "The AI switch could not be changed."));
    } finally {
      setBusy(false);
    }
  };
  const word = (target: boolean) => (target ? "Active" : "Inactive");
  return (
    <>
      {/* The server's own line about AI for this trial, shown even while the people are read. */}
      {detail.ai?.line && (
        <p className="to-ai" role="note">
          <Sparkles size={14} aria-hidden="true" /> {detail.ai.line}
        </p>
      )}
      <Panel eyebrow="AI and usage" title="AI for this trial" source={list}>
        {list.data && !list.data.organization_on && (
          <p className="ac-note" role="status">
            The organization has not switched AI on: no user has AI, whatever these switches say.
          </p>
        )}
        {list.data && !list.data.trial_chain_on && (
          <p className="ac-muted">
            MDARIX has not set the AI services for free trials, so AI stays off for every trial.
          </p>
        )}
        <div className="ca-row-actions">
          <button
            type="button"
            className="ac-secondary"
            disabled={!people.length}
            onClick={() => open({ target: true })}
          >
            Set all Active
          </button>
          <button
            type="button"
            className="ac-secondary"
            disabled={!people.length}
            onClick={() => open({ target: false })}
          >
            Set all Inactive
          </button>
        </div>
        <ul className="to-ai-people" aria-label="AI per person">
          {people.map((person) => (
            <li key={person.user_id}>
              <span>{person.display_name || "Unnamed person"}</span>
              <ToneBadge tone={person.active ? "good" : "neutral"} label={`AI: ${word(person.active)}`} />
              <button
                type="button"
                className="ac-secondary"
                aria-label={`Set ${person.display_name || "this person"} ${word(!person.active)}`}
                onClick={() => open({ target: !person.active, only: person.user_id })}
              >
                Set {word(!person.active)}
              </button>
            </li>
          ))}
        </ul>
        {pending && (
          <div className="ai-review-form" role="dialog" aria-label="Change AI access">
            <p>
              {changing.length
                ? `${changing.length} ${changing.length === 1 ? "person" : "people"} will be set ${word(pending.target)}.`
                : `Everyone is already ${word(pending.target)}; nothing will change.`}
            </p>
            <label>
              Reason (kept in the trial&apos;s audit trail)
              <input value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
            <span className="ca-row-actions">
              <button type="button" className="ac-primary" disabled={busy} onClick={() => void save()}>
                Set {word(pending.target)}
              </button>
              <button type="button" className="ac-secondary" disabled={busy} onClick={() => setPending(null)}>
                Cancel
              </button>
            </span>
            {problem && (
              <p className="ac-error" role="alert">
                {problem}
              </p>
            )}
          </div>
        )}
      </Panel>
      <div id="trial-ai-metrics">
        <TrialAiMetrics tenantId={detail.tenant_id} />
      </div>
    </>
  );
}

/** The panel in the form `TrialOrganizations` takes (`trialAiPanel={trialAiPanel}`). */
export const trialAiPanel = (props: {
  detail: { tenant_id: string; ai?: { line?: string | null } | null };
  onChanged: () => void;
}) => <TrialAiPanel {...props} />;
