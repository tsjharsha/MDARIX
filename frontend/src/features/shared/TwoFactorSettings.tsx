import { useState, type FormEvent, type ReactNode } from "react";
import { Copy, Download, KeyRound, RefreshCw, ShieldCheck, Smartphone } from "lucide-react";
import { Panel } from "../admin/console/charts";
import { formatDate, send, useResource } from "../customer-admin/shared";
import {
  cleanCode,
  reauthMessage,
  recoveryCodesNote,
  recoveryCodesText,
  replaceAuthenticatorHref,
  type MfaStatus,
} from "./twoFactor";

/**
 * Two-factor sign-in on one's own account (My Account, Security; the customer administrator's Security page).
 *
 * Not on yet: the way to set it up, as before. On: since when, the recovery codes left, and two changes, each after
 * the current password and a code from the authenticator app: new recovery codes (shown once here, to copy or
 * download), and a new authenticator app in place of the old one (the setup page, /mfa?setup=1). There is no switch
 * to turn it off.
 */
export function TwoFactorPanel({
  eyebrow = "Sign-in",
  account,
  notOnText = "Add a second step to sign-in. You'll also confirm your identity this way when you sign a decision.",
  children,
}: {
  eyebrow?: string;
  /** The signed-in email, written into the recovery codes file. */
  account?: string | null;
  notOnText?: string;
  children?: ReactNode;
}) {
  const status = useResource<MfaStatus>("/api/v1/auth/mfa/status");
  const [codes, setCodes] = useState<{ list: string[]; issued: Date } | null>(null);
  const returnTo = typeof window === "undefined" ? "/app" : `${window.location.pathname}${window.location.search}`;
  return (
    <Panel eyebrow={eyebrow} title="Multi-factor authentication" source={status}>
      {codes ? (
        <RecoveryCodesList
          codes={codes.list}
          account={account}
          issued={codes.issued}
          onDone={() => {
            setCodes(null);
            status.reload();
          }}
        />
      ) : (
        status.data && (
          <TwoFactorSummary
            status={status.data}
            notOnText={notOnText}
            replaceHref={replaceAuthenticatorHref(returnTo)}
            onCodes={(list) => setCodes({ list, issued: new Date() })}
          />
        )
      )}
      {children}
    </Panel>
  );
}

/** What the panel shows for a known status. Exported for its test. */
export function TwoFactorSummary({
  status,
  notOnText,
  replaceHref,
  onCodes,
  initiallyAsking = false,
}: {
  status: MfaStatus;
  notOnText: string;
  replaceHref: string;
  onCodes: (codes: string[]) => void;
  /** Open with the confirmation form showing (for the test). */
  initiallyAsking?: boolean;
}) {
  const [asking, setAsking] = useState(initiallyAsking);
  if (!status.enrolled)
    return (
      <>
        <p>{notOnText}</p>
        <div className="ca-action-row">
          <a className="ac-primary" href="/mfa?setup=1">
            <ShieldCheck size={16} /> Set up MFA
          </a>
        </div>
      </>
    );
  const note = recoveryCodesNote(status.recovery_codes_left);
  return (
    <>
      <p className="ca-mfa-on">
        <ShieldCheck size={16} aria-hidden="true" />
        <span>
          <strong>Two-factor sign-in is on</strong>
          {status.enrolled_at ? ` since ${formatDate(status.enrolled_at)}` : ""}.
        </span>
      </p>
      <p className={note.low ? "ca-mfa-message is-bad" : "ac-muted"} role={note.low ? "status" : undefined}>
        {note.text}
      </p>
      {status.required_for_role && <p className="ac-muted">Your role requires two-factor sign-in, so it stays on.</p>}
      {status.replacement_pending && (
        <p className="ac-muted">
          A new authenticator app was started but not confirmed. Your current app keeps working until you finish.
        </p>
      )}
      {asking ? (
        <NewRecoveryCodesForm
          onDone={(codes) => {
            setAsking(false);
            onCodes(codes);
          }}
          onCancel={() => setAsking(false)}
        />
      ) : (
        <div className="ca-action-row">
          <button type="button" className="ac-primary" onClick={() => setAsking(true)}>
            <RefreshCw size={16} /> Generate new recovery codes
          </button>
          <a className="ac-secondary" href={replaceHref}>
            <Smartphone size={16} /> Replace authenticator app
          </a>
        </div>
      )}
      <p className="ac-muted">
        Replace the app when you change phones. If you lost your phone, sign in with a recovery code, then replace it.
      </p>
    </>
  );
}

