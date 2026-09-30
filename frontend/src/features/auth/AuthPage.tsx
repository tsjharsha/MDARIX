import React, { useState } from "react";

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
        ? { email, password, display_name: name, organization: company }
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
        setUserId(data.user_id);
        setToken(data.development_token ?? "");
        setMessage(
          data.email_delivery === "SENT"
            ? `Account created. Your User ID is ${data.user_id}. A verification email was sent.`
            : `Account created. Your User ID is ${data.user_id}. Email delivery is not configured on this host; use the controlled verification link below.`,
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
      <div className="auth-shell">
        <a className="brand" href="/">
          MDARIX
        </a>
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
      </div>
    );
  return (
    <div className="auth-shell">
      <a className="brand" href="/">
        MDARIX
      </a>
      <form className="auth-card" onSubmit={submit}>
        <span className="eyebrow">{mode === "signin" ? "Welcome back" : "MDARIX access"}</span>
        <h1>
          {mode === "signin"
            ? "Sign in to MDARIX"
            : mode === "signup"
              ? "Create your MDARIX account"
              : mode === "verify-email"
                ? "Verify your email"
                : mode === "activate-account"
                  ? "Activate your MDARIX account"
                  : mode === "reset-password"
                    ? "Create a new password"
                    : "Reset your password"}
        </h1>
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
        {mode !== "forgot-password" && mode !== "verify-email" && (
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
            {(mode === "signup" || isTokenPassword) && (
              <small>Password is created by the user and never shown to administrators.</small>
            )}
          </>
        )}
        <button className="primary-action" type="submit">
          {mode === "signin"
            ? "Sign in"
            : mode === "signup"
              ? "Create account"
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
        <p className="auth-links">
          <a href="/signup">Create account</a> · <a href="/signin">Sign in</a> ·{" "}
          <a href="/verify-email">Verify email</a> · <a href="/forgot-password">Forgot password?</a>
        </p>
      </form>
    </div>
  );
}
