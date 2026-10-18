import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight, CheckCircle2, Download, Info, MessageSquare, Send } from "lucide-react";
import { Drawer, errorText, send, useResource } from "../../customer-admin/shared";
import { formatDay } from "../../../app/dates";
import { PUBLISHED_CONTACT, useSiteInfo } from "../../../site/legal";
import {
  CALL_TO_ACTION,
  CHANGES_COLUMNS,
  CHANGES_TITLE,
  CONNECTION,
  CONNECTION_TITLE,
  CUSTOMER_ADMINISTRATOR,
  MVP_REQUEST,
  MVP_STEPS,
  NEXT_STEPS_INTRO,
  PRICE,
  QUESTIONS,
  QUESTIONS_TITLE,
  REAL_DATA_NOTICE,
  START_LEDE,
  START_TITLE,
  TRIAL_TO_MVP,
  WHAT_WE_NEED,
  dataMoveExplanation,
} from "../../help/trialNextSteps";
import "./trialNextSteps.css";

export type MvpRequest = {
  id: string;
  status: "NEW" | "CONTACTED" | "CLOSED" | string;
  expectations: string;
  scope: string | null;
  phone: string | null;
  contact_preference: string | null;
  move_trial_data: boolean;
  requested_by: string | null;
  created_at: string | null;
  updated_at: string | null;
};
export type DataMove = {
  allowed: boolean;
  reason: "SAMPLE_DATA_PRESENT" | "NO_OWN_DATA" | null | string;
  sample_records: number;
  own_records: number;
};
export type MvpRequestState = { request: MvpRequest | null; data_move: DataMove };

export const MVP_REQUEST_PATH = "/api/v1/trial/mvp-request";

/** An open request (new, or the MDARIX team has been in touch): asking again updates it. */
export const isOpenMvpRequest = (request: MvpRequest | null | undefined) =>
  !!request && (request.status === "NEW" || request.status === "CONTACTED");

/** What the organization's request says to it: asked for, or followed up; nothing once it is closed. */
export function mvpRequestText(request: MvpRequest | null | undefined): string | null {
  if (!request) return null;
  const on = request.created_at ? ` on ${formatDay(request.created_at)}` : "";
  if (request.status === "NEW")
    return `You asked for an MVP conversation${on}. The MDARIX team will reply to arrange a scoping call.`;
  if (request.status === "CONTACTED") return `The MDARIX team has been in touch about your MVP (asked${on}).`;
  return null;
}

/** Print every answer: closed details do not print, so they open for the print and close again after it. */
function usePrintOpensDetails() {
  useEffect(() => {
    let opened: HTMLDetailsElement[] = [];
    const before = () => {
      opened = [...document.querySelectorAll<HTMLDetailsElement>(".uw-ns details:not([open])")];
      opened.forEach((item) => (item.open = true));
    };
    const after = () => {
      opened.forEach((item) => (item.open = false));
      opened = [];
    };
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
    };
  }, []);
}

/**
 * Next steps, from trial to MVP (trial workspaces only, for everyone in one): what changes from the trial to the MVP,
 * how the MVP starts, how the data is connected, the Customer Administrator, what MDARIX needs, the price (in a written
 * proposal, never a figure here), common questions, and the request for an MVP conversation. The words are in
 * help/trialNextSteps.ts, shared with the free trial user guide. "Download this page as PDF" is the browser's print
 * (trialNextSteps.css lays the page out for paper), as the trial user guide's "Save as PDF".
 */
