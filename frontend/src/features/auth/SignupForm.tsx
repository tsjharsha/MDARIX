import React, { useRef, useState } from "react";
import { CheckCircle2 } from "lucide-react";

import {
  COMPANY_SIZES,
  COMPLAINT_SYSTEMS,
  COMPLAINT_VOLUMES,
  DEVICE_CLASSES,
  EMPTY_PROFILE,
  MARKETS,
  TRIAL_DATA,
  signupBody,
  toggleMarket,
  type Option,
  type TrialProfile,
} from "./trialProfile";

/** Answers whose problems are fixed on the first step: a refusal for one of them takes the person back there. */
const STEP_ONE_CODES = new Set([
  "JOB_TITLE_REQUIRED",
  "COUNTRY_REQUIRED",
  "VALID_EMAIL_REQUIRED",
  "VALID_PHONE_REQUIRED",
]);

const MESSAGES: Record<string, string> = {
  RATE_LIMITED: "Too many attempts. Please wait a few minutes and try again.",
  VALID_EMAIL_REQUIRED: "Enter a valid work email.",
};

function Choice({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Option[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="auth-field">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Choose…</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/**
 * The free-trial request, in two short steps: who you are (required), then your trial (optional details and the
 * no-patient-data confirmation). No password is asked for: the requester sets it from the invitation email and MDARIX
 * staff never see it. POST /api/v1/auth/signup answers the same for new and known emails.
 */
export function SignupForm() {
  const [step, setStep] = useState<1 | 2>(1);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [profile, setProfile] = useState<TrialProfile>(EMPTY_PROFILE);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [message, setMessage] = useState("");
  const stepOne = useRef<HTMLFieldSetElement>(null);
  const answer =
    <K extends keyof TrialProfile>(key: K) =>
    (value: TrialProfile[K]) =>
      setProfile((current) => ({ ...current, [key]: value }));

  const next = () => {
    if (stepOne.current?.reportValidity()) {
      setMessage("");
      setStep(2);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (step === 1) return next();
    if (busy) return;
    setBusy(true);
    setMessage("");
    try {
      let response: Response;
      try {
        response = await fetch("/api/v1/auth/signup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(signupBody(email, name, company, profile)),
        });
      } catch {
        setMessage("MDARIX cannot be reached right now. Check your connection and try again.");
        return;
      }
      const data = await response.json().catch(() => null);
      if (data === null) {
        setMessage("MDARIX is not responding right now. Please try again in a moment.");
        return;
      }
      if (!response.ok) {
        const code: string | undefined = data.detail?.code;
        if (code && STEP_ONE_CODES.has(code)) setStep(1);
        setMessage((code && MESSAGES[code]) || data.detail?.message || "The request could not be completed.");
        return;
      }
      setDone(true);
    } finally {
      setBusy(false);
    }
  };

  if (done)
    return (
      <div className="auth-card su-card su-done" role="status">
        <CheckCircle2 size={40} aria-hidden="true" />
        <h1>Request received</h1>
        <p className="auth-lead">
          Thank you. We review every request, usually within one business day, and email <strong>{email}</strong> an
          invitation once it is approved.
        </p>
        <ol className="su-next">
          <li>We review your request and prepare your workspace with sample data.</li>
          <li>You set your own password from the invitation email. MDARIX never sees it.</li>
          <li>You sign in, explore the sample investigation, then upload your own exports.</li>
        </ol>
        <a className="su-secondary" href="/">
          Back to website
        </a>
      </div>
    );

  return (
    <form className="auth-card su-card" onSubmit={submit}>
      <span className="eyebrow">Request access</span>
      <h1>Start your free trial</h1>
      <p className="auth-lead">
        30 days, up to 3 users and 5,000 records, no credit card. You set your own password from the invitation email;
        MDARIX never sees it.
      </p>
      <ol className="su-steps" aria-label="Request steps">
        <li className={step === 1 ? "is-current" : "is-done"} aria-current={step === 1 ? "step" : undefined}>
          <span>1</span> About you
        </li>
        <li className={step === 2 ? "is-current" : ""} aria-current={step === 2 ? "step" : undefined}>
          <span>2</span> Your trial
        </li>
      </ol>

      {step === 1 ? (
        <fieldset className="su-fields" ref={stepOne}>
          <legend className="su-legend">About you</legend>
          <label className="auth-field">
            Full name
            <input
              required
              maxLength={120}
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="auth-field">
            Job title
            <input
              required
              maxLength={120}
              autoComplete="organization-title"
              value={profile.jobTitle}
              onChange={(e) => answer("jobTitle")(e.target.value)}
            />
          </label>
          <label className="auth-field su-wide">
            Work email
            <input
              required
              type="email"
              maxLength={254}
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className="auth-field">
            Company
            <input
              required
              maxLength={160}
              autoComplete="organization"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
            />
          </label>
          <label className="auth-field">
            Country
            <input
              required
              maxLength={80}
              autoComplete="country-name"
              value={profile.country}
              onChange={(e) => answer("country")(e.target.value)}
            />
          </label>
          <label className="auth-field su-wide">
            <span>
              Phone <small>(optional)</small>
            </span>
            <input
              type="tel"
              maxLength={30}
              autoComplete="tel"
              value={profile.phone}
              onChange={(e) => answer("phone")(e.target.value)}
            />
          </label>
          <button className="primary-action su-wide" type="button" onClick={next}>
            Continue
          </button>
        </fieldset>
      ) : (
        <fieldset className="su-fields">
          <legend className="su-legend">Your trial</legend>
          <p className="su-hint su-wide">
            Optional: these answers help us prepare sample data and checks that match your devices.
          </p>
          <Choice
            label="Company size"
            value={profile.companySize}
            options={COMPANY_SIZES}
            onChange={answer("companySize")}
          />
          <Choice
            label="Highest device class"
            value={profile.deviceClass}
            options={DEVICE_CLASSES}
            onChange={answer("deviceClass")}
          />
          <label className="auth-field su-wide">
            Devices you make
            <input
              maxLength={200}
              placeholder="For example: infusion pumps, patient monitors"
              value={profile.deviceTypes}
              onChange={(e) => answer("deviceTypes")(e.target.value)}
            />
          </label>
          <div className="auth-field su-wide" role="group" aria-labelledby="su-markets">
            <span id="su-markets">Markets you sell in</span>
            <div className="auth-checks">
              {MARKETS.map((market) => (
                <label key={market.value} className="auth-check">
                  <input
                    type="checkbox"
                    checked={profile.markets.includes(market.value)}
                    onChange={() => answer("markets")(toggleMarket(profile.markets, market.value))}
                  />
                  {market.label}
                </label>
              ))}
            </div>
          </div>
          <Choice
            label="Where complaints are handled today"
            value={profile.complaintSystem}
            options={COMPLAINT_SYSTEMS}
            onChange={answer("complaintSystem")}
          />
          <Choice
            label="Complaints received"
            value={profile.complaintVolume}
            options={COMPLAINT_VOLUMES}
            onChange={answer("complaintVolume")}
          />
          <div className="su-wide">
            <Choice
              label="Data you plan to use in the trial"
              value={profile.trialData}
              options={TRIAL_DATA}
              onChange={answer("trialData")}
            />
          </div>
          <label className="auth-field su-wide">
            What would you like to evaluate?
            <textarea
              rows={3}
              maxLength={1000}
              placeholder="For example: faster complaint trending, CAPA effectiveness evidence"
              value={profile.evaluationGoal}
              onChange={(e) => answer("evaluationGoal")(e.target.value)}
            />
          </label>
          <label className="auth-check auth-check-required su-wide su-confirm">
            <input
              type="checkbox"
              required
              checked={profile.noPatientData}
              onChange={(e) => answer("noPatientData")(e.target.checked)}
            />
            We will not upload patient-identifiable data during the trial.
          </label>
          <p className="auth-consent su-wide">
            By requesting a trial you agree to the <a href="/terms">Terms of Service</a> and the{" "}
            <a href="/trial-agreement">Free Trial Agreement</a>, and acknowledge the{" "}
            <a href="/privacy">Privacy Policy</a>. Trial data is deleted 30 days after the trial ends unless you
            continue.
          </p>
          <div className="su-actions su-wide">
            <button className="su-secondary" type="button" onClick={() => setStep(1)} disabled={busy}>
              Back
            </button>
            <button className="primary-action" type="submit" disabled={busy}>
              {busy ? "Sending…" : "Request free trial"}
            </button>
          </div>
        </fieldset>
      )}

      {message && (
        <p className="su-message" role="alert">
          {message}
        </p>
      )}
      <p className="auth-links">
        Already have an account? <a href="/signin">Sign in</a>
      </p>
    </form>
  );
}
