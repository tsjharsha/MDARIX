import { useState } from "react";
import { Panel, ToneBadge, type PanelSource } from "../../admin/console/charts";
import { ConfirmDialog, formatDate, send, useResource, type Confirmation } from "../../customer-admin/shared";
import { accessText, areaNames, supportStatus, type SupportGrant } from "../../customer-admin/supportAccessModel";

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
        `${accessText(grant.write)} access to ${areaNames(grant.areas).toLowerCase()} until ${formatDate(grant.expires_at)}. ` +
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
  return (
    <>
      <SupportAccessView
        grants={grants.data?.items ?? []}
        source={grants}
        notice={notice}
        onDecide={(decision, grant) => {
          setNotice("");
          setConfirm(supportConfirmation(decision, grant, grants.reload));
        }}
      />
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
}: {
  grants: SupportGrant[];
  source: PanelSource;
  notice: string;
  onDecide: (decision: SupportDecision, grant: SupportGrant) => void;
}) {
  const waiting = grants.filter((grant) => grant.can_approve || grant.can_deny).length;
  return (
    <Panel title="Support access" eyebrow={waiting ? `${waiting} waiting for you` : "MDARIX support"} source={source}>
      <p className="uw-trial-note">
        MDARIX support never sees your trial's data unless you approve it here: only the areas named, read-only unless
        you allow changes, and only until the time shown.
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
                    {accessText(grant.write)} until {formatDate(grant.expires_at)} · {grant.reason}
                  </small>
                  {grant.decided_by && <small>Decided by {grant.decided_by}</small>}
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
