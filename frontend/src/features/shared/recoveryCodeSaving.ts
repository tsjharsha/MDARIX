// Copy or download a person's recovery codes: the activation page (auth/AuthPage.tsx) and My Account
// (TwoFactorSettings.tsx). In a module of its own so the sign-in pages do not load the account screens (WEB-06).
import { useState } from "react";
import { recoveryCodesText } from "./twoFactor";

export function useRecoveryCodeSaving(codes: readonly string[], account: string | null | undefined, issued: Date) {
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
  return { said, copy, download };
}
