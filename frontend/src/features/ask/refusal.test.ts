import { describe, expect, it } from "vitest";
import { REFUSAL_MESSAGES, refusalOf, scopeLabel } from "./refusal";

describe("refusalOf", () => {
  it("shows the server's sentence for each stable code", () => {
    for (const code of Object.keys(REFUSAL_MESSAGES)) {
      const refusal = refusalOf({ refusal: { status: "REFUSED", code, user_message: `server says ${code}` } });
      expect(refusal).toEqual({ code, message: `server says ${code}` });
    }
  });

  it("falls back to the known sentence when the server sent only the code", () => {
    expect(refusalOf({ refusal: { status: "REFUSED", code: "GENAI_DISABLED_FOR_ORGANIZATION" } })?.message).toBe(
      "AI processing is switched off for your organization; an administrator can enable it under Security › AI processing.",
    );
    expect(refusalOf({ refusal: { status: "REFUSED", code: "GENAI_MONTHLY_BUDGET_REACHED" } })?.message).toBe(
      "Your organization's monthly AI allowance is used up; an administrator can raise it.",
    );
  });

  it("reads a refused advisory and treats an unknown code as unavailable", () => {
    expect(refusalOf({ status: "REFUSED", code: "SOMETHING_NEW" })).toEqual({
      code: "GENAI_UNAVAILABLE",
      message: REFUSAL_MESSAGES.GENAI_UNAVAILABLE,
    });
  });

  it("returns null when the model answered", () => {
    expect(refusalOf({ provider_output: { answer: "Fine" } })).toBeNull();
    expect(refusalOf(undefined)).toBeNull();
  });
});

describe("scopeLabel", () => {
  it("says when an answer covered the whole organization", () => {
    expect(scopeLabel(true)).toBe("Yes");
    expect(scopeLabel(false)).toBe("No (organization-wide)");
  });
});
