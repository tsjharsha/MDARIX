import { useState } from "react";
import { REASON_MIN, REPORTS, type ObligationState, type ReportDetail } from "../authorityReports";
import { errorText, formatDate, send } from "../../customer-admin/shared";
import { useB9Canada, useB9India } from "../workspaceContext";
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

/** The chain's open follow-up: the next waits until the last is accepted (or cancelled); an FDA request that arrives
 * meanwhile is recorded on it (authority_reports/router.py). */
export const openFollowUp = (detail: ReportDetail) =>
  detail.responses.find((row) => row.follow_up && !VALID.includes(row.state) && row.state !== "CANCELLED");

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
  const india = useB9India();
  const canada = useB9Canada();
  // B9: an India or Canada report's chain, shown while its switch is on.
  const market = detail.india_chain ? "india" : detail.canada_chain ? "canada" : null;
  if (market)
    return (market === "india" ? india : canada) ? (
      <MarketChain market={market} detail={detail} canWrite={canWrite} onChanged={onChanged} onOpen={onOpen} />
    ) : null;
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
  const open = openFollowUp(detail);
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
            follow-ups in order. An FDA request that arrives meanwhile is recorded on it.
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
      {!!detail.fda_requests?.length && (
        <>
          <h3>FDA requests recorded on this follow-up</h3>
          <ul>
            {detail.fda_requests.map((row) => (
              <li key={`${row.received_on}-${row.text}`}>
                Received {formatDate(row.received_on)}, response due {formatDate(row.due_on)}: {row.text}
                {!row.h2_ticked &&
                  ' · H2 "Response to FDA request" is not ticked: this follow-up was approved or sent before the request. Reopen it to tick H2, or answer in the next follow-up.'}
              </li>
            ))}
          </ul>
        </>
      )}
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

/** B9's two market chains: India (steps 14-15, on demand only) and Canada (step 11, the Final made by MDARIX). */
const CHAINS = {
  india: {
    path: "india-chain",
    label: "India",
    types: ["Follow up", "Final"],
    box: "P2",
    sentDay: "P1",
    create: "Create a follow-up or final report",
    intro:
      "MvPI asks for follow-up and final reports as the investigation goes on. MDARIX creates one only when you ask.",
    ended: "A Final report ends the chain: nothing follows it.",
    // One open at a time: the next waits until the last is accepted (or cancelled).
    isOpen: (row: ChainItem) => !VALID.includes(row.state),
  },
  canada: {
    path: "canada-chain",
    label: "Canada",
    types: ["Update"],
    box: "A5",
    sentDay: "A6",
    create: "Create an update",
    intro:
      "Send Health Canada an update when the investigation has news before the final report. The final report was created when the preliminary report was recorded as submitted, due on the date it promised.",
    ended: "The final report is submitted (or the first report was Preliminary & Final): nothing follows it.",
    // The Final waits for its date: only an unsent update holds the chain.
    isOpen: (row: ChainItem) => row.type === "Update" && !SENT.includes(row.state),
  },
} as const;
type ChainItem = { id: string; type: string; state: ObligationState; due_on?: string | null };

/**
 * A market's report chain (B9). On the submitted first report: its later reports with their states, and "Create ..."
 * (one open at a time; nothing after the end). On a later report: what it follows, what is new, its date (Canada's
 * Final: the date the preliminary report promised; otherwise the user's own date, no legal clock) and Cancel while
 * unsent.
 */
