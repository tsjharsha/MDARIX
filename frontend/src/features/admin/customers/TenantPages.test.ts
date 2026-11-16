import { describe, expect, it, vi } from "vitest";
import { domainCheckMessage, platformAiSwitch } from "./TenantPages";

describe("domain verification result", () => {
  it("says the domain is verified only when the server says so", () => {
    expect(domainCheckMessage("example.com", { status: "VERIFIED" })).toBe("Domain example.com is verified.");
  });

  it("explains why a check stayed pending instead of a bare 'Pending'", () => {
    expect(domainCheckMessage("example.com", { status: "PENDING", last_error: "PROOF_NOT_FOUND" })).toBe(
      "Domain example.com is not verified yet: the file was not found at that address.",
    );
    expect(domainCheckMessage("example.com", { status: "PENDING", last_error: "PROOF_HTTP_503" })).toBe(
      "Domain example.com is not verified yet: the site answered HTTP 503.",
    );
    expect(domainCheckMessage("example.com", { status: "PENDING" })).toBe("Domain example.com is not verified yet.");
  });
});

describe("Platform Administrator AI switch", () => {
  it("asks for the password and an authenticator code to turn AI on, and sends them", async () => {
    const put = vi.fn().mockResolvedValue({});
    const turnOn = platformAiSwitch("/x", false, "Acme", "vertex", put);
    expect(turnOn.password).toBe(true);
    expect(turnOn.mfaCode).toBe(true);
    await turnOn.run("Customer signed the AI addendum", "secret", true, " 123456 ");
    expect(put).toHaveBeenCalledWith("/x", "PUT", {
      ai_processing_allowed: true,
      reason: "Customer signed the AI addendum",
      acknowledgement: true,
      password: "secret",
      mfa_code: "123456",
    });
  });

  it("turns AI off with a reason only", async () => {
    const put = vi.fn().mockResolvedValue({});
    const turnOff = platformAiSwitch("/x", true, "Acme", null, put);
    expect(turnOff.password).toBeUndefined();
    await turnOff.run("Pilot paused AI", "", false, "");
    expect(put).toHaveBeenCalledWith("/x", "PUT", { ai_processing_allowed: false, reason: "Pilot paused AI" });
  });
});
