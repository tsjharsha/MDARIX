import React, { useState, type ReactNode } from "react";
import { CalendarCheck, FileSearch, LockKeyhole, ShieldCheck, UserCheck } from "lucide-react";

const ASIDE: Record<string, { eyebrow: string; title: string; points: [typeof ShieldCheck, string, string][] }> = {
  signin: {
    eyebrow: "Investigation intelligence",
    title: "Evidence before inference. Humans decide.",
    points: [
      [ShieldCheck, "Your organization's own workspace", "Every record you see belongs to your tenant only."],
      [
        FileSearch,
        "Evidence-linked investigations",
        "Complaints, versions, lots and suppliers connected in one place.",
      ],
      [UserCheck, "People make the decisions", "AI suggests and cites its evidence; authorized reviewers decide."],
    ],
  },
  signup: {
    eyebrow: "Free 30-day trial",
    title: "See MDARIX on a real investigation in minutes.",
    points: [
      [ShieldCheck, "Your own private workspace", "Approved by our team and isolated from every other customer."],
      [FileSearch, "Ready-made sample data", "Explore a full device investigation before sharing anything."],
      [UserCheck, "Then try your own data", "Simple CSV templates, checked for personal data before import."],
    ],
  },
  "request-demo": {
    eyebrow: "Request a demo",
    title: "See MDARIX on an investigation like yours.",
    points: [
      [FileSearch, "A walkthrough on a real signal", "One complaint trend, traced to the supplier lot it shares."],
      [CalendarCheck, "At a time that suits you", "Our team contacts you to agree the date and who should join."],
      [UserCheck, "Governance you can defend", "Evidence citations, visible unknowns and human sign-off."],
    ],
  },
  security: {
    eyebrow: "Account security",
    title: "Your access is protected at every step.",
    points: [
      [LockKeyhole, "Single-use secure links", "Activation and reset links expire and work only once."],
      [ShieldCheck, "Strong passwords and MFA", "Passwords are yours alone and never shown to administrators."],
      [UserCheck, "Every sign-in is audited", "Access events are recorded for your administrators."],
    ],
  },
};

