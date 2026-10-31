import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ApiError } from "../../app/apiClient";
import { MfaAlreadyOn } from "../auth/MfaAlreadyOn";
import { RecoveryCodesList, TwoFactorSummary } from "./TwoFactorSettings";
import {
  cleanCode,
  reauthMessage,
  recoveryCodesNote,
  recoveryCodesText,
  replaceAuthenticatorHref,
  type MfaStatus,
} from "./twoFactor";

const on: MfaStatus = {
  enrolled: true,
  enrolled_at: "2026-10-01T09:30:00Z",
  recovery_codes_left: 8,
  required_for_role: false,
  replacement_pending: false,
};
const off: MfaStatus = { ...on, enrolled: false, enrolled_at: null, recovery_codes_left: 0 };
const codes = ["0a1b2c3d-4e5f6071", "8192a3b4-c5d6e7f8"];

const summary = (status: MfaStatus, asking = false) =>
  renderToStaticMarkup(
    <TwoFactorSummary
      status={status}
      notOnText="Add a second step to sign-in."
      replaceHref={replaceAuthenticatorHref("/app?section=My Account")}
      onCodes={() => undefined}
      initiallyAsking={asking}
    />,
  );

describe("two-factor sign-in on one's own account", () => {
  it("offers setup, unchanged, when it is not on yet", () => {
    const html = summary(off);
    expect(html).toContain("Add a second step to sign-in.");
    expect(html).toContain('href="/mfa?setup=1"');
    expect(html).toContain("Set up MFA");
    expect(html).not.toContain("Two-factor sign-in is on");
    expect(html).not.toContain("Generate new recovery codes");
  });

  it("says it is on, with new recovery codes and a replacement app, and no way to turn it off", () => {
    const html = summary(on);
    expect(html).toContain("Two-factor sign-in is on");
    expect(html).toContain("8 of 8 recovery codes left.");
    expect(html).toContain("Generate new recovery codes");
    expect(html).toContain("Replace authenticator app");
    expect(html).toContain(`href="/mfa?setup=1&amp;returnTo=${encodeURIComponent("/app?section=My Account")}"`);
    expect(html).not.toContain("Set up MFA");
    expect(html.toLowerCase()).not.toContain("turn off");
    expect(summary({ ...on, required_for_role: true })).toContain("Your role requires two-factor sign-in");
    expect(summary({ ...on, replacement_pending: true })).toContain("Your current app keeps working");
  });

  it("asks for the password and a current authenticator code before new codes", () => {
    const html = summary(on, true);
    expect(html).toContain("Current password");
    expect(html).toContain('type="password"');
    expect(html).toMatch(/autocomplete="current-password"/i);
    expect(html).toContain("Code from your authenticator app");
    expect(html).not.toContain("or a recovery code");
    expect(html).toMatch(/maxlength="6"/i);
    expect(html).toContain("Your current recovery codes stop working as soon as the new ones are made.");
    expect(html).toContain("Generate new codes");
    expect(html).not.toContain("Replace authenticator app</a>");
  });

  it("shows the new codes once, to copy or download", () => {
    const html = renderToStaticMarkup(
      <RecoveryCodesList codes={codes} account="qa@example.invalid" issued={new Date()} onDone={() => undefined} />,
    );
    for (const code of codes) expect(html).toContain(`<code>${code}</code>`);
    expect(html).toContain("Your earlier codes no longer work.");
    expect(html).toContain("Copy all");
    expect(html).toContain("Download");
    expect(html).toContain("I have saved these codes");
  });

  it("writes the codes file with the account, the time and how to use them", () => {
    const text = recoveryCodesText(codes, "qa@example.invalid", new Date("2026-10-16T08:05:00Z"));
    expect(text).toContain("MDARIX recovery codes");
    expect(text).toContain("Account: qa@example.invalid");
    expect(text).toContain("Issued: 2026-10-16 08:05 UTC");
    expect(text).toContain("1. 0a1b2c3d-4e5f6071\n2. 8192a3b4-c5d6e7f8");
    expect(recoveryCodesText(codes, null, new Date())).not.toContain("Account:");
  });

  it("warns when few recovery codes are left", () => {
    expect(recoveryCodesNote(8)).toEqual({ text: "8 of 8 recovery codes left.", low: false });
    expect(recoveryCodesNote(1)).toEqual({ text: "1 of 8 recovery code left. Generate new ones soon.", low: true });
    expect(recoveryCodesNote(0).low).toBe(true);
    expect(recoveryCodesNote(0).text).toContain("no recovery codes left");
  });

  it("keeps only what a code can contain", () => {
    expect(cleanCode("12 34-56a", false)).toBe("123456");
    expect(cleanCode("1234567", false)).toBe("123456");
    expect(cleanCode("0A1B2C3D-4E5F6071 ", true)).toBe("0a1b2c3d-4e5f6071");
    expect(cleanCode("123 456", true)).toBe("123456");
  });

  it("explains a refusal in plain words, never which of the two was wrong", () => {
    const wrong = new ApiError("The password or code is wrong", 403, "REAUTHENTICATION_FAILED");
    expect(reauthMessage(wrong, "x")).toBe("The password or the code is wrong. Check both and try again.");
    expect(reauthMessage(new ApiError("Too many", 429, "MFA_TEMPORARILY_LOCKED"), "x")).toContain("15 minutes");
    expect(reauthMessage(new ApiError("Server said", 500, "OTHER"), "fallback")).toBe("Server said");
    expect(reauthMessage(new Error("boom"), "fallback")).toBe("fallback");
  });

  it("tells someone who already has an app that it is on, and offers to replace it", () => {
    const html = renderToStaticMarkup(
      <MfaAlreadyOn returnTo="/app" busy={false} message="" onReplace={async () => undefined} />,
    );
    expect(html).toContain("Two-factor sign-in is on");
    expect(html).toContain("There is nothing to set up again.");
    expect(html).toContain("Current password");
    expect(html).toContain("Code from your current app, or a recovery code");
    expect(html).toContain("Replace authenticator app");
    // New recovery codes are a step of their own, in My Account › Security.
    expect(html).toContain("open My Account › Security and choose Generate new recovery codes");
    expect(html).toContain('href="/app"');
    expect(html).not.toContain("QR code to add MDARIX");
  });
});
