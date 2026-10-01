import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CircleDot, ClipboardList, FileText, GitBranch, Network, ShieldCheck } from "lucide-react";
import { Panel } from "../../app/ui";
import { TemporalMode, DecisionContext } from "../../app/types";
import { api } from "../../app/api";
import { useCan } from "../workspace/workspaceContext";

export function DecisionCenterView({
  investigationId,
  temporalMode,
  asOf,
}: {
  investigationId: string;
  temporalMode: TemporalMode;
  asOf: string;
}) {
  const [context, setContext] = useState<DecisionContext | null>(null);
  const [advisory, setAdvisory] = useState<any>(null);
  const [selectedAction, setSelectedAction] = useState("NO_DECISION_YET");
  const [rationale, setRationale] = useState("");
  const [message, setMessage] = useState("");
  const [decision, setDecision] = useState<any>(null);
  const [reviewDisposition, setReviewDisposition] = useState("APPROVED");
  const [reviewComments, setReviewComments] = useState("");
  const [reviewSubmitted, setReviewSubmitted] = useState(false);
  const rationaleRef = useRef<HTMLTextAreaElement>(null);
  const [rationaleError, setRationaleError] = useState("");
  const canRunAi = useCan("ai.run");
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
        if (active) setMessage(`Decision context unavailable: ${err.message}`);
      });
    return () => {
      active = false;
    };
  }, [investigationId, temporalMode, asOf]);
  const temporalBody = JSON.stringify({
    temporal_mode: temporalMode,
    as_of: temporalMode === "current" ? null : `${asOf}T00:00:00Z`,
  });
  const runAdvisory = () =>
    fetch(`/api/v1/investigations/${investigationId}/decision-advisory`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: temporalBody,
    })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then(setAdvisory)
      .catch((err) => setMessage(err.message));
  const recordDecision = () => {
    if (!rationale.trim()) {
      setRationaleError("Enter a human rationale before recording this decision.");
      setMessage("Human rationale is required before recording a decision.");
      rationaleRef.current?.focus();
      return;
    }
    fetch(`/api/v1/investigations/${investigationId}/decisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selected_action: selectedAction,
        rationale,
        authorized_by_ref: "CONTROLLED_DEVELOPMENT_REVIEWER",
        temporal_mode: temporalMode,
        as_of: temporalMode === "current" ? null : `${asOf}T00:00:00Z`,
      }),
    })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then((payload) => {
        setDecision(payload);
        setMessage("Decision recorded as REQUIRES_REVIEW. Complete Human Review below.");
      })
      .catch((err) => setMessage(err.message));
  };
  const submitReview = () =>
    fetch(`/api/v1/investigations/decisions/${decision.id}/reviews`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        disposition: reviewDisposition,
        reviewer_ref: "CONTROLLED_DEVELOPMENT_REVIEWER",
        comments: reviewComments,
      }),
    })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then(() => {
        setDecision({
          ...decision,
          decision_status: reviewDisposition === "APPROVED" ? "DECIDED" : "REQUIRES_ADDITIONAL_EVIDENCE",
        });
        setReviewSubmitted(true);
        setMessage(`Human review recorded: ${reviewDisposition}.`);
      })
      .catch((err) => setMessage(`Human review could not be submitted: ${err.message}`));
  return (
    <div className="content">
      <section className="product-header">
        <div>
          <p className="eyebrow">Decision Center</p>
          <h2>{context?.investigation.identifier ?? "Loading investigation"}</h2>
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
                <button className="primary-action" onClick={recordDecision}>
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
            {decision && (
              <div className="human-review-box">
                <strong>Human Review — required before finalization</strong>
                <p>Decision status: {decision.decision_status}</p>
                <select
                  value={reviewDisposition}
                  onChange={(event) => setReviewDisposition(event.target.value)}
                  disabled={reviewSubmitted}
                >
                  <option value="APPROVED">APPROVED</option>
                  <option value="REJECTED">REJECTED</option>
                  <option value="REQUIRES_ADDITIONAL_EVIDENCE">REQUIRES_ADDITIONAL_EVIDENCE</option>
                </select>
                <textarea
                  value={reviewComments}
                  onChange={(event) => setReviewComments(event.target.value)}
                  placeholder="Human review comments"
                  rows={3}
                  disabled={reviewSubmitted}
                />
                <button className="primary-action" onClick={submitReview} disabled={reviewSubmitted}>
                  {reviewSubmitted ? "Human Review Submitted" : "Submit Human Review"}
                </button>
                {reviewSubmitted && (
                  <>
                    <p className="review-success">
                      Review saved successfully. The human disposition is preserved in Decision Memory and audit
                      history.
                    </p>
                    <ControlledSignature
                      decision={decision}
                      onSigned={(result) => {
                        setDecision({ ...decision, decision_status: result.status });
                        setMessage(`Decision ${result.status} — signed.`);
                      }}
                    />
                  </>
                )}
              </div>
            )}
          </section>
        </>
      )}
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
  const [message, setMessage] = useState("");
  const [signed, setSigned] = useState<any>(null);
  const close = () => {
    setPassword("");
    setRemarks("");
    setMessage("");
    setOpen(false);
  };
  const begin = () => {
    fetch("/api/v1/auth/session")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((x) => {
        setSession(x);
        setOpen(true);
      })
      .catch(() => setMessage("Sign in is required before a controlled signature can be recorded."));
  };
  const sign = () => {
    if (!remarks.trim() || !password) {
      setMessage("Decision remarks and current password are required.");
      return;
    }
    fetch(`/api/v1/governance/decisions/${decision.id}/sign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: choice, remarks, password, object_version: decision.updated_at }),
    })
      .then(async (r) => ({
        ok: r.ok,
        status: r.status,
        data: await r.json().catch(() => ({
          detail: {
            code: "INVALID_SERVER_RESPONSE",
            message: `Server returned HTTP ${r.status} without a valid response.`,
          },
        })),
      }))
      .then(({ ok, data }) => {
        setPassword("");
        if (!ok) {
          const code = data.detail?.code;
          const messages: Record<string, string> = {
            INVALID_REAUTHENTICATION: "The entered password is incorrect.",
            APPROVAL_AUTHORITY_DENIED:
              "This role is not authorized to sign decisions. Ask an authorized approver to sign.",
            DENIED_NOT_ENTITLED: "Controlled signatures are not enabled for this tenant.",
            STALE_OBJECT_VERSION:
              "This decision changed while you were reviewing it. Reload the current version and review again.",
            DUPLICATE_SIGNATURE: "This decision version has already been signed.",
            SOD_DENIED: "The decision creator cannot sign their own decision. Use a different authorized approver.",
          };
          setMessage(
            messages[code] ?? data.detail?.message ?? `Signature could not be recorded${code ? ` (${code})` : ""}.`,
          );
          return;
        }
        setSigned(data);
        onSigned(data);
        close();
      })
      .catch(() => {
        setPassword("");
        setMessage("Signature request failed. Check that the backend is running and try again.");
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
      {signed && (
        <div className="advisory-box">
          <strong>{signed.status} — SIGNED</strong>
          <p>Signature ID: {String(signed.signature_id)}</p>
          <p>
            Signed By: {signed.signer} · Role: {signed.role}
          </p>
          <p>Fingerprint: {signed.fingerprint}</p>
        </div>
      )}
      {open && (
        <div className="advisory-box">
          <strong>Controlled Decision Signature</strong>
          <p>User: {session?.display_name} (read only)</p>
          <p>Active role: {session?.active_role} (read only)</p>
          <p>
            Record: {decision.decision_identifier} · Version: {decision.updated_at} (read only)
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
