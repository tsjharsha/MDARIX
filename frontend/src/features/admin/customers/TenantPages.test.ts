import { describe, expect, it } from "vitest";
import { domainCheckMessage } from "./TenantPages";

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
