import React, { useEffect, useRef, useState } from "react";
import { Copy, Download, Eye, EyeOff } from "lucide-react";
import { AuthFrame } from "./AuthFrame";
import { SignupPage } from "./SignupPage";
import { QrCodeSvg } from "../../app/QrCodeSvg";
import { MfaAlreadyOn } from "./MfaAlreadyOn";
import { useRecoveryCodeSaving } from "../shared/recoveryCodeSaving";
import { PUBLISHED_CONTACT, useSiteInfo } from "../../site/legal";

export { AuthFrame };

const APP_ROOTS = ["/app", "/platform-admin"];

/**
 * Where to go after signing in: the page inside the application the person was on, never another site. Only a
 * same-origin path under /app or /platform-admin is accepted (no scheme, no "//host", no backslash tricks); anything
 * else opens /app.
 */
export function safeReturnTo(value: string | null, origin = "https://mdarix.invalid"): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return "/app";
  // Control characters (a tab or newline hidden in the address) are never part of a page the app links to.
  if (/[\u0000-\u001f\u007f]/.test(value)) return "/app";
  let url: URL;
  try {
    url = new URL(value, origin);
  } catch {
    return "/app";
  }
  if (url.origin !== new URL(origin).origin) return "/app";
  if (!APP_ROOTS.some((root) => url.pathname === root || url.pathname.startsWith(`${root}/`))) return "/app";
  return `${url.pathname}${url.search}${url.hash}`;
}

/** Why the person is on the sign-in page, from the address (`reason=idle|expired`; `expired=1` from older links). */
export function signInNotice(query: URLSearchParams): string {
  const reason = query.get("reason");
  if (reason === "idle" || query.get("expired") === "1")
    return "You were signed out after 30 minutes without activity, to protect your organization's data. Sign in again to continue where you left off.";
  if (reason === "expired") return "Your session has ended. Sign in again to continue where you left off.";
  return "";
}

export const MFA_TIMED_OUT =
  "This sign-in timed out: MDARIX waits 10 minutes for the authenticator step. Return to sign in and sign in again; a setup starts again from the beginning.";

/** Who resets a lost authenticator: in a free trial the person who invited you, or MDARIX support for the person who
 * started it; in a pilot, the administrator. */
export const lostAuthenticatorHelp = (support: string) =>
  `Lost your phone and your recovery codes? In a free trial, ask the person who invited you: they can reset it in Getting started › Team. If you started the trial, write to ${support}. In a pilot, ask your administrator.`;

const MESSAGES: Record<string, string> = {
  ACCOUNT_TEMPORARILY_LOCKED:
    "Too many failed sign-in attempts. Wait 15 minutes, then try again or reset your password.",
  INVALID_CREDENTIALS: "That email and password do not match an active account.",
  INVALID_RESET: "This reset link has expired or was already used. Request a new one below.",
  // Anyone with an invitation (a trial owner too) can get a fresh link themselves: "Forgot password?" sends one.
  INVALID_ACTIVATION:
    'This invitation link has expired or was already used. Request a new link from the sign-in page with "Forgot password?", or ask the person who invited you to send a new invitation.',
  // The authenticator step waits 10 minutes (auth/cookies.py PENDING_MFA_SECONDS); after that the server no longer
  // knows the sign-in.
  UNAUTHENTICATED: MFA_TIMED_OUT,
  VALID_EMAIL_REQUIRED: "Enter a valid work email.",
  REAUTHENTICATION_REQUIRED: "Enter your current password and a code from your current app, or a recovery code.",
  REAUTHENTICATION_FAILED: "The password or the code is wrong. Check both and try again.",
  MFA_TEMPORARILY_LOCKED: "Too many wrong codes. Wait 15 minutes, then try again.",
};

/**
 * What to say when a one-time link can no longer be used (asked as its page opens), or null when it still works or
 * the check could not be made: then the form shows and the server decides on submit (exported for its test).
 */
