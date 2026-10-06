import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { CheckCircle2, MessageSquareText, Star, X } from "lucide-react";
import { ApiError, describeError, requestJson } from "../../../app/apiClient";
import { Panel } from "../../admin/console/charts";
import { useWorkspace } from "../workspaceContext";
import { formatDay } from "../../../app/dates";

type Consent = "NAMED" | "ANONYMOUS" | "PRIVATE";
type Submission = {
  id: string;
  created_at: string;
  rating_overall: number;
  publish_consent: Consent;
  publication_status: "NOT_REQUESTED" | "PENDING" | "PUBLISHED" | "HIDDEN";
  quote: string | null;
};
type FeedbackForm = {
  organization_name: string;
  consent_wording: Record<Consent, string>;
  anonymous_attribution: string;
  role_areas: Record<string, string>;
  submissions: Submission[];
};

const RATINGS: [string, string][] = [
  ["rating_overall", "Overall experience"],
  ["rating_ease", "Ease of use"],
  ["rating_usefulness", "Usefulness for your investigations"],
  ["rating_ai_trust", "Trust in AI answers and their evidence"],
  ["rating_speed", "Speed"],
  ["rating_import", "Importing your own data (CSV templates)"],
];
const FEATURES: [string, string][] = [
  ["PRODUCT_360", "Product 360"],
  ["SIGNALS", "Signals and complaints"],
  ["INVESTIGATIONS", "Investigations"],
  ["ASK_MDARIX", "Ask MDARIX"],
  ["EVIDENCE", "Evidence library"],
  ["DECISIONS", "Decisions and sign-off"],
  ["CSV_IMPORT", "CSV import"],
  ["AUDIT_TRAIL", "Audit trail"],
];
const ADOPTION: [string, string][] = [
  ["YES", "Yes"],
  ["MAYBE", "Maybe"],
  ["NO", "No"],
  ["NOT_MY_DECISION", "Not my decision"],
];
const STATUS: Record<Submission["publication_status"], string> = {
  NOT_REQUESTED: "Private to the MDARIX team",
  PENDING: "Waiting for review before it is shown",
  PUBLISHED: "Shown on the MDARIX website",
  HIDDEN: "Reviewed; not shown",
};

const DISMISSED_KEY = "mdarix.trial.feedback-dismissed-until";

// Ask once people have had time to form a view: from day 3 of the trial, or as soon as they import their own data.
const ASK_AFTER_DAYS = 3;

/** Whether to ask for feedback yet: not on a first visit, only after real use (exported for tests). */
export function readyForFeedback(
  status: { starts_at?: string; own_data?: { products: number; lots: number; complaints: number } },
  now = Date.now(),
): boolean {
  const started = status.starts_at ? Date.parse(status.starts_at) : NaN;
  const days = Number.isFinite(started) ? (now - started) / (24 * 3600 * 1000) : 0;
  const own = status.own_data ?? { products: 0, lots: 0, complaints: 0 };
  return days >= ASK_AFTER_DAYS || own.products + own.lots + own.complaints > 0;
}

/** Invitation shown across the trial workspace until the person has given feedback (or chose "Not now"). */
export function FeedbackPrompt({ onOpen }: { onOpen: () => void }) {
  const [state, setState] = useState<"hidden" | "shown">("hidden");
  useEffect(() => {
    let until = 0;
    try {
      until = Number(window.localStorage.getItem(DISMISSED_KEY) ?? 0);
    } catch {
      until = 0;
    }
    if (until > Date.now()) return;
    Promise.all([
      requestJson<FeedbackForm>("/api/v1/trial/feedback"),
      requestJson<{ starts_at?: string; own_data?: { products: number; lots: number; complaints: number } }>(
        "/api/v1/trial/status",
      ),
    ])
      .then(([data, status]) => setState(!data.submissions.length && readyForFeedback(status) ? "shown" : "hidden"))
      .catch(() => setState("hidden"));
  }, []);
  if (state === "hidden") return null;
  const later = () => {
    try {
      window.localStorage.setItem(DISMISSED_KEY, String(Date.now() + 3 * 24 * 3600 * 1000));
    } catch {
      // Without storage the prompt simply returns on the next visit.
    }
    setState("hidden");
  };
  return (
    <aside className="uw-feedback-prompt" aria-label="Feedback request">
      <MessageSquareText size={22} aria-hidden="true" />
      <div>
        <strong>How is your MDARIX trial going?</strong>
        <p>Tell us what works and what to improve. It takes about three minutes and shapes what we build next.</p>
      </div>
      <button type="button" className="ac-primary" onClick={onOpen}>
        Give feedback
      </button>
      <button type="button" className="ac-link" onClick={later} aria-label="Not now; remind me in a few days">
        <X size={16} aria-hidden="true" /> Not now
      </button>
    </aside>
  );
}

