import React, { useMemo, useRef, useState } from "react";
import { CheckCircle2 } from "lucide-react";

import {
  COMPANY_SIZES,
  COMPLAINT_SYSTEMS,
  COMPLAINT_VOLUMES,
  DEVICE_CLASSES,
  EMPTY_PROFILE,
  MARKETS,
  TRIAL_DATA,
  countries,
  isInternationalPhone,
  phoneWithDialCode,
  signupBody,
  toggleMarket,
  type Option,
  type TrialProfile,
} from "./trialProfile";
import { TRIAL_GUIDE_PATH } from "../help/trialGuide";

/** Answers whose problems are fixed on the first step: a refusal for one of them takes the person back there. */
const STEP_ONE_CODES = new Set([
  "JOB_TITLE_REQUIRED",
  "COUNTRY_REQUIRED",
  "VALID_EMAIL_REQUIRED",
  "VALID_PHONE_REQUIRED",
  "EMAIL_ALREADY_REGISTERED",
  "TRIAL_ALREADY_REQUESTED",
]);

const MESSAGES: Record<string, string> = {
  RATE_LIMITED: "Too many attempts. Please wait a few minutes and try again.",
  VALID_EMAIL_REQUIRED: "Enter a valid work email.",
};

const PHONE_HINT = "International format: + country code and number, for example +91 98765 43210.";

/** The asterisk of a required field (the input itself carries `required`, which screen readers announce). */
function Req() {
  return (
    <span className="su-req" aria-hidden="true">
      *
    </span>
  );
}

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
 * The free-trial request, in two short steps: who you are, then your trial. Required fields carry an asterisk. No
 * password is asked for: the requester sets it from the invitation email and MDARIX staff never see it. An email that
 * already has an account is told so, with Sign in and Reset password at hand.
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
  const [problem, setProblem] = useState("");
  const stepOne = useRef<HTMLFieldSetElement>(null);
  const phoneInput = useRef<HTMLInputElement>(null);
  const allCountries = useMemo(() => countries(), []);
  const answer =
    <K extends keyof TrialProfile>(key: K) =>
    (value: TrialProfile[K]) =>
      setProfile((current) => ({ ...current, [key]: value }));

  const chooseCountry = (countryName: string) => {
    const chosen = allCountries.find((country) => country.name === countryName);
    setProfile((current) => ({
      ...current,
      country: countryName,
      phone: chosen ? phoneWithDialCode(current.phone, chosen.dial) : current.phone,
    }));
  };

  const next = () => {
    phoneInput.current?.setCustomValidity(isInternationalPhone(profile.phone) ? "" : PHONE_HINT);
    // A fieldset always reports itself valid (it is not a candidate for constraint validation): each field is checked,
    // and the first one with a problem says so.
    const fields = Array.from(
      stepOne.current?.querySelectorAll<HTMLInputElement | HTMLSelectElement>("input, select") ?? [],
    );
    const invalid = fields.find((field) => !field.checkValidity());
    if (invalid) {
      invalid.reportValidity();
      return;
    }
    setMessage("");
    setProblem("");
    setStep(2);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (step === 1) return next();
    if (busy) return;
    setBusy(true);
    setMessage("");
    setProblem("");
    try {
      let response: Response;
      try {
        response = await fetch("/api/v1/auth/signup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(signupBody(email, name, company, { ...profile, phone: profile.phone.trim() })),
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
        const code: string = data.detail?.code ?? "";
        if (STEP_ONE_CODES.has(code)) setStep(1);
        setProblem(code);
        setMessage(MESSAGES[code] || data.detail?.message || "The request could not be completed.");
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
        <a className="primary-action" href={TRIAL_GUIDE_PATH} target="_blank" rel="noopener">
          Read the free trial user guide
        </a>
        <a className="su-secondary" href="/">
          Back to website
        </a>
      </div>
    );

  const alert = message && (
    <div className="su-message" role="alert">
      <p>{message}</p>
      {problem === "EMAIL_ALREADY_REGISTERED" && (
        <p className="su-message-actions">
          <a href={`/signin?email=${encodeURIComponent(email)}`}>Sign in</a>
          <a href="/forgot-password">Reset password</a>
        </p>
      )}
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
      <p className="su-required-note">
        Fields marked <span className="su-req">*</span> are required.
      </p>

      {step === 1 ? (
        <fieldset className="su-fields" ref={stepOne}>
          <legend className="su-legend">About you</legend>
          {alert && <div className="su-wide">{alert}</div>}
          <label className="auth-field">
            <span>
              Full name <Req />
            </span>
            <input
              required
              maxLength={120}
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="auth-field">
            <span>
              Job title <Req />
            </span>
            <input
              required
              maxLength={120}
              autoComplete="organization-title"
              value={profile.jobTitle}
              onChange={(e) => answer("jobTitle")(e.target.value)}
            />
          </label>
          <label className="auth-field su-wide">
            <span>
              Work email <Req />
            </span>
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
            <span>
              Company <Req />
            </span>
            <input
              required
              maxLength={160}
              autoComplete="organization"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
            />
          </label>
          <label className="auth-field">
            <span>
              Country <Req />
            </span>
            <select required value={profile.country} onChange={(e) => chooseCountry(e.target.value)}>
              <option value="">Choose your country…</option>
              {allCountries.map((country) => (
                <option key={country.code} value={country.name}>
                  {country.label}
                </option>
              ))}
            </select>
          </label>
          <label className="auth-field su-wide">
            Phone
            <input
              ref={phoneInput}
              type="tel"
              maxLength={30}
              autoComplete="tel"
              inputMode="tel"
              placeholder="+91 98765 43210"
              aria-describedby="su-phone-hint"
              value={profile.phone}
              onChange={(e) => {
                e.target.setCustomValidity("");
                answer("phone")(e.target.value);
              }}
            />
            <small id="su-phone-hint">{PHONE_HINT}</small>
          </label>
          <button className="primary-action su-wide" type="button" onClick={next}>
            Continue
          </button>
        </fieldset>
      ) : (
        <fieldset className="su-fields">
          <legend className="su-legend">Your trial</legend>
          <p className="su-hint su-wide">
            These answers help us prepare sample data and checks that match your devices.
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
            <span>
              We will not upload patient-identifiable data during the trial. <Req />
            </span>
          </label>
          <p className="auth-consent su-wide">
            By requesting a trial you agree to the <a href="/terms">Terms of Service</a> and the{" "}
            <a href="/trial-agreement">Free Trial Agreement</a>, and acknowledge the{" "}
            <a href="/privacy">Privacy Policy</a>. Trial data is deleted 30 days after the trial ends unless you
            continue.
          </p>
          {alert && <div className="su-wide">{alert}</div>}
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

      <p className="auth-links">
        Already have an account? <a href="/signin">Sign in</a>
      </p>
    </form>
  );
}
