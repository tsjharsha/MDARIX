import React, { useState, type ReactNode } from "react";
import { FileSearch, LockKeyhole, ShieldCheck, UserCheck } from "lucide-react";

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
function AuthFrame({ mode, children }: { mode: string; children: ReactNode }) {
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

export function AuthPage({ mode }: { mode: string }) {
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [token, setToken] = useState(new URLSearchParams(window.location.search).get("token") ?? "");
  const [userId, setUserId] = useState("");
  const isTokenPassword = mode === "activate-account" || mode === "reset-password";
  const isMfa = mode === "mfa";
  const [mfaCode, setMfaCode] = useState("");
  const [mfaSecret, setMfaSecret] = useState("");
  const [mfaEnrollment] = useState(new URLSearchParams(window.location.search).get("setup") === "1");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isMfa) {
      const response = await fetch("/api/v1/auth/mfa/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: mfaCode }),
      });
      const data = await response.json();
      if (response.ok) {
        setMessage("MFA verified. Loading MDARIX...");
        window.location.href = "/app";
      } else setMessage(data.detail?.message ?? "MFA verification could not be completed.");
      return;
    }
    const endpoint =
      mode === "signin"
        ? "signin"
        : mode === "signup"
          ? "signup"
          : mode === "verify-email"
            ? "verify-email"
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
          : mode === "verify-email"
            ? { token }
            : isTokenPassword
              ? { token, password }
              : { email };
    const response = await fetch(`/api/v1/auth/${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (response.ok) {
      if (mode === "signup") {
        // Sign-up records a request; the account itself is created when the workspace is set up.
        if (data.user_id) setUserId(data.user_id);
        setToken(data.development_token ?? "");
        setMessage(
          data.status === "ONBOARDING_REQUEST_ACCEPTED"
            ? `Thank you, your request is in. Once it is approved, we email ${email} an invitation to activate your free trial workspace for ${company || "your organization"}.`
            : `Account created. Your User ID is ${data.user_id}.`,
        );
      } else if (mode === "verify-email") {
        setMessage("Email verified. You can now sign in with your User ID and password.");
      } else if (mode === "activate-account") {
        setMessage("Account activated. You can now sign in with your email and new password.");
      } else if (mode === "reset-password") {
        setMessage("Password reset complete. You can now sign in with your new password.");
      } else if (mode === "signin") {
        if (data.mfa_required) {
          window.location.href = "/mfa";
        } else {
          setMessage("Signed in. Loading MDARIX...");
          window.location.href = "/app";
        }
      } else
        setMessage(
          data.email_delivery === "SENT"
            ? "If the account exists, reset instructions were emailed."
            : `If the account exists, reset instructions are available.${data.development_token ? ` Development token: ${data.development_token}` : ""}`,
        );
    } else {
      setMessage(
        data.detail?.code === "PASSWORD_POLICY"
          ? "Password must be at least 12 characters."
          : data.detail?.code === "ACCOUNT_EXISTS"
            ? "An account with this email already exists. Use Sign in or verify the existing account."
            : (data.detail?.message ?? "Request could not be completed."),
      );
    }
  };
  if (isMfa)
    return (
      <AuthFrame mode="security">
        <form className="auth-card" onSubmit={submit}>
          <span className="eyebrow">Account security</span>
          <h1>{mfaEnrollment ? "Enroll an authenticator" : "Verify your identity"}</h1>
          <p>
            {mfaEnrollment
              ? "Generate an enrollment secret, add it to your authenticator app, then verify the first code."
              : "Enter the six-digit code from your authenticator app to continue."}
          </p>
          {mfaEnrollment && (
            <>
              <button
                className="secondary-link"
                type="button"
                onClick={async () => {
                  const response = await fetch("/api/v1/auth/mfa/enroll", { method: "POST" });
                  const data = await response.json();
                  setMfaSecret(data.secret ?? "");
                  setMessage(
                    response.ok
                      ? "Secret generated. Add it to your authenticator app."
                      : (data.detail?.message ?? "MFA enrollment is unavailable."),
                  );
                }}
              >
                Generate enrollment secret
              </button>
              {mfaSecret && (
                <p className="mfa-secret" aria-label="MFA enrollment secret">
                  {mfaSecret}
                </p>
              )}
            </>
          )}
          <input
            aria-label="Six digit authentication code"
            inputMode="numeric"
            pattern="[0-9]{6}"
            minLength={6}
            maxLength={6}
            required
            value={mfaCode}
            onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ""))}
            placeholder="000000"
          />
          <button className="primary-action" type="submit">
            {mfaEnrollment ? "Verify and enable MFA" : "Verify MFA code"}
          </button>
          {message && <p role="status">{message}</p>}
          <p className="auth-links">
            <a href="/mfa?setup=1">Set up MFA</a> · <a href="/signin">Return to sign in</a>
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
              : mode === "verify-email"
                ? "Verify your email"
                : mode === "activate-account"
                  ? "Activate your MDARIX account"
                  : mode === "reset-password"
                    ? "Create a new password"
                    : "Reset your password"}
        </h1>
        <p className="auth-lead">
          {mode === "signin"
            ? "Use your work email or User ID to open your workspace."
            : mode === "signup"
              ? "30 days, up to 3 users, no credit card. You will create your password from the invitation email."
              : mode === "forgot-password"
                ? "Enter your work email and we will send you a secure reset link."
                : "Use the secure link or token from your email."}
        </p>
        {mode === "signup" && (
          <>
            <input
              aria-label="Display name"
              required
              placeholder="Full name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <input
              aria-label="Company"
              required
              placeholder="Company / organization"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
            />
          </>
        )}
        {mode === "verify-email" || isTokenPassword ? (
          <input
            aria-label="Token"
            required
            placeholder="Secure token"
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
        ) : (
          <input
            aria-label="User ID or work email"
            required
            type={mode === "forgot-password" ? "email" : "text"}
            placeholder={mode === "signin" ? "User ID or work email" : "Work email"}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        )}{" "}
        {mode !== "forgot-password" && mode !== "verify-email" && mode !== "signup" && (
          <>
            <input
              aria-label="Password"
              required
              minLength={12}
              type="password"
              placeholder={
                isTokenPassword ? "Create password (minimum 12 characters)" : "Password (minimum 12 characters)"
              }
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {isTokenPassword && <small>Password is created by the user and never shown to administrators.</small>}
          </>
        )}
        <button className="primary-action" type="submit">
          {mode === "signin"
            ? "Sign in"
            : mode === "signup"
              ? "Request free trial"
              : mode === "verify-email"
                ? "Verify email"
                : mode === "activate-account"
                  ? "Activate account"
                  : mode === "reset-password"
                    ? "Reset password"
                    : "Send reset instructions"}
        </button>
        {message && (
          <p role="status">
            {message}
            {userId && token && (
              <>
                {" "}
                <br />
                <a href={`/verify-email?token=${encodeURIComponent(token)}`}>Continue to email verification</a>
              </>
            )}
          </p>
        )}
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
            <a href="/signin">Return to sign in</a> · <a href="/signup">Start free trial</a>
            {mode !== "verify-email" && (
              <>
                {" "}
                · <a href="/verify-email">Verify email</a>
              </>
            )}
          </p>
        )}
      </form>
    </AuthFrame>
  );
}
