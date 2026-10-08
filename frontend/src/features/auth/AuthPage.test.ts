import { describe, expect, it } from "vitest";
import { safeReturnTo, signInNotice } from "./AuthPage";

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
