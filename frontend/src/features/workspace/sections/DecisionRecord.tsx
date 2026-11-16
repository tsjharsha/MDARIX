import { useState } from "react";
import { ToneBadge } from "../../admin/console/charts";
import { Drawer, formatDate, listOf, useResource } from "../../customer-admin/shared";
import { safeText } from "../../../app/displayId";
import { roleNote } from "../../../app/roles";
import { shortHash } from "../decisionBrief";
import {
  decisionRecordPath,
  decisionRef,
  hashState,
  outcomeLabel,
  outcomeTone,
  verificationChecks,
  verificationHeadline,
  verificationView,
} from "../humanDecision";
import {
  followUpAssignee,
  followUpCapaText,
  followUpStatusView,
  followUpTypeLabel,
  type FollowUp,
} from "../afterDecision";
import { CaseStoryLink } from "./CaseStoryLink";
import { SignatureBasis } from "../../shared/Basis";

const record = (value: unknown): Record<string, any> =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, any>) : {};

/** A fingerprint shown short, with the whole value on hover and for screen readers. */
export function Fingerprint({ value }: { value: unknown }) {
  const full = typeof value === "string" ? value : "";
  return full ? (
    <code className="ca-mono-sm" title={full} aria-label={full}>
      {shortHash(full)}
    </code>
  ) : (
    <>—</>
  );
}

/**
 * The signed record of a decision (GET /api/v1/decisions/{id}/record): its outcome, conditions and follow-ups, who
 * signed it with which role and when, the meaning of the signature, the fingerprints, the verification checks (Valid,
 * or Invalid with the checks that failed), the evidence snapshot, and the decisions it supersedes or that superseded it.
 * Inside the workspace it links to the case's full story in Trust & Audit (`showCaseStory`, on by default).
 */
