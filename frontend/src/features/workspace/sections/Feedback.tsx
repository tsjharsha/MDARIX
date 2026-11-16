import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { CheckCircle2, MessageSquareText, Star, X } from "lucide-react";
import { ApiError, describeError, requestJson } from "../../../app/apiClient";
import { Panel } from "../../admin/console/charts";
import { useFeatureSet, useWorkspace } from "../workspaceContext";
import { useAiReady } from "../useAiStatus";
import { formatDay } from "../../../app/dates";
import type { FeatureSet } from "../../../app/featureSet";

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
// The ratings and the parts of MDARIX that are about AI: asked only while AI answers for the organization.
const AI_RATINGS = new Set(["rating_ai_trust"]);
const AI_FEATURES = new Set(["ASK_MDARIX"]);
// The screens as each feature set offers them (app/featureSet.ts): the full product, or the lightweight MVP's screens
// with Getting started (trials) and Import data. Product 360 and the evidence library are parked in the MVP.
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
const MVP_FEATURES: [string, string][] = [
  ["GETTING_STARTED", "Getting started (sample data and automatic insights)"],
  ["READINESS", "Readiness"],
  ["COMPLAINTS", "Complaints (second look, backlog, reportability)"],
  ["SIGNALS", "Signals and trend check"],
  ["INVESTIGATIONS", "Investigations"],
  ["ASK_MDARIX", "Ask MDARIX"],
  ["DECISIONS", "Decisions and sign-off"],
  ["RECORDS", "Records (effectiveness checks, risk file input, audit trail, reports)"],
  ["CSV_IMPORT", "Import data (CSV templates)"],
];

/**
 * What the form asks about: the screens this organization sees, and nothing about AI unless AI answers for it (an
 * organization with AI off is not asked to rate AI answers it never saw). Exported for tests.
 */
export function feedbackChoices({
  featureSet,
  aiReady,
  isTrial,
}: {
  featureSet: FeatureSet;
  aiReady: boolean | null;
  isTrial: boolean;
}): { ratings: [string, string][]; features: [string, string][] } {
  const ai = aiReady === true;
  const features = (featureSet === "mvp" ? MVP_FEATURES : FEATURES).filter(
    ([value]) => (ai || !AI_FEATURES.has(value)) && (isTrial || value !== "GETTING_STARTED"),
  );
  return { ratings: RATINGS.filter(([key]) => ai || !AI_RATINGS.has(key)), features };
}
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

// Ask once people have had time to form a view: from day 3 of the trial, or once its own data is imported. And never
// in a person's first 2 days: a colleague invited on day 5 is not asked on their first screen (UX-26).
const ASK_AFTER_DAYS = 3;
const PERSON_ASK_AFTER_DAYS = 2;

type FeedbackTiming = {
  starts_at?: string;
  own_data?: { products: number; lots: number; complaints: number };
  /** When this person first signed in (GET /api/v1/trial/status, backend/app/trial/team.py person). */
  me?: { joined_at?: string | null } | null;
};

const daysSince = (value: string | null | undefined, now: number) => {
  const at = value ? Date.parse(value) : NaN;
  return Number.isFinite(at) ? (now - at) / (24 * 3600 * 1000) : 0;
};

/** Whether to ask for feedback yet: not on a person's first days, only after real use (exported for tests). Without
 * the person's own date (an older server) the trial's start stands in for it. */
export function readyForFeedback(status: FeedbackTiming, now = Date.now()): boolean {
  const trialDays = daysSince(status.starts_at, now);
  const personDays = daysSince(status.me?.joined_at ?? status.starts_at, now);
  if (personDays < PERSON_ASK_AFTER_DAYS) return false;
  const own = status.own_data ?? { products: 0, lots: 0, complaints: 0 };
  return trialDays >= ASK_AFTER_DAYS || own.products + own.lots + own.complaints > 0;
}

const SESSION_KEY = "mdarix.session.started";
const QUIET_MINUTES = 10;

/** Whether this browser session began less than 10 minutes ago: no feedback ask while someone is still finding their
 * way (or giving a demo). The first call marks the session's start. Exported for tests. */
export function quietStart(store: () => Pick<Storage, "getItem" | "setItem">, now = Date.now()): boolean {
  try {
    const storage = store();
    const started = Number(storage.getItem(SESSION_KEY) ?? 0);
    if (!started) storage.setItem(SESSION_KEY, String(now));
    return now - (started || now) < QUIET_MINUTES * 60 * 1000;
  } catch {
    return false;
  }
}

/** Invitation shown across the trial workspace until the person has given feedback (or chose "Not now"). */
export function FeedbackPrompt({ onOpen }: { onOpen: () => void }) {
  const [state, setState] = useState<"hidden" | "shown">("hidden");
  useEffect(() => {
    if (quietStart(() => window.sessionStorage)) return;
    let until = 0;
    try {
      until = Number(window.localStorage.getItem(DISMISSED_KEY) ?? 0);
    } catch {
      until = 0;
    }
    if (until > Date.now()) return;
    Promise.all([
      requestJson<FeedbackForm>("/api/v1/trial/feedback"),
      requestJson<FeedbackTiming>("/api/v1/trial/status"),
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
  const choices = feedbackChoices({ featureSet: useFeatureSet(), aiReady: useAiReady(), isTrial });

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
          // Only what the form asked: a rating or a part hidden since (AI switched off) is not sent.
          ...Object.fromEntries(choices.ratings.map(([key]) => [key, answers.ratings[key]])),
          recommend_score: answers.recommend_score,
          features_used: answers.features_used.filter((value) => choices.features.some(([shown]) => shown === value)),
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
          {choices.ratings.map(([key, label]) => (
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
          {choices.features.map(([value, label]) => (
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
              ["NAMED", `Yes, with my job title and my company's name: ${company}`],
              ["ANONYMOUS", "Yes, anonymously, without my name or my company's name"],
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
