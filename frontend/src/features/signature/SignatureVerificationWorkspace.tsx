import { useState } from "react";
import { requestJson } from "../../app/apiClient";
import { formatDateTime, formatUtc } from "../../app/dates";

export function SignatureVerificationWorkspace() {
  const [decisionId, setDecisionId] = useState("");
  const [code, setCode] = useState("");
  const [report, setReport] = useState<any>(null);
  const [message, setMessage] = useState("");
  const issueChallenge = async () => {
    try {
      const result = await requestJson<any>("/api/v1/auth/mfa/challenge", { method: "POST" });
      setMessage(
        result.development_code
          ? `Development server code: ${result.development_code}`
          : "MFA challenge issued. Enter the code from your authenticator.",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "MFA challenge could not be issued.");
    }
  };
  const verify = async () => {
    if (!decisionId.trim()) {
      setMessage("Decision ID is required.");
      return;
    }
    try {
      setReport(await requestJson<any>(`/api/v1/governance/decisions/${decisionId.trim()}/signature-verification`));
      setMessage("Signature verification report loaded.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Verification report unavailable.");
    }
  };
  return (
    <div className="content governance-view signature-workspace">
      <section className="governance-hero">
        <div>
          <span className="eyebrow">Governed approval · signature evidence</span>
          <h1>Signature verification</h1>
          <p>
            Re-authentication, MFA, object-version binding, duplicate-signature rejection, and human intent are required
            for high-impact decisions.
          </p>
        </div>
        <span className="platform-admin-badge warning">Human approval only</span>
      </section>
      <section className="panel signature-controls">
        <label>
          Decision ID
          <input value={decisionId} onChange={(e) => setDecisionId(e.target.value)} placeholder="Decision UUID" />
        </label>
        <label>
          MFA code
          <input
            inputMode="numeric"
            pattern="[0-9]{6}"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            placeholder="Required when policy enabled"
          />
        </label>
        <div className="toolbar">
          <button onClick={() => void issueChallenge()}>Issue MFA challenge</button>
          <button className="primary-action" onClick={() => void verify()}>
            Load verification report
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
          <div className="platform-admin-badge">{report.verification_status}</div>
          <div className="signature-report-grid">
            {(report.signatures ?? []).map((item: any) => (
              <article key={String(item.signature_id)}>
                <strong>
                  {item.decision} · {item.valid ? "VALID" : "INVALID"}
                </strong>
                <span>Signature: {item.signature_id}</span>
                <span>
                  Signer: {item.signer_user_id} · {item.signer_role}
                </span>
                <span>Object version: {item.object_version}</span>
                <span>
                  Signed: {formatUtc(item.signed_at)} ({formatDateTime(item.signed_at)})
                </span>
                <small>{item.meaning}</small>
              </article>
            ))}
            {!report.signatures?.length && <p className="muted">No signatures recorded for this decision version.</p>}
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
