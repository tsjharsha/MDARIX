import { useState } from "react";
import { Panel, ToneBadge, type PanelSource } from "../../admin/console/charts";
import { ConfirmDialog, formatDate, send, useResource, type Confirmation } from "../../customer-admin/shared";
import {
  accessText,
  areaDetails,
  areaNames,
  supportStatus,
  type SupportActivity,
  type SupportGrant,
} from "../../customer-admin/supportAccessModel";

export const TRIAL_SUPPORT_PATH = "/api/v1/trial/support-access";
const REASON = { label: "Reason (kept in your audit trail)", min: 10 };

export type SupportDecision = "approve" | "deny" | "revoke";

/** What the trial owner can decide on one request: approve or deny one waiting, revoke one that is active. */
export function supportDecisions(grant: SupportGrant): SupportDecision[] {
  const decisions: SupportDecision[] = [];
  if (grant.can_approve) decisions.push("approve");
  if (grant.can_deny) decisions.push("deny");
  if (grant.can_revoke && !grant.can_deny) decisions.push("revoke");
  return decisions;
}

/** The confirmation of one decision, as a customer's administrators confirm it (approving needs the owner's code). */
export function supportConfirmation(decision: SupportDecision, grant: SupportGrant, onDone: () => void): Confirmation {
  const who = grant.person ?? "MDARIX support";
  const path = `${TRIAL_SUPPORT_PATH}/${grant.id}/${decision}`;
  if (decision === "approve")
    return {
      title: `Give ${who} access?`,
      body:
        `${accessText(grant.write)} access until ${formatDate(grant.expires_at)}, to: ${areaDetails(grant.areas)}. ` +
        "Every use is recorded in your audit trail, and you can revoke it at any time.",
      confirmLabel: "Approve",
      reason: REASON,
      mfaCode: true,
      done: "Access approved. MDARIX support has been told.",
      run: async (reason, _password, _acknowledged, mfaCode) => {
        await send(path, "POST", { reason, mfa_code: mfaCode || undefined });
        onDone();
      },
    };
  if (decision === "deny")
    return {
      title: "Deny this request?",
      body: "MDARIX support gets no access. They can ask again with a new request.",
      confirmLabel: "Deny",
      reason: REASON,
      done: "Request denied.",
      run: async (reason) => {
        await send(path, "POST", { reason });
        onDone();
      },
    };
  return {
    title: `End ${who}'s access now?`,
    body: "The access ends immediately, whatever time it had left.",
    confirmLabel: "Revoke",
    danger: true,
    reason: REASON,
    done: "Access revoked.",
    run: async (reason) => {
      await send(path, "POST", { reason });
      onDone();
    },
  };
}

const LABEL: Record<SupportDecision, string> = { approve: "Approve", deny: "Deny", revoke: "Revoke" };

/**
 * Getting started › Team, for the trial owner: the support access MDARIX asks for. A trial has no Customer
 * Administrators, so its owner approves, denies or revokes it, under the same rules (backend/app/support_access_api.py).
 */
export function TrialSupportAccess() {
  const grants = useResource<{ items: SupportGrant[]; awaiting_decision: number }>(TRIAL_SUPPORT_PATH);
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [notice, setNotice] = useState("");
  const [history, setHistory] = useState<string | null>(null);
  return (
    <>
      <SupportAccessView
        grants={grants.data?.items ?? []}
        source={grants}
        notice={notice}
        history={history}
        onHistory={(grant) => setHistory(history === grant.id ? null : grant.id)}
        onDecide={(decision, grant) => {
          setNotice("");
          setConfirm(supportConfirmation(decision, grant, grants.reload));
        }}
      />
      {history && <TrialSupportHistory grantId={history} />}
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(text) => {
          setConfirm(null);
          setNotice(text);
        }}
      />
    </>
  );
}

