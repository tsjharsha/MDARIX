import { useState } from "react";
import { REASON_MIN, REPORTS, type ObligationState, type ReportDetail } from "../authorityReports";
import { errorText, formatDate, send } from "../../customer-admin/shared";
import { InlineError } from "./boardParts";
import { useAction } from "./Reports";

/** FDA's follow-up types (box H2), in FDA's order. */
export const H2_TYPES = ["Correction", "Additional information", "Response to FDA request", "Device evaluation"];

/** Sent through the authority's route: a follow-up in these states counts toward the next one's number. */
const SENT: ObligationState[] = ["SUBMITTED_PENDING", "ACCEPTED", "SUBMITTED_NO_ACK", "FOLLOW_UP_DUE", "COMPLETE"];
/** A valid submission: a follow-up may follow it (authority_reports/rules.py ``VALID_SUBMISSION``). */
const VALID: ObligationState[] = ["ACCEPTED", "SUBMITTED_NO_ACK", "FOLLOW_UP_DUE", "COMPLETE"];
/** Not yet sent: a follow-up in these states may be cancelled (``CANCELLABLE``). */
const UNSENT: ObligationState[] = ["DRAFT", "CORRECTION_REQUIRED", "APPROVED"];

const today = () => new Date().toLocaleDateString("en-CA"); // yyyy-mm-dd, the person's own day

/**
 * US follow-ups (0.10.96, B3 step B3, 21 CFR 803.56). On a submitted US initial report: the chain (initial, then
 * follow-up #1, #2 …, each with its state) and "Start follow-up #n". On a follow-up: what it follows, its H2 types,
 * what changed since the last report sent (the values its file sends), and Cancel while it is not sent.
 */
export function FollowUps({
  detail,
  canWrite,
  onChanged,
  onOpen,
}: {
  detail: ReportDetail;
  canWrite: boolean;
  onChanged: (detail: ReportDetail) => void;
  onOpen: (id: string) => void;
}) {
  if (detail.follow_up)
    return <FollowUpHead detail={detail} canWrite={canWrite} onChanged={onChanged} onOpen={onOpen} />;
  if (detail.kind !== "INITIAL" || detail.form.code !== "FDA_3500A" || !VALID.includes(detail.state)) return null;
  return <FollowUpChain detail={detail} canWrite={canWrite} onOpen={onOpen} />;
}

function H2Boxes({
  ticked,
  disabled,
  onChange,
}: {
  ticked: string[];
  disabled?: boolean;
  onChange: (next: string[]) => void;
}) {
  return (
    <fieldset className="ca-field ca-wide">
      <legend>H2 · Type of follow-up (tick each that applies)</legend>
      {H2_TYPES.map((type) => (
        <label key={type} className="ca-check">
          <input
            type="checkbox"
            checked={ticked.includes(type)}
            disabled={disabled}
            onChange={(event) =>
              onChange(H2_TYPES.filter((item) => (item === type ? event.target.checked : ticked.includes(item))))
            }
          />{" "}
          {type}
        </label>
      ))}
    </fieldset>
  );
}

