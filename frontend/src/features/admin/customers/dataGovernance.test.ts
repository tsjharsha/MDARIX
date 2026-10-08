import { describe, expect, it } from "vitest";
import { ApiError } from "../../../app/apiClient";
import {
  activationLinkError,
  exportAfterSuspension,
  handBackReady,
  legalHoldError,
  legalHoldRequest,
  purgeOutcome,
  purgeRequest,
  type DataExport,
} from "./dataGovernance";

const exportRow = (id: string, status: string, completed: string | null): DataExport => ({
  id,
  status,
  reason: "hand back",
  summary: null,
  created_at: "2026-09-01T00:00:00Z",
  completed_at: completed,
  expires_at: null,
});

describe("delete all data: export or waiver", () => {
  const rows = [
    exportRow("old", "READY", "2026-09-01T10:00:00Z"),
    exportRow("new", "READY", "2026-09-20T10:00:00Z"),
    exportRow("newer-failed", "FAILED", "2026-09-25T10:00:00Z"),
  ];

  it("counts only a READY export completed after the suspension, the newest one", () => {
    expect(exportAfterSuspension(rows, "2026-09-10T00:00:00Z")?.id).toBe("new");
    expect(exportAfterSuspension(rows, "2026-09-21T00:00:00Z")).toBeNull();
    expect(exportAfterSuspension(rows, null)?.id).toBe("new");
  });

  it("needs either that export or a waiver reason of at least 10 characters", () => {
    expect(handBackReady({ kind: "export" }, null)).toBe(false);
    expect(handBackReady({ kind: "export" }, rows[1])).toBe(true);
    expect(handBackReady({ kind: "waiver", reason: "short" }, null)).toBe(false);
    expect(handBackReady({ kind: "waiver", reason: "Customer declined in writing" }, null)).toBe(true);
  });

  it("sends the waiver reason only when the export is waived", () => {
    expect(purgeRequest(" End of pilot ", "pw", " ACME ", { kind: "export" })).toEqual({
      reason: "End of pilot",
      password: "pw",
      confirm_tenant_key: "ACME",
    });
    expect(
      purgeRequest("End of pilot", "pw", "ACME", { kind: "waiver", reason: " Declined in writing " }),
    ).toMatchObject({ export_waiver_reason: "Declined in writing" });
    expect(purgeRequest("End of pilot", "pw", "ACME", null)).not.toHaveProperty("export_waiver_reason");
  });

  it("sends the authenticator code only when one was typed", () => {
    expect(purgeRequest("End of pilot", "pw", "ACME", null, "123456")).toMatchObject({ mfa_code: "123456" });
    expect(purgeRequest("End of pilot", "pw", "ACME", null)).not.toHaveProperty("mfa_code");
  });

  it("is honest when files are still being removed", () => {
    const partial = purgeOutcome("Acme", { status: "PURGING", incomplete: { files: "TimeoutError" } });
    expect(partial.tone).toBe("warning");
    expect(partial.text).toContain("Acme's records are deleted; files are still being removed (stored files)");
    expect(partial.text).toContain("This finishes automatically.");
    expect(purgeOutcome("Acme", { status: "ARCHIVED" })).toEqual({
      tone: "good",
      text: "Acme's data has been deleted and the tenant is archived.",
    });
  });
});

describe("legal hold and activation links", () => {
  it("sends the hold with its reason", () => {
    expect(legalHoldRequest(true, "  Litigation hold, ref 2026-17 ")).toEqual({
      hold: true,
      reason: "Litigation hold, ref 2026-17",
    });
  });

  it("explains MFA refusals instead of a bare 403", () => {
    expect(legalHoldError(new ApiError("x", 403, "MFA_REQUIRED", "req-1"))).toBe(
      "Complete multi-factor sign-in on your own account first, then try again. (reference req-1)",
    );
    expect(legalHoldError(new ApiError("x", 403, "MFA_ENROLLMENT_REQUIRED"))).toMatch(/authenticator/);
    expect(activationLinkError(new ApiError("x", 403, "MFA_REQUIRED"))).toMatch(/before issuing activation links/);
    expect(activationLinkError(new ApiError("x", 409, "ACCOUNT_ALREADY_ACTIVE"))).toMatch(/password reset/);
    expect(activationLinkError(new ApiError("Server said no", 500, "OTHER"))).toBe("Server said no");
  });
});
