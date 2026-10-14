import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { exitRequestText, type TrialExitRequest } from "./sections/EndTrial";
import { exitState, exitWhy } from "../admin/customers/TrialExitRequests";
import { PasswordInput } from "../auth/AuthPage";

const request = (overrides: Partial<TrialExitRequest> = {}): TrialExitRequest => ({
  id: "r1",
  status: "PENDING",
  reason_code: "MISSING",
  reason_label: "Something we need is missing",
  reason: "Our QMS first",
  delete_data: true,
  data_deleted: false,
  created_at: "2026-10-13T09:00:00Z",
  decided_at: null,
  decision_note: null,
  ...overrides,
});

describe("ending a free trial early", () => {
  it("tells the owner where the request stands", () => {
    expect(exitRequestText(null)).toBeNull();
    expect(exitRequestText(request())).toContain("You asked to end the trial early on");
    expect(exitRequestText(request())).toContain("until then the trial continues");
    expect(exitRequestText(request({ status: "DECLINED", decision_note: "Could we talk first?" }))).toBe(
      "The MDARIX team has not ended the trial: Could we talk first?",
    );
    // A withdrawn request says nothing: the owner may simply ask again.
    expect(exitRequestText(request({ status: "WITHDRAWN" }))).toBeNull();
  });

  it("shows Platform Admin each request's state and why the organization is leaving", () => {
    expect(exitState({ status: "PENDING", data_deleted: false })).toEqual({
      label: "Waiting for you",
      tone: "warning",
    });
    expect(exitState({ status: "APPROVED", data_deleted: true }).label).toBe("Ended, data deleted");
    expect(exitState({ status: "APPROVED", data_deleted: false }).label).toBe("Ended, data kept 30 days");
    expect(exitState({ status: "DECLINED", data_deleted: false }).label).toBe("Declined");
    expect(exitWhy({ reason_label: "Something we need is missing", reason: "Our QMS first" })).toBe(
      "Something we need is missing: Our QMS first",
    );
    expect(exitWhy({ reason_label: null, reason: null })).toBe("No reason given");
  });
});

describe("sign-in password", () => {
  it("is hidden by default, with an eye button to show it", () => {
    const html = renderToStaticMarkup(
      <PasswordInput value="secret" onChange={() => undefined} minLength={1} autoComplete="current-password" />,
    );
    expect(html).toContain('type="password"');
    expect(html).toContain('aria-label="Show password"');
    expect(html).toContain('aria-pressed="false"');
    expect(html).toContain('autoComplete="current-password"');
  });
});
