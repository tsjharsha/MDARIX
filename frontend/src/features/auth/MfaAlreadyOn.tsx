import { useState, type FormEvent } from "react";
import { cleanCode } from "../shared/twoFactor";

/**
 * "Set up MFA" opened by someone who already has an authenticator app (/mfa?setup=1): say it is on, and offer to
 * replace the app (a new phone, a lost one) after the current password and a code from the current app or one of the
 * recovery codes. Nothing is set up twice: the old app keeps working until the new one is confirmed.
 */
export function MfaAlreadyOn({
  returnTo,
  busy,
  message,
  onReplace,
}: {
  returnTo: string;
  busy: boolean;
  message: string;
  onReplace: (proof: { password: string; mfa_code: string }) => Promise<void>;
}) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    const proof = { password, mfa_code: code.trim() };
    setPassword("");
    setCode("");
    await onReplace(proof);
  };
  return (
    <form className="auth-card" onSubmit={(event) => void submit(event)}>
      <span className="eyebrow">Account security</span>
      <h1>Two-factor sign-in is on</h1>
      <p>Your account already has an authenticator app, and it keeps working. There is nothing to set up again.</p>
      <p>
        Changed phones, or lost yours? Replace the authenticator app. Confirm with your password and a code from your
        current app, or one of your recovery codes, then scan a new QR code. After that, the old app and your old
        recovery codes stop working, and you are signed out on your other devices.
      </p>
      <label className="auth-field">
        Current password
        <input
          type="password"
          autoComplete="current-password"
          required
          maxLength={128}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>
      <label className="auth-field">
        Code from your current app, or a recovery code
        <input
          inputMode="text"
          autoComplete="one-time-code"
          required
          minLength={6}
          maxLength={17}
          placeholder="000000 or xxxxxxxx-xxxxxxxx"
          value={code}
          onChange={(event) => setCode(cleanCode(event.target.value, true))}
        />
      </label>
      <button className="primary-action" type="submit" disabled={busy}>
        Replace authenticator app
      </button>
      {message && <p role="status">{message}</p>}
      <p>
        Only need new recovery codes? Keep your app: go back, open My Account › Security and choose Generate new
        recovery codes.
      </p>
      <p className="auth-links">
        <a href={returnTo}>Keep my current app and go back</a>
      </p>
    </form>
  );
}