/** Confirm with the current password and an authenticator code, then get the new codes. */
function NewRecoveryCodesForm({ onDone, onCancel }: { onDone: (codes: string[]) => void; onCancel: () => void }) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setProblem("");
    try {
      const result = await send<{ recovery_codes?: string[] }>("/api/v1/auth/mfa/recovery-codes", "POST", {
        password,
        mfa_code: code,
      });
      setPassword("");
      setCode("");
      if (Array.isArray(result?.recovery_codes) && result.recovery_codes.length) onDone(result.recovery_codes);
      else setProblem("No codes came back. Try again.");
    } catch (reason) {
      setPassword("");
      setCode("");
      setProblem(reauthMessage(reason, "New recovery codes could not be generated."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="ca-mfa-form" onSubmit={(event) => void submit(event)} aria-label="Generate new recovery codes">
      <p>
        Your current recovery codes stop working as soon as the new ones are made. To confirm it is you, enter your
        password and the 6-digit code your authenticator app shows now.
      </p>
      <ReauthFields password={password} code={code} onPassword={setPassword} onCode={setCode} />
      {problem && (
        <p className="ca-mfa-message is-bad" role="alert">
          {problem}
        </p>
      )}
      <div className="ca-action-row">
        <button type="submit" className="ac-primary" disabled={busy || !password || code.length !== 6}>
          <KeyRound size={16} /> {busy ? "Generating…" : "Generate new codes"}
        </button>
        <button type="button" className="ac-link" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** The current password and an authenticator code (or, where allowed, a recovery code). Exported for the setup page. */
export function ReauthFields({
  password,
  code,
  onPassword,
  onCode,
  allowRecovery = false,
}: {
  password: string;
  code: string;
  onPassword: (value: string) => void;
  onCode: (value: string) => void;
  allowRecovery?: boolean;
}) {
  return (
    <>
      <label>
        Current password
        <input
          type="password"
          autoComplete="current-password"
          required
          maxLength={128}
          value={password}
          onChange={(event) => onPassword(event.target.value)}
        />
      </label>
      <label>
        {allowRecovery ? "Code from your authenticator app, or a recovery code" : "Code from your authenticator app"}
        <input
          inputMode={allowRecovery ? "text" : "numeric"}
          autoComplete="one-time-code"
          required
          minLength={6}
          maxLength={allowRecovery ? 17 : 6}
          placeholder={allowRecovery ? "000000 or xxxxxxxx-xxxxxxxx" : "000000"}
          value={code}
          onChange={(event) => onCode(cleanCode(event.target.value, allowRecovery))}
        />
      </label>
    </>
  );
}

/** The new codes, shown this once, to copy or download. Exported for its test. */
export function RecoveryCodesList({
  codes,
  account,
  issued,
  onDone,
}: {
  codes: readonly string[];
  account?: string | null;
  issued: Date;
  onDone: () => void;
}) {
  const [said, setSaid] = useState("");
  const text = recoveryCodesText(codes, account, issued);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setSaid("Copied. Paste them into your password manager.");
    } catch {
      setSaid("Copying is not allowed here. Select the codes and copy them, or download them instead.");
    }
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "mdarix-recovery-codes.txt";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setSaid("Downloaded. Keep the file somewhere private, then delete other copies.");
  };
  return (
    <div className="ca-mfa-codes">
      <p className="ca-mfa-message is-good" role="status">
        New recovery codes are ready. Your earlier codes no longer work.
      </p>
      <p>
        Each code signs you in once when your authenticator app is not at hand. They are shown only now: copy them into
        a password manager, download them, or print them.
      </p>
      <ol className="mfa-recovery-codes" aria-label="Recovery codes">
        {codes.map((code) => (
          <li key={code}>
            <code>{code}</code>
          </li>
        ))}
      </ol>
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" onClick={() => void copy()}>
          <Copy size={16} /> Copy all
        </button>
        <button type="button" className="ac-secondary" onClick={download}>
          <Download size={16} /> Download
        </button>
        <button type="button" className="ac-primary" onClick={onDone}>
          I have saved these codes
        </button>
      </div>
      {said && (
        <p className="ac-muted" role="status">
          {said}
        </p>
      )}
    </div>
  );
}
