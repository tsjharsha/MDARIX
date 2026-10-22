import { useContext, useEffect, useState } from "react";
import { describeError, requestJson } from "../../app/apiClient";
import { formatDateTime, formatUtc } from "../../app/dates";
import { titleCase } from "../admin/console/dashboardModel";
import { WorkspaceContext, useFeatureSet } from "../workspace/workspaceContext";
import { displayId, safeText } from "../../app/displayId";
import { isCaseDecision } from "../workspace/humanDecision";
import { DecisionRecordDrawer } from "../workspace/sections/DecisionRecord";
import { SignatureBasis } from "../shared/Basis";

type Decision = {
  id: string;
  business_id?: string | null;
  decision_identifier?: string;
  decision_status?: string;
  selected_action?: string;
  decision_timestamp?: string;
  updated_at?: string;
  // A decision on a case's brief (the decision screen, GET /api/v1/investigations/{id}/decision).
  outcome_label?: string | null;
  decision_status_label?: string | null;
  decided_at?: string | null;
};
type Person = { id: string; display_name: string };

/**
 * Who signed, in words: the signer's name and role, "Meera Iyer (Leader)", also when it is the signed-in person
 * (DEV-024). The name comes from the verification report (``signer_name``), else from the organization's list of
 * people who work on cases; without one, "You (Leader)" for the signed-in person, else the role.
 */
export function signerLabel(
  signerId: string,
  role: string | undefined,
  people: Person[],
  currentUserId: string | undefined,
  signerName?: string | null,
): string {
  const roleText = role ? titleCase(role) : "";
  const name = safeText(signerName) ?? people.find((item) => item.id === signerId)?.display_name;
  if (name) return roleText ? `${name} (${roleText})` : name;
  if (currentUserId && signerId === currentUserId) return roleText ? `You (${roleText})` : "You";
  return roleText ? `A colleague with the ${roleText} role` : "A colleague in your organization";
}

