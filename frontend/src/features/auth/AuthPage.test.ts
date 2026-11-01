import { describe, expect, it } from "vitest";
import { MFA_TIMED_OUT, lostAuthenticatorHelp, safeReturnTo, signInNotice } from "./AuthPage";

const ORIGIN = "https://app.mdarix.example";

describe("return after sign-in", () => {
  it("returns to a page inside the application, with its query", () => {
    expect(safeReturnTo("/app/investigations?tab=Story", ORIGIN)).toBe("/app/investigations?tab=Story");
    expect(safeReturnTo("/platform-admin/customers", ORIGIN)).toBe("/platform-admin/customers");
    expect(safeReturnTo("/app", ORIGIN)).toBe("/app");
  });

  it("never leaves the site or the application", () => {
    for (const value of [
      null,
      "",
      "https://evil.example/app",
      "//evil.example/app",
      "/\\evil.example",
      "/app\\..\\..\\x",
      "/pricing",
      "/application",
      "javascript:alert(1)",
      "/app\n/x",
      "/app\t/x",
    ])
      expect(safeReturnTo(value, ORIGIN)).toBe("/app");
  });

  it("normalises dot segments before deciding", () => {
    expect(safeReturnTo("/app/../pricing", ORIGIN)).toBe("/app");
  });
});

describe("sign-in notice", () => {
  it("explains an idle sign-out and an ended session", () => {
    expect(signInNotice(new URLSearchParams("reason=idle"))).toMatch(/30 minutes without activity/);
    expect(signInNotice(new URLSearchParams("expired=1"))).toMatch(/without activity/);
    expect(signInNotice(new URLSearchParams("reason=expired&returnTo=%2Fapp"))).toMatch(/session has ended/);
    expect(signInNotice(new URLSearchParams(""))).toBe("");
  });
});

describe("who helps with a lost authenticator, and a setup that timed out (J38)", () => {
  it("names the person who invited you in a trial, MDARIX support for the trial owner, the administrator in a pilot", () => {
    const help = lostAuthenticatorHelp("support@mdarix.example");
    expect(help).toContain("In a free trial, ask the person who invited you");
    expect(help).toContain("If you started the trial, write to support@mdarix.example.");
    expect(help).toContain("In a pilot, ask your administrator.");
  });

  it("says the sign-in timed out and how to start the setup again", () => {
    expect(MFA_TIMED_OUT).toContain("timed out");
    expect(MFA_TIMED_OUT).toContain("sign in again to start the setup again");
  });
});