export async function spentLinkMessage(token: string, kind: "activation" | "reset"): Promise<string | null> {
  try {
    const response = await fetch("/api/v1/auth/link-status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, kind }),
    });
    const data = response.ok ? ((await response.json()) as { usable?: boolean; code?: string }) : null;
    if (data?.usable !== false) return null;
    return MESSAGES[data.code ?? ""] ?? MESSAGES[kind === "reset" ? "INVALID_RESET" : "INVALID_ACTIVATION"];
  } catch {
    return null;
  }
}

function problemMessage(data: { detail?: { code?: string; message?: string } } | null, fallback: string): string {
  const code = data?.detail?.code;
  if (code && MESSAGES[code]) return MESSAGES[code];
  return data?.detail?.message ?? fallback;
}

export function AuthPage({ mode }: { mode: string }) {
  const query = new URLSearchParams(window.location.search);
  const returnTo = safeReturnTo(query.get("returnTo"), window.location.origin);
  const [message, setMessage] = useState(() => signInNotice(query));
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
  // A link already used, withdrawn or expired says so as its page opens, with no password form (DEV-004). When the
  // check cannot be made the form shows as before, and the server still refuses a spent link.
  const [linkSpent, setLinkSpent] = useState(false);
  useEffect(() => {
    if (!isTokenPassword || !tokenFromLink || !token) return;
    let current = true;
    void spentLinkMessage(token, mode === "reset-password" ? "reset" : "activation").then((spent) => {
      if (!current || !spent) return;
      setLinkSpent(true);
      setMessage(spent);
    });
    return () => {
      current = false;
    };
    // Checked once, for the link the page was opened with.
  }, []);
  const isMfa = mode === "mfa";
  const [mfaCode, setMfaCode] = useState("");
  const support = useSiteInfo()?.support_email || PUBLISHED_CONTACT.support;
  const [mfaSecret, setMfaSecret] = useState("");
  const [mfaUri, setMfaUri] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [mfaEnrollment] = useState(query.get("setup") === "1");
  // The account already has an authenticator: "Set up MFA" offers to replace it instead (MfaAlreadyOn).
  const [mfaAlreadyOn, setMfaAlreadyOn] = useState(false);
  const [replacingMfa, setReplacingMfa] = useState(false);
  // Setting up the authenticator: the setup key (and its QR code) is asked for as the screen opens; a new one on request.
  // Replacing one sends the current password and a current code (or a recovery code) with the request.
  const generateKey = async (proof?: { password: string; mfa_code: string }) => {
    const response = await fetch(
      "/api/v1/auth/mfa/enroll",
      proof
        ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(proof) }
        : { method: "POST" },
    ).catch(() => null);
    if (!response) {
      setMessage("MDARIX cannot be reached right now. Check your connection and try again.");
      return;
    }
    const data = await response.json().catch(() => ({}));
    const refusal = response.ok ? undefined : data?.detail?.code;
    if (refusal === "MFA_REQUIRED") {
      // Signed in with the password only: the current code comes first.
      window.location.replace(`/mfa?returnTo=${encodeURIComponent(returnTo)}`);
      return;
    }
    if (refusal === "REAUTHENTICATION_REQUIRED" && !proof) {
      setMfaAlreadyOn(true);
      setMessage("");
      return;
    }
    if (proof) {
      if (!response.ok) {
        setMessage(problemMessage(data, "The authenticator app could not be replaced."));
        return;
      }
      setMfaAlreadyOn(false);
      setReplacingMfa(true);
    }
    setMfaSecret(data.secret ?? "");
    setMfaUri(data.otpauth_uri ?? "");
    setMessage(
      response.ok
        ? data.development_code
          ? `Development code: ${data.development_code}`
          : ""
        : problemMessage(data, "MFA setup is unavailable."),
    );
  };
  const keyAsked = useRef(false);
  useEffect(() => {
    if (!isMfa || !mfaEnrollment || keyAsked.current) return;
    keyAsked.current = true;
    void generateKey();
  }, [isMfa, mfaEnrollment]);
  // After activating the account: sign in with the invited email and the password just chosen, then straight on to
  // authenticator setup; null when that cannot be done here (the person signs in themselves).
  const signInAfterActivation = async (activated: string) => {
    const response = await fetch("/api/v1/auth/signin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: activated, password }),
    }).catch(() => null);
    const data = response?.ok ? await response.json().catch(() => null) : null;
    return data && data.status !== "TENANT_SELECTION_REQUIRED" ? data : null;
  };
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
      let response: Response;
      try {
        response = await fetch(mfaEnrollment ? "/api/v1/auth/mfa/verify-enrollment" : "/api/v1/auth/mfa/verify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: mfaCode.trim() }),
        });
      } catch {
        setMessage("MDARIX cannot be reached right now. Check your connection and try again.");
        return;
      }
      const data = await response.json().catch(() => ({}));
      if (response.ok && mfaEnrollment && Array.isArray(data.recovery_codes)) {
        setRecoveryCodes(data.recovery_codes);
        setMessage(
          replacingMfa
            ? "Your new authenticator app is on. The old app and your old recovery codes no longer work, and you were signed out on your other devices."
            : "Authenticator set up. Save your recovery codes before you continue.",
        );
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
        `Thank you. Once your request is approved, we email ${email} an invitation to your free trial workspace.`,
      );
    } else if (mode === "activate-account") {
      const signedIn = typeof data.email === "string" ? await signInAfterActivation(data.email) : null;
      if (signedIn) return afterSignin(signedIn);
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
    let response: Response;
    try {
      response = await fetch("/api/v1/auth/signin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, tenant_id: tenantId }),
      });
    } catch {
      setMessage("MDARIX cannot be reached right now. Check your connection and try again.");
      return;
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setMessage(problemMessage(data, "Sign-in could not be completed."));
      return;
    }
    afterSignin(data);
  };
  if (mode === "signup") return <SignupPage />;
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
        <FirstRecoveryCodes
          codes={recoveryCodes}
          account={email || null}
          message={replacingMfa ? message : ""}
          onDone={() => (window.location.href = returnTo)}
        />
      </AuthFrame>
    );
  if (isMfa && mfaEnrollment && mfaAlreadyOn)
    return (
      <AuthFrame mode="security">
        <MfaAlreadyOn
          returnTo={returnTo}
          busy={busy}
          message={message}
          onReplace={async (proof) => {
            setBusy(true);
            try {
              await generateKey(proof);
            } finally {
              setBusy(false);
            }
          }}
        />
      </AuthFrame>
    );
  if (isMfa)
    return (
      <AuthFrame mode="security">
        <form className="auth-card" onSubmit={submit}>
          <span className="eyebrow">Account security</span>
          <h1>
            {replacingMfa
              ? "Set up your new authenticator app"
              : mfaEnrollment
                ? "Set up your authenticator app"
                : "Verify your identity"}
          </h1>
          <p>
            {mfaEnrollment
              ? "Scan the QR code with an authenticator app on your phone (Microsoft Authenticator, Google Authenticator, 1Password and others), then enter the 6-digit code it shows."
              : useRecovery
                ? "Enter one of your recovery codes. Each code works once."
                : "Enter the 6-digit code from your authenticator app to continue."}
          </p>
          {mfaEnrollment && (
            <>
              {mfaSecret ? (
                <div className="mfa-setup">
                  {mfaUri && <QrCodeSvg text={mfaUri} label="QR code to add MDARIX to your authenticator app" />}
                  <p className="mfa-key-label">No camera? Type this key into the app instead:</p>
                  <p className="mfa-secret" aria-label="Authenticator setup key">
                    {mfaSecret.replace(/(.{4})/g, "$1 ").trim()}
                  </p>
                  <a className="secondary-link" href={mfaUri}>
                    Open in an authenticator app on this device
                  </a>
                </div>
              ) : (
                <p className="mfa-key-label">Preparing your setup key…</p>
              )}
              {/* A replacement key needs the password and a current code again: start over for a new one. */}
              {!replacingMfa && (
                <button className="secondary-link" type="button" onClick={() => void generateKey()}>
                  {mfaSecret ? "Generate a new key" : "Try again"}
                </button>
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
          <p className="auth-links">{lostAuthenticatorHelp(support)}</p>
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
              ? "30 days, up to 3 users and 5,000 uploaded rows, no credit card. You create your password from the invitation email and set up an authenticator app for two-factor sign-in (MFA)."
              : mode === "forgot-password"
                ? "Enter your work email and we will send you a secure reset link."
                : linkSpent
                  ? "This link can no longer be used."
                  : "Choose a password of at least 12 characters. A phrase of several words works well."}
        </p>
        {!done && !linkSpent && (
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
                <PasswordInput
                  minLength={isTokenPassword ? 12 : 1}
                  autoComplete={isTokenPassword ? "new-password" : "current-password"}
                  value={password}
                  onChange={setPassword}
                />
                {isTokenPassword && <small>Only you know it: administrators never see passwords.</small>}
              </label>
            )}
            {mode === "activate-account" && (
              <p className="auth-consent">
                Your account is processed as described in our{" "}
                <a href="/privacy" target="_blank" rel="noopener">
                  Privacy Policy
                </a>{" "}
                (opens in a new tab): your name, email address, role and sign-in records, to give you access and keep an
                audit trail. MDARIX stores only a salted hash of your password.
              </p>
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
            {mode === "activate-account" && (
              <>
                {" "}
                · <a href="/forgot-password">Request a new link</a>
              </>
            )}
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

/**
 * A password field with an eye button that shows what was typed, to check it before signing in or setting it; it is
 * hidden again whenever the form is sent (exported for its test).
 */
export function PasswordInput({
  value,
  onChange,
  minLength,
  autoComplete,
}: {
  value: string;
  onChange: (value: string) => void;
  minLength: number;
  autoComplete: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <span className="auth-password">
      <input
        required
        minLength={minLength}
        maxLength={128}
        type={visible ? "text" : "password"}
        autoComplete={autoComplete}
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onBlur={(event) => {
          // Leaving the form (sending it, or going elsewhere) hides the password again.
          if (!event.currentTarget.form?.contains(event.relatedTarget as Node | null)) setVisible(false);
        }}
      />
      <button
        type="button"
        className="auth-password-toggle"
        aria-label={visible ? "Hide password" : "Show password"}
        aria-pressed={visible}
        title={visible ? "Hide password" : "Show password"}
        onClick={() => setVisible((shown) => !shown)}
      >
        {visible ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
      </button>
    </span>
  );
}

/**
 * The recovery codes right after the authenticator is set up, shown this once: copy them into a password manager or
 * download them, then continue (pre-launch review UX-12: the page said "print them" but offered no way to save them).
 * Exported for its test.
 */
export function FirstRecoveryCodes({
  codes,
  account,
  message,
  onDone,
}: {
  codes: string[];
  account: string | null;
  message: string;
  onDone: () => void;
}) {
  const [issued] = useState(() => new Date());
  const { said, copy, download } = useRecoveryCodeSaving(codes, account, issued);
  return (
    <div className="auth-card">
      <span className="eyebrow">Account security</span>
      <h1>Save your recovery codes</h1>
      {message && <p role="status">{message}</p>}
      <p>
        Each code signs you in once if your phone is lost or not at hand. They are shown only now: copy them into a
        password manager or download them.
      </p>
      <ol className="mfa-recovery-codes" aria-label="Recovery codes">
        {codes.map((code) => (
          <li key={code}>
            <code>{code}</code>
          </li>
        ))}
      </ol>
      <div className="auth-code-actions">
        <button type="button" className="secondary-action" onClick={() => void copy()}>
          <Copy size={16} aria-hidden="true" /> Copy all
        </button>
        <button type="button" className="secondary-action" onClick={download}>
          <Download size={16} aria-hidden="true" /> Download
        </button>
      </div>
      {said && <p role="status">{said}</p>}
      <button className="primary-action" type="button" onClick={onDone}>
        I have saved these codes, continue
      </button>
    </div>
  );
}
