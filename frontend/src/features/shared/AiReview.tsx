import { useState } from "react";
import "./statement-kind.css";
import { Check, PencilLine, Sparkles, X } from "lucide-react";
import { describeError, postJson } from "../../app/apiClient";

/** The label on every AI output nobody accepted or edited yet (AI-R 4.4, owner decision AI-D7). */
export const AI_UNREVIEWED_LABEL = "AI proposal, not reviewed";
export const REVIEW_REASON_MIN = 5;
/** The chip on an AI proposal recorded with the sample (W1): no model was called. Never on a live proposal. */
export const RECORDED_LABEL = "Recorded with the sample · no model was called";

/** The recorded chip, for a proposal the server marks ``recorded``; nothing otherwise. */
export function RecordedChip({ recorded }: { recorded?: boolean | null }) {
  return recorded ? <span className="ms-chip is-sample ai-recorded">{RECORDED_LABEL}</span> : null;
}

export type AiReviewDecision = "ACCEPTED" | "EDITED" | "REJECTED";
/** What the server says about an output: one of the decisions, or not reviewed yet. */
export type AiReviewState = AiReviewDecision | "NOT_REVIEWED";

const DECIDED: Record<AiReviewDecision, string> = {
  ACCEPTED: "Accepted by a person",
  EDITED: "Edited by a person",
  REJECTED: "Rejected by a person",
};

/** The words for a reviewed output, or null while nobody has reviewed it. */
export const reviewedText = (state?: string | null) =>
  state && state in DECIDED ? DECIDED[state as AiReviewDecision] : null;
export type AiReviewBody = { decision: AiReviewDecision; reason?: string; edited_text?: string };

/** The review request, or why it cannot be sent yet (the server checks the same). */
export function aiReviewBody(
  decision: AiReviewDecision,
  reason = "",
  editedText = "",
): { body: AiReviewBody } | { problem: string } {
  if (decision === "ACCEPTED") return { body: { decision } };
  if (reason.trim().length < REVIEW_REASON_MIN)
    return { problem: `Give a reason of at least ${REVIEW_REASON_MIN} characters.` };
  if (decision === "REJECTED") return { body: { decision, reason: reason.trim() } };
  if (!editedText.trim()) return { problem: "Write the corrected text." };
  return { body: { decision, reason: reason.trim(), edited_text: editedText } };
}

/** The "AI proposal, not reviewed" label with Accept, Edit and Reject. The reviewer is the signed-in person (server). */
export function AiReviewActions({
  outputId,
  text,
  onReviewed,
  disabled = false,
  state = null,
}: {
  outputId: string;
  /** The AI's text, the starting point of an edit. */
  text?: string | null;
  onReviewed?: (decision: AiReviewDecision) => void;
  disabled?: boolean;
  /** The server's review state of this output; a reviewed output shows who decided, not the buttons. */
  state?: string | null;
}) {
  const [decided, setDecided] = useState<string | null>(state);
  const [mode, setMode] = useState<"EDITED" | "REJECTED" | null>(null);
  const [reason, setReason] = useState("");
  const [edited, setEdited] = useState(text ?? "");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (decision: AiReviewDecision) => {
    const built = aiReviewBody(decision, reason, edited);
    if ("problem" in built) {
      setProblem(built.problem);
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      await postJson(`/api/v1/ai-outputs/${encodeURIComponent(outputId)}/review`, built.body);
      setMode(null);
      setDecided(decision);
      onReviewed?.(decision);
    } catch (error) {
      setProblem(describeError(error, "The review could not be saved."));
    } finally {
      setBusy(false);
    }
  };
  const done = reviewedText(decided);
  if (done)
    return (
      <div className="ai-review is-reviewed" role="group" aria-label="AI proposal reviewed">
        <span className={`ai-review-label is-${String(decided).toLowerCase()}`} role="note">
          <Check size={13} aria-hidden="true" /> {done}
        </span>
      </div>
    );
  return (
    <div className="ai-review" role="group" aria-label="Review this AI proposal">
      <span className="ai-review-label" role="note">
        <Sparkles size={14} aria-hidden="true" /> {AI_UNREVIEWED_LABEL}
      </span>
      {!disabled && mode === null && (
        <span className="ca-row-actions">
          <button type="button" className="ac-primary" disabled={busy} onClick={() => void submit("ACCEPTED")}>
            <Check size={14} aria-hidden="true" /> Accept
          </button>
          <button type="button" className="ac-secondary" disabled={busy} onClick={() => setMode("EDITED")}>
            <PencilLine size={14} aria-hidden="true" /> Edit
          </button>
          <button type="button" className="ac-secondary" disabled={busy} onClick={() => setMode("REJECTED")}>
            <X size={14} aria-hidden="true" /> Reject
          </button>
        </span>
      )}
      {mode && (
        <div className="ai-review-form">
          {mode === "EDITED" && (
            <label>
              Corrected text
              <textarea value={edited} onChange={(event) => setEdited(event.target.value)} rows={4} />
            </label>
          )}
          <label>
            {mode === "EDITED" ? "Why you changed it" : "Why you reject it"}
            <input value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          <span className="ca-row-actions">
            <button type="button" className="ac-primary" disabled={busy} onClick={() => void submit(mode)}>
              {mode === "EDITED" ? "Save the edit" : "Reject"}
            </button>
            <button type="button" className="ac-secondary" disabled={busy} onClick={() => setMode(null)}>
              Cancel
            </button>
          </span>
        </div>
      )}
      {problem && (
        <p className="ac-error" role="alert">
          {problem}
        </p>
      )}
    </div>
  );
}