export function TrialNextStepsSection() {
  const state = useResource<MvpRequestState>(MVP_REQUEST_PATH);
  const info = useSiteInfo();
  const [asking, setAsking] = useState(false);
  usePrintOpensDetails();
  const support = info?.support_email || PUBLISHED_CONTACT.support;
  const request = state.data?.request ?? null;
  const open = isOpenMvpRequest(request);
  const status = mvpRequestText(request);
  const talk = () => {
    const target = document.getElementById("next-steps-talk");
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
    target?.focus({ preventScroll: true });
  };
  return (
    <div className="uw-ns">
      <section className="uw-ns-intro" aria-labelledby="next-steps-title">
        <p className="uw-ns-eyebrow">{NEXT_STEPS_INTRO.eyebrow}</p>
        <h2 id="next-steps-title">{NEXT_STEPS_INTRO.title}</h2>
        <p className="uw-ns-lede">{NEXT_STEPS_INTRO.lede}</p>
        <div className="uw-ns-actions uw-ns-no-print">
          <button type="button" className="ac-primary" onClick={talk}>
            <MessageSquare size={16} aria-hidden="true" /> {NEXT_STEPS_INTRO.talk}
          </button>
          <button type="button" className="ac-secondary" onClick={() => window.print()}>
            <Download size={16} aria-hidden="true" /> {NEXT_STEPS_INTRO.download}
          </button>
        </div>
      </section>

      <section className="uw-ns-notice" aria-label="Important">
        <Info size={22} aria-hidden="true" />
        <div>
          <strong>{REAL_DATA_NOTICE.title}</strong>
          <p>{REAL_DATA_NOTICE.text}</p>
        </div>
      </section>

      <section className="uw-ns-block" aria-labelledby="next-steps-changes">
        <h2 id="next-steps-changes">{CHANGES_TITLE}</h2>
        <div className="uw-ns-table-wrap">
          <table className="uw-ns-table">
            <thead>
              <tr>
                <td />
                <th scope="col">{CHANGES_COLUMNS.trial}</th>
                <th scope="col" className="is-mvp">
                  {CHANGES_COLUMNS.mvp}
                </th>
              </tr>
            </thead>
            <tbody>
              {TRIAL_TO_MVP.map((row) => (
                <tr key={row.aspect}>
                  <th scope="row">{row.aspect}</th>
                  <td data-label={CHANGES_COLUMNS.trial} className="is-trial">
                    {row.trial}
                  </td>
                  <td data-label={CHANGES_COLUMNS.mvp}>{row.mvp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="uw-ns-block" aria-labelledby="next-steps-start">
        <h2 id="next-steps-start">{START_TITLE}</h2>
        <p className="uw-ns-text">{START_LEDE}</p>
        <ol className="uw-ns-steps">
          {MVP_STEPS.map((step, index) => (
            <li key={step.title} className={index === MVP_STEPS.length - 1 ? "is-start" : undefined}>
              <span className="uw-ns-step-label">{step.label}</span>
              <strong>{step.title}</strong>
              <p>{step.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="uw-ns-block" aria-labelledby="next-steps-connection">
        <h2 id="next-steps-connection">{CONNECTION_TITLE}</h2>
        <ol className="uw-ns-flow">
          {CONNECTION.map((stage, index) => (
            <li key={stage.title} className={index === 1 ? "is-mapping" : undefined}>
              <strong>{stage.title}</strong>
              <p>{stage.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <div className="uw-ns-pair">
        <section className="uw-ns-card" aria-labelledby="next-steps-admin">
          <h2 id="next-steps-admin">{CUSTOMER_ADMINISTRATOR.title}</h2>
          <p className="uw-ns-text">{CUSTOMER_ADMINISTRATOR.lede}</p>
          <ul>
            {CUSTOMER_ADMINISTRATOR.duties.map((duty) => (
              <li key={duty}>{duty}</li>
            ))}
          </ul>
          <p className="uw-ns-small">{CUSTOMER_ADMINISTRATOR.note}</p>
        </section>
        <section className="uw-ns-card" aria-labelledby="next-steps-need">
          <h2 id="next-steps-need">{WHAT_WE_NEED.title}</h2>
          <ul>
            {WHAT_WE_NEED.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      </div>

      <section className="uw-ns-card" aria-labelledby="next-steps-price">
        <h2 id="next-steps-price">{PRICE.title}</h2>
        <p className="uw-ns-text">{PRICE.text}</p>
      </section>

      <section className="uw-ns-block" aria-labelledby="next-steps-questions">
        <h2 id="next-steps-questions">{QUESTIONS_TITLE}</h2>
        {QUESTIONS.map((item) => (
          <details key={item.question} className="uw-ns-question">
            <summary>{item.question}</summary>
            <p>{item.answer}</p>
          </details>
        ))}
      </section>

      <section className="uw-ns-talk" id="next-steps-talk" tabIndex={-1} aria-labelledby="next-steps-talk-title">
        <div>
          <h2 id="next-steps-talk-title">{CALL_TO_ACTION.title}</h2>
          <p>{CALL_TO_ACTION.text}</p>
          {status && (
            <p className="uw-ns-talk-status" role="status">
              <CheckCircle2 size={16} aria-hidden="true" /> {status}
            </p>
          )}
        </div>
        <div className="uw-ns-talk-actions">
          <button
            type="button"
            className="uw-ns-talk-button uw-ns-no-print"
            onClick={() => setAsking(true)}
            disabled={state.state === "loading" && !state.data}
          >
            <Send size={16} aria-hidden="true" /> {open ? "Update your request" : CALL_TO_ACTION.action}
          </button>
          <a href={`mailto:${support}`}>{support}</a>
        </div>
      </section>

      {asking && (
        <MvpRequestForm
          request={open ? request : null}
          dataMove={state.data?.data_move ?? null}
          onClose={() => setAsking(false)}
          onSent={state.reload}
        />
      )}
    </div>
  );
}

/**
 * The request for an MVP conversation: what the organization expects, the products, sites and systems in mind, how to
 * reach the person (optional) and, only when the server says the trial data may move (the sample removed, own data
 * in), whether to move it. Otherwise a short explanation stands in its place. An open request is updated, not doubled.
 */
export function MvpRequestForm({
  request,
  dataMove,
  onClose,
  onSent,
}: {
  request: MvpRequest | null;
  dataMove: DataMove | null;
  onClose: () => void;
  onSent: () => void;
}) {
  const [expectations, setExpectations] = useState(request?.expectations ?? "");
  const [scope, setScope] = useState(request?.scope ?? "");
  const [phone, setPhone] = useState(request?.phone ?? "");
  const [contact, setContact] = useState(request?.contact_preference ?? "");
  const [move, setMove] = useState(!!request?.move_trial_data && !!dataMove?.allowed);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<{ heading: string; text: string } | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (expectations.trim().length < 10) return setError("Tell us in a sentence or two what you expect from the MVP.");
    setBusy(true);
    setError("");
    try {
      const answer = await send<{ status: string; request: MvpRequest }>(MVP_REQUEST_PATH, "POST", {
        expectations: expectations.trim(),
        scope: scope.trim() || null,
        phone: phone.trim() || null,
        contact_preference: contact.trim() || null,
        move_trial_data: !!dataMove?.allowed && move,
      });
      setDone(
        answer.status === "UPDATED"
          ? { heading: "Request updated", text: MVP_REQUEST.updated }
          : { heading: "Request sent", text: MVP_REQUEST.sent },
      );
      onSent();
    } catch (failure) {
      setError(errorText(failure, "Your request was not sent. Please try again."));
    } finally {
      setBusy(false);
    }
  };
  if (done)
    return (
      <Drawer title={MVP_REQUEST.title} onClose={onClose}>
        <section className="ca-drawer-section" role="status">
          <h3>
            <CheckCircle2 size={18} aria-hidden="true" /> {done.heading}
          </h3>
          <p>{done.text}</p>
          <button type="button" className="ac-primary" onClick={onClose}>
            Back to Next steps
          </button>
        </section>
      </Drawer>
    );
  return (
    <Drawer title={MVP_REQUEST.title} onClose={onClose}>
      <form className="ca-form" onSubmit={submit}>
        <section className="ca-drawer-section">
          <p>{MVP_REQUEST.intro}</p>
          <label className="ca-field">
            {MVP_REQUEST.expectations}
            <textarea
              value={expectations}
              required
              minLength={10}
              maxLength={2000}
              rows={4}
              placeholder={MVP_REQUEST.expectationsHint}
              onChange={(event) => setExpectations(event.target.value)}
            />
          </label>
          <label className="ca-field">
            {MVP_REQUEST.scope}
            <textarea
              value={scope}
              maxLength={2000}
              rows={3}
              placeholder={MVP_REQUEST.scopeHint}
              onChange={(event) => setScope(event.target.value)}
            />
          </label>
          <fieldset className="uw-ns-contact">
            <legend>Contact preferences (optional)</legend>
            <label className="ca-field">
              {MVP_REQUEST.phone}
              <input
                value={phone}
                maxLength={30}
                inputMode="tel"
                placeholder="+91 98450 12345"
                onChange={(event) => setPhone(event.target.value)}
              />
            </label>
            <label className="ca-field">
              {MVP_REQUEST.contact}
              <input
                value={contact}
                maxLength={200}
                placeholder={MVP_REQUEST.contactHint}
                onChange={(event) => setContact(event.target.value)}
              />
            </label>
          </fieldset>
          {dataMove?.allowed ? (
            <>
              <label className="ca-check">
                <input type="checkbox" checked={move} onChange={(event) => setMove(event.target.checked)} />{" "}
                {MVP_REQUEST.move}
              </label>
              <p className="ac-muted">{MVP_REQUEST.moveDetail}</p>
            </>
          ) : (
            <p className="uw-ns-move-note">
              <Info size={16} aria-hidden="true" /> <span>{dataMoveExplanation(dataMove?.reason)}</span>
            </p>
          )}
          {error && (
            <p className="uw-flag-critical" role="alert">
              {error}
            </p>
          )}
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy}>
              <ArrowRight size={15} aria-hidden="true" />{" "}
              {busy ? "Sending…" : request ? MVP_REQUEST.update : MVP_REQUEST.send}
            </button>
            <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
              Cancel
            </button>
          </div>
          <p className="ac-muted">{MVP_REQUEST.account}</p>
        </section>
      </form>
    </Drawer>
  );
}
