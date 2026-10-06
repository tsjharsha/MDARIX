import { useContext, useEffect, useState } from "react";
import { describeError, requestJson } from "../../app/apiClient";
import { formatDateTime, formatUtc } from "../../app/dates";
import { titleCase } from "../admin/console/dashboardModel";
import { WorkspaceContext } from "../workspace/workspaceContext";

type Decision = {
  id: string;
  decision_identifier?: string;
  decision_status?: string;
  selected_action?: string;
  decision_timestamp?: string;
  updated_at?: string;
};
type Person = { id: string; display_name: string };

/**
 * Who signed, in words: "you", a colleague's name (from the organization's list of people who work on cases), or —
 * when the signer is not on that list (for example an approver who does not work cases) — their role.
 */
export function signerLabel(
  signerId: string,
  role: string | undefined,
  people: Person[],
  currentUserId: string | undefined,
): string {
  const roleText = role ? titleCase(role) : "";
  if (currentUserId && signerId === currentUserId) return roleText ? `You (${roleText})` : "You";
  const person = people.find((item) => item.id === signerId);
  if (person) return roleText ? `${person.display_name} (${roleText})` : person.display_name;
  return roleText ? `A colleague with the ${roleText} role` : "A colleague in your organization";
}

/** One line to choose a decision by: its identifier, the option chosen, its status and when it was made. */
export function decisionLabel(decision: Decision): string {
  return [
    decision.decision_identifier ?? decision.id.slice(0, 8),
    decision.selected_action ? titleCase(decision.selected_action) : null,
    decision.decision_status ? titleCase(decision.decision_status) : null,
    decision.decision_timestamp ? formatDateTime(decision.decision_timestamp) : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function SignatureVerificationWorkspace() {
  // Inside the workspace the case chosen in the context bar is used; on its own the person chooses a case here.
  const workspace = useContext(WorkspaceContext);
  const contextCase = workspace?.work.investigationId ?? "";
  const [cases, setCases] = useState<Array<{ id: string; investigation_identifier?: string }>>([]);
  const [caseId, setCaseId] = useState(contextCase);
  const [decisions, setDecisions] = useState<Decision[] | null>(null);
  const [decisionId, setDecisionId] = useState("");
  const [people, setPeople] = useState<Person[]>([]);
  const [me, setMe] = useState<string | undefined>(undefined);
  const [report, setReport] = useState<any>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => setCaseId(contextCase), [contextCase]);
  useEffect(() => {
    requestJson<{ user_id?: string }>("/api/v1/auth/session", { retries: 0 })
      .then((session) => setMe(session.user_id))
      .catch(() => undefined);
    requestJson<Person[]>("/api/v1/investigation-assignees")
      .then((rows) => setPeople(Array.isArray(rows) ? rows : []))
      .catch(() => setPeople([]));
    if (!contextCase)
      requestJson<any>("/api/v1/analytics/investigations")
        .then((data) => setCases(Array.isArray(data?.investigations) ? data.investigations : []))
        .catch((error) => setMessage(describeError(error, "Investigations could not be loaded.")));
  }, []);
  useEffect(() => {
    setDecisions(null);
    setDecisionId("");
    setReport(null);
    if (!caseId) return;
    requestJson<Decision[]>(`/api/v1/investigations/${encodeURIComponent(caseId)}/decisions`)
      .then((rows) => {
        const list = Array.isArray(rows) ? rows : [];
        setDecisions(list);
        setDecisionId(list[0]?.id ? String(list[0].id) : "");
      })
      .catch((error) => setMessage(describeError(error, "The decisions of this case could not be loaded.")));
  }, [caseId]);

  const verify = async () => {
    if (!decisionId) return;
    setBusy(true);
    setMessage("");
    try {
      setReport(
        await requestJson<any>(`/api/v1/governance/decisions/${encodeURIComponent(decisionId)}/signature-verification`),
      );
    } catch (error) {
      setReport(null);
      setMessage(describeError(error, "The verification report is unavailable."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="content governance-view signature-workspace">
      <section className="governance-hero">
        <div>
          <span className="eyebrow">Governed approval · signature evidence</span>
          <h1>Signature verification</h1>
          <p>
            Check that every signature on a decision still matches the exact decision version that was signed. Signing
            itself needs your password and authenticator code, and is done in the Decision center.
          </p>
        </div>
        <span className="platform-admin-badge warning">Human approval only</span>
      </section>
      <section className="panel signature-controls">
        {!contextCase && (
          <label>
            Investigation
            <select value={caseId} onChange={(event) => setCaseId(event.target.value)}>
              <option value="">Choose an investigation</option>
              {cases.map((item) => (
                <option key={item.id} value={String(item.id)}>
                  {item.investigation_identifier ?? item.id}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Decision
          <select
            value={decisionId}
            onChange={(event) => {
              setDecisionId(event.target.value);
              setReport(null);
            }}
            disabled={!decisions?.length}
          >
            {!decisions?.length && (
              <option value="">
                {!caseId ? "Choose an investigation first" : decisions ? "No decisions recorded yet" : "Loading…"}
              </option>
            )}
            {decisions?.map((decision) => (
              <option key={decision.id} value={String(decision.id)}>
                {decisionLabel(decision)}
              </option>
            ))}
          </select>
        </label>
        <div className="toolbar">
          <button className="primary-action" onClick={() => void verify()} disabled={!decisionId || busy}>
            {busy ? "Checking…" : "Check signatures"}
          </button>
        </div>
      </section>
      {message && (
        <p className="state-panel" role="status">
          {message}
        </p>
      )}
      {report && (
        <section className="panel">
          <div className="section-title">Verification report</div>
          <div className="platform-admin-badge">
            {report.verification_status === "VALID"
              ? "All signatures valid"
              : titleCase(String(report.verification_status ?? "Not signed"))}
          </div>
          <div className="signature-report-grid">
            {(report.signatures ?? []).map((item: any) => (
              <article key={String(item.signature_id)}>
                <strong>
                  {titleCase(String(item.decision ?? "Signature"))} ·{" "}
                  {item.valid ? "Valid" : "Does not match the signed version"}
                </strong>
                <span>Signed by: {signerLabel(String(item.signer_user_id), item.signer_role, people, me)}</span>
                <span>
                  Decision version of {formatDateTime(item.object_version, String(item.object_version ?? "—"))}
                </span>
                <span>
                  Signed: {formatUtc(item.signed_at)} ({formatDateTime(item.signed_at)})
                </span>
                <small>{item.meaning}</small>
              </article>
            ))}
            {!report.signatures?.length && <p className="muted">No signatures recorded for this decision yet.</p>}
          </div>
        </section>
      )}
      <section className="panel advisory-box">
        <strong>What a signature records</strong>
        <span>
          Each signature records who signed, its meaning, the time and a fingerprint of the signed decision, so any
          later change is detected. Certificate-based digital signatures and signing through your own identity provider
          are not available yet.
        </span>
      </section>
    </div>
  );
}