export function DecisionRecordDrawer({
  decisionId,
  onClose,
  showCaseStory = true,
}: {
  decisionId: string;
  onClose: () => void;
  showCaseStory?: boolean;
}) {
  // A supersede link opens that decision's record in the same drawer.
  const [shown, setShown] = useState(decisionId);
  const data = useResource<Record<string, unknown>>(decisionRecordPath(shown));
  const body = data.data ?? {};
  const decision = record(body.decision);
  const brief = record(body.brief);
  const signature = record(body.signature);
  const verification = record(body.verification);
  const snapshot = record(body.snapshot);
  const followUps = listOf(body.follow_ups) as FollowUp[];
  const checks = verificationChecks(verification.checks);
  const status = verificationView(verification.status);
  const supersedes = decisionRef(body.supersedes ?? decision.supersedes, decision.supersedes_decision_id);
  const supersededBy = decisionRef(body.superseded_by ?? decision.superseded_by, decision.superseded_by_decision_id);
  const hash = hashState(brief);
  const name = safeText(decision.business_id) ?? "Decision";
  return (
    <Drawer title={`Signed record: ${data.data ? name : "decision"}`} onClose={onClose}>
      {data.state === "loading" && !data.data && <p className="ac-muted">Loading the signed record…</p>}
      {(data.state === "error" || data.state === "forbidden") && (
        <p className="ca-inline-error" role="alert">
          {data.state === "forbidden"
            ? "Your role cannot read this signed record."
            : (data.error ?? "The signed record could not be loaded.")}
        </p>
      )}
      {data.data && (
        <>
          <section className="ca-drawer-section" aria-label="Verification">
            <h3>Verification</h3>
            <p>
              <ToneBadge tone={status.tone} label={status.label} />
            </p>
            {String(verification.status ?? "").toUpperCase() === "INVALID" && (
              <p className="ac-message tone-critical" role="alert">
                {verificationHeadline(verification.status, checks)}
              </p>
            )}
            {checks.length > 0 ? (
              <ul className="uw-checklist" aria-label="Verification checks">
                {checks.map((check) => (
                  <li key={check.key}>
                    <ToneBadge tone={check.ok ? "good" : "critical"} label={check.ok ? "Pass" : "Failed"} />
                    <span>
                      <strong>{check.label}</strong>
                      {check.detail && <small>{check.detail}</small>}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="ac-muted">No verification checks reported.</p>
            )}
          </section>
          <section className="ca-drawer-section" aria-label="Decision">
            <h3>Decision</h3>
            <dl className="ca-facts">
              <div>
                <dt>Decision ID</dt>
                <dd>{name}</dd>
              </div>
              <div>
                <dt>Outcome</dt>
                <dd>
                  <ToneBadge
                    tone={outcomeTone(decision.outcome)}
                    label={outcomeLabel(decision.outcome, decision.outcome_label)}
                  />
                </dd>
              </div>
              <div>
                <dt>Decided</dt>
                <dd>{formatDate(decision.decided_at ?? signature.signed_at)}</dd>
              </div>
              <div>
                <dt>Brief</dt>
                <dd>
                  {safeText(brief.business_id) ?? "—"}
                  {brief.version !== undefined && brief.version !== null ? ` · version ${brief.version}` : ""}
                </dd>
              </div>
              <div>
                <dt>Brief fingerprint</dt>
                <dd>
                  <Fingerprint value={brief.content_hash} /> <ToneBadge tone={hash.tone} label={hash.label} />
                </dd>
              </div>
            </dl>
            {safeText(decision.conditions) && (
              <>
                <h3>Conditions</h3>
                <p className="uw-intel-statement">{decision.conditions}</p>
              </>
            )}
            {safeText(decision.rationale) && (
              <>
                <h3>Rationale of the decision maker</h3>
                <p className="uw-intel-statement">{decision.rationale}</p>
              </>
            )}
            <h3>Root-cause attribution</h3>
            <p className="uw-intel-statement">
              {safeText(decision.root_cause_attribution_label) ??
                safeText(decision.attribution_note) ??
                "Recorded before root-cause attribution"}
              {safeText(decision.attribution_reason) ? `: ${decision.attribution_reason}` : ""}
            </p>
            <h3>Confirmed root-cause category</h3>
            <p className="uw-intel-statement">
              {safeText(decision.root_cause_category_label) ?? "Not categorised"}
              {Array.isArray(decision.root_cause_hypothesis_ids) && decision.root_cause_hypothesis_ids.length
                ? ` (${decision.root_cause_hypothesis_ids.length} accepted ${
                    decision.root_cause_hypothesis_ids.length === 1 ? "hypothesis" : "hypotheses"
                  })`
                : ""}
            </p>
          </section>
          <section className="ca-drawer-section" aria-label="Signature">
            <h3>Signature</h3>
            <dl className="ca-facts">
              <div>
                <dt>Signature ID</dt>
                <dd>{safeText(signature.business_id) ?? "—"}</dd>
              </div>
              <div>
                <dt>Signed by</dt>
                <dd>
                  {safeText(signature.signer_name) ?? "—"}
                  {safeText(signature.signer_role) ? roleNote(signature.signer_role) : ""}
                </dd>
              </div>
              <div>
                <dt>Signed</dt>
                <dd>{formatDate(signature.signed_at)}</dd>
              </div>
              <div>
                <dt>Fingerprint</dt>
                <dd>
                  <Fingerprint value={signature.fingerprint} />
                </dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>
                  {safeText(signature.status_label) ?? (safeText(signature.status) ? String(signature.status) : "—")}
                </dd>
              </div>
            </dl>
            {safeText(signature.signature_meaning) && (
              <p className="ca-note-box">
                <strong>Meaning of the signature: </strong>
                {signature.signature_meaning}
              </p>
            )}
            <SignatureBasis />
          </section>
          <section className="ca-drawer-section" aria-label="Follow-up actions">
            <h3>Follow-up actions</h3>
            {followUps.length ? (
              <ul className="uw-intel-list">
                {followUps.map((item, index) => {
                  const view = followUpStatusView(item);
                  const capa = followUpCapaText(item);
                  return (
                    <li key={String(item.id ?? index)}>
                      <strong>{safeText(item.business_id) ?? "Follow-up"}</strong> · {followUpTypeLabel(item)}
                      {safeText(item.title) ? ` · ${item.title}` : ""} ·{" "}
                      <ToneBadge tone={view.tone} label={view.label} />
                      <small className="ac-muted">
                        {" "}
                        · {followUpAssignee(item)}
                        {item.due_at ? ` · due ${formatDate(item.due_at)}` : ""}
                        {capa ? ` · CAPA ${capa}` : ""}
                      </small>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="ac-muted">No follow-up actions were required.</p>
            )}
          </section>
          <section className="ca-drawer-section" aria-label="Evidence snapshot">
            <h3>Evidence snapshot</h3>
            {Object.keys(snapshot).length ? (
              <dl className="ca-facts">
                {safeText(snapshot.business_id) && (
                  <div>
                    <dt>Snapshot ID</dt>
                    <dd>{snapshot.business_id}</dd>
                  </div>
                )}
                <div>
                  <dt>Taken</dt>
                  <dd>{formatDate(snapshot.created_at)}</dd>
                </div>
                <div>
                  <dt>Scope version</dt>
                  <dd>{snapshot.scope_version ?? "—"}</dd>
                </div>
                <div>
                  <dt>Evidence fingerprint</dt>
                  <dd>
                    <Fingerprint value={snapshot.evidence_set_hash} />
                  </dd>
                </div>
              </dl>
            ) : (
              <p className="ac-muted">No evidence snapshot recorded with this decision.</p>
            )}
          </section>
          {(supersedes || supersededBy) && (
            <section className="ca-drawer-section" aria-label="Superseding">
              <h3>Superseding</h3>
              {supersededBy && (
                <p>
                  Superseded by{" "}
                  {supersededBy.id ? (
                    <button type="button" className="ac-link" onClick={() => setShown(String(supersededBy.id))}>
                      {supersededBy.label}
                    </button>
                  ) : (
                    supersededBy.label
                  )}
                  . This signed record is kept unchanged.
                </p>
              )}
              {supersedes && (
                <p>
                  Supersedes{" "}
                  {supersedes.id ? (
                    <button type="button" className="ac-link" onClick={() => setShown(String(supersedes.id))}>
                      {supersedes.label}
                    </button>
                  ) : (
                    supersedes.label
                  )}
                  .
                </p>
              )}
            </section>
          )}
          {shown !== decisionId && (
            <div className="ca-action-row">
              <button type="button" className="ac-secondary" onClick={() => setShown(decisionId)}>
                Back to the first record
              </button>
            </div>
          )}
          {showCaseStory && typeof decision.investigation_id === "string" && (
            <div className="ca-action-row">
              <CaseStoryLink
                investigationId={decision.investigation_id}
                caseLabel={safeText(decision.investigation_business_id)}
              />
            </div>
          )}
        </>
      )}
    </Drawer>
  );
}
