import { describe, expect, it } from "vitest";
import { applicationHealth } from "./Operations";
import { canResetMfa } from "./IdentityAccess";

describe("Application health tile (/health/status)", () => {
  it("maps ok, degraded and down to the tile", () => {
    expect(applicationHealth("ready", "ok")).toMatchObject({ value: "OK", tone: "good" });
    expect(applicationHealth("ready", "degraded")).toMatchObject({ value: "Degraded", tone: "warning" });
    // "down" answers 503, which reaches the screen as a failed request.
    expect(applicationHealth("error", undefined)).toMatchObject({ value: "Down", tone: "critical" });
  });
  it("shows nothing while checking, and Unknown for an answer it does not know", () => {
    expect(applicationHealth("loading", undefined).value).toBeNull();
    expect(applicationHealth("ready", "ready").value).toBe("Unknown");
    expect(applicationHealth("forbidden", undefined).value).toBe("Unknown");
  });
});

describe("Reset MFA for a platform user", () => {
  const admin = { id: "u-2", email: "ops@mdarix.example", role: "PLATFORM_ADMIN" };
  it("is offered for another platform administrator only", () => {
    expect(canResetMfa(admin, "u-1")).toBe(true);
    expect(canResetMfa({ ...admin, role: "Administrator" }, "u-1")).toBe(true);
  });
  it("is never offered for oneself, for other roles, or before the signed-in user is known", () => {
    expect(canResetMfa(admin, "u-2")).toBe(false);
    expect(canResetMfa({ ...admin, role: "VIEWER" }, "u-1")).toBe(false);
    expect(canResetMfa(admin, undefined)).toBe(false);
  });
});