/** One line to choose a decision by: its Decision ID, the option chosen, its status and when it was made. */
export function decisionLabel(decision: Decision): string {
  return [
    displayId(decision, "decision_identifier", "Decision"),
    decision.selected_action ? titleCase(decision.selected_action) : (decision.outcome_label ?? null),
    decision.decision_status_label ?? (decision.decision_status ? titleCase(decision.decision_status) : null),
    decision.decision_timestamp || decision.decided_at
      ? formatDateTime(String(decision.decision_timestamp || decision.decided_at))
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

// What a signature's decision code says, in words: a case decision's outcome or a legacy approval.
const SIGNED_DECISIONS: Record<string, string> = {
  ACCEPT: "Accept the conclusion",
  ACCEPT_COND: "Accept with conditions",
  REJECT: "Reject the conclusion",
  CLOSE_NFA: "Close with no further action",
  APPROVE: "Approved",
};

/** The decision a signature records, in words ("ACCEPT_COND" → "Accept with conditions"). */
export function signedDecisionLabel(code: unknown): string {
  const value = String(code ?? "").toUpperCase();
  return SIGNED_DECISIONS[value] ?? (value ? titleCase(value) : "Signature");
}

/**
 * The version a signature was given on, in words: the brief the decision was made on ("Decision Brief DBV000012
 * version 2", the report's ``version_label``), or for an older approval the moment the decision was last changed. Never
 * the version's own code: for a decision on a brief that is a 64-character fingerprint (0.10.43).
 */
export function signedVersionText(item: { version_label?: unknown; object_version?: unknown }): string {
  const label = safeText(item.version_label);
  if (label) return label;
  const version = String(item.object_version ?? "");
  return /^\d{4}-\d{2}-\d{2}/.test(version) ? `The decision as of ${formatDateTime(version)}` : "Not available";
}

/**
 * The overall result of a verification report in words: every signature valid, at least one that no longer matches
 * what was signed (a problem, never shown as merely unsigned), or no signature yet.
 */
export function verificationSummary(status: unknown): { label: string; tone: "good" | "neutral" | "problem" } {
  switch (String(status ?? "").toUpperCase()) {
    case "VALID":
      return { label: "All signatures valid", tone: "good" };
    case "INVALID":
      return { label: "Invalid — at least one signature does not match the signed version", tone: "problem" };
    case "NOT_SIGNED":
    case "":
      return { label: "Not signed", tone: "neutral" };
    default:
      return { label: titleCase(String(status)), tone: "problem" };
  }
}

const SUMMARY_BADGE = {
  good: "platform-admin-badge success",
  neutral: "platform-admin-badge",
  problem: "platform-admin-badge warning",
};

export function SignatureVerificationWorkspace() {
  // Inside the workspace the case chosen in the context bar is used; on its own the person chooses a case here.
  const workspace = useContext(WorkspaceContext);
  const contextCase = workspace?.work.investigationId ?? "";
  // The lightweight MVP (and every free trial) parks the legacy decision list; its cases' decisions are those of the
  // decision screen, newest first.
  const mvp = useFeatureSet() === "mvp";
  const [cases, setCases] = useState<
    Array<{ id: string; business_id?: string | null; investigation_identifier?: string }>
  >([]);
  const [caseId, setCaseId] = useState(contextCase);
  const [decisions, setDecisions] = useState<Decision[] | null>(null);
  const [decisionId, setDecisionId] = useState("");
  const [people, setPeople] = useState<Person[]>([]);
  const [me, setMe] = useState<string | undefined>(undefined);
  const [report, setReport] = useState<any>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  // The full signed record of a case decision (Phase 6), opened from here.
  const [recordOpen, setRecordOpen] = useState(false);

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
    const path = `/api/v1/investigations/${encodeURIComponent(caseId)}`;
    (mvp
      ? requestJson<{ decisions?: Decision[] }>(`${path}/decision`).then((screen) => screen?.decisions ?? [])
      : requestJson<Decision[]>(`${path}/decisions`)
    )
      .then((rows) => {
        const list = Array.isArray(rows) ? rows : [];
        setDecisions(list);
        setDecisionId(list[0]?.id ? String(list[0].id) : "");
      })
      .catch((error) => setMessage(describeError(error, "The decisions of this case could not be loaded.")));
  }, [caseId, mvp]);

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

  const summary = report ? verificationSummary(report.verification_status) : null;
  const selected = decisions?.find((decision) => String(decision.id) === decisionId) ?? null;
  const caseDecision = !!selected && isCaseDecision(selected as unknown as Record<string, unknown>, report);

  return (
    <div className="content governance-view signature-workspace">
      <section className="governance-hero">
        <div>
          <span className="eyebrow">Governed approval · signature evidence</span>
          <h1>Signature verification</h1>
          <p>
            Check that every signature on a decision still matches the exact decision version that was signed. Signing
            itself needs your password and authenticator code, and is done on the case&apos;s decision.
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
                  {displayId(item, "investigation_identifier", "Investigation")}
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
          {caseDecision && (
            <button className="primary-action secondary" onClick={() => setRecordOpen(true)}>
              Open the signed decision record
            </button>
          )}
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
          {summary && (
            <div className={SUMMARY_BADGE[summary.tone]} role={summary.tone === "problem" ? "alert" : undefined}>
              {summary.label}
            </div>
          )}
          <div className="signature-report-grid">
            {(report.signatures ?? []).map((item: any) => (
              <article key={String(item.signature_id)}>
                <strong>
                  {signedDecisionLabel(item.decision)} · {item.valid ? "Valid" : "Does not match the signed version"}
                </strong>
                {safeText(item.business_id ?? item.signature_business_id) && (
                  <span>Signature ID: {safeText(item.business_id ?? item.signature_business_id)}</span>
                )}
                <span>
                  Signed by: {signerLabel(String(item.signer_user_id), item.signer_role, people, me, item.signer_name)}
                </span>
                <span>Signed version: {signedVersionText(item)}</span>
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
      {recordOpen && selected && (
        <DecisionRecordDrawer
          key={String(selected.id)}
          decisionId={String(selected.id)}
          onClose={() => setRecordOpen(false)}
        />
      )}
      <section className="panel advisory-box">
        <strong>What a signature records</strong>
        <span>
          Each signature records who signed, its meaning, the time and a fingerprint of the signed decision, so any
          later change is detected. Certificate-based digital signatures and signing through your own identity provider
          are not available yet.
        </span>
        <SignatureBasis />
      </section>
    </div>
  );
}