// Shared frame for every sign-in and account page: website brand, light med-tech backdrop, value panel and the form.
export function AuthFrame({ mode, children }: { mode: string; children: ReactNode }) {
  const aside = ASIDE[mode] ?? ASIDE.security;
  return (
    <div className="auth-page">
      <header className="auth-page-top">
        <a className="auth-brand" href="/" aria-label="MDARIX home">
          <span className="auth-logo" aria-hidden="true">
            M
          </span>
          MDARIX<small>Product intelligence</small>
        </a>
        <a className="auth-back" href="/">
          Back to website
        </a>
      </header>
      <main className="auth-page-body">
        <section className="auth-aside" aria-label="About MDARIX">
          <span className="auth-eyebrow">{aside.eyebrow}</span>
          <h2>{aside.title}</h2>
          <ul>
            {aside.points.map(([Icon, title, text]) => (
              <li key={title}>
                <span aria-hidden="true">
                  <Icon size={18} />
                </span>
                <div>
                  <strong>{title}</strong>
                  <p>{text}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
        {children}
      </main>
      <footer className="auth-page-foot">
        <span>MDARIX · System of Intelligence, not System of Record</span>
        <span>
          <LockKeyhole size={13} aria-hidden="true" /> Encrypted connection · Tenant-isolated data
        </span>
      </footer>
    </div>
  );
}

/** Where to go after signing in: a page inside the app the person was on, never another site. */
export function safeReturnTo(value: string | null): string {
  if (!value || !value.startsWith("/app") || value.startsWith("//") || value.includes("\\")) return "/app";
  return value;
}

const MESSAGES: Record<string, string> = {
  RATE_LIMITED: "Too many attempts. Please wait a few minutes and try again.",
  ACCOUNT_TEMPORARILY_LOCKED:
    "Too many failed sign-in attempts. Wait 15 minutes, then try again or reset your password.",
  INVALID_CREDENTIALS: "That email and password do not match an active account.",
  INVALID_RESET: "This reset link has expired or was already used. Request a new one below.",
  INVALID_ACTIVATION: "This invitation link has expired or was already used. Ask your administrator to send a new one.",
  VALID_EMAIL_REQUIRED: "Enter a valid work email.",
};

function problemMessage(data: { detail?: { code?: string; message?: string } } | null, fallback: string): string {
  const code = data?.detail?.code;
  if (code && MESSAGES[code]) return MESSAGES[code];
  return data?.detail?.message ?? fallback;
}

export function AuthPage({ mode }: { mode: string }) {
  const query = new URLSearchParams(window.location.search);
  const returnTo = safeReturnTo(query.get("returnTo"));
  const [message, setMessage] = useState(
    query.get("expired") === "1" ? "You were signed out after a period of inactivity. Sign in again to continue." : "",
  );
  const [email, setEmail] = useState(query.get("email") ?? "");
  // The email and password open accounts in several organizations: the person picks one.
  const [organizations, setOrganizations] = useState<Array<{ tenant_id: string; tenant_name: string }>>([]);
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [token, setToken] = useState(query.get("token") ?? "");
  const [tokenFromLink] = useState(Boolean(query.get("token")));
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const isTokenPassword = mode === "activate-account" || mode === "reset-password";
  const isMfa = mode === "mfa";
  const [mfaCode, setMfaCode] = useState("");
  const [mfaSecret, setMfaSecret] = useState("");
  const [mfaUri, setMfaUri] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [mfaEnrollment] = useState(query.get("setup") === "1");
  const afterSignin = (data: { mfa_enrollment_required?: boolean; mfa_required?: boolean }) => {
    const next = encodeURIComponent(returnTo);
    window.location.href = data.mfa_enrollment_required
      ? `/mfa?setup=1&returnTo=${next}`
      : data.mfa_required
        ? `/mfa?returnTo=${next}`
        : returnTo;
  };
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      await send();
    } finally {
      setBusy(false);
    }
  };
  const send = async () => {
    if (isMfa) {
      // Setting up: confirm the new authenticator with its first code. Signing in: the current code, or a
      // one-time recovery code when the phone is not at hand.
      const response = await fetch(mfaEnrollment ? "/api/v1/auth/mfa/verify-enrollment" : "/api/v1/auth/mfa/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: mfaCode.trim() }),
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok && mfaEnrollment && Array.isArray(data.recovery_codes)) {
        setRecoveryCodes(data.recovery_codes);
        setMessage("Authenticator set up. Save your recovery codes before you continue.");
      } else if (response.ok) {
        setMessage("Verified. Loading MDARIX...");
        window.location.href = returnTo;
      } else
        setMessage(
          data.detail?.code === "MFA_TEMPORARILY_LOCKED"
            ? "Too many wrong codes. Wait 15 minutes, then try again."
            : problemMessage(data, "The code could not be verified."),
        );
      return;
    }
    const endpoint =
      mode === "signin"
        ? "signin"
        : mode === "signup"
          ? "signup"
          : mode === "activate-account"
            ? "activate-account"
            : mode === "reset-password"
              ? "reset-password"
              : "forgot-password";
    const body =
      mode === "signup"
        ? { email, display_name: name, organization: company }
        : mode === "signin"
          ? { email, password }
          : isTokenPassword
            ? { token, password }
            : { email };
    let response: Response;
    try {
      response = await fetch(`/api/v1/auth/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch {
      setMessage("MDARIX cannot be reached right now. Check your connection and try again.");
      return;
    }
    const data = await response.json().catch(() => null);
    if (data === null) {
      // No readable answer (for example the server is restarting): say so instead of failing silently.
      setMessage("MDARIX is not responding right now. Please try again in a moment.");
      return;
    }
    if (!response.ok) {
      setMessage(problemMessage(data, "The request could not be completed."));
      return;
    }
    if (mode === "signup") {
      setDone(true);
      setMessage(
        `Thank you. We review every request, usually within one business day. Once it is approved, we email ${email} an invitation to your free trial workspace.`,
      );
    } else if (mode === "activate-account") {
      setDone(true);
      setMessage("Account activated. You can now sign in with your email and new password.");
    } else if (mode === "reset-password") {
      setDone(true);
      setMessage(
        "Password changed. For your security, every other session was signed out. Sign in with your new password.",
      );
    } else if (mode === "signin" && data.status === "TENANT_SELECTION_REQUIRED") {
      setOrganizations(data.organizations ?? []);
      setMessage("Your account is in more than one organization. Choose the one to open.");
    } else if (mode === "signin") {
      setMessage("Signed in. Loading MDARIX...");
      afterSignin(data);
    } else {
      setDone(true);
      setMessage(
        `If an account exists for ${email}, we have emailed a reset link. It works once and expires in one hour.${data.development_token ? ` Development token: ${data.development_token}` : ""}`,
      );
    }
  };
  const openOrganization = async (tenantId: string) => {
    const response = await fetch("/api/v1/auth/signin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, tenant_id: tenantId }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setMessage(problemMessage(data, "Sign-in could not be completed."));
      return;
    }
    afterSignin(data);
  };
  if (mode === "signin" && organizations.length)
    return (
      <AuthFrame mode="signin">
        <div className="auth-card">
          <span className="eyebrow">Welcome back</span>
          <h1>Choose an organization</h1>
          <p className="auth-lead">
            {email} has an account in each of these organizations. Each has its own data and role.
          </p>
          <ul className="auth-organizations">
            {organizations.map((item) => (
              <li key={item.tenant_id}>
                <button type="button" className="secondary-link" onClick={() => void openOrganization(item.tenant_id)}>
                  {item.tenant_name}
                </button>
              </li>
            ))}
          </ul>
          {message && <p role="status">{message}</p>}
          <p className="auth-links">
            <button type="button" className="ac-link" onClick={() => setOrganizations([])}>
              Use a different account
            </button>
          </p>
        </div>
      </AuthFrame>
    );
  if (isMfa && recoveryCodes.length)
    return (
      <AuthFrame mode="security">
        <div className="auth-card">
          <span className="eyebrow">Account security</span>
          <h1>Save your recovery codes</h1>
          <p>
            Each code signs you in once if your phone is lost or not at hand. They are shown only now: print them or
            keep them in a password manager.
          </p>
          <ol className="mfa-recovery-codes" aria-label="Recovery codes">
            {recoveryCodes.map((code) => (
              <li key={code}>
                <code>{code}</code>
              </li>
            ))}
          </ol>
          <button className="primary-action" type="button" onClick={() => (window.location.href = returnTo)}>
            I have saved these codes, continue
          </button>
        </div>
      </AuthFrame>
    );
  if (isMfa)
    return (
      <AuthFrame mode="security">
        <form className="auth-card" onSubmit={submit}>
          <span className="eyebrow">Account security</span>
          <h1>{mfaEnrollment ? "Set up your authenticator app" : "Verify your identity"}</h1>
          <p>
            {mfaEnrollment
              ? "Add MDARIX to an authenticator app (Microsoft Authenticator, Google Authenticator, 1Password and others), then enter the 6-digit code it shows."
              : useRecovery
                ? "Enter one of your recovery codes. Each code works once."
                : "Enter the 6-digit code from your authenticator app to continue."}
          </p>
          {mfaEnrollment && (
            <>
              <button
                className="secondary-link"
                type="button"
                onClick={async () => {
                  const response = await fetch("/api/v1/auth/mfa/enroll", { method: "POST" });
                  const data = await response.json().catch(() => ({}));
                  setMfaSecret(data.secret ?? "");
                  setMfaUri(data.otpauth_uri ?? "");
                  setMessage(
                    response.ok
                      ? `Add the key below to your authenticator app.${data.development_code ? ` Development code: ${data.development_code}` : ""}`
                      : problemMessage(data, "MFA setup is unavailable."),
                  );
                }}
              >
                {mfaSecret ? "Generate a new key" : "Generate my setup key"}
              </button>
              {mfaSecret && (
                <div className="mfa-setup">
                  <p className="mfa-secret" aria-label="Authenticator setup key">
                    {mfaSecret.replace(/(.{4})/g, "$1 ").trim()}
                  </p>
                  <a className="secondary-link" href={mfaUri}>
                    Open in an authenticator app on this device
                  </a>
                </div>
              )}
            </>
          )}
          <label className="auth-field">
            {useRecovery ? "Recovery code" : "Six digit authentication code"}
            <input
              inputMode={useRecovery ? "text" : "numeric"}
              autoComplete="one-time-code"
              minLength={6}
              maxLength={useRecovery ? 17 : 6}
              required
              value={mfaCode}
              onChange={(e) =>
                setMfaCode(
                  useRecovery ? e.target.value.replace(/[^0-9a-fA-F-]/g, "") : e.target.value.replace(/\D/g, ""),
                )
              }
              placeholder={useRecovery ? "xxxxxxxx-xxxxxxxx" : "000000"}
            />
          </label>
          <button className="primary-action" type="submit" disabled={busy}>
            {mfaEnrollment ? "Verify and turn on MFA" : "Verify"}
          </button>
          {message && <p role="status">{message}</p>}
          <p className="auth-links">
            {!mfaEnrollment && (
              <>
                <button
                  type="button"
                  className="ac-link"
                  onClick={() => {
                    setUseRecovery((value) => !value);
                    setMfaCode("");
                  }}
                >
                  {useRecovery ? "Use my authenticator app" : "Use a recovery code"}
                </button>{" "}
                ·{" "}
              </>
            )}
            <a href="/signin">Return to sign in</a>
          </p>
          <p className="auth-links">
            Lost your phone and your recovery codes? Ask your administrator to reset your multi-factor authentication.
          </p>
        </form>
      </AuthFrame>
    );
  return (
    <AuthFrame mode={mode === "signin" || mode === "signup" ? mode : "security"}>
      <form className="auth-card" onSubmit={submit}>
        <span className="eyebrow">{mode === "signin" ? "Welcome back" : "MDARIX access"}</span>
        <h1>
          {mode === "signin"
            ? "Sign in to MDARIX"
            : mode === "signup"
              ? "Start your free trial"
              : mode === "activate-account"
                ? "Activate your MDARIX account"
                : mode === "reset-password"
                  ? "Create a new password"
                  : "Reset your password"}
        </h1>
        <p className="auth-lead">
          {mode === "signin"
            ? "Use your work email to open your workspace."
            : mode === "signup"
              ? "30 days, up to 3 users and 5,000 uploaded rows, no credit card. You create your password from the invitation email."
              : mode === "forgot-password"
                ? "Enter your work email and we will send you a secure reset link."
                : "Choose a password of at least 12 characters. A phrase of several words works well."}
        </p>
        {!done && (
          <>
            {mode === "signup" && (
              <>
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
                  Company
                  <input
                    required
                    maxLength={160}
                    autoComplete="organization"
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                  />
                </label>
              </>
            )}
            {isTokenPassword ? (
              !tokenFromLink && (
                <label className="auth-field">
                  Code from your email
                  <input required value={token} onChange={(e) => setToken(e.target.value.trim())} />
                </label>
              )
            ) : (
              <label className="auth-field">
                Work email
                <input
                  required
                  type="email"
                  maxLength={254}
                  autoComplete={mode === "signin" ? "username" : "email"}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>
            )}
            {(mode === "signin" || isTokenPassword) && (
              <label className="auth-field">
                {isTokenPassword ? "New password" : "Password"}
                <input
                  required
                  minLength={isTokenPassword ? 12 : 1}
                  maxLength={128}
                  type="password"
                  autoComplete={isTokenPassword ? "new-password" : "current-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                {isTokenPassword && <small>Only you know it: administrators never see passwords.</small>}
              </label>
            )}
            {mode === "signup" && (
              <p className="auth-consent">
                By requesting a trial you agree to the <a href="/terms">Terms of Service</a> and the{" "}
                <a href="/trial-agreement">Free Trial Agreement</a>, and acknowledge the{" "}
                <a href="/privacy">Privacy Policy</a>. Trial data is deleted 30 days after the trial ends unless you
                continue.
              </p>
            )}
            <button className="primary-action" type="submit" disabled={busy}>
              {busy
                ? "Please wait…"
                : mode === "signin"
                  ? "Sign in"
                  : mode === "signup"
                    ? "Request free trial"
                    : mode === "activate-account"
                      ? "Activate account"
                      : mode === "reset-password"
                        ? "Set new password"
                        : "Send reset link"}
            </button>
          </>
        )}
        {message && <p role="status">{message}</p>}
        {mode === "signin" ? (
          <p className="auth-links auth-links-split">
            <a href="/forgot-password">Forgot password?</a>
            <span>
              New to MDARIX? <a href="/signup">Start free trial</a>
            </span>
          </p>
        ) : mode === "signup" ? (
          <p className="auth-links">
            Already have an account? <a href="/signin">Sign in</a>
          </p>
        ) : (
          <p className="auth-links">
            <a href="/signin">Return to sign in</a>
            {mode === "reset-password" && (
              <>
                {" "}
                · <a href="/forgot-password">Request a new reset link</a>
              </>
            )}
          </p>
        )}
      </form>
    </AuthFrame>
  );
}
