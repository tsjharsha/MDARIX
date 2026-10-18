import { useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { Bug } from "lucide-react";
import { describeError, lastFailedRequestId, postJson } from "../../app/apiClient";
import { DialogBehaviour } from "./DialogBehaviour";
import { safeText } from "../../app/displayId";

export const SUMMARY_LIMIT = 200;
export const DETAILS_LIMIT = 5000;

export type ProblemReport = { summary: string; details: string; path: string; request_id?: string };

/**
 * What a problem report sends: the person's own words, the page they were on (without its query, which can carry
 * search terms) and the reference of the last failed request, if any. Nothing else from the screen.
 */
export function problemReport(
  summary: string,
  details: string,
  location: { pathname: string },
  requestId?: string,
): ProblemReport {
  return {
    summary: summary.trim().slice(0, SUMMARY_LIMIT),
    details: details.trim().slice(0, DETAILS_LIMIT),
    path: location.pathname.slice(0, 512),
    ...(requestId ? { request_id: requestId } : {}),
  };
}

/** The email fallback when the report cannot be sent: the same content, addressed to support. */
export function problemMailto(support: string, report: ProblemReport, now = new Date()): string {
  const body = [
    report.details,
    "",
    `Page: ${report.path}`,
    ...(report.request_id ? [`Reference: ${report.request_id}`] : []),
    `Time: ${now.toISOString()}`,
  ].join("\n");
  return `mailto:${support}?subject=${encodeURIComponent(`MDARIX problem: ${report.summary}`)}&body=${encodeURIComponent(body)}`;
}

/** "Report a problem" from the Help menu: a short form that reaches the MDARIX team (POST /api/v1/support/problems). */
export function ReportProblemDialog({ supportEmail, onClose }: { supportEmail?: string; onClose: () => void }) {
  const [summary, setSummary] = useState("");
  const [details, setDetails] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const [failure, setFailure] = useState<{ message: string; mailto?: string } | null>(null);
  const requestId = lastFailedRequestId();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || !summary.trim() || !details.trim()) return;
    const report = problemReport(summary, details, window.location, requestId);
    setBusy(true);
    setFailure(null);
    try {
      const result = await postJson<{ id: string; business_id?: string | null }>("/api/v1/support/problems", report, {
        redirectOnUnauthorized: false,
      });
      // The report's own number (SUPT000012) to quote in a reply; never its UUID.
      setSent(safeText(result?.business_id) ?? "");
    } catch (error) {
      setFailure({
        message: describeError(error, "The report could not be sent."),
        mailto: supportEmail ? problemMailto(supportEmail, report) : undefined,
      });
    } finally {
      setBusy(false);
    }
  };

  // Rendered at the end of the page, not inside the header that opened it: the sticky header is its own stacking
  // context, and the dialog must sit above the privacy notice and everything else. The "admin-console" wrapper
  // carries the workspace's colours and type there; without it the dialog had no background and its text no colour.
  return createPortal(
    <div className="admin-console ac-portal">
      <div className="ac-modal-backdrop" role="presentation">
        <DialogBehaviour onClose={onClose} />
        <section
          className="ac-modal report-problem"
          role="dialog"
          aria-modal="true"
          aria-labelledby="report-problem-title"
        >
          <p className="ac-eyebrow">
            <Bug size={14} aria-hidden="true" /> Help
          </p>
          <h2 id="report-problem-title">Report a problem</h2>
          {sent !== null ? (
            <>
              <p role="status">
                Thank you. Your report has reached the MDARIX team{sent ? ` (report ${sent})` : ""}. We reply by email.
              </p>
              <div className="ac-modal-actions">
                <button type="button" className="ac-primary" onClick={onClose}>
                  Close
                </button>
              </div>
            </>
          ) : (
            <form className="ca-form" onSubmit={submit}>
              <p className="ac-muted">
                Tell us what happened and what you expected.{" "}
                {requestId
                  ? "The page you are on and the reference of the last failed request are sent with it."
                  : "The page you are on is sent with it."}{" "}
                Do not include patient or personal data.
              </p>
              <label className="ca-field">
                What went wrong, in a few words
                <input
                  required
                  maxLength={SUMMARY_LIMIT}
                  value={summary}
                  onChange={(event) => setSummary(event.target.value)}
                />
              </label>
              <label className="ca-field">
                Details: what you did, what happened, what you expected
                <textarea
                  required
                  rows={6}
                  maxLength={DETAILS_LIMIT}
                  value={details}
                  onChange={(event) => setDetails(event.target.value)}
                />
                <small className="ac-muted">
                  {details.length.toLocaleString()} of {DETAILS_LIMIT.toLocaleString()} characters
                </small>
              </label>
              {requestId && (
                <p className="ac-request-id">
                  Reference sent with the report: <code>{requestId}</code>
                </p>
              )}
              {failure && (
                <p className="ca-inline-error" role="alert">
                  {failure.message}{" "}
                  {failure.mailto ? (
                    <a href={failure.mailto}>Send it by email instead</a>
                  ) : (
                    <a href="/contact" target="_blank" rel="noopener">
                      Contact us instead
                    </a>
                  )}
                </p>
              )}
              <div className="ac-modal-actions">
                <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
                  Cancel
                </button>
                <button type="submit" className="ac-primary" disabled={busy || !summary.trim() || !details.trim()}>
                  {busy ? "Sending…" : "Send report"}
                </button>
              </div>
            </form>
          )}
        </section>
      </div>
    </div>,
    document.body,
  );
}
