import { useState } from "react";
import { Sparkles } from "lucide-react";
import { Panel, ToneBadge } from "../console/charts";
import { errorText, send, useResource } from "../../customer-admin/shared";
import "../../shared/statement-kind.css";
import "./trialAi.css";

/*
 * Part 4 of Trial organizations (TO-1 spec 3.6.1): AI per trial and the per-person AI switch, as one self-contained
 * panel for the slot `data-slot="trial-ai"` on a trial's page (`TrialDetail.tsx`, passed to `TrialOrganizations` as
 * `trialAiPanel`). Only a Platform Administrator reaches it; the server checks that again on every change and audits
 * each one (AI_USER_ACCESS_CHANGED). A person has AI only when the trial switched AI on AND their switch is Active.
 */

export const AI_ACCESS_REASON_MIN = 10;

export type AiAccess = "ACTIVE" | "INACTIVE";
export type TrialAiPerson = { user_id: string; display_name: string | null; ai_access: AiAccess };
export type TrialAiAccessList = { organization_on: boolean; trial_chain_on: boolean; items: TrialAiPerson[] };

export const aiAccessPath = (tenantId: string) =>
  `/api/v1/platform-admin/tenants/${encodeURIComponent(tenantId)}/users/ai-access`;

/** The people a change to `target` would change (unchanged people are not sent, so nothing is audited for them). */
export const peopleToChange = (people: TrialAiPerson[], target: AiAccess, only?: string) =>
  people.filter((person) => person.ai_access !== target && (!only || person.user_id === only));

export function aiAccessReasonProblem(reason: string): string | null {
  return reason.trim().length >= AI_ACCESS_REASON_MIN
    ? null
    : `Give a reason of at least ${AI_ACCESS_REASON_MIN} characters; it is kept in the trial's audit trail.`;
}

/** The request for a change: one person (single route) or several (bulk route). */
export function aiAccessRequest(tenantId: string, changing: TrialAiPerson[], target: AiAccess, reason: string) {
  const body = { ai_access: target, reason: reason.trim() };
  return changing.length === 1
    ? {
        path: `/api/v1/platform-admin/tenants/${encodeURIComponent(tenantId)}/users/${encodeURIComponent(changing[0].user_id)}/ai-access`,
        body,
      }
    : { path: aiAccessPath(tenantId), body: { ...body, user_ids: changing.map((person) => person.user_id) } };
}

type Pending = { target: AiAccess; only?: string };

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
    const request = aiAccessRequest(detail.tenant_id, changing, pending.target, reason);
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
  const word = (target: AiAccess) => (target === "ACTIVE" ? "Active" : "Inactive");
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
            onClick={() => open({ target: "ACTIVE" })}
          >
            Set all Active
          </button>
          <button
            type="button"
            className="ac-secondary"
            disabled={!people.length}
            onClick={() => open({ target: "INACTIVE" })}
          >
            Set all Inactive
          </button>
        </div>
        <ul className="to-ai-people" aria-label="AI per person">
          {people.map((person) => (
            <li key={person.user_id}>
              <span>{person.display_name || "Unnamed person"}</span>
              <ToneBadge
                tone={person.ai_access === "ACTIVE" ? "good" : "neutral"}
                label={`AI: ${word(person.ai_access)}`}
              />
              <button
                type="button"
                className="ac-secondary"
                aria-label={`Set ${person.display_name || "this person"} ${person.ai_access === "ACTIVE" ? "Inactive" : "Active"}`}
                onClick={() =>
                  open({ target: person.ai_access === "ACTIVE" ? "INACTIVE" : "ACTIVE", only: person.user_id })
                }
              >
                {person.ai_access === "ACTIVE" ? "Set Inactive" : "Set Active"}
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
    </>
  );
}

/** The panel in the form `TrialOrganizations` takes (`trialAiPanel={trialAiPanel}`). */
export const trialAiPanel = (props: {
  detail: { tenant_id: string; ai?: { line?: string | null } | null };
  onChanged: () => void;
}) => <TrialAiPanel {...props} />;
