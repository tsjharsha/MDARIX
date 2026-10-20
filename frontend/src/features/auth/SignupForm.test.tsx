import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { STEP_ONE_CODES, SignupForm, TrialConsent, WhatHappensNext } from "./SignupForm";
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

  it("says before the request what happens next, for a company and for a personal address", () => {
    const html = renderToStaticMarkup(<SignupForm />);
    expect(html).toContain("sample data from day one");
    expect(html).toContain("AI is off");
    expect(html).toContain("With a company email, the trial is approved automatically and the activation link arrives");
    expect(html).toContain("daily limit of new trials");
    expect(html).toContain("reviewed by the MDARIX team, usually within one business day");
    expect(renderToStaticMarkup(<WhatHappensNext personal={false} />)).toContain(
      "we email you the activation link within minutes",
    );
    expect(renderToStaticMarkup(<WhatHappensNext personal />)).toContain(
      "the MDARIX team reviews your request, usually within one business day",
    );
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
});