function Stars({
  name,
  label,
  value,
  required,
  onChange,
}: {
  name: string;
  label: string;
  value: number | null;
  required?: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <fieldset className="uw-fb-rating">
      <legend>
        {label}
        {required && <span className="uw-fb-required"> (required)</span>}
      </legend>
      <div className="uw-fb-stars">
        {[1, 2, 3, 4, 5].map((score) => (
          <label key={score} title={`${score} of 5`}>
            <input
              type="radio"
              name={name}
              value={score}
              checked={value === score}
              required={required}
              onChange={() => onChange(score)}
            />
            <Star size={22} aria-hidden="true" className={value !== null && score <= value ? "is-on" : ""} />
            <span className="ca-sr-only">{score} of 5</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function Question({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="uw-fb-question">
      <h3>{title}</h3>
      {hint && <p className="uw-fb-hint">{hint}</p>}
      {children}
    </section>
  );
}

type Answers = {
  role_area: string;
  job_title: string;
  ratings: Record<string, number | null>;
  recommend_score: number | null;
  features_used: string[];
  liked: string;
  improve: string;
  missing: string;
  adoption: string;
  quote: string;
  publish_consent: Consent | "";
  contact_ok: boolean;
};
const EMPTY: Answers = {
  role_area: "",
  job_title: "",
  ratings: Object.fromEntries(RATINGS.map(([key]) => [key, null])),
  recommend_score: null,
  features_used: [],
  liked: "",
  improve: "",
  missing: "",
  adoption: "",
  quote: "",
  publish_consent: "",
  contact_ok: false,
};

/** The feedback questionnaire: open to every organization (the routes keep their original "trial" names). */
export function FeedbackSection({ isTrial = false }: { isTrial?: boolean }) {
  const { notify } = useWorkspace();
  const [form, setForm] = useState<FeedbackForm | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [answers, setAnswers] = useState<Answers>(EMPTY);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [writing, setWriting] = useState(false);
  const [loadError, setLoadError] = useState<{ message: string; requestId?: string }>({ message: "" });

  const load = () =>
    requestJson<FeedbackForm>("/api/v1/trial/feedback")
      .then((data) => {
        setForm(data);
        setState("ready");
      })
      .catch((failure) => {
        setLoadError({
          message: failure instanceof Error ? failure.message : "Feedback is not available.",
          requestId: failure instanceof ApiError ? failure.requestId : undefined,
        });
        setState("error");
      });
  useEffect(() => {
    void load();
  }, []);

  const set = <K extends keyof Answers>(key: K, value: Answers[K]) =>
    setAnswers((current) => ({ ...current, [key]: value }));
  const publishing = answers.publish_consent === "NAMED" || answers.publish_consent === "ANONYMOUS";

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    if (!answers.ratings.rating_overall) return setError("Rate your overall experience.");
    if (!answers.publish_consent) return setError("Choose how we may use your feedback.");
    if (publishing && !answers.quote.trim())
      return setError("Write the quote we may show, or choose to keep your feedback private.");
    setSending(true);
    try {
      await requestJson("/api/v1/trial/feedback", {
        method: "POST",
        body: JSON.stringify({
          role_area: answers.role_area || null,
          job_title: answers.job_title || null,
          ...answers.ratings,
          recommend_score: answers.recommend_score,
          features_used: answers.features_used,
          liked: answers.liked || null,
          improve: answers.improve || null,
          missing: answers.missing || null,
          adoption: answers.adoption || null,
          quote: publishing ? answers.quote : null,
          publish_consent: answers.publish_consent,
          contact_ok: answers.contact_ok,
        }),
      });
      setAnswers(EMPTY);
      setWriting(false);
      notify("Thank you. Your feedback has reached the MDARIX team.");
      await load();
      window.scrollTo({ top: 0 });
    } catch (failure) {
      setError(describeError(failure, "Your feedback could not be sent. Please try again."));
    } finally {
      setSending(false);
    }
  };

  const withdraw = async (submission: Submission) => {
    try {
      await requestJson(`/api/v1/trial/feedback/${submission.id}/withdraw-consent`, { method: "POST" });
      notify("Consent withdrawn. Your feedback is now private to the MDARIX team and is not shown anywhere.");
      await load();
    } catch (failure) {
      notify(describeError(failure, "Consent could not be withdrawn."), "critical");
    }
  };

  if (state !== "ready" || !form)
    return (
      <Panel
        title="Share feedback"
        state={state === "error" ? "error" : "loading"}
        error={loadError.message || "Feedback is not available."}
        requestId={loadError.requestId}
        onRetry={() => {
          setState("loading");
          void load();
        }}
      >
        <span />
      </Panel>
    );

  const company = form.organization_name;
  if (form.submissions.length && !writing)
    return (
      <div className="uw-fb">
        <Panel eyebrow="Thank you" title="Your feedback">
          <p className="uw-fb-lead">
            <CheckCircle2 size={18} aria-hidden="true" className="ac-tone-icon tone-good" /> The MDARIX team reads every
            response. If you agreed to be contacted, we may get in touch to learn more.
          </p>
          <ul className="uw-fb-sent">
            {form.submissions.map((submission) => (
              <li key={submission.id}>
                <div>
                  <strong>
                    Sent {formatDay(submission.created_at)} · overall {submission.rating_overall}/5
                  </strong>
                  <span>
                    {submission.publish_consent === "NAMED"
                      ? `May be shown with ${company}`
                      : submission.publish_consent === "ANONYMOUS"
                        ? `May be shown anonymously, as "a ${form.anonymous_attribution}"`
                        : "Private"}{" "}
                    · {STATUS[submission.publication_status]}
                  </span>
                  {submission.quote && <q>{submission.quote}</q>}
                </div>
                {submission.publish_consent !== "PRIVATE" && (
                  <button type="button" className="ac-secondary" onClick={() => void withdraw(submission)}>
                    Withdraw website consent
                  </button>
                )}
              </li>
            ))}
          </ul>
          <button type="button" className="ac-primary" onClick={() => setWriting(true)}>
            Send more feedback
          </button>
        </Panel>
      </div>
    );

  return (
    <form className="uw-fb" onSubmit={submit} noValidate>
      <Panel eyebrow={isTrial ? "Your trial" : "Your experience"} title="Tell us about MDARIX">
        <p className="uw-fb-lead">
          About three minutes. Only the overall rating and the last question are required; answer whatever else you
          like. Your answers go to the MDARIX team.
        </p>
      </Panel>

      <Panel eyebrow="1 of 5" title="About you">
        <div className="uw-fb-grid">
          <label>
            Your area
            <select value={answers.role_area} onChange={(event) => set("role_area", event.target.value)}>
              <option value="">Choose…</option>
              {Object.entries(form.role_areas).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Job title <span className="uw-fb-optional">(optional)</span>
            <input
              value={answers.job_title}
              maxLength={120}
              placeholder="e.g. Director of Quality"
              onChange={(event) => set("job_title", event.target.value)}
            />
          </label>
        </div>
      </Panel>

      <Panel eyebrow="2 of 5" title="Rate your experience">
        <div className="uw-fb-ratings">
          {RATINGS.map(([key, label]) => (
            <Stars
              key={key}
              name={key}
              label={label}
              required={key === "rating_overall"}
              value={answers.ratings[key]}
              onChange={(value) => set("ratings", { ...answers.ratings, [key]: value })}
            />
          ))}
        </div>
        <fieldset className="uw-fb-rating">
          <legend>How likely are you to recommend MDARIX to a colleague? (0 = not at all, 10 = extremely)</legend>
          <div className="uw-fb-scale">
            {Array.from({ length: 11 }, (_, score) => (
              <label key={score} className={answers.recommend_score === score ? "is-on" : ""}>
                <input
                  type="radio"
                  name="recommend_score"
                  value={score}
                  checked={answers.recommend_score === score}
                  onChange={() => set("recommend_score", score)}
                />
                {score}
              </label>
            ))}
          </div>
        </fieldset>
      </Panel>

      <Panel eyebrow="3 of 5" title="What you tried">
        <fieldset className="uw-fb-checks">
          <legend>Which parts of MDARIX did you use?</legend>
          {FEATURES.map(([value, label]) => (
            <label key={value}>
              <input
                type="checkbox"
                checked={answers.features_used.includes(value)}
                onChange={(event) =>
                  set(
                    "features_used",
                    event.target.checked
                      ? [...answers.features_used, value]
                      : answers.features_used.filter((item) => item !== value),
                  )
                }
              />
              {label}
            </label>
          ))}
        </fieldset>
        <fieldset className="uw-fb-checks">
          <legend>
            {isTrial ? "Would your team use MDARIX after the trial?" : "Would your team keep using MDARIX?"}
          </legend>
          {ADOPTION.map(([value, label]) => (
            <label key={value}>
              <input
                type="radio"
                name="adoption"
                checked={answers.adoption === value}
                onChange={() => set("adoption", value)}
              />
              {label}
            </label>
          ))}
        </fieldset>
      </Panel>

      <Panel eyebrow="4 of 5" title="What is good, what to improve">
        <Question title="What did you like most?">
          <textarea
            aria-label="What did you like most?"
            maxLength={2000}
            rows={3}
            value={answers.liked}
            onChange={(event) => set("liked", event.target.value)}
          />
        </Question>
        <Question title="What should we improve?" hint="Anything confusing, slow or missing a step.">
          <textarea
            aria-label="What should we improve?"
            maxLength={2000}
            rows={3}
            value={answers.improve}
            onChange={(event) => set("improve", event.target.value)}
          />
        </Question>
        <Question title="What would you need before using it every day?">
          <textarea
            aria-label="What would you need before using it every day?"
            maxLength={2000}
            rows={3}
            value={answers.missing}
            onChange={(event) => set("missing", event.target.value)}
          />
        </Question>
      </Panel>

      <Panel eyebrow="5 of 5" title="May we share your feedback?">
        <fieldset className="uw-fb-consent">
          <legend>
            Choose how MDARIX may use your words on its website. <span className="uw-fb-required">(required)</span>
          </legend>
          {(
            [
              ["NAMED", `Yes, with my company's name: ${company}`],
              ["ANONYMOUS", "Yes, anonymously, without naming my company"],
              ["PRIVATE", "No, keep my feedback private to the MDARIX team"],
            ] as [Consent, string][]
          ).map(([value, label]) => (
            <label key={value} className={answers.publish_consent === value ? "is-on" : ""}>
              <input
                type="radio"
                name="publish_consent"
                checked={answers.publish_consent === value}
                onChange={() => set("publish_consent", value)}
              />
              <span>
                <strong>{label}</strong>
                <small>{form.consent_wording[value]}</small>
              </span>
            </label>
          ))}
        </fieldset>
        {publishing && (
          <Question
            title="The quote we may show"
            hint={
              answers.publish_consent === "ANONYMOUS"
                ? `Shown as "a ${form.anonymous_attribution}". Leave out your company's and colleagues' names.`
                : `Shown with ${company}${answers.job_title ? ` and your title, ${answers.job_title}` : ""}.`
            }
          >
            <textarea
              aria-label="The quote we may show"
              required
              maxLength={400}
              rows={3}
              value={answers.quote}
              placeholder="One or two sentences about what MDARIX did for you."
              onChange={(event) => set("quote", event.target.value)}
            />
            <small className="uw-fb-hint">{answers.quote.length}/400</small>
          </Question>
        )}
        <label className="uw-fb-contact">
          <input
            type="checkbox"
            checked={answers.contact_ok}
            onChange={(event) => set("contact_ok", event.target.checked)}
          />
          The MDARIX team may contact me about this feedback.
        </label>
        <p className="uw-fb-hint">
          Nothing is shown publicly until the MDARIX team has reviewed it. You can withdraw your consent at any time
          from this page.
        </p>
        {error && (
          <p className="uw-trial-message is-bad" role="alert">
            {error}
          </p>
        )}
        <div className="uw-fb-actions">
          <button type="submit" className="ac-primary" disabled={sending}>
            {sending ? "Sending…" : "Send feedback"}
          </button>
          {form.submissions.length > 0 && (
            <button type="button" className="ac-secondary" onClick={() => setWriting(false)}>
              Cancel
            </button>
          )}
        </div>
      </Panel>
    </form>
  );
}