function FollowUpChain({
  detail,
  canWrite,
  onOpen,
}: {
  detail: ReportDetail;
  canWrite: boolean;
  onOpen: (id: string) => void;
}) {
  const chain = detail.responses.filter((row) => row.follow_up);
  // The next waits until the last is accepted: one still pending may yet be rejected (authority_reports/router.py).
  const open = chain.find((row) => !VALID.includes(row.state) && row.state !== "CANCELLED");
  const next = 1 + chain.filter((row) => SENT.includes(row.state)).length;
  const [form, setForm] = useState({ received: today(), text: "", narrative: "", h2: [] as string[] });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const start = async () => {
    setBusy(true);
    setError("");
    try {
      const made = await send<ReportDetail>(`${REPORTS}/${detail.id}/follow-ups`, "POST", {
        received_on: form.received,
        what_is_new: form.text,
        h2: form.h2,
        narrative: form.narrative.trim() || null,
      });
      onOpen(made.id);
    } catch (reason) {
      setError(errorText(reason, "The follow-up was not started."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="uw-card uw-card-pad" aria-label="Report chain">
      <h2>Report chain</h2>
      <ol>
        <li>
          <b>Initial report</b> · {detail.state_label}
        </li>
        {chain.map((row) => (
          <li key={row.id}>
            <button type="button" className="ac-link" onClick={() => onOpen(row.id)}>
              <b>Follow-up #{row.follow_up}</b>
            </button>{" "}
            · {row.state_label}
            {row.due_on && !SENT.includes(row.state) && row.state !== "CANCELLED" && ` · due ${formatDate(row.due_on)}`}
          </li>
        ))}
      </ol>
      {canWrite &&
        (open ? (
          <p className="ac-muted">
            Follow-up #{open.follow_up} is open: the next one starts once FDA accepts it (or it is cancelled). FDA takes
            follow-ups in order.
          </p>
        ) : (
          <details>
            <summary>Start follow-up #{next}</summary>
            <p className="ac-muted">
              New or corrected information about this event: the follow-up is due 30 calendar days after it arrived (21
              CFR 803.56). Its file sends only what changed since the last report sent.
            </p>
            <div className="ca-form-grid">
              <label className="ca-field">
                Information received on
                <input
                  type="date"
                  value={form.received}
                  onChange={(event) => setForm({ ...form, received: event.target.value })}
                />
              </label>
              <label className="ca-field ca-wide">
                What is new
                <textarea
                  rows={2}
                  value={form.text}
                  onChange={(event) => setForm({ ...form, text: event.target.value })}
                />
              </label>
              <H2Boxes ticked={form.h2} onChange={(h2) => setForm({ ...form, h2 })} />
              <label className="ca-field ca-wide">
                New narrative for B5 (only what is new; FDA keeps the earlier text)
                <textarea
                  rows={3}
                  value={form.narrative}
                  onChange={(event) => setForm({ ...form, narrative: event.target.value })}
                />
              </label>
            </div>
            <button
              type="button"
              className="ac-primary"
              disabled={busy || !form.received || form.text.trim().length < REASON_MIN}
              onClick={() => void start()}
            >
              Start follow-up #{next}
            </button>
          </details>
        ))}
      <InlineError text={error} />
    </section>
  );
}

function FollowUpHead({
  detail,
  canWrite,
  onChanged,
  onOpen,
}: {
  detail: ReportDetail;
  canWrite: boolean;
  onChanged: (detail: ReportDetail) => void;
  onOpen: (id: string) => void;
}) {
  const action = useAction(onChanged, "That step was not recorded.");
  const [reason, setReason] = useState("");
  const h2 = detail.sections.flatMap((section) => section.fields).find((item) => item.id === "H2");
  const ticked = String(h2?.value ?? "")
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean);
  const changed = detail.emdr?.changed ?? [];
  const cleared = (detail.emdr?.left_out ?? []).filter((line) => line.includes("FDA keeps the earlier value"));
  const base = `${REPORTS}/${detail.id}`;
  return (
    <section className="uw-card uw-card-pad" aria-label={`Follow-up #${detail.follow_up}`}>
      <h2>Follow-up #{detail.follow_up}</h2>
      <p>
        Of the{" "}
        {detail.parent_id ? (
          <button type="button" className="ac-link" onClick={() => onOpen(detail.parent_id!)}>
            initial report
          </button>
        ) : (
          "initial report"
        )}
        {detail.request?.received_on && `, for information received on ${formatDate(detail.request.received_on)}`}.
      </p>
      {detail.request?.text && <p className="ac-muted">What is new: {detail.request.text}</p>}
      <H2Boxes
        ticked={ticked}
        disabled={!canWrite || !detail.editable || action.busy}
        onChange={(next) =>
          void action.run(`${base}/fields/H2`, "PUT", next.length ? { value: next.join("; ") } : { clear: true })
        }
      />
      <h3>What changed since the last report sent</h3>
      {changed.length || cleared.length ? (
        <ul>
          {changed.map((line) => (
            <li key={line}>{line}</li>
          ))}
          {cleared.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : (
        <p className="ac-muted">
          No value FDA holds has changed: the file sends the follow-up's number, its H2 types and any new narrative.
        </p>
      )}
      {canWrite && UNSENT.includes(detail.state) && (
        <details>
          <summary>Cancel this follow-up</summary>
          <p className="ac-muted">
            It was never sent: cancelling frees the chain for the next follow-up, which takes its number.
          </p>
          <label className="ca-field ca-wide">
            Why it is cancelled
            <input value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          <button
            type="button"
            className="ac-secondary"
            disabled={action.busy || reason.trim().length < REASON_MIN}
            onClick={() => void action.run(`${base}/cancel`, "POST", { reason })}
          >
            Cancel follow-up #{detail.follow_up}
          </button>
        </details>
      )}
      <InlineError text={action.error} />
    </section>
  );
}