function MarketChain({
  market,
  detail,
  canWrite,
  onChanged,
  onOpen,
}: {
  market: keyof typeof CHAINS;
  detail: ReportDetail;
  canWrite: boolean;
  onChanged: (detail: ReportDetail) => void;
  onOpen: (id: string) => void;
}) {
  const spec = CHAINS[market];
  const chain = (market === "india" ? detail.india_chain : detail.canada_chain)!;
  const action = useAction(onChanged, "That step was not recorded.");
  const [form, setForm] = useState({ type: spec.types[0] as string, text: "", next: "", reason: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (!chain.items) {
    const name = `${chain.type.toLowerCase()} report`;
    return (
      <section className="uw-card uw-card-pad" aria-label={`${spec.label} ${name}`}>
        <h2>{chain.type} report</h2>
        <p>
          Of the{" "}
          {detail.parent_id ? (
            <button type="button" className="ac-link" onClick={() => onOpen(detail.parent_id!)}>
              first report
            </button>
          ) : (
            "first report"
          )}
          . Box {spec.box} says "{chain.type}"; {spec.sentDay} is filled in with the day it is sent for approval.
        </p>
        {detail.request?.text && <p className="ac-muted">What is new: {detail.request.text}</p>}
        <p className="ac-muted">
          {chain.due_on ? `Due ${formatDate(chain.due_on)}: the date the preliminary report promised (A5). ` : ""}
          {chain.next_report_on ? `Next report planned for ${formatDate(chain.next_report_on)}. ` : ""}
          {chain.note}
          {chain.type === "Final" ? " A Final report ends the chain." : ""}
        </p>
        {canWrite && UNSENT.includes(detail.state) && (
          <details>
            <summary>Cancel this {name}</summary>
            <label className="ca-field ca-wide">
              Why it is cancelled
              <input value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} />
            </label>
            <button
              type="button"
              className="ac-secondary"
              disabled={action.busy || form.reason.trim().length < REASON_MIN}
              onClick={() => void action.run(`${REPORTS}/${detail.id}/cancel`, "POST", { reason: form.reason })}
            >
              Cancel the {name}
            </button>
          </details>
        )}
        <InlineError text={action.error} />
      </section>
    );
  }
  const items: ChainItem[] = chain.items;
  if (!items.length && !chain.can_create && !chain.ended) return null; // not submitted yet: nothing follows it
  const open = items.find(spec.isOpen);
  const create = async () => {
    setBusy(true);
    setError("");
    try {
      const made = await send<ReportDetail>(`${REPORTS}/${detail.id}/${spec.path}`, "POST", {
        type: form.type,
        what_is_new: form.text,
        next_report_on: form.next || null,
      });
      onOpen(made.id);
    } catch (reason) {
      setError(errorText(reason, "The report was not created."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="uw-card uw-card-pad" aria-label={`${spec.label} report chain`}>
      <h2>Report chain</h2>
      <ol>
        <li>
          <b>{chain.type} report</b> · {detail.state_label}
        </li>
        {items.map((row) => (
          <li key={row.id}>
            <button type="button" className="ac-link" onClick={() => onOpen(row.id)}>
              <b>{row.type} report</b>
            </button>{" "}
            · {row.state.toLowerCase().replace(/_/g, " ")}
            {row.due_on && !SENT.includes(row.state) && ` · due ${formatDate(row.due_on)}`}
          </li>
        ))}
      </ol>
      {chain.ended ? (
        <p className="ac-muted">{spec.ended}</p>
      ) : open ? (
        <p className="ac-muted">
          The {open.type.toLowerCase()} report is open: submit or cancel it before the next one.
        </p>
      ) : (
        canWrite &&
        chain.can_create && (
          <details>
            <summary>{spec.create}</summary>
            <p className="ac-muted">
              {spec.intro} No legal clock was found for it: the next-report date is optional and yours.
            </p>
            <p className="ac-muted">{chain.note}</p>
            <div className="ca-form-grid">
              {spec.types.length > 1 && (
                <fieldset className="ca-field">
                  <legend>Type (box {spec.box})</legend>
                  {spec.types.map((type) => (
                    <label key={type} className="ca-check">
                      <input
                        type="radio"
                        name={`${spec.path}-type`}
                        checked={form.type === type}
                        onChange={() => setForm({ ...form, type })}
                      />{" "}
                      {type}
                    </label>
                  ))}
                </fieldset>
              )}
              <label className="ca-field">
                Next report on (optional, your date)
                <input
                  type="date"
                  value={form.next}
                  onChange={(event) => setForm({ ...form, next: event.target.value })}
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
            </div>
            <button
              type="button"
              className="ac-primary"
              disabled={busy || form.text.trim().length < REASON_MIN}
              onClick={() => void create()}
            >
              Create the {form.type.toLowerCase()} report
            </button>
          </details>
        )
      )}
      <InlineError text={error} />
    </section>
  );
}
