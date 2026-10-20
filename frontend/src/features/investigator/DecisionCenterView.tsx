import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, CircleDot, ClipboardList, FileText, GitBranch, Network, ShieldCheck } from "lucide-react";
import { Panel } from "../../app/ui";
import { TemporalMode, DecisionContext } from "../../app/types";
import { api } from "../../app/api";
import { AI_TIMEOUT_MS, ApiError, describeError, isUnreachable, postJson, requestJson } from "../../app/apiClient";
import { formatDateTime } from "../../app/dates";
import { useCan, useCanRunAi } from "../workspace/workspaceContext";
import { displayId, safeText } from "../../app/displayId";
import { titleCase } from "../admin/console/dashboardModel";
import { Table, formatDate, idColumn } from "../customer-admin/shared";

/** What the signed-in user may do with a decision, worked out by the server with the review and sign rules. */
export type DecisionActions = {
  can_review: boolean;
  can_approve: boolean;
  can_sign: boolean;
  reason?: string | null;
};

/** A decision of the investigation, as the decision list returns it. */
export type DecisionRow = {
  id: string;
  business_id?: string | null;
  decision_identifier?: string | null;
  decision_status?: string | null;
  selected_action?: string | null;
  authorized_by_name?: string | null;
  decision_timestamp?: string | null;
  updated_at?: string | null;
  actions?: DecisionActions | null;
};

const NO_ACTIONS: DecisionActions = { can_review: false, can_approve: false, can_sign: false, reason: null };

/** The user's actions on a decision; nothing when the server did not say (the server stays the authority). */
export const decisionActionsOf = (decision: DecisionRow | null | undefined): DecisionActions =>
  decision?.actions ?? NO_ACTIONS;

/** The review dispositions offered: none without a right to review, and Approve only to someone who may approve. */
export function reviewDispositions(actions: DecisionActions): string[] {
  if (!actions.can_review) return [];
  return [...(actions.can_approve ? ["APPROVED"] : []), "REJECTED", "REQUIRES_ADDITIONAL_EVIDENCE"];
}

