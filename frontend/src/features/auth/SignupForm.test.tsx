import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SignupForm, TrialConsent, WhatHappensNext } from "./SignupForm";
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
    expect(html).toContain("With a company email, the activation link arrives within minutes.");
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
  });
});
