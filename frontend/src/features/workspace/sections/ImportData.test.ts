import { describe, expect, it } from "vitest";
import { ApiError } from "../../../app/apiClient";
import { IMPORT_TIMEOUT_MS, importFailureText, importUrl } from "./ImportData";

describe("importUrl", () => {
  const base = "/api/v1/data/import";

  it("checks or imports one template, with ISO dates and the default choices adding nothing", () => {
    expect(importUrl(base, "complaints", "check", "ISO")).toBe("/api/v1/data/import/complaints/check");
    expect(importUrl(base, "complaints", "import", "ISO")).toBe("/api/v1/data/import/complaints");
  });

  it("sends the date order and each choice the person made", () => {
    expect(importUrl(base, "lots", "check", "DMY")).toBe("/api/v1/data/import/lots/check?date_format=DMY");
    expect(importUrl(base, "complaints", "import", "ISO", { skipProblems: true, maskPersonal: false })).toBe(
      "/api/v1/data/import/complaints?on_problems=skip",
    );
    expect(importUrl(base, "complaints", "check", "MDY", { skipProblems: true, maskPersonal: true })).toBe(
      "/api/v1/data/import/complaints/check?date_format=MDY&on_problems=skip&personal_data=mask",
    );
  });
});

describe("a slow import", () => {
  it("waits minutes for a full allowance, and a timeout never claims nothing was saved", () => {
    expect(IMPORT_TIMEOUT_MS).toBeGreaterThanOrEqual(5 * 60_000);
    const timeout = importFailureText(new ApiError("MDARIX took too long to answer", 0, "TIMEOUT"));
    expect(timeout).toContain("The import may still finish");
    expect(timeout).not.toContain("nothing was saved");
    expect(importFailureText(new ApiError("Fix the listed problems first", 422, "IMPORT_CHECK_FAILED"))).toBe(
      "Fix the listed problems first",
    );
  });
});