export function DecisionCenterView({
  investigationId,
  temporalMode,
  asOf,
  nextSteps,
}: {
  investigationId: string;
  temporalMode: TemporalMode;
  asOf: string;
  /**
   * The case's next steps (Phase 5). When given, they replace the decision option picker: an investigator moves the
   * case on with a next step and prepares a decision through the Decision Brief. The decision list, review and
   * signing below stay as they are.
   */
  nextSteps?: ReactNode;
}) {
  const [context, setContext] = useState<DecisionContext | null>(null);
  const [advisory, setAdvisory] = useState<any>(null);
  const [selectedAction, setSelectedAction] = useState("NO_DECISION_YET");
  const [rationale, setRationale] = useState("");
  const [message, setMessage] = useState("");
  // Every decision of the investigation (null while loading), so a reviewer or approver can pick any of them.
  const [decisions, setDecisions] = useState<DecisionRow[] | null>(null);
  const [selectedId, setSelectedId] = useState("");
  // No disposition is chosen for the reviewer: they must choose one.
  const [reviewDisposition, setReviewDisposition] = useState("");
  const [reviewComments, setReviewComments] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const [signedResult, setSignedResult] = useState<{ decisionId: string; data: any } | null>(null);
  const rationaleRef = useRef<HTMLTextAreaElement>(null);
  const [rationaleError, setRationaleError] = useState("");
  const canRunAi = useCanRunAi();
  const canWrite = useCan("records.write");
  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({ temporal_mode: temporalMode });
    if (temporalMode !== "current") params.set("as_of", `${asOf}T00:00:00Z`);
    api<DecisionContext>(`/api/v1/investigations/${investigationId}/decision-context?${params}`)
      .then((item) => {
        if (active) {
          setContext(item);
          setMessage("");
        }
      })
      .catch((err) => {
        if (active) setMessage(`Decision context unavailable: ${describeError(err, "try again.")}`);
      });
    return () => {
      active = false;
    };
  }, [investigationId, temporalMode, asOf]);
  // The decisions as the server has them now. Reloaded after every change, so a signature always names the current
  // version (a review changes it) and the offered actions are current.
  const loadDecisions = useCallback(
    (select?: string) =>
      requestJson<DecisionRow[]>(`/api/v1/investigations/${encodeURIComponent(investigationId)}/decisions`)
        .then((rows) => {
          const list = Array.isArray(rows) ? rows : [];
          setDecisions(list);
          setSelectedId((current) => {
            const wanted = select ?? current;
            return list.some((row) => String(row.id) === wanted) ? wanted : "";
          });
        })
        .catch((err) => {
          setDecisions((current) => current ?? []);
          setMessage(`Decisions could not be loaded: ${describeError(err, "try again.")}`);
        }),
    [investigationId],
  );
  useEffect(() => {
    setDecisions(null);
    setSelectedId("");
    setSignedResult(null);
    void loadDecisions();
  }, [loadDecisions]);
  const selected = decisions?.find((row) => String(row.id) === selectedId) ?? null;
  const selectedActions = decisionActionsOf(selected);
  const dispositions = reviewDispositions(selectedActions);
  const choose = (id: string) => {
    setSelectedId(id);
    setReviewDisposition("");
    setReviewComments("");
  };
  const temporalBody = JSON.stringify({
    temporal_mode: temporalMode,
    as_of: temporalMode === "current" ? null : `${asOf}T00:00:00Z`,
  });
  const runAdvisory = () =>
    postJson<any>(`/api/v1/investigations/${investigationId}/decision-advisory`, JSON.parse(temporalBody), {
      timeoutMs: AI_TIMEOUT_MS,
    })
      .then(setAdvisory)
      .catch((err) => setMessage(describeError(err, "The AI advisory could not be generated.")));
  const [recording, setRecording] = useState(false);
  const recordDecision = () => {
    if (recording) return; // one click, one decision
    if (!rationale.trim()) {
      setRationaleError("Enter a human rationale before recording this decision.");
      setMessage("Human rationale is required before recording a decision.");
      rationaleRef.current?.focus();
      return;
    }
    setRecording(true);
    // The author is the signed-in user; the server records them.
    postJson<any>(`/api/v1/investigations/${investigationId}/decisions`, {
      selected_action: selectedAction,
      rationale,
      temporal_mode: temporalMode,
      as_of: temporalMode === "current" ? null : `${asOf}T00:00:00Z`,
    })
      .then((payload) => {
        setMessage(
          `Decision ${displayId(payload, "decision_identifier", "")} recorded as REQUIRES_REVIEW. Another authorized user must review and sign it.`,
        );
        return loadDecisions(payload?.id ? String(payload.id) : undefined);
      })
      .catch((err) => setMessage(describeError(err, "The decision could not be recorded.")))
      .finally(() => setRecording(false));
  };
  const submitReview = () => {
    if (!selected || reviewing) return;
    if (!reviewDisposition) {
      setMessage("Choose a review disposition before submitting the human review.");
      return;
    }
    setReviewing(true);
    // The reviewer is the signed-in user; the server records them.
    postJson(`/api/v1/investigations/decisions/${selected.id}/reviews`, {
      disposition: reviewDisposition,
      comments: reviewComments,
    })
      .then(() => {
        setMessage(
          `Human review of ${displayId(selected, "decision_identifier", "the decision")} recorded: ${titleCase(reviewDisposition)}. It is preserved in Decision Memory and audit history.`,
        );
        setReviewDisposition("");
        setReviewComments("");
        // The review changed the decision's version: reload it so a signature names the current version.
        return loadDecisions(String(selected.id));
      })
      .catch((err) => setMessage(`Human review could not be submitted: ${describeError(err, "try again.")}`))
      .finally(() => setReviewing(false));
  };
  return (
    <div className="content">
      <section className="product-header">
        <div>
          <p className="eyebrow">Decision Center</p>
          <h2>{context ? displayId(context.investigation, "identifier", "Investigation") : "Loading investigation"}</h2>
          <p>
            AI recommends. Authorized humans decide. Temporal context:{" "}
            {String(context?.temporal_context.mode ?? temporalMode)} as of {asOf}.
          </p>
        </div>
        <div className="version-pill">
          <ShieldCheck size={16} /> Human review required
        </div>
      </section>
      {message && <div className="error">{message}</div>}
      {context && (
        <>
          <section className="panel readiness-panel">
            <div className="section-title">
              <ShieldCheck size={18} /> Decision Readiness
            </div>
            <h2>{context.readiness.state}</h2>
            <ul className="limitations">
              {context.readiness.reasons.map((reason) => (
                <li key={reason}>
                  <strong>LIMITATION</strong>
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          </section>
          <div className="two-col">
            <Panel title="What We Know" icon={<FileText />}>
              <DecisionItems items={context.observations} empty="No persisted observations available." />
            </Panel>
            <Panel title="Challenges / Contradictions" icon={<AlertTriangle />}>
              <DecisionItems
                items={[...context.contradictions, ...context.challenges]}
                empty="No challenge output available."
              />
            </Panel>
          </div>
          <div className="two-col">
            <Panel title="Competing Hypotheses" icon={<GitBranch />}>
              <DecisionItems items={context.hypotheses} empty="No hypotheses available." />
            </Panel>
            <Panel title="Unknowns Radar" icon={<CircleDot />}>
              <DecisionItems items={context.unknowns} empty="No unknowns recorded." />
            </Panel>
          </div>
          <Panel title="Failure Chain" icon={<Network />}>
            <DecisionItems items={context.failure_chains} empty="No supportable failure chain available." />
          </Panel>
          {nextSteps ? (
            canRunAi ? (
              <section className="panel">
                <div className="section-title">
                  <ClipboardList size={18} /> AI advisory (optional)
                </div>
                <p className="context-summary" role="note">
                  An AI advisory is a suggestion to review, never a decision. Use the next steps to move the case on.
                </p>
                <div className="toolbar">
                  <button className="primary-action secondary" onClick={runAdvisory}>
                    Generate AI Advisory
                  </button>
                </div>
                {advisory && (
                  <div className="advisory-box">
                    <strong>AI Advisory — not a human decision</strong>
                    <p>Recommended action: {advisory.advisory.recommended_action}</p>
                    <p>
                      {advisory.advisory.additional_evidence_needed.join(" ") ||
                        "No additional evidence need was identified by the controlled advisory."}
                    </p>
                  </div>
                )}
              </section>
            ) : null
          ) : (
            <section className="panel">
              <div className="section-title">
                <ClipboardList size={18} /> Decision Options
              </div>
              <select
                value={selectedAction}
                onChange={(event) => setSelectedAction(event.target.value)}
                aria-label="Decision option"
              >
                {context.decision_options.map((option) => (
                  <option key={option}>{option}</option>
                ))}
              </select>
              <label className="required-field" htmlFor="decision-rationale">
                Human rationale <span>(required)</span>
              </label>
              <textarea
                id="decision-rationale"
                ref={rationaleRef}
                aria-required="true"
                aria-invalid={Boolean(rationaleError)}
                value={rationale}
                onChange={(event) => {
                  setRationale(event.target.value);
                  setRationaleError("");
                  if (message.includes("rationale is required")) setMessage("");
                }}
                placeholder="Explain why this option is supportable or why no decision should be made."
                rows={4}
              />
              {rationaleError && (
                <p className="field-error" role="alert">
                  {rationaleError}
                </p>
              )}
              <div className="toolbar">
                {canRunAi && (
                  <button className="primary-action secondary" onClick={runAdvisory}>
                    Generate AI Advisory
                  </button>
                )}
                {canWrite ? (
                  <button className="primary-action" onClick={recordDecision} disabled={recording}>
                    Record Human Decision
                  </button>
                ) : (
                  <span className="context-summary" role="note">
                    View only: your role cannot record decisions.
                  </span>
                )}
              </div>
              {advisory && (
                <div className="advisory-box">
                  <strong>AI Advisory — not a human decision</strong>
                  <p>Recommended action: {advisory.advisory.recommended_action}</p>
                  <p>
                    {advisory.advisory.additional_evidence_needed.join(" ") ||
                      "No additional evidence need was identified by the controlled advisory."}
                  </p>
                </div>
              )}
            </section>
          )}
        </>
      )}
      {nextSteps}
      <section className="panel">
        <div className="section-title">
          <ClipboardList size={18} /> Decisions on this investigation
        </div>
        {decisions === null ? (
          <p className="empty-copy">Loading decisions…</p>
        ) : (
          <Table
            caption="Decisions on this investigation"
            rows={decisions}
            rowKey={(row) => String(row.id)}
            empty={{
              title: "No decisions yet",
              detail: "Decisions recorded for this investigation appear here for review and signature.",
            }}
            columns={[
              idColumn<DecisionRow>("Decision ID", "decision_identifier"),
              {
                key: "selected_action",
                label: "Option",
                render: (row) => titleCase(String(row.selected_action ?? "—")),
              },
              {
                key: "decision_status",
                label: "Status",
                render: (row) => titleCase(String(row.decision_status ?? "—")),
              },
              {
                key: "authorized_by_name",
                label: "Recorded by",
                render: (row) => safeText(row.authorized_by_name) ?? "—",
              },
              { key: "decision_timestamp", label: "Recorded", render: (row) => formatDate(row.decision_timestamp) },
              { key: "updated_at", label: "Last change", render: (row) => formatDate(row.updated_at) },
              {
                key: "open",
                label: "",
                render: (row) =>
                  String(row.id) === selectedId ? (
                    <strong>Selected</strong>
                  ) : (
                    <button type="button" className="secondary-link" onClick={() => choose(String(row.id))}>
                      Review or sign
                    </button>
                  ),
              },
            ]}
          />
        )}
        {selected && (
          <div className="human-review-box">
            <strong>
              Human Review — {displayId(selected, "decision_identifier", "Decision")} · required before finalization
            </strong>
            <p>Decision status: {titleCase(String(selected.decision_status ?? "—"))}</p>
            {selectedActions.reason && (
              <p className="context-summary" role="note">
                {selectedActions.reason}
              </p>
            )}
            {dispositions.length > 0 && (
              <>
                <select
                  value={reviewDisposition}
                  onChange={(event) => setReviewDisposition(event.target.value)}
                  disabled={reviewing}
                  aria-label="Review disposition"
                >
                  <option value="">Choose a disposition</option>
                  {dispositions.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
                <textarea
                  value={reviewComments}
                  onChange={(event) => setReviewComments(event.target.value)}
                  placeholder="Human review comments"
                  rows={3}
                  disabled={reviewing}
                />
                <button className="primary-action" onClick={submitReview} disabled={reviewing || !reviewDisposition}>
                  {reviewing ? "Submitting…" : "Submit Human Review"}
                </button>
              </>
            )}
            {selectedActions.can_sign && (
              <ControlledSignature
                key={`${selected.id}:${selected.updated_at ?? ""}`}
                decision={selected}
                onSigned={(result) => {
                  setSignedResult({ decisionId: String(selected.id), data: result });
                  setMessage(
                    `Decision ${displayId(selected, "decision_identifier", "")} ${titleCase(String(result.status ?? ""))} — signed.`,
                  );
                  void loadDecisions(String(selected.id));
                }}
              />
            )}
            {signedResult?.decisionId === String(selected.id) && <SignedSummary signed={signedResult.data} />}
          </div>
        )}
      </section>
    </div>
  );
}

/** The signature just recorded: its ID, who signed and the fingerprint of what was signed. */
function SignedSummary({ signed }: { signed: any }) {
  return (
    <div className="advisory-box">
      <strong>{signed.status} — SIGNED</strong>
      {safeText(signed.signature_business_id ?? signed.business_id) && (
        <p>Signature ID: {safeText(signed.signature_business_id ?? signed.business_id)}</p>
      )}
      <p>
        Signed By: {signed.signer} · Role: {signed.role}
      </p>
      <p>Fingerprint: {signed.fingerprint}</p>
    </div>
  );
}

export function DecisionItems({ items, empty }: { items: Array<Record<string, any>>; empty: string }) {
  if (!items.length) return <p className="empty-copy">{empty}</p>;
  return (
    <div className="decision-items">
      {items.slice(0, 8).map((item, index) => (
        <article key={String(item.item_id ?? item.hypothesis_id ?? item.unknown_id ?? item.chain_id ?? index)}>
          <strong>{String(item.semantic_type ?? item.category ?? item.overall_status ?? "Structured context")}</strong>
          <span>
            {String(
              item.statement ?? item.text ?? item.chain_statement ?? item.description ?? "No statement recorded.",
            )}
          </span>
        </article>
      ))}
    </div>
  );
}

export function ControlledSignature({ decision, onSigned }: { decision: any; onSigned: (result: any) => void }) {
  const [open, setOpen] = useState(false);
  const [session, setSession] = useState<any>(null);
  const [choice, setChoice] = useState("APPROVE");
  const [remarks, setRemarks] = useState("");
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [message, setMessage] = useState("");
  const close = () => {
    setPassword("");
    setMfaCode("");
    setRemarks("");
    setMessage("");
    setOpen(false);
  };
  const begin = () => {
    requestJson<any>("/api/v1/auth/session", { retries: 0 })
      .then((x) => {
        setSession(x);
        setOpen(true);
      })
      .catch((err) =>
        setMessage(
          isUnreachable(err)
            ? describeError(err, "MDARIX could not be reached.")
            : "Sign in is required before a controlled signature can be recorded.",
        ),
      );
  };
  const sign = () => {
    if (!remarks.trim() || !password) {
      setMessage("Decision remarks and current password are required.");
      return;
    }
    postJson<any>(`/api/v1/governance/decisions/${decision.id}/sign`, {
      decision: choice,
      remarks,
      password,
      object_version: decision.updated_at,
      ...(mfaCode ? { mfa_code: mfaCode } : {}),
    })
      .then((data) => {
        setPassword("");
        setMfaCode("");
        close();
        onSigned(data);
      })
      .catch((err) => {
        setPassword("");
        setMfaCode("");
        const code = err instanceof ApiError ? err.code : undefined;
        const messages: Record<string, string> = {
          INVALID_REAUTHENTICATION: "The entered password is incorrect.",
          APPROVAL_AUTHORITY_DENIED:
            "This role is not authorized to sign decisions. Ask an authorized approver to sign.",
          DENIED_NOT_ENTITLED: "Controlled signatures are not enabled for this tenant.",
          STALE_OBJECT_VERSION:
            "This decision changed while you were reviewing it. Reload the current version and review again.",
          DUPLICATE_SIGNATURE: "This decision version has already been signed.",
          SOD_DENIED: "The decision creator cannot sign their own decision. Use a different authorized approver.",
          MFA_REQUIRED: "Enter the current 6-digit code from your authenticator app.",
          MFA_ENROLLMENT_REQUIRED:
            "Signing needs multi-factor authentication. Set up your authenticator app under My Account first.",
          SIGNATURE_TEMPORARILY_LOCKED: "Too many failed attempts. Signing is locked for 15 minutes for your account.",
        };
        setMessage((code && messages[code]) || describeError(err, "The signature could not be recorded."));
      });
  };
  const meaning =
    choice === "APPROVE"
      ? "I have reviewed this record and approve this decision."
      : "I have reviewed this record and reject this decision.";
  return (
    <div className="human-review-box">
      <button className="primary-action" onClick={begin}>
        Approve or Reject — Sign
      </button>
      {message && <p role="alert">{message}</p>}
      {open && (
        <div className="advisory-box">
          <strong>Controlled Decision Signature</strong>
          <p>User: {session?.display_name} (read only)</p>
          <p>Active role: {session?.active_role} (read only)</p>
          <p>
            Record: {displayId(decision, "decision_identifier", "Decision")} · Version of{" "}
            {formatDateTime(decision.updated_at)} (read only)
          </p>
          <select value={choice} onChange={(e) => setChoice(e.target.value)} aria-label="Signature decision">
            <option>APPROVE</option>
            <option>REJECT</option>
          </select>
          <textarea
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
            placeholder="Mandatory decision remarks"
            rows={3}
          />
          <p>{meaning}</p>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Current password"
            autoComplete="current-password"
          />
          <input
            aria-label="Authenticator code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={mfaCode}
            onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ""))}
            placeholder="6-digit authenticator code"
          />
          <div className="toolbar">
            <button className="secondary-link" onClick={close}>
              Cancel
            </button>
            <button className="primary-action" onClick={sign}>
              Confirm &amp; Sign
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
