import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  EMAIL_HINTS,
  ReviewedAddressNote,
  STEP_ONE_CODES,
  SignupDone,
  SignupForm,
  TRIAL_AI_LINE,
  TrialConsent,
  WhatHappensNext,
} from "./SignupForm";
import { GUIDE_STEPS } from "../help/trialGuide";

describe("free trial request form", () => {
  it("says before the request that two-factor sign-in needs an authenticator app", () => {
    const html = renderToStaticMarkup(<SignupForm />);
    expect(html).toContain("Have your phone ready.");
    expect(html).toContain("two-factor sign-in (MFA)");
    expect(html).toContain("authenticator app on your phone");
    // The trial guide's first step says it too, so people reading the guide first are ready.
    expect(GUIDE_STEPS[0].actions.join(" ")).toContain("authenticator app on your phone");
  });

  it("says before the request what happens next, by default the same for a company and a personal address", () => {
    // The pre-rendered page, before site-info answers: the server's default (company-and-personal).
    const html = renderToStaticMarkup(<SignupForm />);
    expect(html).toContain("sample data from day one");
    expect(html).toContain(TRIAL_AI_LINE);
    expect(html).not.toContain("AI is off");
    expect(html).toContain(
      "With a company or personal email, the trial is approved automatically and the activation link arrives",
    );
    expect(html).toContain("daily limit of new trials");
    expect(html).toContain("Requests from disposable addresses, and any beyond that limit, are reviewed by the MDARIX");
    expect(html).not.toContain("personal addresses such as Gmail are reviewed");
    const automatic = "the trial is approved automatically and we email you the activation link within minutes";
    const limit =
      "beyond the day&#x27;s limit of new trials, the MDARIX team reviews it first, usually within one business day";
    const company = renderToStaticMarkup(<WhatHappensNext reviewed={false} approval="company-and-personal" />);
    expect(company).toContain(automatic);
    expect(company).toContain(limit);
    expect(company).not.toContain("with a company email");
    // A personal address is approved at once (no note) and reads like a company one; a disposable one is reviewed.
    expect(renderToStaticMarkup(<ReviewedAddressNote kind="personal" approval="company-and-personal" />)).toBe("");
    expect(renderToStaticMarkup(<ReviewedAddressNote kind="company" approval="company-and-personal" />)).toBe("");
    const disposable = renderToStaticMarkup(<ReviewedAddressNote kind="disposable" approval="company-and-personal" />);
    expect(disposable).toContain("This looks like a disposable address.");
    expect(disposable).toContain("With your company or personal email, the activation link arrives within minutes.");
    expect(renderToStaticMarkup(<WhatHappensNext reviewed approval="company-and-personal" />)).toContain(
      "the MDARIX team reviews your request, usually within one business day",
    );
  });

  it("keeps the wording before 0.10.48 when the server approves company emails only, and says so when it is off", () => {
    expect(EMAIL_HINTS["company-domains"]).toBe(
      "With a company email, the trial is approved automatically and the activation link arrives within minutes (up to " +
        "a daily limit of new trials). Requests from personal addresses such as Gmail are reviewed by the MDARIX team, " +
        "usually within one business day.",
    );
    expect(renderToStaticMarkup(<WhatHappensNext reviewed={false} approval="company-domains" />)).toContain(
      "with a company email, the trial is approved automatically and we email you the activation link within minutes (beyond the day&#x27;s limit of new trials, the MDARIX team reviews it first).",
    );
    const personal = renderToStaticMarkup(<ReviewedAddressNote kind="personal" approval="company-domains" />);
    expect(personal).toContain("This looks like a personal address.");
    expect(personal).toContain("With your company email, the activation link arrives within minutes.");
    const disposable = renderToStaticMarkup(<ReviewedAddressNote kind="disposable" approval="company-domains" />);
    expect(disposable).toContain("With your company email, the activation link arrives within minutes.");
    expect(disposable).not.toContain("or personal");
    expect(renderToStaticMarkup(<WhatHappensNext reviewed approval="company-domains" />)).toContain(
      "the MDARIX team reviews your request, usually within one business day",
    );
    // Off: every request is reviewed, said once under the field; no note per address.
    expect(EMAIL_HINTS.off).toContain("The MDARIX team reviews every trial request");
    for (const kind of ["company", "personal", "disposable"] as const)
      expect(renderToStaticMarkup(<ReviewedAddressNote kind={kind} approval="off" />)).toBe("");
  });

  it("opens the legal texts in a new tab, so reading them keeps what was typed", () => {
    const html = renderToStaticMarkup(<TrialConsent />);
    for (const path of ["/terms", "/trial-agreement", "/privacy"])
      expect(html).toContain(`href="${path}" target="_blank" rel="noopener"`);
    expect(html.match(/<a /g)).toHaveLength(3);
    // The request records which version of each text was accepted (backend/app/auth_router.py signup).
    expect(html).toContain("records which version of each text you accepted, and when");
  });

  it("takes the person back to the first step when the server refuses their name, company or email", () => {
    // Release 0.10.36 (FUN-12): the server refuses a blank name or company and an email such as x@localhost; the
    // form shows the server's message on the step that holds the field.
    for (const code of ["NAME_REQUIRED", "ORGANIZATION_REQUIRED", "VALID_EMAIL_REQUIRED", "NAME_HAS_LINK"])
      expect(STEP_ONE_CODES.has(code)).toBe(true);
  });

  it("says precisely how the password is kept, never that MDARIX cannot see it", () => {
    const html = renderToStaticMarkup(<SignupForm />);
    expect(html).toContain("stores only a salted hash of it, so no one at MDARIX can read it");
    expect(html).not.toContain("never sees it");
  });

  it("ends on sign-in as the main step, with the guide as a secondary link", () => {
    const html = renderToStaticMarkup(<SignupDone approving email="a@b.example" />);
    expect(html).toMatch(
      /class="primary-action" href="\/signin\?email=a%40b\.example">Sign in when your email arrives/,
    );
    expect(html).toMatch(/class="su-secondary"[^>]*>Read the free trial user guide/);
  });
});