/** The requests as the server sent them (separate from the request, so it renders on its own in tests). */
export function SupportAccessView({
  grants,
  source,
  notice,
  onDecide,
  history = null,
  onHistory,
}: {
  grants: SupportGrant[];
  source: PanelSource;
  notice: string;
  onDecide: (decision: SupportDecision, grant: SupportGrant) => void;
  /** The request whose history is open, if any. */
  history?: string | null;
  onHistory?: (grant: SupportGrant) => void;
}) {
  const waiting = grants.filter((grant) => grant.can_approve || grant.can_deny).length;
  return (
    <Panel title="Support access" eyebrow={waiting ? `${waiting} waiting for you` : "MDARIX support"} source={source}>
      <p className="uw-trial-note">
        MDARIX support never sees your trial's data unless you approve it here: only the areas named, read-only unless
        you allow changes, and only until the time shown. Only you decide; your colleagues cannot. Every page MDARIX
        opens is in the history of the request.
      </p>
      {grants.length ? (
        <ul className="uw-support">
          {grants.map((grant) => {
            const status = supportStatus(grant);
            return (
              <li key={grant.id}>
                <div>
                  <strong>
                    {grant.person ?? "MDARIX support"}: {areaNames(grant.areas)}
                  </strong>
                  <small>
                    {accessText(grant.write)} · from {formatDate(grant.starts_at)} until {formatDate(grant.expires_at)}{" "}
                    ({durationText(grant.starts_at, grant.expires_at)})
                  </small>
                  <small>Areas: {areaDetails(grant.areas)}</small>
                  <small>Why: {grant.reason}</small>
                  {grant.decided_by && <small>Decided by {grant.decided_by}</small>}
                  {grant.uses > 0 && <small>Used {grant.uses === 1 ? "once" : `${grant.uses} times`}</small>}
                </div>
                <ToneBadge tone={status.tone} label={status.label} />
                {supportDecisions(grant).map((decision) => (
                  <button
                    key={decision}
                    type="button"
                    className={decision === "revoke" ? "ac-link uw-team-danger" : "ac-link"}
                    onClick={() => onDecide(decision, grant)}
                  >
                    {LABEL[decision]}
                  </button>
                ))}
                {onHistory && (
                  <button
                    type="button"
                    className="ac-link"
                    aria-expanded={history === grant.id}
                    onClick={() => onHistory(grant)}
                  >
                    {history === grant.id ? "Hide history" : "History"}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="uw-trial-note">When MDARIX support asks for access to your trial, the request appears here.</p>
      )}
      {notice && (
        <div className="uw-trial-message is-good" role="status">
          <span>{notice}</span>
        </div>
      )}
    </Panel>
  );
}

/** How long a request lasts, in hours ("4 hours"), from its start and end. */
export function durationText(starts?: string | null, expires?: string | null): string {
  if (!starts || !expires) return "time not set";
  const hours = Math.round((new Date(expires).getTime() - new Date(starts).getTime()) / 3_600_000);
  if (hours < 1) return "less than an hour";
  return hours === 1 ? "1 hour" : `${hours} hours`;
}

/** One request's life, from the trial's own audit trail: who asked, the decision, each page read, each export, the end. */
function TrialSupportHistory({ grantId }: { grantId: string }) {
  const activity = useResource<{ items: SupportActivity[] }>(`${TRIAL_SUPPORT_PATH}/${grantId}/activity`);
  return <SupportHistoryView items={activity.data?.items ?? []} source={activity} />;
}

export function SupportHistoryView({ items, source }: { items: SupportActivity[]; source: PanelSource }) {
  return (
    <Panel title="History of this access" eyebrow="From your trial's audit trail" source={source}>
      {items.length ? (
        <ol className="uw-support-history">
          {items.map((item, index) => (
            <li key={`${item.at}-${index}`}>
              <strong>{item.what ?? item.action}</strong>
              <small>
                {item.who ?? "MDARIX"} · {formatDate(item.at)}
              </small>
              {item.covers && <small>{item.covers}</small>}
              {item.reason && <small>{item.reason}</small>}
            </li>
          ))}
        </ol>
      ) : (
        <p className="uw-trial-note">The request, your decision and every use will appear here.</p>
      )}
    </Panel>
  );
}
